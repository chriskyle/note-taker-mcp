"""Stdio MCP server for note storage and retrieval."""

from __future__ import annotations

import asyncio
import secrets
import inspect
import logging
import os
import shutil
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from .index import NotesIndex
from .storage import NoteNotFound, NoteStorage

try:  # pragma: no cover - import resolution depends on installed package name
    from fastmcp import FastMCP  # type: ignore
except ImportError:  # pragma: no cover
    try:
        from mcp.server.fastmcp import FastMCP  # type: ignore
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "FastMCP is required; install the `fastmcp` or `mcp` package."
        ) from exc


LOG = logging.getLogger("notes_mcp.server")


def _resolve_data_root(session_id: str, data_dir: Optional[Path]) -> tuple[Path, Optional[Path]]:
    """Pick a data root for this server instance and note whether it should be cleaned up."""
    env = os.getenv("NOTES_MCP_DATA_DIR")
    if data_dir:
        root = Path(data_dir).expanduser()
        cleanup_root: Optional[Path] = None
    elif env:
        root = Path(env).expanduser()
        cleanup_root = None
    else:
        root = Path("/tmp") / f"notes-{session_id}"
        cleanup_root = root

    root.mkdir(parents=True, exist_ok=True)
    return root, cleanup_root


def default_data_dir() -> Path:
    session_id = secrets.token_hex(8)
    data_dir, _ = _resolve_data_root(session_id=session_id, data_dir=None)
    return data_dir


def build_server(
    data_dir: Optional[Path] = None,
    collection_name: str = "notes",
) -> FastMCP:
    """Create and configure the FastMCP server instance."""
    session_id = secrets.token_hex(8)
    storage: Optional[NoteStorage] = None
    index: Optional[NotesIndex] = None
    cleanup_root: Optional[Path] = None

    def _ensure_ready() -> tuple[NoteStorage, NotesIndex]:
        if storage is None or index is None:
            raise RuntimeError("notes-mcp server not initialized yet")
        return storage, index

    def _bootstrap_without_lifespan() -> None:
        nonlocal storage, index, cleanup_root
        data_root, cleanup_root = _resolve_data_root(session_id=session_id, data_dir=data_dir)
        notes_dir = data_root / "notes"
        chroma_dir = data_root / "chroma"
        storage = NoteStorage(notes_dir=notes_dir)
        index = NotesIndex(chroma_path=chroma_dir, collection_name=collection_name)
        if cleanup_root:
            LOG.warning(
                "FastMCP lifespan hooks unavailable; temporary data dir %s will not auto-clean.",
                cleanup_root,
            )

    @asynccontextmanager
    async def lifespan(_: FastMCP):
        nonlocal storage, index, cleanup_root
        data_root, cleanup_root = _resolve_data_root(session_id=session_id, data_dir=data_dir)
        notes_dir = data_root / "notes"
        chroma_dir = data_root / "chroma"
        storage = NoteStorage(notes_dir=notes_dir)
        index = NotesIndex(chroma_path=chroma_dir, collection_name=collection_name)
        LOG.info("notes-mcp session %s using data dir %s", session_id, data_root)
        try:
            yield
        finally:
            if cleanup_root and cleanup_root.exists():
                try:
                    shutil.rmtree(cleanup_root)
                    LOG.info("Cleaned temporary notes data dir %s", cleanup_root)
                except Exception:
                    LOG.warning("Failed to clean temporary data dir %s", cleanup_root, exc_info=True)

    try:
        mcp = FastMCP("notes-mcp", lifespan=lifespan)
    except TypeError:
        _bootstrap_without_lifespan()
        mcp = FastMCP("notes-mcp")

    @mcp.tool(description="Create a new note and index its summary for retrieval.")
    def write_note(note: str, when_to_use: str, tags: Optional[list[str]] = None) -> dict:
        storage_obj, index_obj = _ensure_ready()
        note_id, path = storage_obj.write_note(note_text=note)
        index_obj.add_entry(note_id=note_id, when_to_use=when_to_use, path=str(path), tags=tags)
        return {"note_id": note_id}

    @mcp.tool(description="Search for notes by query with optional tag filtering.")
    def search_notes(
        query: str,
        tags: Optional[list[str]] = None,
        score_threshold: float = 0.75,
        k: int = 5,
    ) -> dict:
        storage_obj, index_obj = _ensure_ready()
        hits = index_obj.search(query=query, k=k, tags=tags, score_threshold=score_threshold)
        results = []
        for hit in hits:
            try:
                note_text = storage_obj.read_note(note_id=hit.note_id)
            except NoteNotFound:
                LOG.warning("Indexed note missing on disk: %s", hit.note_id)
                continue
            results.append(
                {
                    "note_id": hit.note_id,
                    "note": note_text,
                    "score": hit.score,
                    "when_to_use": hit.when_to_use,
                    "tags": hit.tags or [],
                }
            )
        if not results:
            raise ValueError("no matching notes found")
        return {"results": results}

    @mcp.tool(description="Overwrite an existing note by id.")
    def update_note(note_id: str, note: str) -> dict:
        storage_obj, _ = _ensure_ready()
        try:
            storage_obj.update_note(note_id=note_id, note_text=note)
        except NoteNotFound:
            raise
        return {"note_id": note_id}

    @mcp.tool(description="Remove a note and its index entry by id.")
    def remove_note(note_id: str) -> dict:
        storage_obj, index_obj = _ensure_ready()
        try:
            storage_obj.remove_note(note_id=note_id)
        except NoteNotFound:
            raise
        index_obj.remove_entry(note_id=note_id)
        return {"note_id": note_id}

    return mcp


def _run_server(server: FastMCP) -> None:
    """Run the server using whichever run method FastMCP exposes."""
    run_callable = getattr(server, "run_stdio", None) or getattr(server, "run", None)
    if run_callable is None:
        raise RuntimeError("FastMCP server missing run/run_stdio method")

    if inspect.iscoroutinefunction(run_callable):
        asyncio.run(run_callable())  # type: ignore[arg-type]
    else:
        run_callable()


def main(argv: Optional[list[str]] = None) -> int:
    argv = list(argv) if argv is not None else sys.argv[1:]
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    server = build_server()
    if argv and argv[0] == "--check":
        LOG.info("notes-mcp server wiring OK (dry run)")
        return 0
    LOG.info("Starting notes-mcp server over stdio...")
    _run_server(server)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
