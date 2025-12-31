# Example Agent Instructions For Note Taking
> The models are not really able to properly reason about when they should take notes as a tool call since they don't see the tool as a direct contributor towards solving their current task. This example instruction file shows how you can get the model to reliably take notes while executing tasks.

## Notes MCP = Model Working Notes (anti-context-loss)

When `note-taker-mcp.write_note`, `note-taker-mcp.search_notes`, `note-taker-mcp.update_note`, and `note-taker-mcp.delete_note` are available, treat them as a model-owned
working notebook to prevent loss of important details due to long context, compaction, or task length.

These notes are NOT user-preferences storage. They are concise, task-relevant working memory.

### When to take working notes (write during work, not just at the end)
Write a note whenever any of the following occurs:
- You introduce a non-trivial assumption, invariant, or constraint that future steps depend on.
- You derive an intermediate result (numbers, mappings, decisions, file paths, commands, API shapes).
- You identify a key uncertainty / hypothesis to verify later.
- You plan a multi-step approach where later steps depend on earlier specifics.
- You are about to traverse many files, apply multiple edits, or run a long investigation.

### When to read notes
- At the start of each user request: `note-taker-mcp.search_notes` using the main entities/goals.
- During long tasks: re-read notes at natural phase boundaries (after investigation, before edits, before final response).
- If you feel uncertain about a previously derived detail, read notes rather than re-deriving from memory.

### What to write (allowed content)
Write ONLY compact, externally-verifiable working memory, such as:
- Key facts discovered (with minimal pointers like filenames, function names, identifiers)
- Hypothesis on different solutions to a problem or sub-problem
- Decisions taken + short rationale
- Intermediate outputs (e.g., “decided X because Y”, “computed Z=…”, “API expects fields A/B/C”)
- TODOs / next checks
- Reusable snippets (commands, paths), kept short

DO NOT write hidden chain-of-thought, extended deliberation, or private reasoning transcripts.

### Format (keep it compact)
Prefer a single note per phase, 5–12 bullets, under ~1500 characters:

- Goal:
- Working facts:
- Assumptions:
- Decisions:
- Open questions:
- Next steps:

### Tagging
Use tags to enable retrieval across long runs:
- tags: ["worknote", "<project_or_repo>", "<topic>"]

### Retrieval-first discipline (to create payoff)
If you wrote a working note earlier in the same task, re-read it before continuing work.
Use the notes as the source of truth for intermediate results that might get diluted.

### Avoid spam
- Do not write notes for trivial, single-step questions.
- If nothing new was learned or decided in a phase, skip writing.
