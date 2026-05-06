from __future__ import annotations

import os
import secrets
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .fs_tools import resolve_scoped


@dataclass
class ShellSession:
    session_id: str
    kind: str
    cwd: Path
    created_at: float = field(default_factory=time.time)
    last_used_at: float = field(default_factory=time.time)
    env: dict[str, str] = field(default_factory=dict)


class ShellSessionManager:
    def __init__(self, root: Path) -> None:
        self._root = root
        self._sessions: dict[str, ShellSession] = {}

    def start(self, kind: str | None, cwd: str | None) -> ShellSession:
        if not kind:
            kind = "powershell" if os.name == "nt" else "bash"
        if kind not in {"powershell", "bash"}:
            kind = "powershell" if os.name == "nt" else "bash"
        scoped = resolve_scoped(self._root, cwd or ".")
        if scoped.exists() and not scoped.is_dir():
            scoped = scoped.parent
        scoped.mkdir(parents=True, exist_ok=True)
        session_id = secrets.token_urlsafe(12)
        sess = ShellSession(session_id=session_id, kind=kind, cwd=scoped)
        self._sessions[session_id] = sess
        return sess

    def list(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for s in self._sessions.values():
            out.append(
                {
                    "session_id": s.session_id,
                    "kind": s.kind,
                    "cwd": str(s.cwd),
                    "created_at": s.created_at,
                    "last_used_at": s.last_used_at,
                }
            )
        return out

    def stop(self, session_id: str) -> bool:
        return self._sessions.pop(session_id, None) is not None

    def run(
        self,
        session_id: str,
        command: str,
        timeout_ms: int,
        cwd: str | None,
        env: dict[str, str] | None,
        max_output_bytes: int,
    ) -> dict[str, Any]:
        sess = self._sessions.get(session_id)
        if not sess:
            return {"exit_code": None, "stdout": "", "stderr": "Unknown session_id", "duration_ms": 0}

        run_cwd = sess.cwd
        if cwd is not None:
            run_cwd = resolve_scoped(self._root, cwd)
            if run_cwd.exists() and not run_cwd.is_dir():
                run_cwd = run_cwd.parent
            sess.cwd = run_cwd

        merged_env = dict(os.environ)
        merged_env.update(sess.env)
        if env:
            for k, v in env.items():
                if not isinstance(k, str):
                    continue
                merged_env[k] = str(v)

        start = time.monotonic()

        if sess.kind == "powershell":
            exe = "powershell" if os.name == "nt" else "pwsh"
            args = [exe, "-NoLogo", "-NoProfile", "-Command", command]
        else:
            exe = "bash"
            args = [exe, "-lc", command]

        try:
            cp = subprocess.run(
                args,
                cwd=str(run_cwd),
                env=merged_env,
                capture_output=True,
                text=True,
                timeout=max(0.001, timeout_ms / 1000),
            )
            stdout = cp.stdout or ""
            stderr = cp.stderr or ""
            # Output cap (truncate)
            stdout_b = stdout.encode("utf-8", errors="ignore")
            stderr_b = stderr.encode("utf-8", errors="ignore")
            if len(stdout_b) > max_output_bytes:
                stdout = stdout_b[:max_output_bytes].decode("utf-8", errors="replace") + "\n…(truncated)…"
            if len(stderr_b) > max_output_bytes:
                stderr = stderr_b[:max_output_bytes].decode("utf-8", errors="replace") + "\n…(truncated)…"
            dur_ms = int((time.monotonic() - start) * 1000)
            sess.last_used_at = time.time()
            return {"exit_code": cp.returncode, "stdout": stdout, "stderr": stderr, "duration_ms": dur_ms}
        except subprocess.TimeoutExpired as exc:
            dur_ms = int((time.monotonic() - start) * 1000)
            sess.last_used_at = time.time()
            out = (exc.stdout or "") if isinstance(exc.stdout, str) else ""
            err = (exc.stderr or "") if isinstance(exc.stderr, str) else ""
            return {"exit_code": None, "stdout": out, "stderr": f"Timeout after {timeout_ms}ms\n{err}", "duration_ms": dur_ms}

