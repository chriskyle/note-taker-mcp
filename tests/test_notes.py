from __future__ import annotations

import datetime as dt
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skill" / "scripts" / "notes.py"


def load_notes_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("notes_script", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


notes = load_notes_module()


def run_git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )


def make_git_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    run_git(repo, "init")
    run_git(repo, "checkout", "-B", "main")
    run_git(repo, "config", "user.email", "test@example.com")
    run_git(repo, "config", "user.name", "Test User")
    (repo / "README.md").write_text("# test\n", encoding="utf-8")
    run_git(repo, "add", "README.md")
    run_git(repo, "commit", "-m", "initial")
    return repo


def cli(
    tmp_path: Path,
    repo: Path,
    *args: str,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    child_env = os.environ.copy()
    child_env.pop("NOTE_TAKER_SESSION_ID", None)
    child_env.pop("CODEX_THREAD_ID", None)
    child_env.pop("NOTE_TAKER_ROOT", None)
    child_env.update(env or {"CODEX_THREAD_ID": "thread-a"})
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--root",
            str(tmp_path / "notes-root"),
            "--cwd",
            str(repo),
            *args,
        ],
        check=False,
        capture_output=True,
        text=True,
        env=child_env,
    )


def test_same_thread_repo_and_branch_resolve_same_session(tmp_path: Path) -> None:
    repo = make_git_repo(tmp_path)
    env = {"CODEX_THREAD_ID": "thread-a"}
    base = tmp_path / "notes-root"

    first = notes.resolve_session(cwd=repo, env=env, base_dir=base)
    second = notes.resolve_session(cwd=repo, env=env, base_dir=base)

    assert first.path == second.path
    assert first.scope.git_ref == "main"


def test_different_thread_or_branch_resolves_different_session(tmp_path: Path) -> None:
    repo = make_git_repo(tmp_path)
    base = tmp_path / "notes-root"

    thread_a = notes.resolve_session(
        cwd=repo, env={"CODEX_THREAD_ID": "thread-a"}, base_dir=base
    )
    thread_b = notes.resolve_session(
        cwd=repo, env={"CODEX_THREAD_ID": "thread-b"}, base_dir=base
    )
    run_git(repo, "checkout", "-b", "feature")
    feature = notes.resolve_session(
        cwd=repo, env={"CODEX_THREAD_ID": "thread-a"}, base_dir=base
    )

    assert thread_a.path != thread_b.path
    assert thread_a.path != feature.path
    assert feature.scope.git_ref == "feature"


def test_note_taker_session_id_overrides_codex_thread_id(tmp_path: Path) -> None:
    repo = make_git_repo(tmp_path)
    base = tmp_path / "notes-root"

    first = notes.resolve_session(
        cwd=repo,
        env={"NOTE_TAKER_SESSION_ID": "explicit", "CODEX_THREAD_ID": "thread-a"},
        base_dir=base,
    )
    second = notes.resolve_session(
        cwd=repo,
        env={"NOTE_TAKER_SESSION_ID": "explicit", "CODEX_THREAD_ID": "thread-b"},
        base_dir=base,
    )

    assert first.path == second.path
    assert first.scope.identity_source == "NOTE_TAKER_SESSION_ID"


def test_missing_identity_fails_loudly(tmp_path: Path) -> None:
    repo = make_git_repo(tmp_path)

    with pytest.raises(notes.SessionIdentityError):
        notes.resolve_session(cwd=repo, env={}, base_dir=tmp_path / "notes-root")


def test_init_creates_manifest_notes_and_todo(tmp_path: Path) -> None:
    repo = make_git_repo(tmp_path)
    session = notes.ensure_session(
        cwd=repo,
        env={"CODEX_THREAD_ID": "thread-a"},
        base_dir=tmp_path / "notes-root",
        now=dt.datetime(2026, 5, 13, 12, 0, tzinfo=dt.timezone.utc),
    )

    manifest = json.loads(session.manifest_path.read_text(encoding="utf-8"))
    assert manifest["identity_source"] == "CODEX_THREAD_ID"
    assert manifest["git_ref"] == "main"
    assert "identity_value" not in manifest
    assert "Current Understanding" in session.notes_path.read_text(encoding="utf-8")
    assert "## Current" in session.todo_path.read_text(encoding="utf-8")


def test_resume_cli_prints_bounded_context_and_paths(tmp_path: Path) -> None:
    repo = make_git_repo(tmp_path)

    result = cli(tmp_path, repo, "resume", "--max-chars", "1000")

    assert result.returncode == 0, result.stderr
    assert "Session:" in result.stdout
    assert "NOTES.md:" in result.stdout
    assert "TODO.md:" in result.stdout
    assert "## TODO.md" in result.stdout
    assert "## NOTES.md" in result.stdout


def test_search_cli_searches_notes_and_todo(tmp_path: Path) -> None:
    repo = make_git_repo(tmp_path)
    session = notes.ensure_session(
        cwd=repo, env={"CODEX_THREAD_ID": "thread-a"}, base_dir=tmp_path / "notes-root"
    )
    session.notes_path.write_text(
        "# Notes\n\nDECISION: Remove MCP and use a skill script.\n",
        encoding="utf-8",
    )
    session.todo_path.write_text(
        "# TODO\n\n## Current\n- [ ] Add resolver tests.\n",
        encoding="utf-8",
    )

    notes_result = cli(tmp_path, repo, "search", "remove skill")
    todo_result = cli(tmp_path, repo, "search", "resolver tests")
    miss_result = cli(tmp_path, repo, "search", "definitely absent")

    assert notes_result.returncode == 0, notes_result.stderr
    assert "NOTES.md:" in notes_result.stdout
    assert "Remove MCP" in notes_result.stdout
    assert "TODO.md:" in todo_result.stdout
    assert "resolver tests" in todo_result.stdout
    assert miss_result.returncode == 0
    assert "No matches." in miss_result.stdout


def test_gc_removes_expired_non_current_sessions_only(tmp_path: Path) -> None:
    repo = make_git_repo(tmp_path)
    base = tmp_path / "notes-root"
    current = notes.ensure_session(
        cwd=repo,
        env={"CODEX_THREAD_ID": "thread-a"},
        base_dir=base,
        now=dt.datetime(2026, 5, 13, 12, 0, tzinfo=dt.timezone.utc),
    )
    old = base / "sessions" / "old-session"
    old.mkdir(parents=True)
    (old / "MANIFEST.json").write_text(
        json.dumps({"last_used_at": "2026-05-10T12:00:00Z"}),
        encoding="utf-8",
    )

    result = cli(tmp_path, repo, "gc", "--ttl-hours", "24")

    assert result.returncode == 0, result.stderr
    assert not old.exists()
    assert current.path.exists()
