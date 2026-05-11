from __future__ import annotations

import os
import shutil

import pytest

from vaultwares_mcp.fs_tools import PathEscapeError, fs_edit_text, fs_read_text, fs_write_text, resolve_scoped
from vaultwares_mcp.ops_tools import ops_journal_append, ops_note_append, ops_tasklog_append
from vaultwares_mcp.shell_tools import ShellSessionManager
from vaultwares_mcp.ssh_tools import ssh_run


def test_resolve_scoped_denies_absolute(tmp_path):
    root = tmp_path.resolve()
    if os.name == "nt":
        with pytest.raises(PathEscapeError):
            resolve_scoped(root, "C:\\Windows\\System32")
    else:
        with pytest.raises(PathEscapeError):
            resolve_scoped(root, "/etc/passwd")


def test_resolve_scoped_denies_parent_escape(tmp_path):
    root = tmp_path.resolve()
    with pytest.raises(PathEscapeError):
        resolve_scoped(root, "..")


def test_fs_write_then_read(tmp_path):
    root = tmp_path.resolve()
    out_w = fs_write_text(root, "a/b.txt", "hello", create_dirs=True, mode="overwrite", max_bytes=1024)
    assert out_w["error"] is None
    assert out_w["bytes"] == 5

    out_r = fs_read_text(root, "a/b.txt", max_bytes=1024)
    assert out_r["error"] is None
    assert out_r["content"] == "hello"
    assert out_r["bytes"] == 5


def test_fs_edit_match(tmp_path):
    root = tmp_path.resolve()
    fs_write_text(root, "x.txt", "hello world", create_dirs=True, mode="overwrite", max_bytes=1024)
    out = fs_edit_text(
        root,
        "x.txt",
        edits=[{"match": "world", "replace": "there"}],
        create_backup=True,
        max_bytes=1024,
    )
    assert out["error"] is None
    assert out["applied_count"] >= 1
    out_r = fs_read_text(root, "x.txt", max_bytes=1024)
    assert out_r["content"] == "hello there"


def test_fs_edit_range(tmp_path):
    root = tmp_path.resolve()
    fs_write_text(root, "x.txt", "a\nb\nc\n", create_dirs=True, mode="overwrite", max_bytes=1024)
    out = fs_edit_text(
        root,
        "x.txt",
        edits=[{"range": {"start": 2, "end": 2}, "replace": "B"}],
        create_backup=False,
        max_bytes=1024,
    )
    assert out["error"] is None
    out_r = fs_read_text(root, "x.txt", max_bytes=1024)
    assert out_r["content"].splitlines() == ["a", "B", "c"]


def test_shell_session_lifecycle(tmp_path):
    root = tmp_path.resolve()
    mgr = ShellSessionManager(root=root)
    sess = mgr.start(kind=None, cwd=".")
    if os.name == "nt":
        cmd = 'Write-Output "hi"'
    else:
        cmd = "echo hi"
    out = mgr.run(
        session_id=sess.session_id,
        command=cmd,
        timeout_ms=10_000,
        cwd=None,
        env=None,
        max_output_bytes=1024 * 1024,
    )
    assert out["exit_code"] in (0, 1, 2, 127) or out["exit_code"] is None  # platform variance
    assert "hi" in (out["stdout"] or out["stderr"])
    assert mgr.stop(sess.session_id) is True


def test_ssh_run_missing_binary(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda _: None)
    out = ssh_run("example.com", "echo hi")
    assert out["exit_code"] is None
    assert "not found" in out["stderr"].lower()


def test_ops_writes(tmp_path, monkeypatch):
    monkeypatch.setenv("VAULTWARES_MCP_OPS_DIR", str(tmp_path))
    j = ops_journal_append("hello", date_prefix=True)
    n = ops_note_append("note", topic="t1")
    t = ops_tasklog_append("evt")
    assert j["bytes"] > 0 and n["bytes"] > 0 and t["bytes"] > 0
    assert os.path.exists(j["path"])
    assert os.path.exists(n["path"])
    assert os.path.exists(t["path"])

