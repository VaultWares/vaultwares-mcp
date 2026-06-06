"""
Ledger tooling — agent-ledger + health-ledger readers.

Two stores, two on-disk shapes:

  agent-ledger  C:/.../agent-ledger/events/<year>/<month>/<file>.json
                One file per event. Fields: Project, Kind, Summary, Files,
                Commands, Actor, AgentRole, Model, Mode, etc.

  health-ledger C:/.../health-ledger/data/events/<year>/<month>/<day>.jsonl
                One JSONL line per event. Fields: event_type, run_id,
                timestamp, service_id, service_name, path_id, url, repo,
                ok, status_code, duration_ms, failure_class, etc.

Roots are overridable via env vars:
  VW_AGENT_LEDGER_ROOT   default: C:/Users/Administrator/Desktop/Github Repos/agent-ledger/events
  VW_HEALTH_LEDGER_ROOT  default: C:/Users/Administrator/Desktop/Github Repos/health-ledger/data/events

The four public functions match what `vaultwares_mcp.server` imports.
The old `get_ledger_entries` / `search_ledger` names are kept as aliases for
back-compat with any caller that lingered on the pre-split API.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from typing import Iterable, Optional

# ─── roots ──────────────────────────────────────────────────────────────────

_DEFAULT_AGENT_LEDGER_ROOT = (
    r"C:\Users\Administrator\Desktop\Github Repos\agent-ledger\events"
)
_DEFAULT_HEALTH_LEDGER_ROOT = (
    r"C:\Users\Administrator\Desktop\Github Repos\health-ledger\data\events"
)


def _agent_root() -> str:
    return os.environ.get("VW_AGENT_LEDGER_ROOT", _DEFAULT_AGENT_LEDGER_ROOT)


def _health_root() -> str:
    return os.environ.get("VW_HEALTH_LEDGER_ROOT", _DEFAULT_HEALTH_LEDGER_ROOT)


# ─── shared helpers ────────────────────────────────────────────────────────

def _parse_date(date: Optional[str]) -> datetime:
    if not date:
        return datetime.now()
    try:
        return datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        return datetime.now()


def _iter_months_backwards(start: datetime, stop_year: int = 2025) -> Iterable[tuple[int, int]]:
    """Yield (year, month) tuples backwards from `start` until `stop_year`."""
    year, month = start.year, start.month
    while year >= stop_year:
        yield year, month
        month -= 1
        if month == 0:
            month = 12
            year -= 1


def _iter_days_backwards(start: datetime, stop_year: int = 2025) -> Iterable[datetime]:
    """Yield datetimes one day at a time backwards from `start` until `stop_year`."""
    cursor = datetime(start.year, start.month, start.day)
    stop = datetime(stop_year, 1, 1)
    while cursor >= stop:
        yield cursor
        cursor -= timedelta(days=1)


# ─── agent-ledger ──────────────────────────────────────────────────────────

def get_agent_ledger_entries(
    n: int = 25,
    project: Optional[str] = None,
    kind: Optional[str] = None,
    model: Optional[str] = None,
    assistant: Optional[str] = None,
    date: Optional[str] = None,
) -> list[dict]:
    """
    Fetch the last N agent-ledger entries with optional filters.

    Filters are case-insensitive substring matches on the corresponding
    top-level field. `date` is `YYYY-MM-DD`; when set, only entries whose
    file name starts with the compact form (e.g. `20260606-`) are returned.
    """
    root = _agent_root()
    if not os.path.isdir(root):
        return []

    out: list[dict] = []
    target = _parse_date(date)
    compact_date = target.strftime("%Y%m%d") if date else None

    for year, month in _iter_months_backwards(target):
        if len(out) >= n:
            break
        month_dir = os.path.join(root, str(year), f"{month:02d}")
        if not os.path.isdir(month_dir):
            continue
        # newest first
        for fname in sorted(os.listdir(month_dir), reverse=True):
            if len(out) >= n:
                break
            if not fname.endswith(".json"):
                continue
            if compact_date and not fname.startswith(compact_date):
                continue
            path = os.path.join(month_dir, fname)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except (OSError, json.JSONDecodeError):
                continue
            # Real schema is camelCase (`project`, `kind`, `actor`, with
            # `model` nested under `runtime`). Accept PascalCase as a
            # fallback for any older entries.
            field_project = data.get("project") or data.get("Project") or ""
            field_kind = data.get("kind") or data.get("Kind") or ""
            field_actor = data.get("actor") or data.get("Actor") or ""
            runtime = data.get("runtime") if isinstance(data.get("runtime"), dict) else {}
            field_model = runtime.get("model") or data.get("model") or data.get("Model") or ""

            if project and project.lower() not in str(field_project).lower():
                continue
            if kind and kind.lower() not in str(field_kind).lower():
                continue
            if model and model.lower() not in str(field_model).lower():
                continue
            if assistant and assistant.lower() not in str(field_actor).lower():
                continue
            out.append(data)
    return out


def search_agent_ledger(query: str, n: int = 10) -> list[dict]:
    """
    Substring search across recent agent-ledger entries.
    Searches Summary, PlanPath, Files, Commands, and Project.
    Scans the most recent ~200 entries and returns the first N matches.
    """
    if not query:
        return []
    q = query.lower()
    matches: list[dict] = []
    for entry in get_agent_ledger_entries(n=200):
        haystack_parts = [
            str(entry.get("summary") or entry.get("Summary") or ""),
            str(entry.get("planPath") or entry.get("PlanPath") or ""),
            str(entry.get("project") or entry.get("Project") or ""),
        ]
        files = entry.get("files") or entry.get("Files")
        if isinstance(files, list):
            haystack_parts.extend(str(x) for x in files)
        cmds = entry.get("commands") or entry.get("Commands")
        if isinstance(cmds, list):
            haystack_parts.extend(str(x) for x in cmds)
        if q in " ".join(haystack_parts).lower():
            matches.append(entry)
            if len(matches) >= n:
                break
    return matches


# ─── health-ledger ─────────────────────────────────────────────────────────

def get_health_ledger_entries(
    n: int = 25,
    service_id: Optional[str] = None,
    run_id: Optional[str] = None,
    ok: Optional[bool] = None,
    event_type: Optional[str] = None,
    date: Optional[str] = None,
) -> list[dict]:
    """
    Fetch the last N health-ledger probe events with optional filters.

    Filters:
      service_id   case-insensitive substring
      run_id       case-insensitive substring
      ok           True/False match
      event_type   case-insensitive substring (e.g. "probe_result")
      date         YYYY-MM-DD: restricts to that day's file only

    Reads `<root>/<year>/<month>/<day>.jsonl`, one JSON object per line.
    """
    root = _health_root()
    if not os.path.isdir(root):
        return []

    out: list[dict] = []
    target = _parse_date(date)

    if date:
        day_path = os.path.join(
            root,
            f"{target.year:04d}",
            f"{target.month:02d}",
            f"{target.day:02d}.jsonl",
        )
        if os.path.isfile(day_path):
            _consume_jsonl(day_path, out, n, service_id, run_id, ok, event_type, reverse=True)
        return out

    for day in _iter_days_backwards(target):
        if len(out) >= n:
            break
        day_path = os.path.join(
            root,
            f"{day.year:04d}",
            f"{day.month:02d}",
            f"{day.day:02d}.jsonl",
        )
        if not os.path.isfile(day_path):
            continue
        _consume_jsonl(day_path, out, n, service_id, run_id, ok, event_type, reverse=True)
    return out


def _consume_jsonl(
    path: str,
    out: list[dict],
    n: int,
    service_id: Optional[str],
    run_id: Optional[str],
    ok: Optional[bool],
    event_type: Optional[str],
    reverse: bool = True,
) -> None:
    """Read a JSONL file and append matching records to `out` up to `n`."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except OSError:
        return
    if reverse:
        lines = list(reversed(lines))
    for raw in lines:
        if len(out) >= n:
            return
        raw = raw.strip()
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if service_id and service_id.lower() not in str(data.get("service_id", "")).lower():
            continue
        if run_id and run_id.lower() not in str(data.get("run_id", "")).lower():
            continue
        if event_type and event_type.lower() not in str(data.get("event_type", "")).lower():
            continue
        if ok is not None and bool(data.get("ok")) != bool(ok):
            continue
        out.append(data)


def search_health_ledger(query: str, n: int = 10) -> list[dict]:
    """
    Substring search across recent health-ledger events.
    Searches service_id, service_name, url, repo, failure_class, error,
    skipped_reason, and event_type. Scans the most recent ~500 entries.
    """
    if not query:
        return []
    q = query.lower()
    matches: list[dict] = []
    for entry in get_health_ledger_entries(n=500):
        haystack = " ".join(
            str(entry.get(k, ""))
            for k in (
                "service_id",
                "service_name",
                "url",
                "repo",
                "failure_class",
                "error",
                "skipped_reason",
                "event_type",
                "path_id",
                "probe_location_id",
            )
        ).lower()
        if q in haystack:
            matches.append(entry)
            if len(matches) >= n:
                break
    return matches


# ─── back-compat aliases ───────────────────────────────────────────────────

# Pre-split names; kept so any lingering caller from the hallucinated-API
# window doesn't crash.
get_ledger_entries = get_agent_ledger_entries
search_ledger = search_agent_ledger


__all__ = [
    "get_agent_ledger_entries",
    "search_agent_ledger",
    "get_health_ledger_entries",
    "search_health_ledger",
    "get_ledger_entries",
    "search_ledger",
]
