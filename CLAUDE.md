# VaultWares — Claude Code pre-instructions (repo stub)

> ⚠ **READ `CRITICAL.md` BEFORE TOUCHING ANY CODE IN THIS REPO.**
> The shipped `vaultwares_mcp/server.py` currently has an ImportError at
> module load (hallucinated ledger API). All tools served by this MCP are
> unreachable until that's fixed. Do not pattern-match on the existing
> imports — they're the source of the bug.

This file is intentionally short. It routes work to the company protocol TOC.
Always start at: `C:\Users\Administrator\Desktop\Github Repos\vaultwares-docs\instructions\ROUTER.md`
Execute the ROUTER routine first (always): scan all protocol categories end-to-end, select relevant categories, then open only the selected summaries in category order.
Execute other routines only when relevant (tools/routines). Ledger is always the last step before replying.
Estimate step (mandatory): compute `estimated_output_tokens` after reading required summaries; if >=8000 apply overlay `LONG_RUNNING_TASKS` and include/resume from `VW_STATE` without recomputing the estimate.
Read full notes only when explicitly prompted: `read full notes`
Mandatory ledger (last step before replying): use `C:\Users\Administrator\Desktop\Github Repos\agent-ledger\scripts\record-agent-change.ps1`

