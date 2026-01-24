"""Company name normalization pipeline."""

from __future__ import annotations

import re
import unicodedata

from bizmatch.acronyms import generate_acronym, is_collision, normalize_acronym_input
from bizmatch.config import MatchConfig
from bizmatch.designators import canonicalize_token, strip_designators
from bizmatch.types import NormalizedName


def normalize(name: str, config: MatchConfig | None = None) -> NormalizedName:
    """Normalize a company name into a stable NormalizedName representation."""
    if config is None:
        config = MatchConfig()

    original = name
    warnings: list[str] = []

    # 1. Unicode normalize (NFKC)
    s = unicodedata.normalize("NFKC", name)

    # 2. Casefold
    s = s.casefold()

    # Store normalized_text before further processing
    normalized_text = s

    # 3. Symbol replacement
    s = s.replace("&", " and ")
    if config.normalization.plus_to_and:
        s = s.replace("+", " and ")

    # 4. Tokenize by whitespace first (before punctuation removal)
    raw_split = s.split()

    # 5. Apply alias canonicalization before punctuation removal
    #    This handles "inc.", "l.l.c.", etc. correctly
    tokens: list[str] = []
    for t in raw_split:
        canonical = canonicalize_token(t)
        if canonical != t:
            # Alias matched (e.g. "inc." -> "inc")
            tokens.append(canonical)
        else:
            # Strip punctuation from token, preserve alphanumerics
            cleaned = re.sub(r"[^\w]", "", t)
            if cleaned:
                tokens.append(cleaned)
    # No additional canonicalization needed

    # 7. Save raw_tokens
    raw_tokens = list(tokens)

    # Check if the entire input looks like an acronym before designator stripping
    acronym_from_input = normalize_acronym_input(original)

    # 8. Strip legal designators
    core_tokens, removed_designators = strip_designators(
        tokens, strip_prefix=config.normalization.strip_prefix_designators
    )

    # 9. Safety rule: if stripping left fewer than 2 tokens, it was reverted
    if not removed_designators and any(
        canonicalize_token(t) != t or t in _get_designator_set()
        for t in tokens
    ):
        # strip_designators already handles the revert internally
        pass
    if len(core_tokens) < 2 and removed_designators:
        # This shouldn't happen as strip_designators handles it, but safety check
        core_tokens = list(tokens)
        removed_designators = []
        warnings.append("designator_strip_reverted_short_core")

    if len(core_tokens) == 1:
        warnings.append("single_token_core")

    # 10. Extract numeric tokens
    numeric_tokens = _extract_numeric_tokens(core_tokens)

    # 11. Acronym generation
    core_string = " ".join(core_tokens)
    acronym = acronym_from_input or generate_acronym(core_tokens, config.acronym)

    # If core is a single token that looks like an acronym itself
    # (all alpha, length >= min_length, and original was uppercase)
    if acronym is None and len(core_tokens) == 1:
        token = core_tokens[0]
        if (
            token.isalpha()
            and len(token) >= config.acronym.min_length
            and original.strip().replace(".", "").isupper()
        ):
            acronym = token

    if acronym and is_collision(acronym):
        warnings.append("collision_acronym")

    # 12. Generate blocking keys
    keys = _generate_blocking_keys(core_tokens, core_string, acronym)

    # 13. Build meta
    meta = {
        "removed_designators": removed_designators,
        "warnings": warnings,
        "notes": {},
    }

    return NormalizedName(
        original=original,
        normalized_text=normalized_text,
        raw_tokens=raw_tokens,
        core_tokens=core_tokens,
        core_string=core_string,
        acronym=acronym,
        numeric_tokens=numeric_tokens,
        keys=keys,
        meta=meta,
    )


def _extract_numeric_tokens(tokens: list[str]) -> list[str]:
    """Extract numeric content from tokens."""
    numerics: list[str] = []
    for token in tokens:
        if token.isdigit():
            numerics.append(token)
        else:
            # Extract numeric substrings
            nums = re.findall(r"\d+", token)
            numerics.extend(nums)
    return numerics


def _generate_blocking_keys(
    core_tokens: list[str], core_string: str, acronym: str | None
) -> dict[str, str]:
    """Generate blocking keys for candidate retrieval."""
    keys: dict[str, str] = {}

    keys["k_core"] = core_string

    if len(core_tokens) >= 2:
        keys["k_prefix2"] = " ".join(core_tokens[:2])

    if len(core_tokens) >= 3:
        keys["k_prefix3"] = " ".join(core_tokens[:3])

    if acronym:
        keys["k_acronym"] = acronym

    if core_tokens:
        keys["k_first"] = core_tokens[0]

    return keys


def _get_designator_set() -> set[str]:
    from bizmatch.designators import DESIGNATORS
    return DESIGNATORS
