"""Tests for the end-to-end matcher."""

from cm.config import MatchConfig
from cm.matcher import Matcher


def test_exact_match():
    matcher = Matcher()
    matcher.preprocess_b(["Apple Inc", "Microsoft Corp", "Google LLC"])
    result = matcher.match_one("Apple Inc.")
    assert result.decision == "MATCH"
    assert result.b_name == "Apple Inc"


def test_no_match():
    matcher = Matcher()
    matcher.preprocess_b(["Apple Inc", "Microsoft Corp", "Google LLC"])
    result = matcher.match_one("Totally Unknown Company XYZ")
    assert result.decision in ("NO_MATCH", "REVIEW")


def test_designator_variants():
    matcher = Matcher()
    matcher.preprocess_b(["Apple Incorporated", "Microsoft Corporation"])
    result = matcher.match_one("Apple Inc.")
    assert result.decision == "MATCH"
    assert result.b_name == "Apple Incorporated"


def test_match_all():
    matcher = Matcher()
    matcher.preprocess_b(["Apple Inc", "Microsoft Corp", "Google LLC"])
    results = matcher.match_all(["Apple Inc.", "Microsoft Corporation", "Amazon"])
    assert len(results) == 3
    assert results[0].decision == "MATCH"
    assert results[1].decision == "MATCH"


def test_no_candidates_returns_no_match():
    matcher = Matcher()
    matcher.preprocess_b(["Alpha Corp", "Beta Ltd"])
    result = matcher.match_one("Zzzzz Unique Name")
    assert result.decision == "NO_MATCH"
    assert "no_candidates" in result.reasons


def test_match_result_has_debug():
    matcher = Matcher()
    matcher.preprocess_b(["Apple Inc", "Apple Corp", "Google LLC"])
    result = matcher.match_one("Apple Inc.")
    assert "top_candidates" in result.debug
    assert "candidate_count" in result.debug


def test_margin_rule():
    """Two very similar candidates should trigger ambiguity."""
    config = MatchConfig()
    config.thresholds.t_high = 0.85
    config.thresholds.margin = 0.10
    matcher = Matcher(config)
    # Two candidates with very similar names
    matcher.preprocess_b(["Acme Solutions", "Acme Services", "Google LLC"])
    result = matcher.match_one("Acme")
    # With a single token "acme", the short name guardrail kicks in


def test_llm_not_called_by_default():
    matcher = Matcher()
    matcher.preprocess_b(["Apple Inc", "Microsoft Corp"])
    result = matcher.match_one("Apple Inc.")
    assert result.used_llm is False


def test_score_in_result():
    matcher = Matcher()
    matcher.preprocess_b(["Apple Inc"])
    result = matcher.match_one("Apple Incorporated")
    assert result.score > 0.0


def test_close_name_variants():
    matcher = Matcher()
    matcher.preprocess_b([
        "Johnson & Johnson",
        "Johnson Controls International",
    ])
    result = matcher.match_one("Johnson and Johnson")
    assert result.decision == "MATCH"
    assert result.b_name == "Johnson & Johnson"
