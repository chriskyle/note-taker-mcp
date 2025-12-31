import shutil
from pathlib import Path

import pytest

fastmcp = pytest.importorskip("fastmcp")

from note_taker_mcp.server import (  # noqa: E402 - fastmcp must import first
    build_server,
    default_data_dir,
)


def test_build_server(tmp_path: Path) -> None:
    server = build_server(data_dir=tmp_path)
    assert server is not None


def test_default_data_dir_uses_tmp(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NOTES_MCP_DATA_DIR", raising=False)
    data_dir = default_data_dir()
    assert data_dir.parent == Path("/tmp")
    assert data_dir.name.startswith("notes-")
    assert data_dir.is_dir()
    shutil.rmtree(data_dir)


def test_default_data_dir_respects_env(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    custom = tmp_path / "custom-notes"
    monkeypatch.setenv("NOTES_MCP_DATA_DIR", str(custom))
    data_dir = default_data_dir()
    assert data_dir == custom
    assert data_dir.is_dir()
