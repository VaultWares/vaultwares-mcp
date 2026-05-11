from __future__ import annotations

import shutil
import subprocess
import time
from typing import Any


def ssh_run(
    host: str,
    command: str,
    *,
    user: str | None = None,
    port: int = 22,
    timeout_ms: int = 60000,
    identity_file: str | None = None,
) -> dict[str, Any]:
    ssh = shutil.which("ssh")
    if not ssh:
        return {"exit_code": None, "stdout": "", "stderr": "ssh binary not found on PATH", "duration_ms": 0}

    target = f"{user}@{host}" if user else host
    args: list[str] = [ssh, "-p", str(int(port)), target, "--", command]
    if identity_file:
        args[1:1] = ["-i", identity_file]

    start = time.monotonic()
    try:
        cp = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=max(0.001, timeout_ms / 1000),
        )
        dur_ms = int((time.monotonic() - start) * 1000)
        return {"exit_code": cp.returncode, "stdout": cp.stdout or "", "stderr": cp.stderr or "", "duration_ms": dur_ms}
    except subprocess.TimeoutExpired as exc:
        dur_ms = int((time.monotonic() - start) * 1000)
        out = (exc.stdout or "") if isinstance(exc.stdout, str) else ""
        err = (exc.stderr or "") if isinstance(exc.stderr, str) else ""
        return {"exit_code": None, "stdout": out, "stderr": f"Timeout after {timeout_ms}ms\n{err}", "duration_ms": dur_ms}

