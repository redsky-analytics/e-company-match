"""Core types for the bizmatch company name matching system."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


@dataclass
class NormalizedName:
    original: str
    normalized_text: str
    raw_tokens: list[str]
    core_tokens: list[str]
    core_string: str
    acronym: str | None
    numeric_tokens: list[str]
    keys: dict[str, str]
    meta: dict = field(default_factory=lambda: {
        "removed_designators": [],
        "warnings": [],
        "notes": {},
    })


@dataclass
class Candidate:
    b_id: int
    sources: set[str] = field(default_factory=set)


@dataclass
class ScoredCandidate:
    b_id: int
    score: float
    features: dict[str, float | bool | str] = field(default_factory=dict)
    reasons: list[str] = field(default_factory=list)


Decision = Literal["MATCH", "NO_MATCH", "REVIEW"]


@dataclass
class MatchResult:
    a_id: int
    a_name: str
    b_id: int | None
    b_name: str | None
    decision: Decision
    score: float
    runner_up_score: float | None = None
    margin: float | None = None
    used_llm: bool = False
    reasons: list[str] = field(default_factory=list)
    debug: dict = field(default_factory=dict)


@dataclass
class LLMResponse:
    decision: Literal["SAME", "DIFFERENT", "UNSURE"]
    confidence: float
    reason: str
