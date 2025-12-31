"""Filesystem-backed note storage."""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path


class StorageError(Exception):
    """Generic storage-related error."""


class NoteNotFound(StorageError, FileNotFoundError):
    """Raised when a note id is unknown."""

    def __init__(self, note_id: str):
        super().__init__(f"note not found: {note_id}")
        self.note_id = note_id


def _validate_note_id(note_id: str) -> str:
    """Ensure the note id is a UUID string to avoid path traversal."""
    try:
        uuid.UUID(note_id)
    except Exception as exc:  # noqa: BLE001 - propagate as storage error
        raise StorageError(f"invalid note id: {note_id}") from exc
    return note_id


@dataclass
class NoteStorage:
    """Handles writing, reading, updating, and removing note files."""

    notes_dir: Path

    def __post_init__(self) -> None:
        self.notes_dir = Path(self.notes_dir)
        self.notes_dir.mkdir(parents=True, exist_ok=True)

    def write_note(self, note_text: str) -> tuple[str, Path]:
        """Create a new note file, returning (note_id, path)."""
        note_id = str(uuid.uuid4())
        path = self._path_for(note_id)
        self._write_atomic(path, note_text)
        return note_id, path

    def read_note(self, note_id: str) -> str:
        """Read a note by id."""
        note_id = _validate_note_id(note_id)
        path = self._path_for(note_id)
        if not path.exists():
            raise NoteNotFound(note_id)
        return path.read_text(encoding="utf-8")

    def update_note(self, note_id: str, note_text: str) -> None:
        """Overwrite an existing note."""
        note_id = _validate_note_id(note_id)
        path = self._path_for(note_id)
        if not path.exists():
            raise NoteNotFound(note_id)
        self._write_atomic(path, note_text)

    def remove_note(self, note_id: str) -> None:
        """Delete a note file."""
        note_id = _validate_note_id(note_id)
        path = self._path_for(note_id)
        if not path.exists():
            raise NoteNotFound(note_id)
        path.unlink()

    def list_note_ids(self) -> Iterable[str]:
        """List all note ids present on disk."""
        for path in self.notes_dir.glob("*.txt"):
            yield path.stem

    def _path_for(self, note_id: str) -> Path:
        return self.notes_dir / f"{note_id}.txt"

    @staticmethod
    def _write_atomic(path: Path, contents: str) -> None:
        """Write to a temp file then rename for durability."""
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        tmp_path.write_text(contents, encoding="utf-8")
        tmp_path.replace(path)
