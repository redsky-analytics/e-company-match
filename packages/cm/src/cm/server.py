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


def create_app(
    top_path: str,
    cup_path: str,
    matches_path: str,
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
        if not q:
            return [NameEntry(**e) for e in b_entries]
        q_lower = q.lower()
        return [NameEntry(**e) for e in b_entries if q_lower in e["name"].lower()]

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
