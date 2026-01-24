"""Acronym generation and handling."""

from __future__ import annotations

import re
from pathlib import Path

from bizmatch.config import AcronymConfig

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"


def _load_collision_list() -> set[str]:
    path = DATA_DIR / "acronym_collision.txt"
    return {line.strip() for line in path.read_text().splitlines() if line.strip()}


COLLISION_LIST: set[str] = _load_collision_list()


def generate_acronym(
    core_tokens: list[str], config: AcronymConfig | None = None
) -> str | None:
    """Generate an acronym from core tokens (first letter of each token).

    Returns None if the result is too short.
    """
    if config is None:
        config = AcronymConfig()

    if len(core_tokens) < config.min_length:
        return None

    acronym = "".join(t[0] for t in core_tokens if t)
    if len(acronym) < config.min_length:
        return None

    return acronym


def normalize_acronym_input(text: str) -> str | None:
    """Normalize acronym-like inputs (e.g. 'I.B.M.' -> 'ibm').

    Returns the normalized acronym if the input looks like an acronym,
    otherwise None.
    """
    # Pattern: single letters separated by dots or spaces: I.B.M. or I B M
    cleaned = re.sub(r"[.\s]+", "", text)
    if len(cleaned) >= 3 and cleaned.isalpha() and all(
        len(part) == 1 for part in re.split(r"[.\s]+", text) if part
    ):
        return cleaned.lower()
    return None


def is_collision(acronym: str) -> bool:
    """Check if an acronym is in the collision list."""
    return acronym.lower() in COLLISION_LIST


def acronym_relation(
    a_acronym: str | None,
    a_core_tokens: list[str],
    b_acronym: str | None,
    b_core_tokens: list[str],
) -> str:
    """Determine the acronym relation between two names.

    Returns one of: 'exact', 'initialism', 'collision', 'none'.
    """
    if a_acronym and b_acronym and a_acronym == b_acronym:
        if is_collision(a_acronym):
            return "collision"
        return "exact"

    # Check if one side's acronym matches the other side's initialism
    if a_acronym and len(b_core_tokens) >= 3:
        b_initialism = "".join(t[0] for t in b_core_tokens)
        if a_acronym == b_initialism:
            if is_collision(a_acronym):
                return "collision"
            return "initialism"

    if b_acronym and len(a_core_tokens) >= 3:
        a_initialism = "".join(t[0] for t in a_core_tokens)
        if b_acronym == a_initialism:
            if is_collision(b_acronym):
                return "collision"
            return "initialism"

    return "none"
