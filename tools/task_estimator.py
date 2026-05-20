"""Task estimate tool (token-first).

This tool is deliberately decoupled from credit optimization.
Primary output: estimated_output_tokens.
Optional output: derived model execution time per provider (TTFT + tokens/TPS).

Notes:
- Tokens are the solid estimate in AI environments.
- "Time" here means model execution time, not human time.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ProviderRate:
    provider: str
    model: str
    ttft_s: float
    tps: float


# User-provided reference table (May 2026). Treated as configuration.
_PROVIDER_RATES: list[ProviderRate] = [
    ProviderRate("OpenAI (ChatGPT)", "GPT-5.5", 0.60, 92.0),
    ProviderRate("Anthropic (Claude)", "Claude Opus 4.7", 1.60, 67.0),
    ProviderRate("Anthropic (Claude)", "Claude Sonnet 4.6", 0.73, 55.0),
    ProviderRate("Google (Gemini)", "Gemini 3.1 Pro", 0.80, 60.0),
    ProviderRate("Google (Gemini)", "Gemini 3 Flash", 0.15, 200.0),
    ProviderRate("Microsoft (Copilot Pro)", "GPT-5.4 / GPT-5.5", 1.00, 92.0),
]


_PROTOCOL_WEIGHTS: dict[str, int] = {
    "MULTI_AGENT_FLOW": 1400,
    "NETWORK_INFRASTRUCTURE": 900,
    "DEPLOYMENT_POLICY": 900,
    "INCIDENT_RESPONSE": 900,
    "GUI_VERIFICATION": 700,
    "BACKUP_EXPORT_POLICY": 700,
    "CLEANUP_REFACTOR": 600,
    "HANDLING_BUGS": 500,
    "SECURITY_POSTURE": 600,
    "SECRETS_HANDLING": 400,
    "DOCS_STANDARDS": 350,
    "PR_POLICY": 350,
    "VERIFICATION": 350,
    "LONG_RUNNING_TASKS": 0,
}


def estimate_task(
    *,
    protocols: list[str] | None = None,
    repos: int = 1,
    files_read: int = 0,
    files_changed: int = 0,
    tools: int = 0,
    commands: int = 0,
    include_time_estimates: bool = True,
) -> dict[str, Any]:
    """Return a token-first estimate for a task."""

    normalized_protocols = [
        str(x).strip().upper() for x in (protocols or []) if str(x).strip()
    ]

    base = 500
    add_repos = max(0, int(repos) - 1) * 250
    add_read = max(0, int(files_read)) * 150
    add_changed = max(0, int(files_changed)) * 320
    add_tools = max(0, int(tools)) * 120
    add_cmds = max(0, int(commands)) * 90

    add_protocols = 0
    for proto in normalized_protocols:
        add_protocols += int(_PROTOCOL_WEIGHTS.get(proto, 0))

    estimated = (
        base + add_repos + add_read + add_changed + add_tools + add_cmds + add_protocols
    )
    if estimated < 1:
        estimated = 1

    rationale_parts: list[str] = []
    rationale_parts.append(f"base={base}")
    if add_repos:
        rationale_parts.append(f"repos={add_repos}")
    if add_read:
        rationale_parts.append(f"files_read={add_read}")
    if add_changed:
        rationale_parts.append(f"files_changed={add_changed}")
    if add_tools:
        rationale_parts.append(f"tools={add_tools}")
    if add_cmds:
        rationale_parts.append(f"commands={add_cmds}")
    if add_protocols:
        rationale_parts.append(f"protocols={add_protocols}")
    rationale_parts.append(f"total={estimated}")

    out: dict[str, Any] = {
        "estimated_output_tokens": int(estimated),
        "rationale": ", ".join(rationale_parts),
        "protocols": normalized_protocols,
    }

    if include_time_estimates:
        time_rows = []
        for rate in _PROVIDER_RATES:
            total_s = float(rate.ttft_s) + (float(estimated) / float(rate.tps))
            time_rows.append(
                {
                    "provider": rate.provider,
                    "model": rate.model,
                    "ttft_s": rate.ttft_s,
                    "tps": rate.tps,
                    "estimated_time_s": round(total_s, 3),
                    "formula": "TTFT + (tokens/TPS)",
                }
            )
        out["model_time_estimates"] = time_rows

    return out

