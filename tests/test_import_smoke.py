"""
Import-smoke gate.

Catches the class of regression that took the server offline on 2026-06-05:
a tool tier added a `from .ledger_tools import (...)` block referencing
symbols that never existed in `ledger_tools.py`. The package was shipped
without anyone running `python -c "import vaultwares_mcp.server"`.

Runs without pytest — pytest-collectable too, but a bare
`python tests/test_import_smoke.py` is enough.
"""
from __future__ import annotations

import importlib
import sys


REQUIRED_LEDGER_FUNCTIONS = (
    "get_agent_ledger_entries",
    "search_agent_ledger",
    "get_health_ledger_entries",
    "search_health_ledger",
)

REQUIRED_CLI_TOOLS = (
    "run_agent_ledger_record_change",
    "run_agent_ledger_render_ledger",
    "run_agent_ledger_render_impact",
    "run_agent_ledger_sync_ledger",
    "run_health_ledger_probe",
)


def test_server_module_imports() -> None:
    mod = importlib.import_module("vaultwares_mcp.server")
    assert mod is not None
    # Spot-check that the module exposes the FastMCP server object the
    # entrypoint expects to call .run() on.
    assert hasattr(mod, "mcp"), "vaultwares_mcp.server.mcp missing"


def test_ledger_tools_exports_all_functions() -> None:
    lt = importlib.import_module("vaultwares_mcp.ledger_tools")
    for fn_name in REQUIRED_LEDGER_FUNCTIONS:
        assert hasattr(lt, fn_name), (
            f"vaultwares_mcp.ledger_tools.{fn_name} missing — "
            "this is the regression that took the server offline on 2026-06-05."
        )
        assert callable(getattr(lt, fn_name)), f"{fn_name} is not callable"


def test_ledger_tools_return_shape() -> None:
    """Each fn must return a list (possibly empty) and not raise on default args."""
    lt = importlib.import_module("vaultwares_mcp.ledger_tools")
    assert isinstance(lt.get_agent_ledger_entries(n=1), list)
    assert isinstance(lt.search_agent_ledger("vaultwares", n=1), list)
    assert isinstance(lt.get_health_ledger_entries(n=1), list)
    assert isinstance(lt.search_health_ledger("vaultwares", n=1), list)


def test_cli_tools_exports_all_functions() -> None:
    ct = importlib.import_module("vaultwares_mcp.vw_cli_tools")
    for fn_name in REQUIRED_CLI_TOOLS:
        assert hasattr(ct, fn_name), f"vaultwares_mcp.vw_cli_tools.{fn_name} missing"
        assert callable(getattr(ct, fn_name)), f"{fn_name} is not callable"


if __name__ == "__main__":  # bare-script invocation
    failures: list[str] = []
    for name in ("test_server_module_imports", "test_ledger_tools_exports_all_functions", "test_ledger_tools_return_shape", "test_cli_tools_exports_all_functions"):
        try:
            globals()[name]()
            print(f"  OK  {name}")
        except AssertionError as e:
            print(f"  FAIL {name}: {e}")
            failures.append(name)
        except Exception as e:  # noqa: BLE001
            print(f"  FAIL {name}: {e.__class__.__name__}: {e}")
            failures.append(name)
    sys.exit(1 if failures else 0)
