from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class PathEscapeError(ValueError):
    pass


def _is_within(child: Path, root: Path) -> bool:
    try:
        child.relative_to(root)
        return True
    except Exception:  # noqa: BLE001
        return False


def resolve_scoped(root: Path, user_path: str) -> Path:
    if not isinstance(user_path, str) or not user_path.strip():
        user_path = "."

    p = Path(user_path)

    if p.is_absolute():
        raise PathEscapeError("Absolute paths are not allowed (scoped to server working directory).")

    candidate = (root / p).resolve()

    if not _is_within(candidate, root):
        raise PathEscapeError("Path escapes root scope.")

    # Deny symlink escape: walk parents and ensure no symlink points outside root
    # (best-effort: if target doesn't exist yet, we validate existing parents).
    cur = candidate
    while True:
        if cur.exists() and cur.is_symlink():
            target = cur.resolve()
            if not _is_within(target, root):
                raise PathEscapeError("Symlink resolves outside root scope.")
        if cur == root:
            break
        cur = cur.parent

    return candidate


@dataclass(frozen=True)
class FsListEntry:
    name: str
    path: str
    kind: str
    size: int | None


def fs_list(root: Path, path: str = ".") -> dict[str, Any]:
    scoped = resolve_scoped(root, path)
    if not scoped.exists():
        return {"entries": [], "error": "Path does not exist."}
    if not scoped.is_dir():
        return {"entries": [], "error": "Path is not a directory."}

    entries: list[FsListEntry] = []
    for child in sorted(scoped.iterdir(), key=lambda p: p.name.lower()):
        kind = "dir" if child.is_dir() else "file"
        size = None
        if child.is_file():
            try:
                size = child.stat().st_size
            except Exception:  # noqa: BLE001
                size = None
        rel = str(child.relative_to(root)).replace("\\", "/")
        entries.append(FsListEntry(name=child.name, path=rel, kind=kind, size=size))

    return {"entries": [e.__dict__ for e in entries], "error": None}


def fs_read_text(root: Path, path: str, max_bytes: int) -> dict[str, Any]:
    scoped = resolve_scoped(root, path)
    if not scoped.exists() or not scoped.is_file():
        return {"content": None, "bytes": 0, "error": "File not found."}

    size = scoped.stat().st_size
    if size > max_bytes:
        return {
            "content": None,
            "bytes": 0,
            "error": f"File exceeds max_read_bytes ({size} > {max_bytes}).",
        }

    data = scoped.read_bytes()
    try:
        content = data.decode("utf-8")
    except UnicodeDecodeError:
        content = data.decode("utf-8", errors="replace")
    return {"content": content, "bytes": len(data), "error": None}


def fs_write_text(
    root: Path,
    path: str,
    content: str,
    create_dirs: bool,
    mode: str,
    max_bytes: int,
) -> dict[str, Any]:
    if not isinstance(content, str):
        raise ValueError("content must be a string")

    scoped = resolve_scoped(root, path)
    if create_dirs:
        scoped.parent.mkdir(parents=True, exist_ok=True)

    encoded = content.encode("utf-8")
    if len(encoded) > max_bytes:
        return {
            "bytes": 0,
            "error": f"Write exceeds max_write_bytes ({len(encoded)} > {max_bytes}).",
        }

    if mode not in {"overwrite", "append"}:
        mode = "overwrite"

    if mode == "append":
        with scoped.open("ab") as f:
            f.write(encoded)
    else:
        scoped.write_bytes(encoded)

    return {"bytes": len(encoded), "error": None}


def fs_edit_text(
    root: Path,
    path: str,
    edits: list[dict[str, Any]],
    create_backup: bool,
    max_bytes: int,
) -> dict[str, Any]:
    scoped = resolve_scoped(root, path)
    if not scoped.exists() or not scoped.is_file():
        return {"applied_count": 0, "error": "File not found."}

    raw = scoped.read_bytes()
    if len(raw) > max_bytes:
        return {"applied_count": 0, "error": f"File exceeds max_read_bytes ({len(raw)} > {max_bytes})."}
    text = raw.decode("utf-8", errors="replace")

    original_text = text
    applied = 0

    for e in edits or []:
        if not isinstance(e, dict):
            continue

        if "match" in e:
            match = str(e.get("match", ""))
            replace = str(e.get("replace", ""))
            count = e.get("count")
            try:
                count_int = int(count) if count is not None else 0
            except Exception:  # noqa: BLE001
                count_int = 0
            before = text
            if count_int and count_int > 0:
                text = text.replace(match, replace, count_int)
            else:
                text = text.replace(match, replace)
            if text != before:
                applied += 1
            continue

        if "range" in e:
            # range is 1-based inclusive line numbers: { "range": {"start":1,"end":3}, "replace":"..." }
            r = e.get("range") or {}
            try:
                start = int(r.get("start"))
                end = int(r.get("end"))
            except Exception:  # noqa: BLE001
                continue
            if start <= 0 or end < start:
                continue
            replace = str(e.get("replace", ""))
            lines = text.splitlines(keepends=True)
            if start > len(lines):
                continue
            end = min(end, len(lines))
            before = "".join(lines)
            lines[start - 1 : end] = [replace if replace.endswith(("\n", "\r\n")) else replace + "\n"]
            text = "".join(lines)
            if text != before:
                applied += 1
            continue

    if text == original_text:
        return {"applied_count": 0, "error": None}

    if create_backup:
        backup = scoped.with_suffix(scoped.suffix + ".bak")
        try:
            shutil.copy2(scoped, backup)
        except Exception:  # noqa: BLE001
            pass

    encoded = text.encode("utf-8")
    if len(encoded) > max_bytes:
        return {"applied_count": 0, "error": f"Edited file exceeds max_write_bytes ({len(encoded)} > {max_bytes})."}
    scoped.write_bytes(encoded)
    return {"applied_count": applied, "error": None}

