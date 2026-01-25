"""FastAPI server for the grep UI."""

from pathlib import Path
from typing import Any

import pandas as pd
import structlog
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from cm.manual_matches import ManualMatchStore

log = structlog.get_logger()


class CreateMatchRequest(BaseModel):
    """Request body for creating a manual match."""

    a_names: list[str]
    b_name: str
    b_id: str | None = None
    notes: str = ""


class MatchResponse(BaseModel):
    """Response for a manual match."""

    a_names: list[str]
    b_name: str
    b_id: str | None
    created_at: str
    notes: str


class NameEntry(BaseModel):
    """A name entry with optional ID."""

    name: str
    id: str | None = None
    match_type: str | None = None  # "CM" for manual, "AM" for automatic


class AutoMatchResponse(BaseModel):
    """Response for automatic matches grouped by B name."""

    b_name: str
    b_id: str | None
    a_names: list[str]
    decision: str
    score: float


def create_app(
    top_path: str,
    cup_path: str,
    matches_path: str,
    results_path: str | None = None,
) -> FastAPI:
    """Create the FastAPI application."""
    app = FastAPI(title="CM Grep UI")

    # Load data at startup
    log.info("server_loading_data", top=top_path, cup=cup_path)
    top_df = pd.read_excel(top_path)
    cup_df = pd.read_excel(cup_path)

    # Extract names
    a_names_list: list[str] = top_df["A"].dropna().tolist()
    b_entries: list[dict[str, Any]] = []
    for idx, row in cup_df.iterrows():
        if pd.notna(row["CUP_NAME"]):
            b_entries.append({
                "name": row["CUP_NAME"],
                "id": str(row["CUP_ID"]) if pd.notna(row.get("CUP_ID")) else None,
            })

    log.info("server_data_loaded", a_count=len(a_names_list), b_count=len(b_entries))

    # Initialize match store
    store = ManualMatchStore(Path(matches_path))
    store.load()

    # Load automatic matches from results file if it exists
    auto_matches: dict[str, AutoMatchResponse] = {}  # b_name -> AutoMatchResponse
    if results_path and Path(results_path).exists():
        log.info("loading_auto_matches", path=results_path)
        results_df = pd.read_excel(results_path)
        # Group by matched_CUP_NAME for MATCH decisions (not MANUAL_MATCH)
        for _, row in results_df.iterrows():
            if row.get("decision") == "MATCH" and pd.notna(row.get("matched_CUP_NAME")):
                b_name = str(row["matched_CUP_NAME"])
                b_id = str(row["matched_CUP_ID"]) if pd.notna(row.get("matched_CUP_ID")) else None
                a_name = str(row["A_name"])
                score = float(row["score"]) if pd.notna(row.get("score")) else 0.0

                if b_name not in auto_matches:
                    auto_matches[b_name] = AutoMatchResponse(
                        b_name=b_name,
                        b_id=b_id,
                        a_names=[],
                        decision="MATCH",
                        score=score,
                    )
                if a_name not in auto_matches[b_name].a_names:
                    auto_matches[b_name].a_names.append(a_name)
        log.info("auto_matches_loaded", count=len(auto_matches))

    # Build sets for quick lookup of which B names have matches
    manual_b_names = {m.b_name for m in store.get_all()}
    auto_b_names = set(auto_matches.keys())

    # Determine UI dist path
    ui_dist_path = Path(__file__).parent.parent.parent / "ui" / "dist"

    @app.get("/api/names/a")
    async def get_a_names(q: str = "") -> list[str]:
        """Get A names, optionally filtered by query."""
        if not q:
            return a_names_list
        q_lower = q.lower()
        return [n for n in a_names_list if q_lower in n.lower()]

    @app.get("/api/names/b")
    async def get_b_names(q: str = "") -> list[NameEntry]:
        """Get B names with IDs, optionally filtered by query."""
        # Refresh manual B names set (in case matches were added/removed)
        current_manual_b = {m.b_name for m in store.get_all()}

        def make_entry(e: dict[str, Any]) -> NameEntry:
            name = e["name"]
            match_type = None
            if name in current_manual_b:
                match_type = "CM"  # Custom/Manual match
            elif name in auto_b_names:
                match_type = "AM"  # Automatic match
            return NameEntry(name=name, id=e["id"], match_type=match_type)

        if not q:
            return [make_entry(e) for e in b_entries]
        q_lower = q.lower()
        return [make_entry(e) for e in b_entries if q_lower in e["name"].lower()]

    @app.get("/api/auto-matches")
    async def get_auto_matches() -> list[AutoMatchResponse]:
        """Get all automatic matches from results file."""
        return list(auto_matches.values())

    @app.get("/api/auto-matches/{b_name}")
    async def get_auto_match(b_name: str) -> AutoMatchResponse | None:
        """Get automatic match for a specific B name."""
        return auto_matches.get(b_name)

    @app.get("/api/matches")
    async def get_matches() -> list[MatchResponse]:
        """Get all manual matches."""
        return [
            MatchResponse(
                a_names=m.a_names,
                b_name=m.b_name,
                b_id=m.b_id,
                created_at=m.created_at,
                notes=m.notes,
            )
            for m in store.get_all()
        ]

    @app.post("/api/matches")
    async def create_match(req: CreateMatchRequest) -> MatchResponse:
        """Create a new manual match."""
        if not req.a_names:
            raise HTTPException(status_code=400, detail="a_names cannot be empty")
        if not req.b_name:
            raise HTTPException(status_code=400, detail="b_name cannot be empty")

        match = store.add_match(
            a_names=req.a_names,
            b_name=req.b_name,
            b_id=req.b_id,
            notes=req.notes,
        )
        return MatchResponse(
            a_names=match.a_names,
            b_name=match.b_name,
            b_id=match.b_id,
            created_at=match.created_at,
            notes=match.notes,
        )

    @app.delete("/api/matches/{index}")
    async def delete_match(index: int) -> dict[str, bool]:
        """Delete a manual match by index."""
        if store.remove_match(index):
            return {"success": True}
        raise HTTPException(status_code=404, detail="Match not found")

    @app.get("/api/download/{filename}")
    async def download_file(filename: str) -> FileResponse:
        """Download a file from the results directory."""
        if not results_path:
            raise HTTPException(status_code=400, detail="No results path configured")
        file_path = Path(results_path).parent / filename
        if not file_path.exists():
            raise HTTPException(status_code=404, detail="File not found")
        return FileResponse(
            file_path,
            filename=filename,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    @app.post("/api/finalize")
    async def finalize_matches() -> dict[str, Any]:
        """Finalize matching results by applying manual matches."""
        if not results_path or not Path(results_path).exists():
            raise HTTPException(status_code=400, detail="No results file available")

        # Load automatic matching results
        results_df = pd.read_excel(results_path)

        # Build a mapping from A name to manual match info
        manual_matches = store.get_all()
        a_to_manual: dict[str, tuple[str, str | None]] = {}
        for match in manual_matches:
            for a_name in match.a_names:
                a_to_manual[a_name] = (match.b_name, match.b_id)

        # Apply manual matches to results
        updated_count = 0
        for idx, row in results_df.iterrows():
            a_name = row["A_name"]
            if a_name in a_to_manual:
                b_name, b_id = a_to_manual[a_name]
                results_df.at[idx, "matched_CUP_NAME"] = b_name
                results_df.at[idx, "matched_CUP_ID"] = b_id
                results_df.at[idx, "decision"] = "MANUAL_MATCH"
                results_df.at[idx, "score"] = 1.0
                results_df.at[idx, "runner_up_score"] = None
                results_df.at[idx, "reasons"] = "manual_match"
                updated_count += 1

        # Save finalized results
        output_path = Path(results_path).parent / "finalized_matching_results.xlsx"
        results_df.to_excel(output_path, index=False)

        # Build mapping from finalized results: A_name -> (matched_CUP_NAME, matched_CUP_ID)
        a_to_cup: dict[str, tuple[str | None, str | None]] = {}
        cup_to_a: dict[str, list[str]] = {}
        for _, row in results_df.iterrows():
            a_name = row["A_name"]
            cup_name = row.get("matched_CUP_NAME")
            cup_id = row.get("matched_CUP_ID")
            if pd.notna(cup_name):
                a_to_cup[a_name] = (str(cup_name), str(cup_id) if pd.notna(cup_id) else None)
                if cup_name not in cup_to_a:
                    cup_to_a[cup_name] = []
                cup_to_a[cup_name].append(a_name)

        # Generate top_2000_unmapped_matched.xlsx
        top_matched_df = top_df.copy()
        top_matched_df["matched_CUP_NAME"] = top_matched_df["A"].apply(
            lambda x: a_to_cup.get(x, (None, None))[0]
        )
        top_matched_df["matched_CUP_ID"] = top_matched_df["A"].apply(
            lambda x: a_to_cup.get(x, (None, None))[1]
        )
        top_matched_path = Path(results_path).parent / "top_2000_unmapped_matched.xlsx"
        top_matched_df.to_excel(top_matched_path, index=False)

        # Generate CUP_raw_data_matched.xlsx
        cup_matched_df = cup_df.copy()
        cup_matched_df["matched_A_names"] = cup_matched_df["CUP_NAME"].apply(
            lambda x: "; ".join(cup_to_a.get(x, [])) if pd.notna(x) else ""
        )
        cup_matched_path = Path(results_path).parent / "CUP_raw_data_matched.xlsx"
        cup_matched_df.to_excel(cup_matched_path, index=False)

        log.info(
            "finalize_complete",
            output=str(output_path),
            top_matched=str(top_matched_path),
            cup_matched=str(cup_matched_path),
            total_rows=len(results_df),
            manual_matches_applied=updated_count,
        )

        return {
            "success": True,
            "output": str(output_path),
            "top_matched": str(top_matched_path),
            "cup_matched": str(cup_matched_path),
            "total_rows": len(results_df),
            "manual_matches_applied": updated_count,
        }

    # Serve static files if UI is built
    if ui_dist_path.exists():
        # Mount assets directory
        assets_path = ui_dist_path / "assets"
        if assets_path.exists():
            app.mount("/assets", StaticFiles(directory=str(assets_path)), name="assets")

        @app.get("/")
        async def serve_index() -> FileResponse:
            """Serve the React app."""
            return FileResponse(ui_dist_path / "index.html")

        # Catch-all for SPA routing
        @app.get("/{path:path}")
        async def serve_spa(path: str) -> FileResponse:
            """Serve the React app for all other paths."""
            file_path = ui_dist_path / path
            if file_path.exists() and file_path.is_file():
                return FileResponse(file_path)
            return FileResponse(ui_dist_path / "index.html")
    else:
        @app.get("/")
        async def no_ui() -> dict[str, str]:
            """Return message when UI is not built."""
            return {
                "error": "UI not built",
                "message": "Run 'cd packages/cm/ui && npm install && npm run build' to build the UI",
            }

    return app
