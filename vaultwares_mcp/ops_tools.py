from __future__ import annotations

import datetime as _dt
import os
from pathlib import Path
from typing import Any


def _ops_root() -> Path:
    env = os.environ.get("VAULTWARES_MCP_OPS_DIR")
    if env:
        return Path(env).expanduser().resolve()
    return (Path.cwd() / ".vaultwares_ops").resolve()


def _append(path: Path, text: str) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = text.encode("utf-8")
    with path.open("ab") as f:
        f.write(data)
    return len(data)


def ops_journal_append(entry: str, date_prefix: bool = True) -> dict[str, Any]:
    root = _ops_root()
    today = _dt.date.today().isoformat()
    path = root / "journal" / f"{today}.md"
    stamp = _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"- {stamp} {entry.strip()}\n" if date_prefix else f"- {entry.strip()}\n"
    n = _append(path, line)
    return {"path": str(path), "bytes": n, "error": None}


def ops_note_append(note: str, topic: str = "general") -> dict[str, Any]:
    root = _ops_root()
    safe_topic = "".join(c for c in (topic or "general") if c.isalnum() or c in {"-", "_"}).strip() or "general"
    path = root / "notes" / f"{safe_topic}.md"
    stamp = _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"- {stamp} {note.strip()}\n"
    n = _append(path, line)
    return {"path": str(path), "bytes": n, "error": None}


def ops_tasklog_append(event: str) -> dict[str, Any]:
    root = _ops_root()
    path = root / "tasklog.jsonl"
    stamp = _dt.datetime.now().isoformat(timespec="seconds")
    line = f'{{"ts":"{stamp}","event":{event!r}}}\n'
    n = _append(path, line)
    return {"path": str(path), "bytes": n, "error": None}

