"""
Live integration tests for the vaultwares-mcp server running on http://127.0.0.1:9020/mcp.
Run with:  python tests/test_live_server.py
"""

from __future__ import annotations

import asyncio
import json
import sys
import traceback
from typing import Any

SERVER_URL = "http://127.0.0.1:9020/mcp"

PASS = "\033[32mPASS\033[0m"
FAIL = "\033[31mFAIL\033[0m"
SKIP = "\033[33mSKIP\033[0m"

results: list[dict] = []


def _ok(name: str, detail: str = "") -> None:
    results.append({"name": name, "status": "PASS", "detail": detail})
    print(f"  [{PASS}] {name}" + (f" — {detail}" if detail else ""))


def _fail(name: str, detail: str = "") -> None:
    results.append({"name": name, "status": "FAIL", "detail": detail})
    print(f"  [{FAIL}] {name}" + (f" — {detail}" if detail else ""))


def _skip(name: str, reason: str = "") -> None:
    results.append({"name": name, "status": "SKIP", "detail": reason})
    print(f"  [{SKIP}] {name}" + (f" — {reason}" if reason else ""))


def check(name: str, result: Any, *, must_contain: list[str] | None = None, error_ok: bool = False) -> bool:
    """Generic checker: result must be a dict, no non-null 'error' unless error_ok, must contain given keys."""
    if not isinstance(result, dict):
        _fail(name, f"result is not a dict: {type(result).__name__} = {str(result)[:120]}")
        return False
    if not error_ok and result.get("error") is not None:
        _fail(name, f"unexpected error: {result['error']}")
        return False
    if must_contain:
        missing = [k for k in must_contain if k not in result]
        if missing:
            _fail(name, f"missing keys: {missing}")
            return False
    _ok(name, json.dumps({k: result[k] for k in (must_contain or [])[:3]}, default=str)[:100])
    return True


async def run_all():
    from fastmcp import Client
    from fastmcp.client.transports import StreamableHttpTransport

    transport = StreamableHttpTransport(SERVER_URL)
    async with Client(transport) as client:

        # ------------------------------------------------------------------
        # 0. tools/list
        # ------------------------------------------------------------------
        print("\n[tools/list]")
        tools = await client.list_tools()
        tool_names = {t.name for t in tools}
        print(f"  Discovered {len(tools)} tools: {sorted(tool_names)}")
        if len(tools) == 0:
            _fail("tools/list", "no tools returned")
        else:
            _ok("tools/list", f"{len(tools)} tools found")

        # ------------------------------------------------------------------
        # Helper to call a tool
        # ------------------------------------------------------------------
        async def call(name: str, **kwargs) -> Any:
            try:
                r = await client.call_tool(name, kwargs)
                # fastmcp returns a CallToolResult with .content list and .is_error
                if r.is_error:
                    return {"error": str(r.content)}
                if r.content:
                    item = r.content[0]
                    text = item.text if hasattr(item, "text") else str(item)
                    try:
                        return json.loads(text)
                    except Exception:
                        return {"content": text}
                return {}
            except Exception as exc:
                return {"error": str(exc)}

        # ------------------------------------------------------------------
        # Tier 5: Diagnostics (most reliable, no side effects)
        # ------------------------------------------------------------------
        print("\n[Tier 5: Diagnostics]")
        r = await call("diag_status")
        check("diag_status", r, must_contain=["name", "version", "transport", "pid", "uptime_s"])

        r = await call("diag_usage")
        check("diag_usage", r, must_contain=["tool_calls_total", "per_tool_counts", "bytes_read", "bytes_written"])

        r = await call("diag_limits")
        check("diag_limits", r, must_contain=["configured_limits", "remaining"])

        # ------------------------------------------------------------------
        # Credit Optimizer
        # ------------------------------------------------------------------
        print("\n[Credit Optimizer]")
        r = await call("credit_classify", prompt="Translate this paragraph to French")
        check("credit_classify", r, must_contain=["intent"])

        r = await call("credit_recommend", prompt="Write a Python function to sort a list")
        check("credit_recommend", r, must_contain=["model"])

        r = await call("credit_estimate", prompt="Summarize the history of Rome in 3 paragraphs")
        check("credit_estimate", r, must_contain=["credits_approx"])

        r = await call("credit_optimize", prompt="Please could you kindly help me to write a very detailed and comprehensive summary of the French revolution for my history essay?", max_tokens=200)
        check("credit_optimize", r, must_contain=["optimized_prompt"])

        r = await call("credit_analyze_batch", prompts=["Translate to Spanish", "Debug this Python error", "Write a haiku"])
        check("credit_analyze_batch", r, must_contain=["items", "total_prompts"])

        # ------------------------------------------------------------------
        # Fast Navigation
        # ------------------------------------------------------------------
        print("\n[Fast Navigation]")
        r = await call("nav_fetch", url="http://httpbin.org/get", as_text=True, ttl=60)
        check("nav_fetch", r, must_contain=["content", "status"])

        r = await call("nav_fetch_many", urls=["http://httpbin.org/get", "http://httpbin.org/ip"], as_text=True, ttl=60)
        check("nav_fetch_many", r, must_contain=["results", "total"])

        # ------------------------------------------------------------------
        # Task Estimator
        # ------------------------------------------------------------------
        print("\n[Task Estimator]")
        r = await call("task_estimate", protocols=["code-review"], repos=1, files_read=5, files_changed=2, tools=3, commands=2, include_time_estimates=True)
        check("task_estimate", r, must_contain=["estimated_output_tokens"])

        # ------------------------------------------------------------------
        # Tier 1: Filesystem
        # ------------------------------------------------------------------
        print("\n[Tier 1: Filesystem]")
        r = await call("fs_list_dir", path=".")
        check("fs_list_dir", r, must_contain=["entries"], error_ok=True)

        r = await call("fs_read", path="README.md")
        check("fs_read", r, must_contain=["content"], error_ok=True)

        test_path = "_test_live_write.tmp"
        r = await call("fs_write", path=test_path, content="live test content\n", create_dirs=False, mode="overwrite")
        check("fs_write", r, must_contain=["bytes"], error_ok=True)

        r = await call("fs_edit", path=test_path, match="live test", replace="LIVE TEST", create_backup=False)
        if check("fs_edit", r, must_contain=["applied_count"], error_ok=True):
            if r.get("applied_count", 0) < 1:
                _fail("fs_edit applied_count", f"expected >=1 applied edits, got {r.get('applied_count')}")
            else:
                _ok("fs_edit applied_count", f"applied {r['applied_count']} edit(s)")

        # Clean up test file
        r = await call("fs_write", path=test_path, content="", mode="overwrite")
        # Ignore result

        # ------------------------------------------------------------------
        # Tier 2: Shell sessions
        # ------------------------------------------------------------------
        print("\n[Tier 2: Shell Sessions]")
        r = await call("sh_session_list")
        check("sh_session_list", r, must_contain=["sessions"])

        r = await call("sh_session_start", kind="", cwd=".")
        if check("sh_session_start", r, must_contain=["session_id"]):
            session_id = r["session_id"]

            r = await call("sh_run", session_id=session_id, command="echo hello_from_mcp", timeout_ms=10000)
            passed = check("sh_run", r, must_contain=["stdout"])
            if passed and "hello_from_mcp" not in r.get("stdout", ""):
                _fail("sh_run output", f"expected 'hello_from_mcp' in stdout, got: {r.get('stdout', '')!r}")
            elif passed:
                _ok("sh_run output", "echo output verified")

            r = await call("sh_session_stop", session_id=session_id)
            check("sh_session_stop", r, must_contain=["stopped"])
        else:
            _skip("sh_run", "sh_session_start failed")
            _skip("sh_session_stop", "sh_session_start failed")

        
        # ------------------------------------------------------------------
        # Tier 3: Ledger (agent-ledger + health-ledger)
        # ------------------------------------------------------------------
        print("\n[Tier 6: Ledger]")
        r = await call("agent_ledger_get_recent", n=5)
        check("agent_ledger_get_recent", r, must_contain=["entries"])

        r = await call("agent_ledger_search", query="vaultwares-mcp", n=5)
        check("agent_ledger_search", r, must_contain=["results"])

        r = await call("health_ledger_get_recent", n=5)
        check("health_ledger_get_recent", r, must_contain=["entries"])

        r = await call("health_ledger_search", query="vaultwares", n=5)
        check("health_ledger_search", r, must_contain=["results"])

    # ---------------------------------------------------------------------------
    # Tier 4: Diagnostics
    # ---------------------------------------------------------------------------
    # TODO

def main():
    print(f"=== VaultWares MCP Live Test Suite ===")
    print(f"Target: {SERVER_URL}\n")

    try:
        asyncio.run(run_all())
    except Exception as exc:
        print(f"\n[{FAIL}] Unhandled exception during test run:")
        traceback.print_exc()

    total = len(results)
    passed = sum(1 for r in results if r["status"] == "PASS")
    failed = sum(1 for r in results if r["status"] == "FAIL")
    skipped = sum(1 for r in results if r["status"] == "SKIP")

    print(f"\n{'='*50}")
    print(f"Results: {passed}/{total} passed, {failed} failed, {skipped} skipped")

    if failed:
        print("\nFailed tests:")
        for r in results:
            if r["status"] == "FAIL":
                print(f"  - {r['name']}: {r['detail']}")
        sys.exit(1)
    else:
        print("All tests passed!")
        sys.exit(0)


if __name__ == "__main__":
    main()
