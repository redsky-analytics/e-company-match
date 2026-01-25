"""Manual match storage for the grep UI."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
import json

import structlog


@dataclass
class ManualMatch:
    """A manually created match between A names and a B name."""

    a_names: list[str]  # Multiple A names can map to one B
    b_name: str
    b_id: str | None  # CUP_ID if available
    created_at: str  # ISO timestamp
    notes: str = ""  # Optional user notes


@dataclass
class ManualMatchStore:
    """Persistent storage for manual matches."""

    path: Path
    matches: list[ManualMatch] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.log = structlog.get_logger()
        if isinstance(self.path, str):
            self.path = Path(self.path)

    def load(self) -> None:
        """Load matches from disk."""
        if not self.path.exists():
            self.log.info("manual_matches_file_not_found", path=str(self.path))
            self.matches = []
            return

        try:
            with open(self.path) as f:
                data = json.load(f)

            self.matches = [
                ManualMatch(
                    a_names=m["a_names"],
                    b_name=m["b_name"],
                    b_id=m.get("b_id"),
                    created_at=m["created_at"],
                    notes=m.get("notes", ""),
                )
                for m in data.get("matches", [])
            ]
            self.log.info("manual_matches_loaded", count=len(self.matches))
        except (json.JSONDecodeError, KeyError) as e:
            self.log.error("manual_matches_load_error", error=str(e))
            self.matches = []

    def save(self) -> None:
        """Save matches to disk."""
        self.path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "matches": [
                {
                    "a_names": m.a_names,
                    "b_name": m.b_name,
                    "b_id": m.b_id,
                    "created_at": m.created_at,
                    "notes": m.notes,
                }
                for m in self.matches
            ]
        }

        with open(self.path, "w") as f:
            json.dump(data, f, indent=2)

        self.log.info("manual_matches_saved", count=len(self.matches))

    def add_match(
        self,
        a_names: list[str],
        b_name: str,
        b_id: str | None = None,
        notes: str = "",
    ) -> ManualMatch:
        """Add a new manual match."""
        match = ManualMatch(
            a_names=a_names,
            b_name=b_name,
            b_id=b_id,
            created_at=datetime.now(timezone.utc).isoformat(),
            notes=notes,
        )
        self.matches.append(match)
        self.save()
        self.log.info(
            "manual_match_added",
            a_names=a_names,
            b_name=b_name,
            b_id=b_id,
        )
        return match

    def remove_match(self, index: int) -> bool:
        """Remove a manual match by index."""
        if 0 <= index < len(self.matches):
            removed = self.matches.pop(index)
            self.save()
            self.log.info(
                "manual_match_removed",
                index=index,
                a_names=removed.a_names,
                b_name=removed.b_name,
            )
            return True
        return False

    def get_all(self) -> list[ManualMatch]:
        """Get all manual matches."""
        return self.matches

    def get_a_to_b_map(self) -> dict[str, tuple[str, str | None]]:
        """Get a mapping from A name to (B name, B id) for use in matching."""
        result: dict[str, tuple[str, str | None]] = {}
        for match in self.matches:
            for a_name in match.a_names:
                result[a_name] = (match.b_name, match.b_id)
        return result
