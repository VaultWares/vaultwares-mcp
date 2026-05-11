from __future__ import annotations

import time
from dataclasses import dataclass, field
from threading import Lock


@dataclass
class UsageCounters:
    started_at: float = field(default_factory=lambda: time.time())
    tool_calls_total: int = 0
    per_tool_counts: dict[str, int] = field(default_factory=dict)
    bytes_read: int = 0
    bytes_written: int = 0
    shell_ms_total: int = 0
    ssh_ms_total: int = 0


class UsageTracker:
    def __init__(self) -> None:
        self._lock = Lock()
        self._c = UsageCounters()

    def inc_tool(self, name: str) -> None:
        with self._lock:
            self._c.tool_calls_total += 1
            self._c.per_tool_counts[name] = self._c.per_tool_counts.get(name, 0) + 1

    def add_read_bytes(self, n: int) -> None:
        with self._lock:
            self._c.bytes_read += int(max(0, n))

    def add_written_bytes(self, n: int) -> None:
        with self._lock:
            self._c.bytes_written += int(max(0, n))

    def add_shell_ms(self, n: int) -> None:
        with self._lock:
            self._c.shell_ms_total += int(max(0, n))

    def add_ssh_ms(self, n: int) -> None:
        with self._lock:
            self._c.ssh_ms_total += int(max(0, n))

    def snapshot(self) -> UsageCounters:
        with self._lock:
            return UsageCounters(
                started_at=self._c.started_at,
                tool_calls_total=self._c.tool_calls_total,
                per_tool_counts=dict(self._c.per_tool_counts),
                bytes_read=self._c.bytes_read,
                bytes_written=self._c.bytes_written,
                shell_ms_total=self._c.shell_ms_total,
                ssh_ms_total=self._c.ssh_ms_total,
            )

