"""Tests for acronym handling."""

from cm.acronyms import (
    acronym_relation,
    generate_acronym,
    is_collision,
    normalize_acronym_input,
)
from cm.config import AcronymConfig


def test_generate_acronym():
    tokens = ["international", "business", "machines"]
    result = generate_acronym(tokens)
    assert result == "ibm"


def test_generate_acronym_too_short():
    tokens = ["ab"]
    result = generate_acronym(tokens)
    assert result is None


def test_generate_acronym_min_length():
    config = AcronymConfig(min_length=4)
    tokens = ["a", "b", "c"]
    result = generate_acronym(tokens, config)
    assert result is None


def test_normalize_acronym_ibm():
    assert normalize_acronym_input("I.B.M.") == "ibm"


def test_normalize_acronym_spaced():
    assert normalize_acronym_input("I B M") == "ibm"


def test_normalize_acronym_not_acronym():
    assert normalize_acronym_input("Apple") is None


def test_collision_list():
    assert is_collision("abc")
    assert is_collision("usa")
    assert not is_collision("ibm")


def test_acronym_relation_exact():
    result = acronym_relation("ibm", ["ibm"], "ibm", ["ibm"])
    assert result == "exact"


def test_acronym_relation_initialism():
    result = acronym_relation(
        "ibm", ["ibm"],
        None, ["international", "business", "machines"]
    )
    assert result == "initialism"


def test_acronym_relation_collision():
    result = acronym_relation("abc", ["abc"], "abc", ["abc"])
    assert result == "collision"


def test_acronym_relation_none():
    result = acronym_relation("xyz", ["xyz"], "abc", ["abc"])
    assert result == "none"
