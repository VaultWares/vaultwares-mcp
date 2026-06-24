"""VaultWares Mcp server.

Tiered "any-machine" utilities:
  Tier 1: Filesystem tools (scoped to process working directory)
  Tier 2: Shell execution w/ persistent sessions
  Tier 3: Agent and Health Ledgers search tools
  Tier 4: Diagnstics tools, usage, limits
"""

from __future__ import annotations

import argparse
import os
import platform
import sys
import time
from typing import Any

from fastmcp import FastMCP as VaultwaresMCP

from tools.credit_optimizer import (
    analyze_batch,
    classify_intent,
    estimate_credits,
    optimize_prompt,
    recommend_model,
)
from tools.fast_navigation import fetch_url, fetch_urls
from tools.task_estimator import estimate_task

from .config import load_config
from .fs_tools import PathEscapeError, fs_edit_text, fs_list, fs_read_text, fs_write_text
from .limits import TokenBucket
from .shell_tools import ShellSessionManager
from .usage import UsageTracker
from .ledger_tools import (
    get_agent_ledger_entries,
    search_agent_ledger,
    get_health_ledger_entries,
    search_health_ledger,
)
from .vw_cli_tools import (
    run_agent_ledger_record_change,
    run_agent_ledger_render_ledger,
    run_agent_ledger_render_impact,
    run_agent_ledger_sync_ledger,
    run_health_ledger_probe,
)


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


mcp = VaultwaresMCP(
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

@mcp.tool
def task_estimate(
    protocols: list[str] | None = None,
    repos: int = 1,
    files_read: int = 0,
    files_changed: int = 0,
    tools: int = 0,
    commands: int = 0,
    include_time_estimates: bool = True,
) -> dict[str, Any]:
    """Estimate task size (token-first).

    This is intentionally decoupled from credit optimization.
    Primary output is estimated_output_tokens; time is derived if requested.
    """
    if (blocked := _rate_and_count("task_estimate")) is not None:
        return blocked
    return estimate_task(
        protocols=protocols or [],
        repos=int(repos),
        files_read=int(files_read),
        files_changed=int(files_changed),
        tools=int(tools),
        commands=int(commands),
        include_time_estimates=bool(include_time_estimates),
    )


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
def fs_edit(path: str, match: str, replace: str, count: int = 0, create_backup: bool = True) -> dict[str, Any]:
    if (blocked := _rate_and_count("fs_edit")) is not None:
        return blocked
    try:
        return fs_edit_text(
            cfg.root_dir,
            path=path,
            edits=[{"match": match, "replace": replace, "count": count}],
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
# Tier 3: Ledger (agent-ledger: coding/projects  |  health-ledger: deployments/health)
# ---------------------------------------------------------------------------


@mcp.tool
def agent_ledger_get_recent(
    n: int = 25,
    project: str | None = None,
    kind: str | None = None,
    model: str | None = None,
    assistant: str | None = None,
    date: str | None = None,
) -> dict[str, Any]:
    """
    Fetch the last N agent-ledger entries (coding and project work) with optional filters.
    Filters: project, kind (code-change, plan, etc.), model, assistant, date (YYYY-MM-DD).
    """
    if (blocked := _rate_and_count("agent_ledger_get_recent")) is not None:
        return blocked
    return {"entries": get_agent_ledger_entries(n=n, project=project, kind=kind, model=model, assistant=assistant, date=date)}


@mcp.tool
def agent_ledger_search(query: str, n: int = 10) -> dict[str, Any]:
    """Search through recent agent-ledger entries (coding/project work) for a query string."""
    if (blocked := _rate_and_count("agent_ledger_search")) is not None:
        return blocked
    return {"results": search_agent_ledger(query=query, n=n)}


@mcp.tool
def health_ledger_get_recent(
    n: int = 25,
    service_id: str | None = None,
    run_id: str | None = None,
    ok: bool | None = None,
    event_type: str | None = None,
    date: str | None = None,
) -> dict[str, Any]:
    """
    Fetch the last N health-ledger entries (deployments and server health probes) with optional filters.
    Filters: service_id, run_id, ok (True/False), event_type (probe_result, etc.), date (YYYY-MM-DD).
    """
    if (blocked := _rate_and_count("health_ledger_get_recent")) is not None:
        return blocked
    return {"entries": get_health_ledger_entries(n=n, service_id=service_id, run_id=run_id, ok=ok, event_type=event_type, date=date)}


@mcp.tool
def health_ledger_search(query: str, n: int = 10) -> dict[str, Any]:
    """Search through recent health-ledger entries (deployments/server health) for a query string."""
    if (blocked := _rate_and_count("health_ledger_search")) is not None:
        return blocked
    return {"results": search_health_ledger(query=query, n=n)}


@mcp.tool
def agent_ledger_record_change(
    project: str,
    summary: str,
    kind: str = "general",
    commands: list[str] | None = None,
    files: list[str] | None = None,
    plan_path: str | None = None,
    actor: str | None = None,
    agent_role: str = "subagent",
    model: str | None = None,
    thinking: str = "medium",
    mode: str = "code",
    permissions: str = "ask",
    network: str | None = None,
    tools_used: list[str] | None = None,
) -> dict[str, Any]:
    """Execute the record-agent-change.ps1 script."""
    if (blocked := _rate_and_count("agent_ledger_record_change")) is not None:
        return blocked
    return run_agent_ledger_record_change(project, summary, kind, commands, files, plan_path, actor, agent_role, model, thinking, mode, permissions, network, tools_used)


@mcp.tool
def agent_ledger_render_ledger() -> dict[str, Any]:
    """Execute the render-agent-ledger.ps1 script."""
    if (blocked := _rate_and_count("agent_ledger_render_ledger")) is not None:
        return blocked
    return run_agent_ledger_render_ledger()


@mcp.tool
def agent_ledger_render_impact() -> dict[str, Any]:
    """Execute the render-work-impact.ps1 script."""
    if (blocked := _rate_and_count("agent_ledger_render_impact")) is not None:
        return blocked
    return run_agent_ledger_render_impact()


@mcp.tool
def agent_ledger_sync_ledger(commit_message: str | None = None) -> dict[str, Any]:
    """Execute the sync-agent-ledger.ps1 script."""
    if (blocked := _rate_and_count("agent_ledger_sync_ledger")) is not None:
        return blocked
    return run_agent_ledger_sync_ledger(commit_message)


@mcp.tool
def health_ledger_run_probe(services: list[str] | None = None, no_tailnet: bool = False) -> dict[str, Any]:
    """Run the Node-based health-ledger probe once."""
    if (blocked := _rate_and_count("health_ledger_run_probe")) is not None:
        return blocked
    return run_health_ledger_probe(services, no_tailnet)


# ---------------------------------------------------------------------------
# Tier 4: Diagnostics
# ---------------------------------------------------------------------------


@mcp.tool
def diag_status() -> dict[str, Any]:
    if (blocked := _rate_and_count("diag_status")) is not None:
        return blocked
    snap = usage.snapshot()
    return {
        "name": "VaultWares MCP",
        "version": "3.0.1",
        "transport": _CURRENT_TRANSPORT,
        "pid": os.getpid(),
        "platform": platform.platform(),
        "python": sys.version.split()[0],
        "cwd_root": str(cfg.root_dir),
        "enabled_tiers": {
            "tier1_filesystem": True,
            "tier2_shell": True,
            "tier3_ledger": True,
            "tier4_diag": True,
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
        },
        "remaining": {"requests_tokens": snap.tokens},
        "reset_in_s": snap.reset_in_s,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="VaultWares Mcp server")
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
        default=int(os.environ.get("MCP_PORT", "9020")),
        help="Port for HTTP transports (default: 9020)",
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


