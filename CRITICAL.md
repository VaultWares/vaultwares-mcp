# CRITICAL — RESOLVED 2026-06-06

> Kept at the repo root as institutional memory. The bug is fixed; the
> story is the value. If you're a new agent landing here, read this once,
> then trust `tests/test_import_smoke.py` to catch the next regression.

## Was

`vaultwares_mcp/server.py` imported four ledger functions
(`get_agent_ledger_entries`, `search_agent_ledger`,
`get_health_ledger_entries`, `search_health_ledger`) that did not exist
in `vaultwares_mcp/ledger_tools.py`. Only `get_ledger_entries` (singular)
was defined. An earlier agent hallucinated the API, wrote tests against
the hallucinated names, and shipped `vaultwares-mcp-3.0.0.mcpb` without
ever running `python -c "import vaultwares_mcp.server"`.

Symptom: ImportError at module load. Every tool the server exposes —
sh_run, fs_*, credit_*, nav_*, ops_*, ledger_* — unreachable.

GitHub: https://github.com/VaultWares/vaultwares-mcp/issues/2

## Now

Fixed in commit (see git log of `vaultwares_mcp/ledger_tools.py`,
2026-06-06):

- All four ledger functions implemented. `get_agent_ledger_entries` +
  `search_agent_ledger` read the existing agent-ledger
  (`<root>/<year>/<month>/<file>.json`, one file per event, camelCase
  fields). `get_health_ledger_entries` + `search_health_ledger` read the
  health-ledger (`<root>/<year>/<month>/<day>.jsonl`, JSONL).
- Roots are env-overridable: `VW_AGENT_LEDGER_ROOT`,
  `VW_HEALTH_LEDGER_ROOT`. Defaults point at the Windows workstation paths.
- Pre-split aliases (`get_ledger_entries`, `search_ledger`) preserved for
  back-compat.
- New `tests/test_import_smoke.py`. Runs as a plain script
  (`python tests/test_import_smoke.py`) or under pytest. Verifies
  `vaultwares_mcp.server` imports cleanly, the four functions are
  present and callable, and they return lists without raising on default
  args. **This is the gate that should have existed.**

## How this slipped through

- The hallucinated symbols had plausible names that matched the rest of
  the fleet vocabulary ("agent-ledger", "health-ledger"), so reviewers
  reading the diff would assume the implementation existed.
- The `.mcpb` was built and committed without a "does the server actually
  start" gate.
- Subsequent agents pattern-matched on the existing import block when
  asked to extend `server.py`, propagating the bad assumption.

## Going forward

- `tests/test_import_smoke.py` MUST stay in CI's required check set
  (or any pre-mcpb-build step). It runs in <2s and catches the entire
  class of "tool added without backing implementation" regression.
- When adding a new tool tier, add the import smoke first, then the
  implementation, then the registration in `server.py`. The order is the
  same one a TDD purist would pick — and for the same reason.
