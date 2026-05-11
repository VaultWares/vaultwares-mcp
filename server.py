"""Compatibility wrapper for the VaultWares MCP server.

Prefer `python -m vaultwares_mcp` or the `vaultwares-mcp` entrypoint.
"""

from __future__ import annotations

from vaultwares_mcp.server import main


if __name__ == "__main__":
    main()
