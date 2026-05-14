---
name: note-taker
description: Use for multi-step Codex tasks that need temporary, session-scoped working notes across turns or compaction. Maintains mutable NOTES.md and TODO.md files under a strict temp-session directory resolved from NOTE_TAKER_SESSION_ID or CODEX_THREAD_ID.
metadata:
  short-description: Maintain temporary working notes
---

# Note Taker

Use this skill when a task has enough moving parts that losing intermediate facts, decisions, files, or TODOs would make later steps less reliable.

The bundled script is `scripts/notes.py`, relative to this `SKILL.md`. Run it with Python 3.

## Workflow

1. At the start of a multi-step task, run:

   ```bash
   python <skill-dir>/scripts/notes.py resume
   ```

2. Use the printed paths for the current temp-session files:

   - `NOTES.md`: mutable working understanding, findings, decisions, relevant files, open questions, and corrected assumptions.
   - `TODO.md`: mutable task tracking with current, blocked, and done sections.

3. During work, edit `NOTES.md` and `TODO.md` directly when the task state changes. Keep both files compact and accurate. Replace stale notes instead of accumulating contradictions.

4. After compaction, a long investigation, or before risky edits, run `resume` again and/or use `rg` over the session files.

5. Do not store hidden reasoning transcripts, user preferences, secrets, or unrelated durable memory. Store only externally useful working context for the current task/session.

## Commands

```bash
python <skill-dir>/scripts/notes.py init
python <skill-dir>/scripts/notes.py where
python <skill-dir>/scripts/notes.py resume
python <skill-dir>/scripts/notes.py search "query"
python <skill-dir>/scripts/notes.py gc
```

Session resolution is strict. The script uses `NOTE_TAKER_SESSION_ID` first, then `CODEX_THREAD_ID`. If neither exists, set `NOTE_TAKER_SESSION_ID` before using the skill.
