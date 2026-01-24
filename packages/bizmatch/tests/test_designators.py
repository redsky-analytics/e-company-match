"""Tests for designator handling."""

from bizmatch.designators import canonicalize_token, is_designator, strip_designators


def test_common_designators():
    assert is_designator("inc")
    assert is_designator("corp")
    assert is_designator("ltd")
    assert is_designator("llc")
    assert is_designator("gmbh")


def test_not_designator():
    assert not is_designator("apple")
    assert not is_designator("general")


def test_canonicalize_inc_dot():
    assert canonicalize_token("inc.") == "inc"


def test_canonicalize_llc_dots():
    assert canonicalize_token("l.l.c") == "llc"


def test_canonicalize_unknown():
    assert canonicalize_token("apple") == "apple"


def test_strip_suffix_designators():
    # Safety rule: stripping "inc" leaves only 1 token, so it's reverted
    tokens = ["apple", "inc"]
    core, removed = strip_designators(tokens)
    assert core == ["apple", "inc"]
    assert removed == []


def test_strip_suffix_when_enough_tokens():
    tokens = ["apple", "computer", "inc"]
    core, removed = strip_designators(tokens)
    assert core == ["apple", "computer"]
    assert removed == ["inc"]


def test_strip_multiple_suffix():
    tokens = ["foo", "bar", "ltd", "corp"]
    core, removed = strip_designators(tokens)
    assert core == ["foo", "bar"]
    assert "ltd" in removed
    assert "corp" in removed


def test_strip_safety_short_core():
    # If stripping leaves < 2 tokens, revert
    tokens = ["inc", "corp"]
    core, removed = strip_designators(tokens)
    assert core == ["inc", "corp"]
    assert removed == []


def test_no_prefix_strip_by_default():
    tokens = ["ltd", "foo", "bar"]
    core, removed = strip_designators(tokens)
    # "ltd" is at the start, but prefix stripping is off
    assert "ltd" in core


def test_prefix_strip_when_enabled():
    tokens = ["ltd", "foo", "bar"]
    core, removed = strip_designators(tokens, strip_prefix=True)
    assert "ltd" not in core
    assert "ltd" in removed


def test_middle_designator_not_stripped():
    tokens = ["foo", "inc", "bar"]
    core, removed = strip_designators(tokens)
    # "inc" is in the middle, not a suffix
    assert "inc" in core
