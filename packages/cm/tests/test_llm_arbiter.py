"""Tests for the LLM arbiter module."""

import json

import pytest

from cm.config import LLMConfig
from cm.llm_arbiter import LLMArbiter, LLMProvider
from cm.types import LLMResponse, NormalizedName, ScoredCandidate


class MockLLMProvider:
    """Mock LLM provider for testing."""

    def __init__(self, response: str = '{"decision": "SAME", "confidence": 0.9, "reason": "test"}'):
        self.response = response
        self.calls: list[str] = []

    def query(self, prompt: str) -> str:
        self.calls.append(prompt)
        return self.response


def make_normalized_name(
    original: str,
    core_tokens: list[str] | None = None,
    numeric_tokens: list[str] | None = None,
    acronym: str | None = None,
) -> NormalizedName:
    """Helper to create NormalizedName instances for testing."""
    tokens = core_tokens or original.lower().split()
    return NormalizedName(
        original=original,
        normalized_text=original.lower(),
        raw_tokens=tokens,
        core_tokens=tokens,
        core_string=" ".join(tokens),
        acronym=acronym,
        numeric_tokens=numeric_tokens or [],
        keys={"blocking": "".join(tokens)},
    )


def make_scored_candidate(score: float = 0.8, features: dict | None = None) -> ScoredCandidate:
    """Helper to create ScoredCandidate instances for testing."""
    return ScoredCandidate(
        b_id=1,
        score=score,
        features=features or {"fuzzy_similarity": 0.8, "token_overlap": 0.7},
        reasons=[],
    )


class TestLLMArbiterEligibility:
    """Tests for LLM eligibility gating."""

    def test_disabled_llm_not_eligible(self):
        config = LLMConfig(enabled=False)
        arbiter = LLMArbiter(config)
        a = make_normalized_name("Apple Inc", ["apple", "inc"])
        b = make_normalized_name("Apple Incorporated", ["apple", "incorporated"])
        scored = make_scored_candidate()

        result = arbiter.is_eligible(a, b, scored, runner_up_score=0.75)

        assert result is False

    def test_enabled_llm_eligible(self):
        config = LLMConfig(enabled=True, min_confidence=0.75)
        arbiter = LLMArbiter(config)
        a = make_normalized_name("Apple Inc", ["apple", "inc"])
        b = make_normalized_name("Apple Incorporated", ["apple", "incorporated"])
        scored = make_scored_candidate(score=0.80)

        result = arbiter.is_eligible(a, b, scored, runner_up_score=0.78)

        assert result is True

    def test_numeric_conflict_not_eligible(self):
        config = LLMConfig(enabled=True)
        arbiter = LLMArbiter(config)
        a = make_normalized_name("Company 2020", ["company"], ["2020"])
        b = make_normalized_name("Company 2021", ["company"], ["2021"])
        scored = make_scored_candidate()

        result = arbiter.is_eligible(a, b, scored, runner_up_score=0.75)

        assert result is False

    def test_both_single_token_not_eligible(self):
        config = LLMConfig(enabled=True, forbid_both_single_token=True)
        arbiter = LLMArbiter(config)
        a = make_normalized_name("Apple", ["apple"])
        b = make_normalized_name("Microsoft", ["microsoft"])
        scored = make_scored_candidate()

        result = arbiter.is_eligible(a, b, scored, runner_up_score=0.75)

        assert result is False

    def test_one_side_multi_token_eligible(self):
        config = LLMConfig(enabled=True, forbid_both_single_token=True, min_confidence=0.9)
        arbiter = LLMArbiter(config)
        a = make_normalized_name("Apple", ["apple"])
        b = make_normalized_name("Apple Inc", ["apple", "inc"])
        scored = make_scored_candidate(score=0.80)

        result = arbiter.is_eligible(a, b, scored, runner_up_score=0.78)

        assert result is True

    def test_high_margin_not_eligible(self):
        config = LLMConfig(enabled=True, min_confidence=0.10)
        arbiter = LLMArbiter(config)
        a = make_normalized_name("Apple Inc", ["apple", "inc"])
        b = make_normalized_name("Apple Incorporated", ["apple", "incorporated"])
        scored = make_scored_candidate(score=0.90)

        result = arbiter.is_eligible(a, b, scored, runner_up_score=0.70)

        assert result is False

    def test_global_cap_reached_not_eligible(self):
        config = LLMConfig(enabled=True, global_call_cap=0)
        arbiter = LLMArbiter(config)
        a = make_normalized_name("Apple Inc", ["apple", "inc"])
        b = make_normalized_name("Apple Incorporated", ["apple", "incorporated"])
        scored = make_scored_candidate()

        result = arbiter.is_eligible(a, b, scored, runner_up_score=0.75)

        assert result is False


class TestLLMArbiterArbitrate:
    """Tests for LLM arbitration."""

    def test_no_provider_returns_review(self):
        config = LLMConfig(enabled=True)
        arbiter = LLMArbiter(config, provider=None)
        a = make_normalized_name("Apple Inc", ["apple", "inc"])
        b = make_normalized_name("Apple Incorporated", ["apple", "incorporated"])
        scored = make_scored_candidate()

        decision, response = arbiter.arbitrate(a, b, scored, runner_up_score=0.75)

        assert decision == "REVIEW"
        assert response.decision == "UNSURE"
        assert response.reason == "no_provider"

    def test_same_decision_high_confidence(self):
        config = LLMConfig(enabled=True, min_confidence=0.75)
        provider = MockLLMProvider('{"decision": "SAME", "confidence": 0.95, "reason": "same_company"}')
        arbiter = LLMArbiter(config, provider=provider)
        a = make_normalized_name("Apple Inc", ["apple", "inc"])
        b = make_normalized_name("Apple Incorporated", ["apple", "incorporated"])
        scored = make_scored_candidate()

        decision, response = arbiter.arbitrate(a, b, scored, runner_up_score=0.75)

        assert decision == "MATCH"
        assert response.decision == "SAME"
        assert response.confidence == 0.95

    def test_different_decision_high_confidence(self):
        config = LLMConfig(enabled=True, min_confidence=0.75)
        provider = MockLLMProvider('{"decision": "DIFFERENT", "confidence": 0.90, "reason": "distinct"}')
        arbiter = LLMArbiter(config, provider=provider)
        a = make_normalized_name("Apple Inc", ["apple", "inc"])
        b = make_normalized_name("Microsoft Corp", ["microsoft", "corp"])
        scored = make_scored_candidate()

        decision, response = arbiter.arbitrate(a, b, scored, runner_up_score=0.75)

        assert decision == "NO_MATCH"
        assert response.decision == "DIFFERENT"

    def test_low_confidence_returns_review(self):
        config = LLMConfig(enabled=True, min_confidence=0.75)
        provider = MockLLMProvider('{"decision": "SAME", "confidence": 0.50, "reason": "uncertain"}')
        arbiter = LLMArbiter(config, provider=provider)
        a = make_normalized_name("Apple Inc", ["apple", "inc"])
        b = make_normalized_name("Apple Corp", ["apple", "corp"])
        scored = make_scored_candidate()

        decision, response = arbiter.arbitrate(a, b, scored, runner_up_score=0.75)

        assert decision == "REVIEW"

    def test_unsure_decision_returns_review(self):
        config = LLMConfig(enabled=True)
        provider = MockLLMProvider('{"decision": "UNSURE", "confidence": 0.50, "reason": "ambiguous"}')
        arbiter = LLMArbiter(config, provider=provider)
        a = make_normalized_name("Apple Inc", ["apple", "inc"])
        b = make_normalized_name("Apple Corp", ["apple", "corp"])
        scored = make_scored_candidate()

        decision, response = arbiter.arbitrate(a, b, scored, runner_up_score=0.75)

        assert decision == "REVIEW"


class TestLLMArbiterCaching:
    """Tests for LLM response caching."""

    def test_cache_hit(self):
        config = LLMConfig(enabled=True)
        provider = MockLLMProvider('{"decision": "SAME", "confidence": 0.95, "reason": "test"}')
        arbiter = LLMArbiter(config, provider=provider)
        a = make_normalized_name("Apple Inc", ["apple", "inc"])
        b = make_normalized_name("Apple Incorporated", ["apple", "incorporated"])
        scored = make_scored_candidate()

        # First call
        arbiter.arbitrate(a, b, scored, runner_up_score=0.75)
        # Second call with same inputs
        arbiter.arbitrate(a, b, scored, runner_up_score=0.75)

        # Provider should only be called once
        assert len(provider.calls) == 1

    def test_different_pairs_not_cached(self):
        config = LLMConfig(enabled=True)
        provider = MockLLMProvider('{"decision": "SAME", "confidence": 0.95, "reason": "test"}')
        arbiter = LLMArbiter(config, provider=provider)
        a1 = make_normalized_name("Apple Inc", ["apple", "inc"])
        b1 = make_normalized_name("Apple Incorporated", ["apple", "incorporated"])
        a2 = make_normalized_name("Microsoft Corp", ["microsoft", "corp"])
        b2 = make_normalized_name("Microsoft Corporation", ["microsoft", "corporation"])
        scored = make_scored_candidate()

        arbiter.arbitrate(a1, b1, scored, runner_up_score=0.75)
        arbiter.arbitrate(a2, b2, scored, runner_up_score=0.75)

        assert len(provider.calls) == 2


class TestLLMArbiterCallCounting:
    """Tests for global call counting."""

    def test_calls_made_property(self):
        config = LLMConfig(enabled=True)
        provider = MockLLMProvider()
        arbiter = LLMArbiter(config, provider=provider)

        assert arbiter.calls_made == 0

        a = make_normalized_name("Apple Inc", ["apple", "inc"])
        b = make_normalized_name("Apple Incorporated", ["apple", "incorporated"])
        scored = make_scored_candidate()

        arbiter.arbitrate(a, b, scored, runner_up_score=0.75)

        assert arbiter.calls_made == 1

    def test_cache_hits_dont_count(self):
        config = LLMConfig(enabled=True)
        provider = MockLLMProvider()
        arbiter = LLMArbiter(config, provider=provider)
        a = make_normalized_name("Apple Inc", ["apple", "inc"])
        b = make_normalized_name("Apple Incorporated", ["apple", "incorporated"])
        scored = make_scored_candidate()

        arbiter.arbitrate(a, b, scored, runner_up_score=0.75)
        arbiter.arbitrate(a, b, scored, runner_up_score=0.75)

        assert arbiter.calls_made == 1


class TestLLMArbiterErrorHandling:
    """Tests for error handling in LLM calls."""

    def test_invalid_json_response(self):
        config = LLMConfig(enabled=True)
        provider = MockLLMProvider("not valid json")
        arbiter = LLMArbiter(config, provider=provider)
        a = make_normalized_name("Apple Inc", ["apple", "inc"])
        b = make_normalized_name("Apple Incorporated", ["apple", "incorporated"])
        scored = make_scored_candidate()

        decision, response = arbiter.arbitrate(a, b, scored, runner_up_score=0.75)

        assert decision == "REVIEW"
        assert response.decision == "UNSURE"
        assert response.reason == "parse_error"

    def test_provider_exception(self):
        config = LLMConfig(enabled=True)

        class FailingProvider:
            def query(self, prompt: str) -> str:
                raise Exception("API error")

        arbiter = LLMArbiter(config, provider=FailingProvider())
        a = make_normalized_name("Apple Inc", ["apple", "inc"])
        b = make_normalized_name("Apple Incorporated", ["apple", "incorporated"])
        scored = make_scored_candidate()

        decision, response = arbiter.arbitrate(a, b, scored, runner_up_score=0.75)

        assert decision == "REVIEW"
        assert response.decision == "UNSURE"
        assert response.reason == "error"


class TestLLMArbiterPromptBuilding:
    """Tests for prompt construction."""

    def test_prompt_contains_names(self):
        config = LLMConfig(enabled=True)
        provider = MockLLMProvider()
        arbiter = LLMArbiter(config, provider=provider)
        a = make_normalized_name("Apple Inc", ["apple", "inc"])
        b = make_normalized_name("Apple Incorporated", ["apple", "incorporated"])
        scored = make_scored_candidate()

        arbiter.arbitrate(a, b, scored, runner_up_score=0.75)

        prompt = provider.calls[0]
        assert "Apple Inc" in prompt
        assert "Apple Incorporated" in prompt

    def test_prompt_with_strip_categories(self):
        config = LLMConfig(enabled=True)
        provider = MockLLMProvider()
        arbiter = LLMArbiter(config, provider=provider)
        a = make_normalized_name("Apple Inc", ["apple", "inc"])
        b = make_normalized_name("Apple Incorporated", ["apple", "incorporated"])
        scored = make_scored_candidate()

        arbiter.arbitrate(a, b, scored, runner_up_score=0.75, strip_categories=["location", "branch"])

        prompt = provider.calls[0]
        assert "location" in prompt
        assert "branch" in prompt
        assert "IGNORE" in prompt
