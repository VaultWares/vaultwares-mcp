#!/usr/bin/env bash
set -euo pipefail

# VaultWares MCP installer.
#
# This script is intentionally thin: the real installer is the cross-platform
# Python module `vaultwares_fastmcp.installer`.

PYTHON_BIN="${PYTHON_BIN:-python}"

exec "${PYTHON_BIN}" -m vaultwares_fastmcp.installer "$@"

