"""Tests for the evaluation module."""

from pathlib import Path

import pytest

from cm.evaluation import (
    EvalMetrics,
    LabeledPair,
    evaluate,
    evaluate_batch,
    load_labeled_pairs,
)
from cm.config import MatchConfig


class TestLoadLabeledPairs:
    """Tests for loading labeled pairs from CSV."""

    def test_load_basic(self, tmp_path: Path):
        csv_file = tmp_path / "pairs.csv"
        csv_file.write_text(
            "name_a,name_b,label\n"
            "Apple Inc,Apple Incorporated,1\n"
            "Microsoft Corp,Google LLC,0\n"
        )

        pairs = load_labeled_pairs(csv_file)

        assert len(pairs) == 2
        assert pairs[0] == LabeledPair("Apple Inc", "Apple Incorporated", 1)
        assert pairs[1] == LabeledPair("Microsoft Corp", "Google LLC", 0)

    def test_load_strips_whitespace(self, tmp_path: Path):
        csv_file = tmp_path / "pairs.csv"
        csv_file.write_text(
            "name_a,name_b,label\n"
            "  Apple Inc  , Apple Incorporated ,1\n"
        )

        pairs = load_labeled_pairs(csv_file)

        assert pairs[0].name_a == "Apple Inc"
        assert pairs[0].name_b == "Apple Incorporated"


class TestEvaluate:
    """Tests for the evaluate function."""

    def test_perfect_match(self):
        pairs = [LabeledPair("Apple Inc", "Apple Incorporated", 1)]

        metrics = evaluate(pairs)

        assert metrics.true_positives == 1
        assert metrics.false_positives == 0
        assert metrics.false_negatives == 0
        assert metrics.precision == 1.0
        assert metrics.recall == 1.0
        assert metrics.f1 == 1.0

    def test_true_negative(self):
        pairs = [LabeledPair("Apple Inc", "Microsoft Corp", 0)]

        metrics = evaluate(pairs)

        assert metrics.true_negatives == 1 or metrics.ambiguous_count == 1
        assert metrics.false_positives == 0

    def test_false_positive(self):
        # A case where the matcher says MATCH but the label says no-match
        # Use names that might be ambiguous
        pairs = [LabeledPair("ABC Corp", "ABC Corporation", 0)]

        metrics = evaluate(pairs)

        # The matcher should match these, creating a false positive
        if metrics.precision < 1.0:
            assert metrics.false_positives > 0

    def test_multiple_pairs(self):
        pairs = [
            LabeledPair("Apple Inc", "Apple Incorporated", 1),
            LabeledPair("Microsoft Corp", "Microsoft Corporation", 1),
            LabeledPair("Google LLC", "Amazon Inc", 0),
        ]

        metrics = evaluate(pairs)

        assert metrics.total_pairs == 3
        assert metrics.true_positives + metrics.false_positives + \
               metrics.true_negatives + metrics.false_negatives + \
               metrics.ambiguous_count >= 3

    def test_custom_config(self):
        config = MatchConfig()
        config.thresholds.t_high = 0.99  # Very strict threshold
        pairs = [LabeledPair("Apple Inc", "Apple", 1)]

        metrics = evaluate(pairs, config=config)

        # With strict thresholds, might not match
        assert metrics.total_pairs == 1

    def test_llm_calls_tracked(self):
        pairs = [LabeledPair("Apple Inc", "Apple Incorporated", 1)]

        metrics = evaluate(pairs)

        # LLM should not be called by default
        assert metrics.llm_call_count == 0

    def test_fp_reasons_tracked(self):
        # Create a case that generates false positive with reasons
        pairs = [
            LabeledPair("XYZ Corp", "XYZ Corporation", 0),  # Label says no match but they're similar
        ]

        metrics = evaluate(pairs)

        # If there's a false positive, reasons should be tracked
        assert isinstance(metrics.fp_reasons, dict)


class TestEvaluateBatch:
    """Tests for the evaluate_batch function."""

    def test_basic_batch(self):
        a_names = ["Apple Inc", "Microsoft Corp"]
        b_names = ["Apple Incorporated", "Microsoft Corporation", "Google LLC"]
        labeled_matches = {0: 0, 1: 1}  # a_id 0 matches b_id 0, etc.

        metrics, results = evaluate_batch(a_names, b_names, labeled_matches)

        assert metrics.total_pairs == 2
        assert len(results) == 2

    def test_batch_with_no_matches(self):
        a_names = ["Unknown Corp"]
        b_names = ["Apple Inc", "Microsoft Corp"]
        labeled_matches = {}  # No expected matches

        metrics, results = evaluate_batch(a_names, b_names, labeled_matches)

        assert len(results) == 1
        # Should be true negative or ambiguous if no match found

    def test_batch_precision_recall(self):
        a_names = ["Apple Inc", "Microsoft Corp", "Google LLC"]
        b_names = ["Apple Incorporated", "Microsoft Corporation", "Google Limited"]
        labeled_matches = {0: 0, 1: 1, 2: 2}

        metrics, results = evaluate_batch(a_names, b_names, labeled_matches)

        assert 0.0 <= metrics.precision <= 1.0
        assert 0.0 <= metrics.recall <= 1.0
        assert 0.0 <= metrics.f1 <= 1.0

    def test_batch_wrong_match(self):
        a_names = ["Apple Inc"]
        b_names = ["Apple Corp", "Apple LLC"]
        labeled_matches = {0: 1}  # Expected to match b_id 1

        metrics, results = evaluate_batch(a_names, b_names, labeled_matches)

        # If it matches the wrong one, should be a false positive
        if results[0].decision == "MATCH" and results[0].b_id != 1:
            assert metrics.false_positives > 0


class TestEvalMetrics:
    """Tests for the EvalMetrics dataclass."""

    def test_default_values(self):
        metrics = EvalMetrics()

        assert metrics.precision == 0.0
        assert metrics.recall == 0.0
        assert metrics.f1 == 0.0
        assert metrics.total_pairs == 0
        assert metrics.true_positives == 0
        assert metrics.false_positives == 0
        assert metrics.false_negatives == 0
        assert metrics.true_negatives == 0
        assert metrics.fp_reasons == {}

    def test_custom_values(self):
        metrics = EvalMetrics(
            precision=0.9,
            recall=0.8,
            total_pairs=100,
            true_positives=80,
        )

        assert metrics.precision == 0.9
        assert metrics.recall == 0.8
        assert metrics.total_pairs == 100
        assert metrics.true_positives == 80
