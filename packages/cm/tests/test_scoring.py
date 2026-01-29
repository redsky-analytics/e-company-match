"""Tests for the deterministic scoring module."""

from cm.config import MatchConfig
from cm.normalize import normalize
from cm.scoring import score_pair


def test_identical_names_high_score():
    config = MatchConfig()
    a = normalize("Apple Inc", config)
    b = normalize("Apple Inc.", config)
    result = score_pair(a, b, config)
    assert result.score >= 0.9


def test_completely_different_names_low_score():
    config = MatchConfig()
    a = normalize("Apple Inc", config)
    b = normalize("Microsoft Corporation", config)
    result = score_pair(a, b, config)
    assert result.score < 0.5


def test_numeric_mismatch_penalized():
    config = MatchConfig()
    a = normalize("Company 2020", config)
    b = normalize("Company 2021", config)
    result = score_pair(a, b, config)
    assert "numeric_mismatch" in result.reasons


def test_numeric_one_side_only():
    config = MatchConfig()
    a = normalize("Company 123", config)
    b = normalize("Company", config)
    result = score_pair(a, b, config)
    assert "numeric_one_side_only" in result.reasons


def test_acronym_boost():
    config = MatchConfig()
    a = normalize("IBM", config)
    b = normalize("International Business Machines", config)
    result = score_pair(a, b, config)
    assert result.features.get("acronym_score", 0) > 0


def test_fuzzy_similarity_close_names():
    config = MatchConfig()
    a = normalize("Goldman Sachs", config)
    b = normalize("Goldmann Sachs", config)  # slight misspelling
    result = score_pair(a, b, config)
    assert result.score > 0.7


def test_token_overlap_partial():
    config = MatchConfig()
    a = normalize("General Electric Company", config)
    b = normalize("General Electric Power", config)
    result = score_pair(a, b, config)
    assert result.features["token_overlap"] > 0.5


def test_semantic_cap():
    """Semantic should not push score across T_high without lexical evidence."""
    config = MatchConfig()
    a = normalize("Foo Bar", config)
    b = normalize("Baz Qux", config)
    # Score without embedding would be low
    # With a high embedding_cosine it should be capped
    result = score_pair(a, b, config, embedding_cosine=0.99)
    assert result.score < config.thresholds.t_high


def test_score_in_valid_range():
    config = MatchConfig()
    a = normalize("Test Company Ltd", config)
    b = normalize("Another Firm Inc", config)
    result = score_pair(a, b, config)
    assert 0.0 <= result.score <= 1.0
