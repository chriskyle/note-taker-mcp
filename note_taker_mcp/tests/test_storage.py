from pathlib import Path

import pytest

from note_taker_mcp.storage import NoteNotFound, NoteStorage


def test_write_read_update_remove(tmp_path: Path) -> None:
    storage = NoteStorage(notes_dir=tmp_path / "notes")

    note_id, path = storage.write_note("hello")
    assert path.exists()

    assert storage.read_note(note_id) == "hello"

    storage.update_note(note_id, "updated")
    assert storage.read_note(note_id) == "updated"

    storage.remove_note(note_id)
    with pytest.raises(NoteNotFound):
        storage.read_note(note_id)
