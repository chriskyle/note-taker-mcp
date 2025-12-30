import pytest
from pathlib import Path

chromadb = pytest.importorskip("chromadb")

from notes_mcp.index import NotesIndex  # noqa: E402  - chroma must import first


def test_index_add_and_search(tmp_path: Path) -> None:
    index = NotesIndex(chroma_path=tmp_path / "chroma")
    index.add_entry(note_id="fruit", when_to_use="remember apples and oranges", path="path1", tags=["food"])
    index.add_entry(note_id="code", when_to_use="write python code snippets", path="path2", tags=["dev"])

    hits = index.search(query="apples", k=1)
    assert hits, "expected at least one search hit"
    assert hits[0].note_id == "fruit"
    assert hits[0].tags == ["food"]


def test_search_tag_filter_and_threshold(tmp_path: Path) -> None:
    index = NotesIndex(chroma_path=tmp_path / "chroma2")
    index.add_entry(note_id="frontend", when_to_use="build ui with react", path="path1", tags=["frontend"])
    index.add_entry(note_id="backend", when_to_use="write api with fastapi", path="path2", tags=["backend"])

    # Tag filter should return only matching tag
    hits = index.search(query="build", tags=["frontend"], k=5)
    assert hits and hits[0].note_id == "frontend"
    assert all("frontend" in hit.tags for hit in hits)

    # Score threshold too high should yield empty
    hits = index.search(query="irrelevant", tags=["frontend"], k=5, score_threshold=0.99)
    assert hits == []
