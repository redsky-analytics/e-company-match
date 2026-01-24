"""Tests for the blocking index and candidate retrieval."""

from cm.config import CandidateConfig
from cm.index import BlockingIndex
from cm.normalize import normalize


def test_build_and_retrieve():
    index = BlockingIndex()
    b_names = [normalize(n) for n in ["Apple Inc", "Microsoft Corp", "Google LLC"]]
    index.build(b_names)

    a = normalize("Apple Inc.")
    candidates = index.retrieve_candidates(a)
    b_ids = {c.b_id for c in candidates}
    assert 0 in b_ids  # Apple Inc is at index 0


def test_prefix_blocking():
    index = BlockingIndex()
    b_names = [
        normalize(n) for n in [
            "General Electric Company",
            "General Motors Corp",
            "Google LLC",
        ]
    ]
    index.build(b_names)

    a = normalize("General Electric")
    candidates = index.retrieve_candidates(a)
    b_ids = {c.b_id for c in candidates}
    assert 0 in b_ids  # GE matches on prefix


def test_candidate_cap():
    config = CandidateConfig(max_candidates_total=2)
    index = BlockingIndex(config)
    b_names = [normalize(f"Test Company {i}") for i in range(100)]
    index.build(b_names)

    a = normalize("Test Company")
    candidates = index.retrieve_candidates(a)
    assert len(candidates) <= 2


def test_source_tracking():
    index = BlockingIndex()
    b_names = [normalize("Apple Inc")]
    index.build(b_names)

    a = normalize("Apple Inc.")
    candidates = index.retrieve_candidates(a)
    assert len(candidates) > 0
    assert len(candidates[0].sources) > 0


def test_no_candidates_found():
    index = BlockingIndex()
    b_names = [normalize("Apple Inc")]
    index.build(b_names)

    a = normalize("Zzzzz Unique Name")
    candidates = index.retrieve_candidates(a)
    # May or may not find candidates depending on k_first
    # With k_first disabled (default), should find none
    assert len(candidates) == 0


def test_acronym_blocking():
    index = BlockingIndex()
    b_names = [normalize("International Business Machines Corp")]
    index.build(b_names)

    a = normalize("IBM")
    candidates = index.retrieve_candidates(a)
    # The acronym "ibm" should match
    b_ids = {c.b_id for c in candidates}
    assert 0 in b_ids


def test_embedding_candidates_merged():
    index = BlockingIndex()
    b_names = [normalize(n) for n in ["Alpha", "Beta", "Gamma"]]
    index.build(b_names)

    a = normalize("Delta")
    # Provide embedding candidates
    candidates = index.retrieve_candidates(a, embedding_candidates=[1, 2])
    b_ids = {c.b_id for c in candidates}
    assert 1 in b_ids
    assert 2 in b_ids
