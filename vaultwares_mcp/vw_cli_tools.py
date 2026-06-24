from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any


def _get_repo_root(repo_name: str) -> str:
    """Resolve the base path for agent-ledger or health-ledger based on OS and env vars."""
    if repo_name == "agent-ledger":
        env_val = os.environ.get("VW_AGENT_LEDGER_ROOT")
        if env_val:
            # VW_AGENT_LEDGER_ROOT usually points to the 'events' subdirectory
            path = Path(env_val)
            if path.name == "events":
                return str(path.parent)
            return str(path)
        return r"C:\Users\Administrator\Desktop\Github Repos\agent-ledger" if os.name == "nt" else "/opt/agent-ledger"
    elif repo_name == "health-ledger":
        env_val = os.environ.get("VW_HEALTH_LEDGER_ROOT")
        if env_val:
            # VW_HEALTH_LEDGER_ROOT usually points to the 'data/events' subdirectory
            path = Path(env_val)
            if path.name == "events" and path.parent.name == "data":
                return str(path.parent.parent)
            return str(path)
        return r"C:\Users\Administrator\Desktop\Github Repos\health-ledger" if os.name == "nt" else "/opt/health-ledger"
    raise ValueError(f"Unknown repo_name: {repo_name}")


def _escape_ps_val(val: Any) -> str:
    """Format Python values into PowerShell CLI string arguments."""
    if val is None:
        return "$null"
    if isinstance(val, bool):
        return "$true" if val else "$false"
    if isinstance(val, (int, float)):
        return str(val)
    if isinstance(val, list):
        items = [_escape_ps_val(item) for item in val]
        return f"@({', '.join(items)})"
    
    # Escape single quotes by doubling them (PowerShell standard)
    escaped = str(val).replace("'", "''")
    return f"'{escaped}'"


def _run_ps_script(repo_name: str, script_relpath: str, args_dict: dict[str, Any] = None) -> dict[str, Any]:
    """Execute a PowerShell script using pwsh across platforms."""
    cwd = _get_repo_root(repo_name)
    script_path = os.path.join(cwd, script_relpath)
    
    # pwsh is installed via snap on Linux, and natively available on Windows
    exe = "pwsh"
    
    ps_args = [f"& '{script_path}'"]
    if args_dict:
        for k, v in args_dict.items():
            if v is not None:
                ps_args.append(f"{k} {_escape_ps_val(v)}")
                
    ps_cmd = " ".join(ps_args)
    
    cmd = [exe, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", ps_cmd]
    
    try:
        cp = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=120,
        )
        return {
            "exit_code": cp.returncode,
            "stdout": cp.stdout.strip(),
            "stderr": cp.stderr.strip()
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "exit_code": None,
            "stdout": (exc.stdout or "").strip() if isinstance(exc.stdout, str) else "",
            "stderr": f"Timeout expired: {exc}",
        }
    except Exception as exc:
        return {
            "exit_code": None,
            "stdout": "",
            "stderr": f"Execution error: {exc}",
        }


def run_agent_ledger_record_change(
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
    # Ensure network uses a sane default on Linux if not specified
    if not network:
        network = "vps-ovhcloud" if os.name != "nt" else "clopeux-desktop"
        
    args = {
        "-Project": project,
        "-Kind": kind,
        "-Summary": summary,
        "-Commands": commands or [],
        "-Files": files or [],
        "-PlanPath": plan_path,
        "-Actor": actor or os.environ.get("AGENT_NAME", "VaultWares MCP"),
        "-AgentRole": agent_role,
        "-Model": model or "unknown",
        "-Thinking": thinking,
        "-Mode": mode,
        "-Permissions": permissions,
        "-Network": network,
        "-ToolsUsed": tools_used or [],
    }
    return _run_ps_script("agent-ledger", "scripts/record-agent-change.ps1", args)


def run_agent_ledger_render_ledger() -> dict[str, Any]:
    """Execute the render-agent-ledger.ps1 script."""
    return _run_ps_script("agent-ledger", "scripts/render-agent-ledger.ps1")


def run_agent_ledger_render_impact() -> dict[str, Any]:
    """Execute the render-work-impact.ps1 script."""
    return _run_ps_script("agent-ledger", "scripts/render-work-impact.ps1")


def run_agent_ledger_sync_ledger(commit_message: str | None = None) -> dict[str, Any]:
    """Execute the sync-agent-ledger.ps1 script."""
    args = {}
    if commit_message:
        args["-CommitMessage"] = commit_message
    return _run_ps_script("agent-ledger", "scripts/sync-agent-ledger.ps1", args)


def run_health_ledger_probe(
    services: list[str] | None = None,
    no_tailnet: bool = False,
) -> dict[str, Any]:
    """Run the Node-based health-ledger probe once."""
    cwd = _get_repo_root("health-ledger")
    script_path = os.path.join(cwd, "scripts", "probe-joker.mjs")
    
    args = ["node", script_path, "--once"]
    if services:
        for srv in services:
            args.extend(["--service", srv])
    if no_tailnet:
        args.append("--no-tailnet")
        
    try:
        cp = subprocess.run(
            args,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=180,
        )
        # Parse the JSON output if possible to provide structured data
        stdout = cp.stdout.strip()
        parsed_json = None
        try:
            if stdout:
                # The script outputs a single JSON block at the end (the rest might be logs, but it outputs single object if --once)
                parsed_json = __import__("json").loads(stdout)
        except Exception:
            pass
            
        return {
            "exit_code": cp.returncode,
            "stdout": stdout,
            "stderr": cp.stderr.strip(),
            "parsed": parsed_json,
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "exit_code": None,
            "stdout": (exc.stdout or "").strip() if isinstance(exc.stdout, str) else "",
            "stderr": f"Timeout expired: {exc}",
            "parsed": None,
        }
    except Exception as exc:
        return {
            "exit_code": None,
            "stdout": "",
            "stderr": f"Execution error: {exc}",
            "parsed": None,
        }
