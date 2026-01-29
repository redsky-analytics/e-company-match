"""Tests for the io module (CSV/JSONL reading and writing)."""

from pathlib import Path
import json
import tempfile

import pytest

from cm.io import read_names, write_results
from cm.types import MatchResult


class TestReadNames:
    """Tests for reading company names from files."""

    def test_read_csv_with_defaults(self, tmp_path: Path):
        csv_file = tmp_path / "names.csv"
        csv_file.write_text("id,name\n1,Apple Inc\n2,Microsoft Corp\n")

        result = read_names(csv_file)

        assert result == [(1, "Apple Inc"), (2, "Microsoft Corp")]

    def test_read_csv_custom_columns(self, tmp_path: Path):
        csv_file = tmp_path / "names.csv"
        csv_file.write_text("company_id,company_name\n10,Google LLC\n20,Meta Inc\n")

        result = read_names(csv_file, name_column="company_name", id_column="company_id")

        assert result == [(10, "Google LLC"), (20, "Meta Inc")]

    def test_read_csv_no_id_column(self, tmp_path: Path):
        csv_file = tmp_path / "names.csv"
        csv_file.write_text("name\nApple Inc\nMicrosoft Corp\n")

        result = read_names(csv_file, id_column=None)

        assert result == [(0, "Apple Inc"), (1, "Microsoft Corp")]

    def test_read_csv_skips_empty_names(self, tmp_path: Path):
        csv_file = tmp_path / "names.csv"
        csv_file.write_text("id,name\n1,Apple Inc\n2,\n3,Google\n")

        result = read_names(csv_file)

        assert result == [(1, "Apple Inc"), (3, "Google")]

    def test_read_csv_strips_whitespace(self, tmp_path: Path):
        csv_file = tmp_path / "names.csv"
        csv_file.write_text("id,name\n1,  Apple Inc  \n2, Microsoft \n")

        result = read_names(csv_file)

        assert result == [(1, "Apple Inc"), (2, "Microsoft")]

    def test_read_jsonl(self, tmp_path: Path):
        jsonl_file = tmp_path / "names.jsonl"
        jsonl_file.write_text(
            '{"id": 1, "name": "Apple Inc"}\n'
            '{"id": 2, "name": "Microsoft Corp"}\n'
        )

        result = read_names(jsonl_file)

        assert result == [(1, "Apple Inc"), (2, "Microsoft Corp")]

    def test_read_jsonl_custom_columns(self, tmp_path: Path):
        jsonl_file = tmp_path / "names.jsonl"
        jsonl_file.write_text(
            '{"company_id": 10, "company_name": "Google LLC"}\n'
            '{"company_id": 20, "company_name": "Meta Inc"}\n'
        )

        result = read_names(jsonl_file, name_column="company_name", id_column="company_id")

        assert result == [(10, "Google LLC"), (20, "Meta Inc")]

    def test_read_jsonl_skips_empty_lines(self, tmp_path: Path):
        jsonl_file = tmp_path / "names.jsonl"
        jsonl_file.write_text(
            '{"id": 1, "name": "Apple Inc"}\n'
            '\n'
            '{"id": 2, "name": "Microsoft Corp"}\n'
        )

        result = read_names(jsonl_file)

        assert result == [(1, "Apple Inc"), (2, "Microsoft Corp")]

    def test_read_jsonl_no_id_uses_index(self, tmp_path: Path):
        jsonl_file = tmp_path / "names.jsonl"
        jsonl_file.write_text(
            '{"name": "Apple Inc"}\n'
            '{"name": "Microsoft Corp"}\n'
        )

        result = read_names(jsonl_file, id_column=None)

        assert result == [(0, "Apple Inc"), (1, "Microsoft Corp")]


class TestWriteResults:
    """Tests for writing match results to files."""

    def test_write_csv_basic(self, tmp_path: Path):
        csv_file = tmp_path / "results.csv"
        results = [
            MatchResult(
                a_id=1, a_name="Apple Inc", b_id=10, b_name="Apple Incorporated",
                decision="MATCH", score=0.95, runner_up_score=0.80, margin=0.15,
                used_llm=False, reasons=["high_score", "token_overlap"],
            ),
        ]

        write_results(results, csv_file)

        content = csv_file.read_text()
        lines = content.strip().split("\n")
        assert len(lines) == 2
        assert "a_id,a_name,b_id,b_name,decision" in lines[0]
        assert "1,Apple Inc,10,Apple Incorporated,MATCH" in lines[1]
        assert "high_score|token_overlap" in lines[1]

    def test_write_csv_no_match(self, tmp_path: Path):
        csv_file = tmp_path / "results.csv"
        results = [
            MatchResult(
                a_id=1, a_name="Unknown Corp", b_id=None, b_name=None,
                decision="NO_MATCH", score=0.0, reasons=["no_candidates"],
            ),
        ]

        write_results(results, csv_file)

        content = csv_file.read_text()
        assert "NO_MATCH" in content
        assert "no_candidates" in content

    def test_write_csv_with_debug(self, tmp_path: Path):
        csv_file = tmp_path / "results.csv"
        results = [
            MatchResult(
                a_id=1, a_name="Apple", b_id=10, b_name="Apple Inc",
                decision="MATCH", score=0.9,
                debug={"warnings": ["short_name"], "top_candidates": [{"id": 10, "score": 0.9}]},
            ),
        ]

        write_results(results, csv_file, include_debug=True)

        content = csv_file.read_text()
        assert "warnings" in content
        assert "short_name" in content
        assert "top_candidates" in content

    def test_write_jsonl_basic(self, tmp_path: Path):
        jsonl_file = tmp_path / "results.jsonl"
        results = [
            MatchResult(
                a_id=1, a_name="Apple Inc", b_id=10, b_name="Apple Incorporated",
                decision="MATCH", score=0.95, runner_up_score=0.80, margin=0.15,
                used_llm=False, reasons=["high_score"],
            ),
        ]

        write_results(results, jsonl_file)

        content = jsonl_file.read_text().strip()
        record = json.loads(content)
        assert record["a_id"] == 1
        assert record["b_id"] == 10
        assert record["decision"] == "MATCH"
        assert record["score"] == 0.95
        assert record["reasons"] == ["high_score"]

    def test_write_jsonl_with_debug(self, tmp_path: Path):
        jsonl_file = tmp_path / "results.jsonl"
        results = [
            MatchResult(
                a_id=1, a_name="Apple", b_id=10, b_name="Apple Inc",
                decision="MATCH", score=0.9,
                debug={"warnings": ["test_warning"], "candidate_count": 5},
            ),
        ]

        write_results(results, jsonl_file, include_debug=True)

        content = jsonl_file.read_text().strip()
        record = json.loads(content)
        assert "debug" in record
        assert record["debug"]["warnings"] == ["test_warning"]
        assert record["debug"]["candidate_count"] == 5

    def test_write_multiple_results(self, tmp_path: Path):
        csv_file = tmp_path / "results.csv"
        results = [
            MatchResult(a_id=1, a_name="A", b_id=10, b_name="A Inc", decision="MATCH", score=0.9),
            MatchResult(a_id=2, a_name="B", b_id=None, b_name=None, decision="NO_MATCH", score=0.0),
            MatchResult(a_id=3, a_name="C", b_id=30, b_name="C Corp", decision="REVIEW", score=0.8),
        ]

        write_results(results, csv_file)

        content = csv_file.read_text()
        lines = content.strip().split("\n")
        assert len(lines) == 4  # header + 3 results
