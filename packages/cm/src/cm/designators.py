"""Legal designator handling for company names."""

from __future__ import annotations

import json
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"


def _load_designators() -> set[str]:
    path = DATA_DIR / "designators_global.txt"
    return {line.strip() for line in path.read_text().splitlines() if line.strip()}


def _load_aliases() -> dict[str, str]:
    path = DATA_DIR / "designator_aliases.json"
    return json.loads(path.read_text())


DESIGNATORS: set[str] = _load_designators()
ALIASES: dict[str, str] = _load_aliases()


def canonicalize_token(token: str) -> str:
    """Apply alias map to a token (e.g. 'inc.' -> 'inc')."""
    return ALIASES.get(token, token)


def is_designator(token: str) -> bool:
    """Check if a token is a legal designator."""
    return token in DESIGNATORS


def strip_designators(
    tokens: list[str],
    *,
    strip_prefix: bool = False,
) -> tuple[list[str], list[str]]:
    """Strip legal designators from token list.

    Default: suffix-only stripping.

    Returns:
        Tuple of (core_tokens, removed_designators).
        If stripping would leave fewer than 2 tokens, returns original
        tokens unchanged and empty removed list (caller should add warning).
    """
    removed: list[str] = []
    core: list[str] = []

    # Find suffix designators (from the end)
    suffix_start = len(tokens)
    for i in range(len(tokens) - 1, -1, -1):
        if is_designator(tokens[i]):
            suffix_start = i
        else:
            break

    # Find prefix designators (from the start)
    prefix_end = 0
    if strip_prefix:
        for i in range(len(tokens)):
            if is_designator(tokens[i]):
                prefix_end = i + 1
            else:
                break

    # Build core tokens, collecting removed
    for i, token in enumerate(tokens):
        if i < prefix_end or i >= suffix_start:
            removed.append(token)
        else:
            core.append(token)

    # Safety: never strip if resulting tokens < 2
    if len(core) < 2:
        return list(tokens), []

    return core, removed
