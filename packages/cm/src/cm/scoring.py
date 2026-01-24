"""Deterministic scoring of candidate pairs."""

from __future__ import annotations

from rapidfuzz import fuzz

from cm.acronyms import acronym_relation
from cm.config import MatchConfig
from cm.designators import is_designator
from cm.types import NormalizedName, ScoredCandidate


def _effective_core(name: NormalizedName) -> tuple[list[str], str]:
    """Get effective core tokens, stripping designators for scoring comparison.

    This handles the case where the safety rule kept designators in core_tokens.
    """
    effective = [t for t in name.core_tokens if not is_designator(t)]
    if len(effective) == 0:
        # All tokens are designators, use original
        return name.core_tokens, name.core_string
    return effective, " ".join(effective)


def score_pair(
    a: NormalizedName,
    b: NormalizedName,
    config: MatchConfig,
    embedding_cosine: float | None = None,
) -> ScoredCandidate:
    """Score a candidate pair (A, B) using deterministic features."""
    features: dict[str, float | bool | str] = {}
    reasons: list[str] = []
    weights = config.scoring
    penalties = config.penalties

    # Use effective core (designators stripped for comparison)
    a_eff_tokens, a_eff_string = _effective_core(a)
    b_eff_tokens, b_eff_string = _effective_core(b)

    # 1. Token overlap coefficient: |A∩B| / min(|A|, |B|)
    a_set = set(a_eff_tokens)
    b_set = set(b_eff_tokens)
    min_len = min(len(a_set), len(b_set))
    if min_len > 0:
        overlap = len(a_set & b_set) / min_len
    else:
        overlap = 0.0
    features["token_overlap"] = overlap

    if overlap >= 0.8:
        reasons.append("core_overlap_high")

    # 2. Fuzzy similarity (WRatio)
    fuzzy_score = fuzz.WRatio(a_eff_string, b_eff_string) / 100.0
    features["fuzzy_similarity"] = fuzzy_score

    if fuzzy_score >= 0.85:
        reasons.append("fuzzy_high")

    # 3. Acronym relation
    acr_rel = acronym_relation(
        a.acronym, a.core_tokens, b.acronym, b.core_tokens
    )
    features["acronym_relation"] = acr_rel

    if acr_rel == "exact":
        acronym_score = 1.0
        reasons.append("acronym_match_strong")
    elif acr_rel == "initialism":
        acronym_score = 0.9
        reasons.append("acronym_match_strong")
    elif acr_rel == "collision":
        acronym_score = 0.3
        reasons.append("acronym_match_weak")
    else:
        acronym_score = 0.0

    features["acronym_score"] = acronym_score

    # 4. Numeric consistency
    penalty = 0.0
    a_nums = set(a.numeric_tokens)
    b_nums = set(b.numeric_tokens)

    if a_nums and b_nums:
        if a_nums != b_nums:
            penalty += penalties.numeric_mismatch
            reasons.append("numeric_mismatch")
    elif a_nums or b_nums:
        penalty += penalties.numeric_one_side_only
        reasons.append("numeric_one_side_only")

    features["numeric_penalty"] = penalty

    # 5. Short-name guardrail (use original core_tokens length, not effective)
    min_core_len = min(len(a.core_tokens), len(b.core_tokens))
    short_penalty = 0.0
    if min_core_len <= 1:
        short_penalty = penalties.short_name_guardrail
        reasons.append("short_name_guardrail")
    features["short_name_penalty"] = short_penalty

    # 6. Semantic similarity (optional)
    semantic_score = 0.0
    if embedding_cosine is not None and min_core_len > 1:
        semantic_score = max(0.0, embedding_cosine)
        if semantic_score >= 0.85:
            reasons.append("semantic_boost")
    features["semantic_similarity"] = semantic_score

    # Weighted combination with normalization
    # Normalize by active weight sum so score stays in [0, 1] range
    # regardless of which features are applicable
    active_weight_sum = weights.token_overlap + weights.fuzzy_similarity
    weighted_sum = (
        weights.token_overlap * overlap
        + weights.fuzzy_similarity * fuzzy_score
    )

    if acronym_score > 0:
        active_weight_sum += weights.acronym_signal
        weighted_sum += weights.acronym_signal * acronym_score

    has_semantic = embedding_cosine is not None and min_core_len > 1
    if has_semantic and semantic_score > 0:
        active_weight_sum += weights.semantic_similarity
        weighted_sum += weights.semantic_similarity * semantic_score

    raw_score = weighted_sum / active_weight_sum if active_weight_sum > 0 else 0.0

    # Apply penalties
    score = max(0.0, min(1.0, raw_score - penalty - short_penalty))

    # Constraint: semantic must not push across T_high without lexical evidence
    if has_semantic:
        lexical_weight = weights.token_overlap + weights.fuzzy_similarity
        if acronym_score > 0:
            lexical_weight += weights.acronym_signal
        lexical_sum = (
            weights.token_overlap * overlap
            + weights.fuzzy_similarity * fuzzy_score
            + (weights.acronym_signal * acronym_score if acronym_score > 0 else 0)
        )
        lexical_only_score = (lexical_sum / lexical_weight) - penalty - short_penalty
        if lexical_only_score < config.thresholds.t_high and score >= config.thresholds.t_high:
            score = config.thresholds.t_high - 0.01
            reasons.append("semantic_capped")

    features["final_score"] = score

    return ScoredCandidate(
        b_id=0,  # Will be set by caller
        score=score,
        features=features,
        reasons=reasons,
    )
