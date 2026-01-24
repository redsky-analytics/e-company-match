"""Lexical blocking index and candidate retrieval."""

from __future__ import annotations

from collections import defaultdict

from bizmatch.config import CandidateConfig
from bizmatch.types import Candidate, NormalizedName


class BlockingIndex:
    """Inverted index for B names, mapping blocking keys to B IDs."""

    def __init__(self, config: CandidateConfig | None = None) -> None:
        self.config = config or CandidateConfig()
        self._index: dict[str, set[int]] = defaultdict(set)
        self._names: dict[int, NormalizedName] = {}

    def build(self, names: list[NormalizedName]) -> None:
        """Build the inverted index from a list of B names."""
        for b_id, name in enumerate(names):
            self._names[b_id] = name
            for key_type, key_value in name.keys.items():
                if key_type == "k_first" and not self.config.use_k_first:
                    continue
                composite_key = f"{key_type}::{key_value}"
                self._index[composite_key].add(b_id)

    def get_name(self, b_id: int) -> NormalizedName:
        """Get the NormalizedName for a B ID."""
        return self._names[b_id]

    def retrieve_candidates(
        self,
        a_name: NormalizedName,
        embedding_candidates: list[int] | None = None,
    ) -> list[Candidate]:
        """Retrieve candidates for an A name using blocking keys.

        Returns deduplicated candidates with source tracking, capped at limits.
        """
        candidates: dict[int, set[str]] = defaultdict(set)

        # Lexical blocking
        for key_type, key_value in a_name.keys.items():
            if key_type == "k_first" and not self.config.use_k_first:
                continue
            composite_key = f"{key_type}::{key_value}"
            for b_id in self._index.get(composite_key, set()):
                candidates[b_id].add(key_type)

        # Apply lexical cap
        lexical_ids = list(candidates.keys())
        if len(lexical_ids) > self.config.max_candidates_lexical:
            # Prioritize candidates with more sources
            lexical_ids.sort(
                key=lambda bid: len(candidates[bid]), reverse=True
            )
            lexical_ids = lexical_ids[: self.config.max_candidates_lexical]
            candidates = {
                bid: candidates[bid]
                for bid in lexical_ids
            }

        # Union with embedding candidates
        if embedding_candidates:
            for b_id in embedding_candidates[: self.config.max_candidates_embedding]:
                candidates[b_id].add("embedding")

        # Apply total cap
        if len(candidates) > self.config.max_candidates_total:
            sorted_ids = sorted(
                candidates.keys(),
                key=lambda bid: len(candidates[bid]),
                reverse=True,
            )
            sorted_ids = sorted_ids[: self.config.max_candidates_total]
            candidates = {bid: candidates[bid] for bid in sorted_ids}

        return [
            Candidate(b_id=bid, sources=sources)
            for bid, sources in candidates.items()
        ]
