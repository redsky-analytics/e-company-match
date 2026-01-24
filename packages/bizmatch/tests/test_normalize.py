"""Tests for the normalization pipeline."""

from bizmatch.config import MatchConfig
from bizmatch.normalize import normalize


def test_basic_normalization():
    result = normalize("Apple Inc.")
    assert result.original == "Apple Inc."
    assert "apple" in result.core_tokens
    # Safety rule: stripping "inc" would leave < 2 tokens, so it stays
    assert result.core_string == "apple inc"


def test_unicode_normalization():
    # NFKC normalization
    result = normalize("Ｆｕｌｌｗｉｄｔｈ Corp")
    assert "fullwidth" in result.core_tokens


def test_casefold():
    result = normalize("MICROSOFT Corporation")
    assert "microsoft" in result.core_tokens


def test_ampersand_replacement():
    result = normalize("Johnson & Johnson")
    assert "johnson" in result.core_tokens
    assert "and" in result.core_tokens


def test_plus_replacement():
    result = normalize("A + B Technologies")
    assert "and" in result.core_tokens


def test_punctuation_removal():
    result = normalize("Procter & Gamble, Inc.")
    assert "procter" in result.core_tokens
    assert "gamble" in result.core_tokens


def test_designator_stripping():
    result = normalize("General Electric Corp.")
    assert "corp" not in result.core_tokens
    assert "general" in result.core_tokens
    assert "electric" in result.core_tokens
    assert "corp" in result.meta["removed_designators"]


def test_designator_safety_short_core():
    # Should NOT strip if it would leave < 2 tokens
    result = normalize("LLC Corp")
    # "llc" is a designator, "corp" is a designator
    # Stripping both would leave 0 tokens, so should revert
    assert len(result.core_tokens) >= 1


def test_single_word_company():
    result = normalize("Google")
    assert result.core_tokens == ["google"]
    assert "single_token_core" in result.meta["warnings"]


def test_numeric_extraction():
    result = normalize("3M Company")
    assert "3" in result.numeric_tokens


def test_numeric_standalone():
    result = normalize("Company 2023")
    assert "2023" in result.numeric_tokens


def test_acronym_generation():
    result = normalize("International Business Machines")
    assert result.acronym == "ibm"


def test_acronym_too_short():
    result = normalize("Big Co")
    # Only 1 core token after stripping "co" -> no acronym from core
    # But "big co" without stripping: "big" is 1 token core
    # Actually "co" is a designator, so core = ["big"] -> single token, no acronym


def test_acronym_input_normalization():
    result = normalize("I.B.M.")
    assert result.acronym == "ibm"


def test_blocking_keys_generated():
    result = normalize("General Electric Company")
    assert "k_core" in result.keys
    assert "k_prefix2" in result.keys
    assert result.keys["k_core"] == "general electric"


def test_blocking_keys_prefix():
    result = normalize("The Goldman Sachs Group Inc")
    assert "k_prefix2" in result.keys


def test_alias_canonicalization():
    result = normalize("Acme Widget Inc.")
    # "inc." should be canonicalized to "inc" then stripped (enough tokens)
    assert "inc" not in result.core_tokens
    assert "acme" in result.core_tokens
    assert "widget" in result.core_tokens


def test_multiple_designators():
    result = normalize("Foo Bar Ltd Corp")
    assert "foo" in result.core_tokens
    assert "bar" in result.core_tokens
    assert "ltd" not in result.core_tokens
    assert "corp" not in result.core_tokens


def test_preserves_digits_in_name():
    result = normalize("7-Eleven Inc")
    assert "7" in result.core_tokens or any("7" in t for t in result.core_tokens)


def test_config_no_plus_to_and():
    config = MatchConfig()
    config.normalization.plus_to_and = False
    result = normalize("A + B", config)
    # "+" should become space (punctuation removal) but not "and"
    assert "and" not in result.core_tokens
