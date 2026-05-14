# Note Taker Skill

`note-taker` is a Codex skill for temporary, session-scoped working notes. It is designed for long or multi-step agent tasks where intermediate facts, decisions, files, and TODOs need to survive across turns or compaction without becoming durable cross-run memory.

The runtime artifact is the skill directory:

```text
skill/
  SKILL.md
  scripts/
    notes.py
```

There is no MCP server, package installation, vector store, or runtime dependency.

## Design

The skill resolves a deterministic temp session from:

1. `NOTE_TAKER_SESSION_ID`, if set.
2. `CODEX_THREAD_ID`, if set.
3. Otherwise it fails loudly and asks for `NOTE_TAKER_SESSION_ID`.

The session key is a hash of:

```text
session identity + workspace root + git branch/ref
```

By default, session files live under:

```text
/tmp/note-taker/v1/sessions/<session-key>/
  MANIFEST.json
  NOTES.md
  TODO.md
```

This gives the intended lifetime:

- same thread, repo, and branch: same temp notes across turns
- new thread: new notes
- new branch/ref: new notes
- missing session identity: no fuzzy reuse

`MANIFEST.json` is script-owned metadata. The model-facing files are:

- `NOTES.md`: mutable working understanding, findings, decisions, relevant files, open questions, and corrected assumptions.
- `TODO.md`: mutable task tracking with current, blocked, and done sections.

## Usage

Run the bundled script directly:

```bash
python skill/scripts/notes.py resume
```

Useful commands:

```bash
python skill/scripts/notes.py init
python skill/scripts/notes.py where
python skill/scripts/notes.py resume
python skill/scripts/notes.py search "query"
python skill/scripts/notes.py gc
```

Use `NOTE_TAKER_ROOT` or `--root` to override the temp base directory.

## Installing As A Codex Skill

Copy `skill/` into your Codex skills directory as `note-taker`. The skill instructions in `skill/SKILL.md` describe when and how the agent should use the bundled script.

## Development

This repo keeps `pyproject.toml` only for development tooling. It is not a Python package and is not intended for PyPI distribution.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install pytest ruff
.venv/bin/python -m pytest
.venv/bin/python -m ruff check .
```
