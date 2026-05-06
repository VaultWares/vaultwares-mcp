"""VaultWares FastMCP server.

Tiered "any-machine" utilities:
  Tier 1: Filesystem tools (scoped to process working directory)
  Tier 2: Shell execution w/ persistent sessions
  Tier 3: Optional SSH execution via system `ssh`
  Tier 4: Personal ops tools (journal/notes/tasklog)
  Tier 5: Diagnostics + usage + limits
"""

from __future__ import annotations

import argparse
import os
import platform
import sys
import time
from typing import Any

from fastmcp import FastMCP

from tools.credit_optimizer import (
    analyze_batch,
    classify_intent,
    estimate_credits,
    optimize_prompt,
    recommend_model,
)
from tools.fast_navigation import fetch_url, fetch_urls

from .config import load_config
from .fs_tools import PathEscapeError, fs_edit_text, fs_list, fs_read_text, fs_write_text
from .limits import TokenBucket
from .ops_tools import ops_journal_append, ops_note_append, ops_tasklog_append
from .shell_tools import ShellSessionManager
from .ssh_tools import ssh_run as _ssh_run
from .usage import UsageTracker


_STARTED_AT = time.time()
_CURRENT_TRANSPORT = "stdio"

cfg = load_config()
usage = UsageTracker()
bucket = TokenBucket(capacity=cfg.rate_limit_per_minute, refill_per_sec=cfg.rate_limit_per_minute / 60.0)
shell_sessions = ShellSessionManager(root=cfg.root_dir)

def _rate_and_count(tool_name: str) -> dict[str, Any] | None:
    if not bucket.take(1):
        snap = bucket.snapshot()
        return {"error": "Rate limit exceeded", "reset_in_s": snap.reset_in_s}
    usage.inc_tool(tool_name)
    return None


mcp = FastMCP(
    name="VaultWares MCP",
    instructions=(
        "VaultWares MCP is a tiered utility server. "
        "Filesystem and shell tools are scoped to the server's working directory. "
        "Use diag_status/diag_usage/diag_limits for health and usage insight."
    ),
)


# ---------------------------------------------------------------------------
# Existing tools (Credit Optimizer + Fast Navigation)
# ---------------------------------------------------------------------------


@mcp.tool
def credit_classify(prompt: str) -> dict[str, Any]:
    if (blocked := _rate_and_count("credit_classify")) is not None:
        return blocked
    return {"intent": classify_intent(prompt)}


@mcp.tool
def credit_recommend(prompt: str) -> dict[str, Any]:
    if (blocked := _rate_and_count("credit_recommend")) is not None:
        return blocked
    return recommend_model(prompt)


@mcp.tool
def credit_optimize(prompt: str, max_tokens: int = 1500) -> dict[str, Any]:
    if (blocked := _rate_and_count("credit_optimize")) is not None:
        return blocked
    return optimize_prompt(prompt, max_tokens=max_tokens)


@mcp.tool
def credit_estimate(prompt: str, model: str = "") -> dict[str, Any]:
    if (blocked := _rate_and_count("credit_estimate")) is not None:
        return blocked
    return estimate_credits(prompt, model=model or None)


@mcp.tool
def credit_analyze_batch(prompts: list[str]) -> dict[str, Any]:
    if (blocked := _rate_and_count("credit_analyze_batch")) is not None:
        return blocked
    return analyze_batch(prompts[:50])


@mcp.tool
def nav_fetch(url: str, as_text: bool = True, ttl: int = 300) -> dict[str, Any]:
    if (blocked := _rate_and_count("nav_fetch")) is not None:
        return blocked
    return fetch_url(url, as_text=as_text, ttl=ttl)


@mcp.tool
def nav_fetch_many(
    urls: list[str],
    as_text: bool = True,
    ttl: int = 300,
    max_concurrency: int = 10,
) -> dict[str, Any]:
    if (blocked := _rate_and_count("nav_fetch_many")) is not None:
        return blocked
    return fetch_urls(urls, as_text=as_text, ttl=ttl, max_concurrency=max_concurrency)


# ---------------------------------------------------------------------------
# Tier 1: Filesystem
# ---------------------------------------------------------------------------


@mcp.tool
def fs_list_dir(path: str = ".") -> dict[str, Any]:
    if (blocked := _rate_and_count("fs_list")) is not None:
        return blocked
    try:
        return fs_list(cfg.root_dir, path=path)
    except PathEscapeError as exc:
        return {"entries": [], "error": str(exc)}


@mcp.tool
def fs_read(path: str) -> dict[str, Any]:
    if (blocked := _rate_and_count("fs_read")) is not None:
        return blocked
    try:
        out = fs_read_text(cfg.root_dir, path=path, max_bytes=cfg.max_read_bytes)
        if out.get("bytes"):
            usage.add_read_bytes(int(out["bytes"]))
        return out
    except PathEscapeError as exc:
        return {"content": None, "bytes": 0, "error": str(exc)}


@mcp.tool
def fs_write(path: str, content: str, create_dirs: bool = True, mode: str = "overwrite") -> dict[str, Any]:
    if (blocked := _rate_and_count("fs_write")) is not None:
        return blocked
    try:
        out = fs_write_text(
            cfg.root_dir,
            path=path,
            content=content,
            create_dirs=bool(create_dirs),
            mode=str(mode),
            max_bytes=cfg.max_write_bytes,
        )
        if out.get("bytes"):
            usage.add_written_bytes(int(out["bytes"]))
        return out
    except PathEscapeError as exc:
        return {"bytes": 0, "error": str(exc)}


@mcp.tool
def fs_edit(path: str, edits: list[dict[str, Any]], create_backup: bool = True) -> dict[str, Any]:
    if (blocked := _rate_and_count("fs_edit")) is not None:
        return blocked
    try:
        return fs_edit_text(
            cfg.root_dir,
            path=path,
            edits=edits,
            create_backup=bool(create_backup),
            max_bytes=max(cfg.max_read_bytes, cfg.max_write_bytes),
        )
    except PathEscapeError as exc:
        return {"applied_count": 0, "error": str(exc)}


# ---------------------------------------------------------------------------
# Tier 2: Shell (sessions)
# ---------------------------------------------------------------------------


@mcp.tool
def sh_session_start(kind: str = "", cwd: str = ".") -> dict[str, Any]:
    if (blocked := _rate_and_count("sh_session_start")) is not None:
        return blocked
    try:
        sess = shell_sessions.start(kind or None, cwd or ".")
        return {"session_id": sess.session_id, "kind": sess.kind, "cwd": str(sess.cwd)}
    except PathEscapeError as exc:
        return {"error": str(exc)}


@mcp.tool
def sh_session_list() -> dict[str, Any]:
    if (blocked := _rate_and_count("sh_session_list")) is not None:
        return blocked
    return {"sessions": shell_sessions.list()}


@mcp.tool
def sh_session_stop(session_id: str) -> dict[str, Any]:
    if (blocked := _rate_and_count("sh_session_stop")) is not None:
        return blocked
    stopped = shell_sessions.stop(session_id)
    return {"stopped": bool(stopped)}


@mcp.tool
def sh_run(
    session_id: str,
    command: str,
    timeout_ms: int | None = None,
    cwd: str | None = None,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    if (blocked := _rate_and_count("sh_run")) is not None:
        return blocked
    tm = int(timeout_ms) if timeout_ms is not None else cfg.default_shell_timeout_ms
    start = time.monotonic()
    try:
        out = shell_sessions.run(
            session_id=session_id,
            command=command,
            timeout_ms=tm,
            cwd=cwd,
            env=env,
            max_output_bytes=cfg.max_shell_output_bytes,
        )
        usage.add_shell_ms(int((time.monotonic() - start) * 1000))
        return out
    except PathEscapeError as exc:
        return {"exit_code": None, "stdout": "", "stderr": str(exc), "duration_ms": 0}


# ---------------------------------------------------------------------------
# Tier 3: SSH (optional)
# ---------------------------------------------------------------------------


@mcp.tool
def ssh_run(
    host: str,
    command: str,
    user: str = "",
    port: int = 22,
    timeout_ms: int = 60000,
    identity_file: str = "",
) -> dict[str, Any]:
    if (blocked := _rate_and_count("ssh_run")) is not None:
        return blocked
    if not cfg.enable_ssh:
        return {"error": "SSH is disabled. Set VAULTWARES_MCP_ENABLE_SSH=1 to enable."}
    start = time.monotonic()
    out = _ssh_run(
        host=host,
        command=command,
        user=user or None,
        port=int(port),
        timeout_ms=int(timeout_ms),
        identity_file=identity_file or None,
    )
    usage.add_ssh_ms(int((time.monotonic() - start) * 1000))
    return out


# ---------------------------------------------------------------------------
# Tier 4: Personal ops
# ---------------------------------------------------------------------------


@mcp.tool
def ops_journal(entry: str, date_prefix: bool = True) -> dict[str, Any]:
    if (blocked := _rate_and_count("ops_journal_append")) is not None:
        return blocked
    out = ops_journal_append(entry, date_prefix=bool(date_prefix))
    if out.get("bytes"):
        usage.add_written_bytes(int(out["bytes"]))
    return out


@mcp.tool
def ops_note(note: str, topic: str = "general") -> dict[str, Any]:
    if (blocked := _rate_and_count("ops_note_append")) is not None:
        return blocked
    out = ops_note_append(note, topic=topic or "general")
    if out.get("bytes"):
        usage.add_written_bytes(int(out["bytes"]))
    return out


@mcp.tool
def ops_tasklog(event: str) -> dict[str, Any]:
    if (blocked := _rate_and_count("ops_tasklog_append")) is not None:
        return blocked
    out = ops_tasklog_append(event)
    if out.get("bytes"):
        usage.add_written_bytes(int(out["bytes"]))
    return out


# ---------------------------------------------------------------------------
# Tier 5: Diagnostics
# ---------------------------------------------------------------------------


@mcp.tool
def diag_status() -> dict[str, Any]:
    if (blocked := _rate_and_count("diag_status")) is not None:
        return blocked
    snap = usage.snapshot()
    return {
        "name": "VaultWares MCP",
        "version": "2.0.0",
        "transport": _CURRENT_TRANSPORT,
        "pid": os.getpid(),
        "platform": platform.platform(),
        "python": sys.version.split()[0],
        "cwd_root": str(cfg.root_dir),
        "enabled_tiers": {
            "tier1_filesystem": True,
            "tier2_shell": True,
            "tier3_ssh": bool(cfg.enable_ssh),
            "tier4_ops": True,
            "tier5_diag": True,
        },
        "uptime_s": int(time.time() - _STARTED_AT),
        "tool_calls_total": snap.tool_calls_total,
    }


@mcp.tool
def diag_usage() -> dict[str, Any]:
    if (blocked := _rate_and_count("diag_usage")) is not None:
        return blocked
    snap = usage.snapshot()
    return {
        "tool_calls_total": snap.tool_calls_total,
        "per_tool_counts": snap.per_tool_counts,
        "bytes_read": snap.bytes_read,
        "bytes_written": snap.bytes_written,
        "shell_ms_total": snap.shell_ms_total,
        "ssh_ms_total": snap.ssh_ms_total,
    }


@mcp.tool
def diag_limits() -> dict[str, Any]:
    if (blocked := _rate_and_count("diag_limits")) is not None:
        return blocked
    snap = bucket.snapshot()
    return {
        "configured_limits": {
            "rate_limit_per_minute": cfg.rate_limit_per_minute,
            "max_read_bytes": cfg.max_read_bytes,
            "max_write_bytes": cfg.max_write_bytes,
            "max_shell_output_bytes": cfg.max_shell_output_bytes,
            "default_shell_timeout_ms": cfg.default_shell_timeout_ms,
            "ssh_enabled": bool(cfg.enable_ssh),
        },
        "remaining": {"requests_tokens": snap.tokens},
        "reset_in_s": snap.reset_in_s,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="VaultWares FastMCP server")
    parser.add_argument(
        "--transport",
        default=os.environ.get("MCP_TRANSPORT", "stdio"),
        choices=["stdio", "sse", "streamable-http"],
        help="Transport to use (default: stdio)",
    )
    parser.add_argument(
        "--host",
        default=os.environ.get("MCP_HOST", "0.0.0.0"),
        help="Host for HTTP transports (default: 0.0.0.0)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("MCP_PORT", "8000")),
        help="Port for HTTP transports (default: 8000)",
    )
    parser.add_argument(
        "--path",
        default=os.environ.get("MCP_PATH", "/mcp"),
        help="URL path for HTTP transports (default: /mcp)",
    )
    args = parser.parse_args()

    global _CURRENT_TRANSPORT  # noqa: PLW0603
    _CURRENT_TRANSPORT = args.transport

    if args.transport == "stdio":
        mcp.run(transport="stdio")
    else:
        mcp.run(transport=args.transport, host=args.host, port=args.port, path=args.path)


if __name__ == "__main__":
    main()
