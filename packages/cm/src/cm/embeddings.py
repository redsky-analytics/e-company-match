"""Gemini embedding provider with caching and ANN index."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol

import numpy as np
import structlog

from cm.config import EmbeddingConfig

log = structlog.get_logger()


class EmbeddingProvider(Protocol):
    """Protocol for embedding providers (e.g. Gemini)."""

    def embed_batch(self, texts: list[str]) -> list[list[float]]: ...


class EmbeddingIndex:
    """Embedding-based ANN index for candidate generation."""

    def __init__(
        self, config: EmbeddingConfig, provider: EmbeddingProvider | None = None
    ) -> None:
        self.config = config
        self.provider = provider
        self._embeddings: np.ndarray | None = None
        self._cache: dict[str, list[float]] = {}
        self._cache_dir = Path(config.cache_dir)
        # Stats tracking
        self.api_calls: int = 0
        self.cache_hits: int = 0

    def build(self, core_strings: list[str]) -> None:
        """Compute and store embeddings for all B core_strings."""
        if self.provider is None:
            log.warning("no_embedding_provider", reason="skipping build")
            return

        self._load_cache()
        log.info("embedding_cache_loaded", cached_count=len(self._cache))

        all_embeddings = self._batch_embed(core_strings, label="B")

        self._embeddings = np.array(all_embeddings, dtype=np.float32)
        # Normalize for cosine similarity
        norms = np.linalg.norm(self._embeddings, axis=1, keepdims=True)
        norms = np.where(norms == 0, 1, norms)
        self._embeddings = self._embeddings / norms
        log.info("embeddings_normalized", shape=self._embeddings.shape)

    def precompute(self, core_strings: list[str]) -> None:
        """Pre-compute and cache embeddings for a list of strings (e.g., A names).

        Call this before matching to avoid per-query API calls.
        """
        if self.provider is None:
            return
        self._batch_embed(core_strings, label="A")

    def _batch_embed(self, core_strings: list[str], label: str = "") -> list[list[float]]:
        """Batch embed strings, using cache where possible."""
        all_embeddings: list[list[float]] = []
        to_compute: list[tuple[int, str]] = []

        for i, cs in enumerate(core_strings):
            if cs in self._cache:
                all_embeddings.append(self._cache[cs])
                self.cache_hits += 1
            else:
                all_embeddings.append([])  # placeholder
                to_compute.append((i, cs))

        log.info(
            "embedding_batch_plan",
            label=label,
            total=len(core_strings),
            from_cache=len(core_strings) - len(to_compute),
            to_compute=len(to_compute),
        )

        # Batch compute missing embeddings
        if to_compute:
            total_batches = (len(to_compute) + self.config.batch_size - 1) // self.config.batch_size
            for batch_num, batch_start in enumerate(range(0, len(to_compute), self.config.batch_size)):
                batch = to_compute[batch_start : batch_start + self.config.batch_size]
                texts = [cs for _, cs in batch]
                log.info(
                    "embedding_api_call",
                    label=label,
                    batch=batch_num + 1,
                    total_batches=total_batches,
                    batch_size=len(batch),
                )
                embeddings = self.provider.embed_batch(texts)
                self.api_calls += 1
                for (idx, cs), emb in zip(batch, embeddings):
                    all_embeddings[idx] = emb
                    self._cache[cs] = emb

            self._save_cache()
            log.info("embedding_cache_saved", total_cached=len(self._cache))

        return all_embeddings

    def query(self, core_string: str) -> tuple[list[int], list[float]]:
        """Find ANN neighbors for a query core_string.

        Returns (b_ids, cosine_similarities).
        """
        if self._embeddings is None or self.provider is None:
            return [], []

        # Get embedding for query (should be cached from precompute)
        if core_string in self._cache:
            query_emb = np.array(self._cache[core_string], dtype=np.float32)
        else:
            log.warning("embedding_cache_miss_query", core_string=core_string[:50])
            embeddings = self.provider.embed_batch([core_string])
            query_emb = np.array(embeddings[0], dtype=np.float32)
            self._cache[core_string] = embeddings[0]

        # Normalize
        norm = np.linalg.norm(query_emb)
        if norm > 0:
            query_emb = query_emb / norm

        # Compute cosine similarities (dot product of normalized vectors)
        similarities = self._embeddings @ query_emb

        # Get top-k neighbors
        k = min(self.config.ann_neighbors, len(similarities))
        top_indices = np.argpartition(similarities, -k)[-k:]
        top_indices = top_indices[np.argsort(similarities[top_indices])[::-1]]

        return top_indices.tolist(), similarities[top_indices].tolist()

    def cosine_similarity(self, core_string_a: str, core_string_b: str) -> float | None:
        """Compute cosine similarity between two core strings."""
        if self.provider is None:
            return None

        emb_a = self._get_or_compute(core_string_a)
        emb_b = self._get_or_compute(core_string_b)

        if emb_a is None or emb_b is None:
            return None

        a = np.array(emb_a, dtype=np.float32)
        b = np.array(emb_b, dtype=np.float32)

        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        if norm_a == 0 or norm_b == 0:
            return 0.0

        return float(np.dot(a, b) / (norm_a * norm_b))

    def _get_or_compute(self, core_string: str) -> list[float] | None:
        if core_string in self._cache:
            return self._cache[core_string]
        if self.provider is None:
            return None
        log.warning("embedding_cache_miss_compute", core_string=core_string[:50])
        embeddings = self.provider.embed_batch([core_string])
        self._cache[core_string] = embeddings[0]
        return embeddings[0]

    def _load_cache(self) -> None:
        cache_file = self._cache_dir / "embedding_cache.json"
        if cache_file.exists():
            self._cache = json.loads(cache_file.read_text())

    def _save_cache(self) -> None:
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        cache_file = self._cache_dir / "embedding_cache.json"
        cache_file.write_text(json.dumps(self._cache))
