"""Tests for the embeddings module."""

import json
from pathlib import Path

import numpy as np
import pytest

from cm.config import EmbeddingConfig
from cm.embeddings import EmbeddingIndex, EmbeddingProvider


class MockEmbeddingProvider:
    """Mock embedding provider for testing."""

    def __init__(self, embedding_dim: int = 4):
        self.embedding_dim = embedding_dim
        self.calls: list[list[str]] = []

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(texts)
        # Generate deterministic embeddings based on text hash
        embeddings = []
        for text in texts:
            # Create a simple deterministic embedding based on text
            np.random.seed(hash(text) % (2**32))
            embedding = np.random.randn(self.embedding_dim).tolist()
            embeddings.append(embedding)
        return embeddings


class TestEmbeddingIndexBuild:
    """Tests for building the embedding index."""

    def test_build_without_provider(self, tmp_path: Path):
        config = EmbeddingConfig(enabled=True, cache_dir=str(tmp_path))
        index = EmbeddingIndex(config, provider=None)

        # Should not raise, just skip building
        index.build(["Apple Inc", "Microsoft Corp"])

        assert index._embeddings is None

    def test_build_with_provider(self, tmp_path: Path):
        config = EmbeddingConfig(enabled=True, cache_dir=str(tmp_path))
        provider = MockEmbeddingProvider()
        index = EmbeddingIndex(config, provider=provider)

        index.build(["Apple Inc", "Microsoft Corp", "Google LLC"])

        assert index._embeddings is not None
        assert index._embeddings.shape == (3, 4)

    def test_build_normalizes_embeddings(self, tmp_path: Path):
        config = EmbeddingConfig(enabled=True, cache_dir=str(tmp_path))
        provider = MockEmbeddingProvider()
        index = EmbeddingIndex(config, provider=provider)

        index.build(["Apple Inc", "Microsoft Corp"])

        # Check embeddings are normalized (unit vectors)
        norms = np.linalg.norm(index._embeddings, axis=1)
        np.testing.assert_array_almost_equal(norms, [1.0, 1.0])


class TestEmbeddingIndexCaching:
    """Tests for embedding cache behavior."""

    def test_cache_saves_embeddings(self, tmp_path: Path):
        config = EmbeddingConfig(enabled=True, cache_dir=str(tmp_path))
        provider = MockEmbeddingProvider()
        index = EmbeddingIndex(config, provider=provider)

        index.build(["Apple Inc", "Microsoft Corp"])

        cache_file = tmp_path / "embedding_cache.json"
        assert cache_file.exists()
        cache = json.loads(cache_file.read_text())
        assert "Apple Inc" in cache
        assert "Microsoft Corp" in cache

    def test_cache_loads_on_build(self, tmp_path: Path):
        # Pre-populate cache
        cache_file = tmp_path / "embedding_cache.json"
        cache_file.write_text(json.dumps({"Apple Inc": [1.0, 0.0, 0.0, 0.0]}))

        config = EmbeddingConfig(enabled=True, cache_dir=str(tmp_path))
        provider = MockEmbeddingProvider()
        index = EmbeddingIndex(config, provider=provider)

        index.build(["Apple Inc", "Microsoft Corp"])

        # Only Microsoft Corp should be computed (Apple Inc from cache)
        assert len(provider.calls) == 1
        assert "Microsoft Corp" in provider.calls[0]
        assert "Apple Inc" not in provider.calls[0]

    def test_cache_hits_tracked(self, tmp_path: Path):
        # Pre-populate cache
        cache_file = tmp_path / "embedding_cache.json"
        cache_file.write_text(json.dumps({"Apple Inc": [1.0, 0.0, 0.0, 0.0]}))

        config = EmbeddingConfig(enabled=True, cache_dir=str(tmp_path))
        provider = MockEmbeddingProvider()
        index = EmbeddingIndex(config, provider=provider)

        index.build(["Apple Inc", "Microsoft Corp"])

        assert index.cache_hits == 1


class TestEmbeddingIndexQuery:
    """Tests for querying the embedding index."""

    def test_query_without_provider(self, tmp_path: Path):
        config = EmbeddingConfig(enabled=True, cache_dir=str(tmp_path))
        index = EmbeddingIndex(config, provider=None)

        indices, similarities = index.query("Apple Inc")

        assert indices == []
        assert similarities == []

    def test_query_without_index(self, tmp_path: Path):
        config = EmbeddingConfig(enabled=True, cache_dir=str(tmp_path))
        provider = MockEmbeddingProvider()
        index = EmbeddingIndex(config, provider=provider)
        # Don't build index

        indices, similarities = index.query("Apple Inc")

        assert indices == []
        assert similarities == []

    def test_query_returns_top_k(self, tmp_path: Path):
        config = EmbeddingConfig(enabled=True, cache_dir=str(tmp_path), ann_neighbors=2)
        provider = MockEmbeddingProvider()
        index = EmbeddingIndex(config, provider=provider)
        index.build(["Apple Inc", "Microsoft Corp", "Google LLC", "Meta Inc"])
        # Precompute the query embedding
        index.precompute(["Apple Inc"])

        indices, similarities = index.query("Apple Inc")

        assert len(indices) == 2
        assert len(similarities) == 2
        # Should be sorted by similarity (descending)
        assert similarities[0] >= similarities[1]

    def test_query_from_cache(self, tmp_path: Path):
        config = EmbeddingConfig(enabled=True, cache_dir=str(tmp_path), ann_neighbors=2)
        provider = MockEmbeddingProvider()
        index = EmbeddingIndex(config, provider=provider)
        index.build(["Apple Inc", "Microsoft Corp"])
        index.precompute(["Test Query"])

        # Query should use cached embedding
        initial_calls = len(provider.calls)
        index.query("Test Query")

        # No additional API calls should be made
        assert len(provider.calls) == initial_calls


class TestEmbeddingIndexPrecompute:
    """Tests for precomputing embeddings."""

    def test_precompute_without_provider(self, tmp_path: Path):
        config = EmbeddingConfig(enabled=True, cache_dir=str(tmp_path))
        index = EmbeddingIndex(config, provider=None)

        # Should not raise
        index.precompute(["Apple Inc", "Microsoft Corp"])

    def test_precompute_caches_embeddings(self, tmp_path: Path):
        config = EmbeddingConfig(enabled=True, cache_dir=str(tmp_path))
        provider = MockEmbeddingProvider()
        index = EmbeddingIndex(config, provider=provider)

        index.precompute(["Apple Inc", "Microsoft Corp"])

        assert "Apple Inc" in index._cache
        assert "Microsoft Corp" in index._cache

    def test_precompute_uses_cache(self, tmp_path: Path):
        # Pre-populate cache
        cache_file = tmp_path / "embedding_cache.json"
        cache_file.write_text(json.dumps({"Apple Inc": [1.0, 0.0, 0.0, 0.0]}))

        config = EmbeddingConfig(enabled=True, cache_dir=str(tmp_path))
        provider = MockEmbeddingProvider()
        index = EmbeddingIndex(config, provider=provider)
        index._load_cache()

        index.precompute(["Apple Inc", "Microsoft Corp"])

        # Only Microsoft Corp should be computed
        assert len(provider.calls) == 1
        assert "Apple Inc" not in provider.calls[0]


class TestEmbeddingIndexCosineSimilarity:
    """Tests for cosine similarity computation."""

    def test_cosine_similarity_without_provider(self, tmp_path: Path):
        config = EmbeddingConfig(enabled=True, cache_dir=str(tmp_path))
        index = EmbeddingIndex(config, provider=None)

        result = index.cosine_similarity("Apple Inc", "Apple Incorporated")

        assert result is None

    def test_cosine_similarity_identical(self, tmp_path: Path):
        config = EmbeddingConfig(enabled=True, cache_dir=str(tmp_path))
        provider = MockEmbeddingProvider()
        index = EmbeddingIndex(config, provider=provider)

        result = index.cosine_similarity("Apple Inc", "Apple Inc")

        assert result is not None
        assert result == pytest.approx(1.0, abs=0.01)

    def test_cosine_similarity_different(self, tmp_path: Path):
        config = EmbeddingConfig(enabled=True, cache_dir=str(tmp_path))
        provider = MockEmbeddingProvider()
        index = EmbeddingIndex(config, provider=provider)

        result = index.cosine_similarity("Apple Inc", "Microsoft Corp")

        assert result is not None
        # Different texts should have different embeddings
        assert -1.0 <= result <= 1.0

    def test_cosine_similarity_uses_cache(self, tmp_path: Path):
        config = EmbeddingConfig(enabled=True, cache_dir=str(tmp_path))
        provider = MockEmbeddingProvider()
        index = EmbeddingIndex(config, provider=provider)

        # First call computes embeddings
        index.cosine_similarity("Apple Inc", "Microsoft Corp")
        initial_calls = len(provider.calls)

        # Second call should use cache
        index.cosine_similarity("Apple Inc", "Microsoft Corp")

        assert len(provider.calls) == initial_calls


class TestEmbeddingIndexBatching:
    """Tests for batch embedding computation."""

    def test_batch_size_respected(self, tmp_path: Path):
        config = EmbeddingConfig(enabled=True, cache_dir=str(tmp_path), batch_size=2)
        provider = MockEmbeddingProvider()
        index = EmbeddingIndex(config, provider=provider)

        index.build(["A", "B", "C", "D", "E"])

        # With batch_size=2 and 5 items, should make 3 API calls
        assert len(provider.calls) == 3
        assert len(provider.calls[0]) == 2
        assert len(provider.calls[1]) == 2
        assert len(provider.calls[2]) == 1

    def test_api_calls_tracked(self, tmp_path: Path):
        config = EmbeddingConfig(enabled=True, cache_dir=str(tmp_path), batch_size=2)
        provider = MockEmbeddingProvider()
        index = EmbeddingIndex(config, provider=provider)

        index.build(["A", "B", "C"])

        assert index.api_calls == 2  # 3 items with batch_size=2


class TestEmbeddingConfig:
    """Tests for embedding configuration."""

    def test_default_config(self):
        config = EmbeddingConfig()

        assert config.enabled is False
        assert config.ann_neighbors == 100
        assert config.batch_size == 250

    def test_custom_config(self):
        config = EmbeddingConfig(
            enabled=True,
            ann_neighbors=50,
            cache_dir="/custom/path",
            batch_size=100,
        )

        assert config.enabled is True
        assert config.ann_neighbors == 50
        assert config.cache_dir == "/custom/path"
        assert config.batch_size == 100
