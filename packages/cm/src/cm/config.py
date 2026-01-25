"""Configuration for the cm company name matching system."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ScoringWeights:
    token_overlap: float = 0.35
    fuzzy_similarity: float = 0.30
    acronym_signal: float = 0.20
    semantic_similarity: float = 0.15


@dataclass
class Penalties:
    numeric_mismatch: float = 0.30
    numeric_one_side_only: float = 0.10
    short_name_guardrail: float = 0.25


@dataclass
class Thresholds:
    t_high: float = 0.92
    t_low: float = 0.75
    margin: float = 0.06


@dataclass
class CandidateConfig:
    max_candidates_total: int = 500
    max_candidates_lexical: int = 300
    max_candidates_embedding: int = 200
    use_k_first: bool = True


@dataclass
class LLMConfig:
    enabled: bool = False
    top_k: int = 3
    global_call_cap: int = 50
    per_item_call_cap: int = 2
    min_confidence: float = 0.75
    forbid_both_single_token: bool = True


@dataclass
class EmbeddingConfig:
    enabled: bool = False
    ann_neighbors: int = 100
    cache_dir: str = ".cm_cache/embeddings"
    batch_size: int = 250  # Vertex AI limit: 250 texts per request


@dataclass
class AcronymConfig:
    min_length: int = 3


@dataclass
class NormalizationConfig:
    strip_prefix_designators: bool = False
    strip_categories: list[str] = None  # --no <category> (e.g., ["location", "institution"])

    def __post_init__(self) -> None:
        if self.strip_categories is None:
            self.strip_categories = []


@dataclass
class MatchConfig:
    scoring: ScoringWeights = field(default_factory=ScoringWeights)
    penalties: Penalties = field(default_factory=Penalties)
    thresholds: Thresholds = field(default_factory=Thresholds)
    candidates: CandidateConfig = field(default_factory=CandidateConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    embedding: EmbeddingConfig = field(default_factory=EmbeddingConfig)
    acronym: AcronymConfig = field(default_factory=AcronymConfig)
    normalization: NormalizationConfig = field(default_factory=NormalizationConfig)
