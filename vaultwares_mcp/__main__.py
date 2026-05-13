from __future__ import annotations

import os
import sys

if not __package__:
    # Executed as `python vaultwares_mcp` (script mode, no package context).
    # Add the project root to sys.path so `vaultwares_mcp` and `tools` are importable.
    _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if _root not in sys.path:
        sys.path.insert(0, _root)
    from vaultwares_mcp.server import main
else:
    # Executed as `python -m vaultwares_mcp` — package context is set.
    from .server import main

if __name__ == "__main__":
    main()

