"""Evaluation and tuning utilities for the matching system."""

from __future__ import annotations

import csv
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from bizmatch.config import MatchConfig
from bizmatch.matcher import Matcher
from bizmatch.types import MatchResult


@dataclass
class EvalMetrics:
    precision: float = 0.0
    recall: float = 0.0
    f1: float = 0.0
    total_pairs: int = 0
    true_positives: int = 0
    false_positives: int = 0
    false_negatives: int = 0
    true_negatives: int = 0
    ambiguous_count: int = 0
    llm_call_count: int = 0
    fp_reasons: dict[str, int] = field(default_factory=dict)


@dataclass
class LabeledPair:
    name_a: str
    name_b: str
    label: int  # 1 = match, 0 = no-match


def load_labeled_pairs(path: str | Path) -> list[LabeledPair]:
    """Load labeled pairs from CSV (name_a, name_b, label)."""
    path = Path(path)
    pairs: list[LabeledPair] = []
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            pairs.append(LabeledPair(
                name_a=row["name_a"].strip(),
                name_b=row["name_b"].strip(),
                label=int(row["label"]),
            ))
    return pairs


def evaluate(
    pairs: list[LabeledPair],
    config: MatchConfig | None = None,
) -> EvalMetrics:
    """Evaluate the matcher on labeled pairs.

    For each pair, we build a B list of just [name_b] and match name_a against it.
    This tests the scoring and decision logic in isolation.
    """
    config = config or MatchConfig()
    metrics = EvalMetrics(total_pairs=len(pairs))
    fp_reasons: Counter[str] = Counter()

    for pair in pairs:
        matcher = Matcher(config)
        matcher.preprocess_b([pair.name_b])
        result = matcher.match_one(pair.name_a)

        predicted_match = result.decision == "MATCH"
        actual_match = pair.label == 1

        if result.decision == "REVIEW":
            metrics.ambiguous_count += 1

        if result.used_llm:
            metrics.llm_call_count += 1

        if predicted_match and actual_match:
            metrics.true_positives += 1
        elif predicted_match and not actual_match:
            metrics.false_positives += 1
            for reason in result.reasons:
                fp_reasons[reason] += 1
        elif not predicted_match and actual_match:
            metrics.false_negatives += 1
        else:
            metrics.true_negatives += 1

    # Compute precision, recall, F1
    if metrics.true_positives + metrics.false_positives > 0:
        metrics.precision = metrics.true_positives / (
            metrics.true_positives + metrics.false_positives
        )
    if metrics.true_positives + metrics.false_negatives > 0:
        metrics.recall = metrics.true_positives / (
            metrics.true_positives + metrics.false_negatives
        )
    if metrics.precision + metrics.recall > 0:
        metrics.f1 = (
            2 * metrics.precision * metrics.recall
            / (metrics.precision + metrics.recall)
        )

    metrics.fp_reasons = dict(fp_reasons)
    return metrics


def evaluate_batch(
    a_names: list[str],
    b_names: list[str],
    labeled_matches: dict[int, int],
    config: MatchConfig | None = None,
) -> tuple[EvalMetrics, list[MatchResult]]:
    """Evaluate on full A/B lists with known matches.

    labeled_matches: dict mapping a_id -> b_id for known matches.
    """
    config = config or MatchConfig()
    matcher = Matcher(config)
    matcher.preprocess_b(b_names)
    results = matcher.match_all(a_names)

    metrics = EvalMetrics(total_pairs=len(results))
    fp_reasons: Counter[str] = Counter()

    for result in results:
        expected_b_id = labeled_matches.get(result.a_id)
        actual_match = expected_b_id is not None
        predicted_match = result.decision == "MATCH"

        if result.decision == "REVIEW":
            metrics.ambiguous_count += 1
        if result.used_llm:
            metrics.llm_call_count += 1

        if predicted_match and actual_match and result.b_id == expected_b_id:
            metrics.true_positives += 1
        elif predicted_match and (not actual_match or result.b_id != expected_b_id):
            metrics.false_positives += 1
            for reason in result.reasons:
                fp_reasons[reason] += 1
        elif not predicted_match and actual_match:
            metrics.false_negatives += 1
        else:
            metrics.true_negatives += 1

    if metrics.true_positives + metrics.false_positives > 0:
        metrics.precision = metrics.true_positives / (
            metrics.true_positives + metrics.false_positives
        )
    if metrics.true_positives + metrics.false_negatives > 0:
        metrics.recall = metrics.true_positives / (
            metrics.true_positives + metrics.false_negatives
        )
    if metrics.precision + metrics.recall > 0:
        metrics.f1 = (
            2 * metrics.precision * metrics.recall
            / (metrics.precision + metrics.recall)
        )

    metrics.fp_reasons = dict(fp_reasons)
    return metrics, results
