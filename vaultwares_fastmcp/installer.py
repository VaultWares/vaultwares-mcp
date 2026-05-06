from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class InstallTarget:
    name: str
    path: Path
    kind: str  # "json" | "toml"


def _home() -> Path:
    return Path.home().resolve()


def _backup(path: Path) -> Path:
    bak = path.with_suffix(path.suffix + ".bak")
    shutil.copy2(path, bak)
    return bak


def _ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    _ensure_parent(path)
    path.write_text(text, encoding="utf-8")


def _json_load(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(_read_text(path) or "{}")


def _json_dump(path: Path, data: dict[str, Any], *, pretty: bool = True) -> None:
    text = json.dumps(data, indent=2 if pretty else None, sort_keys=False) + "\n"
    _write_text(path, text)


def _patch_toml_add_block(toml_text: str, block_name: str, block_lines: list[str]) -> tuple[str, bool]:
    header = f"[{block_name}]"
    if header in toml_text:
        return toml_text, False
    if not toml_text.endswith("\n"):
        toml_text += "\n"
    patched = toml_text + "\n" + header + "\n" + "\n".join(block_lines) + "\n"
    return patched, True


def _patch_json_mcpserver(
    data: dict[str, Any],
    server_id: str,
    server_value: dict[str, Any],
    *,
    key: str = "mcpServers",
) -> tuple[dict[str, Any], bool]:
    obj = dict(data)
    servers = obj.get(key)
    if not isinstance(servers, dict):
        servers = {}
    if server_id in servers:
        return obj, False
    servers = dict(servers)
    servers[server_id] = server_value
    obj[key] = servers
    return obj, True


def discover_targets(project_dir: Path) -> list[InstallTarget]:
    targets: list[InstallTarget] = []

    # Codex (CLI/Desktop)
    targets.append(InstallTarget("codex", _home() / ".codex" / "config.toml", "toml"))

    # Claude Desktop (platform-specific defaults)
    if sys.platform.startswith("win"):
        appdata = os.environ.get("APPDATA")
        if appdata:
            targets.append(
                InstallTarget(
                    "claude-desktop",
                    Path(appdata) / "Claude" / "claude_desktop_config.json",
                    "json",
                )
            )
    elif sys.platform == "darwin":
        targets.append(
            InstallTarget(
                "claude-desktop",
                _home() / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json",
                "json",
            )
        )
    else:
        targets.append(
            InstallTarget(
                "claude-desktop",
                _home() / ".config" / "Claude" / "claude_desktop_config.json",
                "json",
            )
        )

    # Claude Code / generic project mcpServers JSON
    targets.append(InstallTarget("project-mcp", project_dir / ".mcp.json", "json"))

    # VS Code (workspace)
    targets.append(InstallTarget("vscode-workspace", project_dir / ".vscode" / "mcp.json", "json"))

    # Gemini CLI
    targets.append(InstallTarget("gemini-cli", _home() / ".gemini" / "settings.json", "json"))

    return targets


def install(
    *,
    project_dir: Path,
    dry_run: bool,
    scope: str,
    transport: str,
    enable_ssh: bool,
) -> dict[str, Any]:
    python = sys.executable

    server_id = "vaultwares-mcp"
    stdio_value = {"command": python, "args": ["-m", "vaultwares_fastmcp"], "env": {}}
    http_value = {"url": "http://127.0.0.1:8000/mcp"}

    server_value = http_value if transport == "http" else stdio_value
    if enable_ssh:
        if "env" not in server_value or not isinstance(server_value.get("env"), dict):
            server_value["env"] = {}
        server_value["env"]["VAULTWARES_MCP_ENABLE_SSH"] = "1"

    results: list[dict[str, Any]] = []

    for t in discover_targets(project_dir):
        if scope == "project" and t.name in {"codex", "claude-desktop", "claude-desktop-macos", "gemini-cli"}:
            continue
        if scope == "global" and t.name in {"project-mcp", "vscode-workspace"}:
            continue

        if t.kind == "toml":
            if not t.path.exists():
                # If Codex isn't installed, don't create a new file silently.
                results.append({"target": t.name, "path": str(t.path), "changed": False, "skipped": "missing"})
                continue
            before = _read_text(t.path)
            block_lines = [
                f'command = "{python}"',
                'args = ["-m", "vaultwares_fastmcp"]',
                "enabled = true",
                "startup_timeout_sec = 10",
            ]
            if enable_ssh:
                block_lines.insert(2, 'env = { VAULTWARES_MCP_ENABLE_SSH = "1" }')
            after, changed = _patch_toml_add_block(before, f"mcp_servers.{server_id}", block_lines)
            if changed and not dry_run:
                _backup(t.path)
                _write_text(t.path, after)
            results.append({"target": t.name, "path": str(t.path), "changed": changed, "skipped": None})
            continue

        if t.kind == "json":
            data = _json_load(t.path)
            # Claude Desktop uses top-level "mcpServers"
            key = "mcpServers"
            patched, changed = _patch_json_mcpserver(data, server_id, server_value, key=key)
            if changed and not dry_run:
                if t.path.exists():
                    _backup(t.path)
                _json_dump(t.path, patched, pretty=True)
            results.append({"target": t.name, "path": str(t.path), "changed": changed, "skipped": None})
            continue

    snippet = json.dumps({"mcpServers": {server_id: server_value}}, indent=2) + "\n"
    return {"ok": True, "results": results, "paste_snippet": snippet}


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Install VaultWares MCP into common MCP hosts.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--scope", choices=["global", "project"], default="global")
    parser.add_argument("--transport", choices=["stdio", "http"], default="stdio")
    parser.add_argument("--enable-ssh", action="store_true")
    args = parser.parse_args(argv)

    result = install(
        project_dir=Path.cwd(),
        dry_run=bool(args.dry_run),
        scope=str(args.scope),
        transport=str(args.transport),
        enable_ssh=bool(args.enable_ssh),
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
