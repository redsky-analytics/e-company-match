"""Legal designator handling for company names."""

from __future__ import annotations

import json
import os
from pathlib import Path

DATA_DIR = Path(os.environ.get("CM_CONFIG_DATA") or "config_data")


def _load_word_list(filename: str) -> set[str]:
    path = DATA_DIR / filename
    if not path.exists():
        return set()
    return {line.strip().lower() for line in path.read_text().splitlines() if line.strip()}


def _load_aliases() -> dict[str, str]:
    path = DATA_DIR / "designator_aliases.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError:
        return {}


# Cache for dynamically loaded word lists
_CATEGORY_CACHE: dict[str, set[str]] = {}


def load_category_words(category: str) -> set[str]:
    """Load word list for a category (e.g., 'location' loads 'location.txt')."""
    if category not in _CATEGORY_CACHE:
        _CATEGORY_CACHE[category] = _load_word_list(f"{category}.txt")
    return _CATEGORY_CACHE[category]


def get_available_categories() -> list[str]:
    """Return list of available category names (files matching *.txt except designators)."""
    exclude = {"designators_global.txt", "designator_aliases.json"}
    categories = []
    for path in DATA_DIR.glob("*.txt"):
        if path.name not in exclude:
            categories.append(path.stem)
    return sorted(categories)


DESIGNATORS: set[str] = _load_word_list("designators_global.txt")
ALIASES: dict[str, str] = _load_aliases()


def canonicalize_token(token: str) -> str:
    """Apply alias map to a token (e.g. 'inc.' -> 'inc')."""
    return ALIASES.get(token, token)


def is_designator(token: str) -> bool:
    """Check if a token is a legal designator."""
    return token in DESIGNATORS


def is_in_category(token: str, category: str) -> bool:
    """Check if a token belongs to a word category."""
    words = load_category_words(category)
    return token.lower() in words


def strip_word_categories(
    tokens: list[str],
    categories: list[str],
) -> tuple[list[str], list[str]]:
    """Strip words from specified categories from token list.

    Args:
        tokens: List of tokens to process.
        categories: List of category names (e.g., ["location", "institution"]).

    Returns:
        Tuple of (filtered_tokens, removed_words).
        If stripping would leave fewer than 1 token, returns original unchanged.
    """
    if not categories:
        return list(tokens), []

    # Load all category word sets
    category_words: set[str] = set()
    for category in categories:
        category_words.update(load_category_words(category))

    removed: list[str] = []
    filtered: list[str] = []

    for token in tokens:
        if token.lower() in category_words:
            removed.append(token)
        else:
            filtered.append(token)

    # Safety: never strip if resulting tokens < 1
    if len(filtered) < 1:
        return list(tokens), []

    return filtered, removed


def strip_designators(
    tokens: list[str],
    *,
    strip_prefix: bool = False,
    min_tokens: int = 2,
) -> tuple[list[str], list[str]]:
    """Strip legal designators from token list.

    Default: suffix-only stripping.

    Args:
        tokens: List of tokens to process.
        strip_prefix: Also strip designators from the beginning.
        min_tokens: Minimum tokens to keep (default 2, use 1 for aggressive stripping).

    Returns:
        Tuple of (core_tokens, removed_designators).
        If stripping would leave fewer than min_tokens, returns original
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

    # Safety: never strip if resulting tokens < min_tokens
    if len(core) < min_tokens:
        return list(tokens), []

    return core, removed
