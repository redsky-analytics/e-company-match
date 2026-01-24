"""CSV/JSONL input and output for company name matching."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from bizmatch.types import MatchResult


def read_names(path: str | Path, name_column: str = "name", id_column: str | None = "id") -> list[tuple[int, str]]:
    """Read company names from CSV or JSONL.

    Returns list of (id, name) tuples.
    """
    path = Path(path)

    if path.suffix == ".jsonl":
        return _read_jsonl(path, name_column, id_column)
    else:
        return _read_csv(path, name_column, id_column)


def _read_csv(path: Path, name_column: str, id_column: str | None) -> list[tuple[int, str]]:
    results: list[tuple[int, str]] = []
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader):
            name = row.get(name_column, "").strip()
            if not name:
                continue
            if id_column and id_column in row:
                item_id = int(row[id_column])
            else:
                item_id = i
            results.append((item_id, name))
    return results


def _read_jsonl(path: Path, name_column: str, id_column: str | None) -> list[tuple[int, str]]:
    results: list[tuple[int, str]] = []
    with path.open(encoding="utf-8") as f:
        for i, line in enumerate(f):
            if not line.strip():
                continue
            row = json.loads(line)
            name = row.get(name_column, "").strip()
            if not name:
                continue
            if id_column and id_column in row:
                item_id = int(row[id_column])
            else:
                item_id = i
            results.append((item_id, name))
    return results


def write_results(
    results: list[MatchResult],
    path: str | Path,
    include_debug: bool = False,
) -> None:
    """Write match results to CSV or JSONL."""
    path = Path(path)

    if path.suffix == ".jsonl":
        _write_jsonl(results, path, include_debug)
    else:
        _write_csv(results, path, include_debug)


def _write_csv(results: list[MatchResult], path: Path, include_debug: bool) -> None:
    fieldnames = [
        "a_id", "a_name", "b_id", "b_name", "decision",
        "score", "runner_up_score", "margin", "used_llm", "reasons",
    ]
    if include_debug:
        fieldnames.extend(["warnings", "top_candidates"])

    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in results:
            row = {
                "a_id": r.a_id,
                "a_name": r.a_name,
                "b_id": r.b_id if r.b_id is not None else "",
                "b_name": r.b_name or "",
                "decision": r.decision,
                "score": f"{r.score:.4f}",
                "runner_up_score": f"{r.runner_up_score:.4f}" if r.runner_up_score is not None else "",
                "margin": f"{r.margin:.4f}" if r.margin is not None else "",
                "used_llm": r.used_llm,
                "reasons": "|".join(r.reasons),
            }
            if include_debug:
                row["warnings"] = "|".join(r.debug.get("warnings", []))
                row["top_candidates"] = json.dumps(r.debug.get("top_candidates", []))
            writer.writerow(row)


def _write_jsonl(results: list[MatchResult], path: Path, include_debug: bool) -> None:
    with path.open("w", encoding="utf-8") as f:
        for r in results:
            record = {
                "a_id": r.a_id,
                "a_name": r.a_name,
                "b_id": r.b_id,
                "b_name": r.b_name,
                "decision": r.decision,
                "score": r.score,
                "runner_up_score": r.runner_up_score,
                "margin": r.margin,
                "used_llm": r.used_llm,
                "reasons": r.reasons,
            }
            if include_debug:
                record["debug"] = r.debug
            f.write(json.dumps(record) + "\n")
