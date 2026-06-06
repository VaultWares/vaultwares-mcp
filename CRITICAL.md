# CRITICAL — server is broken

**Status as of 2026-06-06:** `vaultwares-mcp` does **not start**. The shipped
`vaultwares_mcp/server.py` imports four ledger functions that do not exist in
`vaultwares_mcp/ledger_tools.py`. An earlier agent hallucinated the API,
wrote tests against the hallucinated names, and shipped the package
(`vaultwares-mcp-3.0.0.mcpb`) without verifying it could be imported.

**Symptom.** Loading the MCP server returns `ImportError` at module load.
Every tool the server is supposed to expose — including `ssh_run`,
`sh_run`, the filesystem tools, the credit / nav tools — is unreachable as
a result. This is what blocked the Prom-King deploy from being driven over
SSH on 2026-06-06.

## The lie

`vaultwares_mcp/server.py` (lines 39-43):

```python
from .ledger_tools import (
    get_agent_ledger_entries,
    search_agent_ledger,
    get_health_ledger_entries,
    search_health_ledger,
)
```

`vaultwares_mcp/ledger_tools.py` defines exactly **one** public function:
`get_ledger_entries(...)`. No `agent_*`, no `health_*`, no `search_*`.

`tests/test_live_server.py` also references the hallucinated names and so
gives a false sense of coverage — the test file imports successfully only
because nothing actually exercises the missing symbols at collection time
(or because a stub silently swallowed the ImportError).

## What to do (in priority order)

1. **Decide whether the ledger feature is desired at all.** The
   `agent-ledger` lives at `C:\Users\Administrator\Desktop\Github Repos\agent-ledger\events\`
   and is well-defined; the `health-ledger` referenced in the hallucinated
   API is not currently a separate artifact in the fleet (we have
   `vaultwares-docs/docs-content/operations/health-ledger.mdx` as a
   *design*, not a populated store).
2. **If yes:** rewrite `ledger_tools.py` to export the four functions
   `server.py` expects (`get_agent_ledger_entries`, `search_agent_ledger`,
   `get_health_ledger_entries`, `search_health_ledger`). The existing
   `get_ledger_entries` is the basis for the agent-ledger pair; the
   health-ledger pair needs to be defined or stubbed against the design doc.
3. **If no:** remove the four ledger imports from `server.py`, delete
   the ledger tool registrations (around `server.py:348-400`, "Tier 6:
   Ledger"), and rewrite the affected tests in `test_live_server.py` to
   match. Bump the manifest version and rebuild the `.mcpb`.
4. **In either case:** the integration test must actually `import server`
   in a fresh process and fail if it can't. Right now nothing catches
   this kind of regression. Add a smoke test that runs
   `python -c "import vaultwares_mcp.server"` before any tool exercise.
5. **Until this is fixed:** keep treating SSH / sh / fs as **unavailable**
   from any Claude session that connects through this MCP. Sessions that
   need to drive remote work should ask the operator to enable the path
   manually (e.g. `VAULTWARES_MCP_ENABLE_SSH=1`, but only after the
   ImportError is resolved).

## How this slipped through

- The hallucinated symbols had plausible names that matched the rest of
  the fleet's vocabulary ("agent-ledger", "health-ledger"), so reviewers
  reading the diff would assume the implementation existed.
- The `.mcpb` was built and committed without a "does the server actually
  start" gate.
- Subsequent agents pattern-matched on the existing import block when
  asked to extend `server.py`, propagating the bad assumption.

Owner: please triage. This file should stay at the repo root until the
server boots clean and the regression test exists.
