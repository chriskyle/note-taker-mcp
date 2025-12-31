# Notes MCP

The goal of the notes mcp server is to allow for LLMs to write and read small chunks of information that they think may be important to reference later.

# Design

- The notes will be stored as filestore files with a unique uuid for each file.
- A summary of the note (or details the model provides on when it would want to use that note again) will be persisted to a local vector store along with a metadata field on the entry containing the uuid to reference back to the file.
- The vector store is a local Chroma instance backed by an on-device embedding function, persisted under `.notes/chroma/`.

The system is designed with four core actions to interact with this system

## Actions

### Write Note

Description: This should create a new note, persist it to disk, and add an entry into the Vector Store.

Args:
- note: str - the note to persist to disk
- when_to_use - a summary of the note and when the model would want to use this note
- tags: list[str] (optional) - metadata tags to aid filtered search

### Search Notes

Description: Returns up to five notes matching the query, optionally filtered by tags and score threshold.

Args:
- query: str - the search query
- tags: list[str] (optional) - only return notes that share at least one of these tags
- score_threshold: float (optional, default 0.75) - minimum similarity score required
- k: int (optional, default 5) - max results to return

Return:
- results: list of objects each containing `note`, `note_id`, `score`, `when_to_use`, and `tags`

### Remove Note

Description: Deletes a note from filestore & vectore store

Args:
- note_id: str - the id of the note to delete

### Update Note

Description: Updates an existing note. Will overwrite the entire note with the new content provided, is not diff based

Args:
- note_id: str - the id of the note to update
- note: str - the new note content to overwrite the old note

# Running the server

> TODO: Add `uvx note-taker-mcp` support.

Requirements: Python 3.10+, [`uv`](https://github.com/astral-sh/uv), and the `fastmcp`/`chromadb` dependencies installed via `uv sync`.

Quick start:

``` 
uv sync
uv run notes-mcp
```

By default, each server process creates its own session-scoped data root under `/tmp/notes-<session-id>/`, with note bodies in `notes/` and the vector index in `chroma/`. When the server shuts down, this temp directory is deleted. Set `NOTES_MCP_DATA_DIR=/custom/path` (or pass `data_dir` to `build_server`) to use a persistent location instead.

# Getting the model to reliably take notes

Reference [example.AGENTS.md](./example.AGENTS.md)

# Development notes

- Entry point: `notes_mcp/server.py` (script name: `notes-mcp`).
- Storage layer: `notes_mcp/storage.py` writes UTF-8 note files keyed by UUID.
- Vector index: `notes_mcp/index.py` uses Chroma’s persistent client and default local embedding function.
- Tests: `uv run python -m pytest`.

The server runs over stdio via `uv run notes-mcp` and registers four MCP tools: `write_note`, `search_notes`, `update_note`, and `remove_note`.
