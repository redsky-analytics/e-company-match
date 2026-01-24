"""Rare LLM arbitration for ambiguous company name matches."""

from __future__ import annotations

import hashlib
import json
from typing import Protocol

import structlog

from cm.config import LLMConfig
from cm.types import Decision, LLMResponse, NormalizedName, ScoredCandidate

log = structlog.get_logger()


class LLMProvider(Protocol):
    """Protocol for LLM providers."""

    def query(self, prompt: str) -> str: ...


class LLMArbiter:
    """Controlled LLM arbitration with strict gating and caching."""

    def __init__(self, config: LLMConfig, provider: LLMProvider | None = None) -> None:
        self.config = config
        self.provider = provider
        self._cache: dict[str, LLMResponse] = {}
        self._global_calls: int = 0

    @property
    def calls_made(self) -> int:
        return self._global_calls

    def is_eligible(
        self,
        a: NormalizedName,
        b: NormalizedName,
        scored: ScoredCandidate,
        runner_up_score: float | None,
    ) -> bool:
        """Check if this pair passes all LLM gating rules."""
        if not self.config.enabled:
            return False

        # Rule 1: implicitly satisfied (caller only calls for AMBIGUOUS)

        # Rule 2: No numeric conflict
        a_nums = set(a.numeric_tokens)
        b_nums = set(b.numeric_tokens)
        if a_nums and b_nums and a_nums != b_nums:
            return False

        # Rule 3: At least one side has core_tokens >= 2
        if len(a.core_tokens) < 2 and len(b.core_tokens) < 2:
            return False

        # Rule 5: Margin below threshold (close race)
        if runner_up_score is not None:
            margin = scored.score - runner_up_score
            if margin >= self.config.min_confidence:
                return False

        # Rule 6: Global cap
        if self._global_calls >= self.config.global_call_cap:
            return False

        # Rule 7: Both single-token cores forbidden
        if self.config.forbid_both_single_token:
            if len(a.core_tokens) == 1 and len(b.core_tokens) == 1:
                return False

        return True

    def arbitrate(
        self,
        a: NormalizedName,
        b: NormalizedName,
        scored: ScoredCandidate,
        runner_up_score: float | None,
    ) -> tuple[Decision, LLMResponse]:
        """Call LLM to arbitrate an ambiguous pair.

        Returns (decision, llm_response).
        """
        cache_key = self._cache_key(a, b)

        # Check cache
        if cache_key in self._cache:
            response = self._cache[cache_key]
            return self._map_response(response), response

        if self.provider is None:
            # No provider configured, default to REVIEW
            response = LLMResponse(decision="UNSURE", confidence=0.0, reason="no_provider")
            return "REVIEW", response

        # Build prompt
        prompt = self._build_prompt(a, b, scored, runner_up_score)

        # Call LLM
        try:
            raw_response = self.provider.query(prompt)
            response = self._parse_response(raw_response)
        except Exception as e:
            log.warning("llm_call_failed", error=str(e))
            response = LLMResponse(decision="UNSURE", confidence=0.0, reason="error")
            self._cache[cache_key] = response
            return "REVIEW", response

        self._global_calls += 1
        self._cache[cache_key] = response

        return self._map_response(response), response

    def _cache_key(self, a: NormalizedName, b: NormalizedName) -> str:
        a_hash = hashlib.sha256(a.core_string.encode()).hexdigest()[:16]
        b_hash = hashlib.sha256(b.core_string.encode()).hexdigest()[:16]
        return f"{a_hash}::{b_hash}"

    def _map_response(self, response: LLMResponse) -> Decision:
        if response.decision == "SAME" and response.confidence >= self.config.min_confidence:
            return "MATCH"
        if response.decision == "DIFFERENT" and response.confidence >= self.config.min_confidence:
            return "NO_MATCH"
        return "REVIEW"

    def _build_prompt(
        self,
        a: NormalizedName,
        b: NormalizedName,
        scored: ScoredCandidate,
        runner_up_score: float | None,
    ) -> str:
        evidence = {
            "name_a_original": a.original,
            "name_b_original": b.original,
            "name_a_core": a.core_string,
            "name_b_core": b.core_string,
            "a_tokens": a.core_tokens,
            "b_tokens": b.core_tokens,
            "a_acronym": a.acronym,
            "b_acronym": b.acronym,
            "numeric_tokens_a": a.numeric_tokens,
            "numeric_tokens_b": b.numeric_tokens,
            "features": {
                "fuzzy": scored.features.get("fuzzy_similarity", 0.0),
                "token_overlap": scored.features.get("token_overlap", 0.0),
                "acronym_relation": scored.features.get("acronym_relation", "none"),
                "embedding_cosine": scored.features.get("semantic_similarity", 0.0),
                "deterministic_score": scored.score,
                "margin": scored.score - (runner_up_score or 0.0),
            },
        }

        return (
            "You are a company name matching expert. Determine if these two entries "
            "refer to the SAME company or DIFFERENT companies.\n\n"
            f"Evidence:\n{json.dumps(evidence, indent=2)}\n\n"
            "Respond with a JSON object:\n"
            '{"decision": "SAME|DIFFERENT|UNSURE", "confidence": 0.0-1.0, "reason": "short_label"}\n'
            "Only output the JSON object, nothing else."
        )

    def _parse_response(self, raw: str) -> LLMResponse:
        try:
            data = json.loads(raw.strip())
            return LLMResponse(
                decision=data.get("decision", "UNSURE"),
                confidence=float(data.get("confidence", 0.0)),
                reason=data.get("reason", ""),
            )
        except (json.JSONDecodeError, KeyError, TypeError):
            return LLMResponse(decision="UNSURE", confidence=0.0, reason="parse_error")
