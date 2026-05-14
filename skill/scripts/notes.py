#!/usr/bin/env python3
"""Session-scoped temporary working notes for agents.

This script is intentionally stdlib-only. It resolves a deterministic temp
session from an explicit agent/session identity plus the current repo/ref, then
creates and reports two mutable Markdown files: NOTES.md and TODO.md.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SESSION_VERSION = 1
SESSION_ENV_VARS = ("NOTE_TAKER_SESSION_ID", "CODEX_THREAD_ID")
DEFAULT_TTL_HOURS = 24
NOTES_TEMPLATE = """# Notes

## Current Understanding

## Decisions

## Findings

## Relevant Files

## Open Questions

## Corrected Assumptions
"""
TODO_TEMPLATE = """# TODO

## Current

## Blocked

## Done
"""


class SessionIdentityError(RuntimeError):
    """Raised when no strict session identity is available."""


class SessionStateError(RuntimeError):
    """Raised when an existing session directory is inconsistent."""


@dataclass(frozen=True)
class SessionScope:
    identity_source: str
    identity_value: str
    workspace_root: Path
    git_ref: str

    def payload(self) -> dict[str, str]:
        return {
            "version": str(SESSION_VERSION),
            "identity_source": self.identity_source,
            "identity_value": self.identity_value,
            "workspace_root": str(self.workspace_root),
            "git_ref": self.git_ref,
        }

    @property
    def key(self) -> str:
        encoded = json.dumps(self.payload(), sort_keys=True).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()[:24]

    @property
    def identity_fingerprint(self) -> str:
        return hashlib.sha256(self.identity_value.encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True)
class Session:
    scope: SessionScope
    base_dir: Path

    @property
    def path(self) -> Path:
        return self.base_dir / "sessions" / self.scope.key

    @property
    def manifest_path(self) -> Path:
        return self.path / "MANIFEST.json"

    @property
    def notes_path(self) -> Path:
        return self.path / "NOTES.md"

    @property
    def todo_path(self) -> Path:
        return self.path / "TODO.md"


def resolve_session(
    *,
    cwd: Path | str | None = None,
    env: Mapping[str, str] | None = None,
    base_dir: Path | str | None = None,
) -> Session:
    """Resolve the deterministic session path without creating files."""
    env_map = os.environ if env is None else env
    cwd_path = Path.cwd() if cwd is None else Path(cwd)
    cwd_path = cwd_path.expanduser().resolve()
    identity_source, identity_value = _resolve_identity(env_map)
    workspace_root = _resolve_workspace_root(cwd_path)
    git_ref = _resolve_git_ref(workspace_root)
    scope = SessionScope(
        identity_source=identity_source,
        identity_value=identity_value,
        workspace_root=workspace_root,
        git_ref=git_ref,
    )
    return Session(scope=scope, base_dir=_resolve_base_dir(env_map, base_dir))


def ensure_session(
    *,
    cwd: Path | str | None = None,
    env: Mapping[str, str] | None = None,
    base_dir: Path | str | None = None,
    now: dt.datetime | None = None,
) -> Session:
    """Create or validate the session directory and default note files."""
    session = resolve_session(cwd=cwd, env=env, base_dir=base_dir)
    timestamp = _format_timestamp(now or _now())
    session.path.mkdir(parents=True, exist_ok=True)

    existing = _load_manifest(session.manifest_path)
    if existing is not None:
        _validate_manifest(session, existing)

    _write_if_missing(session.notes_path, NOTES_TEMPLATE)
    _write_if_missing(session.todo_path, TODO_TEMPLATE)
    manifest = _build_manifest(session, existing, timestamp)
    _write_atomic(
        session.manifest_path,
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
    )
    return session


def format_resume(session: Session, *, max_chars: int = 24_000) -> str:
    """Return a bounded rehydration view of the current session."""
    lines = [
        f"Session: {session.path}",
        f"Workspace: {session.scope.workspace_root}",
        f"Git ref: {session.scope.git_ref}",
        "Files:",
        f"- NOTES.md: {session.notes_path}",
        f"- TODO.md: {session.todo_path}",
        "",
        "## TODO.md",
        _bounded_file_text(session.todo_path, max_chars=max_chars),
        "",
        "## NOTES.md",
        _bounded_file_text(session.notes_path, max_chars=max_chars),
    ]
    return "\n".join(lines).rstrip() + "\n"


def search_session(session: Session, query: str) -> list[tuple[Path, int, str]]:
    """Search NOTES.md and TODO.md with simple case-insensitive matching."""
    query = query.strip()
    if not query:
        return []

    matches: list[tuple[Path, int, str]] = []
    for path in (session.notes_path, session.todo_path):
        if not path.exists():
            continue
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if _line_matches(line, query):
                matches.append((path, line_number, line))
    return matches


def gc_sessions(
    *,
    cwd: Path | str | None = None,
    env: Mapping[str, str] | None = None,
    base_dir: Path | str | None = None,
    ttl_hours: float = DEFAULT_TTL_HOURS,
    now: dt.datetime | None = None,
) -> list[Path]:
    """Remove expired session directories, never removing the current session."""
    env_map = os.environ if env is None else env
    root = _resolve_base_dir(env_map, base_dir)
    sessions_dir = root / "sessions"
    if not sessions_dir.exists():
        return []

    current_key: str | None = None
    try:
        current_key = resolve_session(cwd=cwd, env=env_map, base_dir=root).scope.key
    except SessionIdentityError:
        current_key = None

    cutoff = (now or _now()) - dt.timedelta(hours=ttl_hours)
    removed: list[Path] = []
    for child in sessions_dir.iterdir():
        if not child.is_dir() or child.name == current_key:
            continue
        last_used = _last_used_at(child)
        if last_used < cutoff:
            shutil.rmtree(child)
            removed.append(child)
    return removed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Manage strict temp-session working notes for agents."
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help="Override the note-taker base dir. Defaults to NOTE_TAKER_ROOT or /tmp/note-taker/v1.",
    )
    parser.add_argument(
        "--cwd",
        type=Path,
        default=None,
        help="Resolve workspace/git scope from this directory. Defaults to the current working directory.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="Create or validate the current session files.")
    init_parser.add_argument("--json", action="store_true", help="Print session paths as JSON.")

    where_parser = subparsers.add_parser("where", help="Print the current session file paths.")
    where_parser.add_argument("--json", action="store_true", help="Print session paths as JSON.")

    resume_parser = subparsers.add_parser("resume", help="Print a bounded view of TODO.md and NOTES.md.")
    resume_parser.add_argument(
        "--max-chars",
        type=int,
        default=24_000,
        help="Maximum characters to print from each Markdown file.",
    )

    search_parser = subparsers.add_parser("search", help="Search NOTES.md and TODO.md.")
    search_parser.add_argument("query", help="Case-insensitive query string.")

    gc_parser = subparsers.add_parser("gc", help="Remove expired non-current sessions.")
    gc_parser.add_argument(
        "--ttl-hours",
        type=float,
        default=DEFAULT_TTL_HOURS,
        help="Remove sessions idle for more than this many hours.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command in {"init", "where", "resume", "search"}:
            session = ensure_session(cwd=args.cwd, base_dir=args.root)

        if args.command == "init":
            if args.json:
                print(json.dumps(_paths_payload(session), indent=2, sort_keys=True))
            else:
                print(f"Initialized note-taker session at {session.path}")
            return 0

        if args.command == "where":
            if args.json:
                print(json.dumps(_paths_payload(session), indent=2, sort_keys=True))
            else:
                print(f"Session: {session.path}")
                print(f"NOTES.md: {session.notes_path}")
                print(f"TODO.md: {session.todo_path}")
            return 0

        if args.command == "resume":
            print(format_resume(session, max_chars=max(args.max_chars, 0)), end="")
            return 0

        if args.command == "search":
            matches = search_session(session, args.query)
            if not matches:
                print("No matches.")
                return 0
            for path, line_number, line in matches:
                print(f"{path.name}:{line_number}: {line}")
            return 0

        if args.command == "gc":
            removed = gc_sessions(cwd=args.cwd, base_dir=args.root, ttl_hours=args.ttl_hours)
            print(f"Removed {len(removed)} expired session(s).")
            return 0
    except (SessionIdentityError, SessionStateError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    parser.error(f"unknown command: {args.command}")
    return 2


def _resolve_identity(env: Mapping[str, str]) -> tuple[str, str]:
    for name in SESSION_ENV_VARS:
        value = env.get(name, "").strip()
        if value:
            return name, value
    raise SessionIdentityError(
        "no session identity found; set NOTE_TAKER_SESSION_ID "
        "or run in an environment that provides CODEX_THREAD_ID"
    )


def _resolve_base_dir(env: Mapping[str, str], base_dir: Path | str | None) -> Path:
    if base_dir is not None:
        return Path(base_dir).expanduser().resolve()
    env_root = env.get("NOTE_TAKER_ROOT", "").strip()
    if env_root:
        return Path(env_root).expanduser().resolve()
    return Path(tempfile.gettempdir()).resolve() / "note-taker" / "v1"


def _resolve_workspace_root(cwd: Path) -> Path:
    root = _git_output(["rev-parse", "--show-toplevel"], cwd)
    if root:
        return Path(root).expanduser().resolve()
    return cwd


def _resolve_git_ref(workspace_root: Path) -> str:
    branch = _git_output(["rev-parse", "--abbrev-ref", "HEAD"], workspace_root)
    if branch and branch != "HEAD":
        return branch
    sha = _git_output(["rev-parse", "--verify", "HEAD"], workspace_root)
    if sha:
        return f"detached:{sha[:12]}"
    return "no-git"


def _git_output(args: list[str], cwd: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=cwd,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    output = result.stdout.strip()
    return output or None


def _load_manifest(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SessionStateError(f"could not read session manifest: {path}") from exc
    if not isinstance(loaded, dict):
        raise SessionStateError(f"session manifest is not an object: {path}")
    return loaded


def _validate_manifest(session: Session, manifest: Mapping[str, Any]) -> None:
    expected = {
        "version": SESSION_VERSION,
        "session_key": session.scope.key,
        "identity_source": session.scope.identity_source,
        "identity_fingerprint": session.scope.identity_fingerprint,
        "workspace_root": str(session.scope.workspace_root),
        "git_ref": session.scope.git_ref,
    }
    for key, value in expected.items():
        if manifest.get(key) != value:
            raise SessionStateError(
                f"session manifest mismatch for {key} in {session.manifest_path}"
            )


def _build_manifest(
    session: Session, existing: Mapping[str, Any] | None, timestamp: str
) -> dict[str, Any]:
    created_at = timestamp if existing is None else str(existing.get("created_at", timestamp))
    return {
        "version": SESSION_VERSION,
        "session_key": session.scope.key,
        "identity_source": session.scope.identity_source,
        "identity_fingerprint": session.scope.identity_fingerprint,
        "workspace_root": str(session.scope.workspace_root),
        "git_ref": session.scope.git_ref,
        "created_at": created_at,
        "last_used_at": timestamp,
        "expires_after_seconds": int(DEFAULT_TTL_HOURS * 60 * 60),
        "files": ["NOTES.md", "TODO.md"],
    }


def _paths_payload(session: Session) -> dict[str, str]:
    return {
        "session": str(session.path),
        "manifest": str(session.manifest_path),
        "notes": str(session.notes_path),
        "todo": str(session.todo_path),
        "workspace": str(session.scope.workspace_root),
        "git_ref": session.scope.git_ref,
    }


def _write_if_missing(path: Path, text: str) -> None:
    if not path.exists():
        _write_atomic(path, text)


def _write_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp_path.write_text(text, encoding="utf-8")
    tmp_path.replace(path)


def _bounded_file_text(path: Path, *, max_chars: int) -> str:
    if not path.exists():
        return "(missing)"
    text = path.read_text(encoding="utf-8").rstrip()
    if not text:
        return "(empty)"
    if len(text) <= max_chars:
        return text
    tail = text[-max_chars:] if max_chars else ""
    if "\n" in tail:
        tail = tail[tail.find("\n") + 1 :]
    return f"(truncated to last {max_chars} chars)\n{tail}".rstrip()


def _line_matches(line: str, query: str) -> bool:
    haystack = line.lower()
    needle = query.lower()
    if needle in haystack:
        return True
    terms = needle.split()
    return len(terms) > 1 and all(term in haystack for term in terms)


def _last_used_at(session_dir: Path) -> dt.datetime:
    manifest_path = session_dir / "MANIFEST.json"
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            if isinstance(manifest, dict) and isinstance(manifest.get("last_used_at"), str):
                return _parse_timestamp(manifest["last_used_at"])
        except (OSError, json.JSONDecodeError, ValueError):
            pass
    return dt.datetime.fromtimestamp(session_dir.stat().st_mtime, tz=dt.timezone.utc)


def _now() -> dt.datetime:
    return dt.datetime.now(tz=dt.timezone.utc)


def _format_timestamp(value: dt.datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=dt.timezone.utc)
    return value.astimezone(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _parse_timestamp(value: str) -> dt.datetime:
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    parsed = dt.datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


if __name__ == "__main__":
    raise SystemExit(main())
