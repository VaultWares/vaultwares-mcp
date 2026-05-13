"""Compatibility wrapper for the VaultWares MCP server.

Prefer `python -m vaultwares_mcp` or the `vaultwares-mcp` entrypoint.
When launched by Claude Desktop's extension mechanism the manifest already
points to the venv Python, but the fallback bootstrap below handles the case
where this file is run with a system Python that lacks the required packages.
"""

from __future__ import annotations

import os
import sys


def _bootstrap_venv() -> None:
    """Inject venv site-packages into sys.path when fastmcp is not importable."""
    try:
        import fastmcp  # noqa: F401  # already available
        return
    except ImportError:
        pass

    candidates: list[str] = []

    # 1. Explicit env var set by manifest (extension context)
    venv_site = os.environ.get("VAULTWARES_VENV_SITE")
    if venv_site:
        candidates.append(venv_site)

    # 2. .venv sibling of this file (project-dir context)
    here = os.path.dirname(os.path.abspath(__file__))
    for _ in range(4):  # walk up to 4 levels
        candidate = os.path.join(here, ".venv", "Lib", "site-packages")
        if os.path.isdir(candidate):
            candidates.append(candidate)
            break
        here = os.path.dirname(here)

    for site_pkg in candidates:
        if os.path.isdir(site_pkg) and site_pkg not in sys.path:
            sys.path.insert(0, site_pkg)
        try:
            import fastmcp  # noqa: F401
            return
        except ImportError:
            continue


_bootstrap_venv()

from vaultwares_mcp.server import main  # noqa: E402


if __name__ == "__main__":
    main()
