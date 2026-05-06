from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ServerConfig:
    root_dir: Path
    enable_ssh: bool
    max_read_bytes: int
    max_write_bytes: int
    max_shell_output_bytes: int
    default_shell_timeout_ms: int
    rate_limit_per_minute: int


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def load_config() -> ServerConfig:
    root_dir = Path(os.getcwd()).resolve()
    enable_ssh = _env_bool("VAULTWARES_MCP_ENABLE_SSH", False)

    max_read_bytes = int(os.environ.get("VAULTWARES_MCP_MAX_READ_BYTES", str(2 * 1024 * 1024)))
    max_write_bytes = int(os.environ.get("VAULTWARES_MCP_MAX_WRITE_BYTES", str(2 * 1024 * 1024)))
    max_shell_output_bytes = int(
        os.environ.get("VAULTWARES_MCP_MAX_SHELL_OUTPUT_BYTES", str(2 * 1024 * 1024))
    )
    default_shell_timeout_ms = int(os.environ.get("VAULTWARES_MCP_SHELL_TIMEOUT_MS", "60000"))
    rate_limit_per_minute = int(os.environ.get("VAULTWARES_MCP_RATE_LIMIT_PER_MIN", "600"))

    return ServerConfig(
        root_dir=root_dir,
        enable_ssh=enable_ssh,
        max_read_bytes=max_read_bytes,
        max_write_bytes=max_write_bytes,
        max_shell_output_bytes=max_shell_output_bytes,
        default_shell_timeout_ms=default_shell_timeout_ms,
        rate_limit_per_minute=rate_limit_per_minute,
    )

