"""Credit Optimizer tools for the VaultWares Mcp server.

Analyzes prompts to route them to the cheapest Manus AI model that still
delivers identical quality.  Covers four problem categories identified in the
Manus Power Stack:

  1. Wrong model routing  – Simple tasks should run in Standard (or Chat) mode.
  2. No chat detection    – Pure Q&A / brainstorm tasks cost $0 in Chat Mode.
  3. Context bloat        – Accumulated tokens grow exponentially; this tool
                            trims them.
  4. Batch detection      – Related tasks grouped together reduce overhead.
"""

from __future__ import annotations

import re
from typing import Literal

# ---------------------------------------------------------------------------
# Intent classification
# ---------------------------------------------------------------------------

IntentCategory = Literal[
    "code",
    "research",
    "creative",
    "data",
    "translation",
    "bug_fix",
    "documentation",
    "analysis",
    "qa",
    "brainstorm",
    "refactor",
    "mixed",
]

ModelRecommendation = Literal["chat", "standard", "max"]

# Keywords that signal each intent category
_INTENT_PATTERNS: dict[str, list[str]] = {
    "code": [
        r"\bwrite\b.*\bcode\b",
        r"\bcode\b.*\b(function|class|script|module)\b",
        r"\bimplement\b",
        r"\b(create|build)\b.*\b(app|application|api|endpoint|server|cli)\b",
        r"\bpython\b|\bjavascript\b|\btypescript\b|\brust\b|\bgo\b|\bjava\b|\bc\+\+\b",
    ],
    "bug_fix": [
        r"\bfix\b.*\b(bug|error|issue|problem|crash|exception)\b",
        r"\b(debug|troubleshoot)\b",
        r"\bwhy.*\b(fail|error|crash|broken)\b",
        r"\b(not working|doesn.?t work|broken)\b",
    ],
    "refactor": [
        r"\brefactor\b",
        r"\b(clean up|improve|optimise|optimize)\b.*\bcode\b",
        r"\b(rewrite|restructure)\b.*\b(function|class|module)\b",
    ],
    "data": [
        r"\b(analyse|analyze|parse|process)\b.*\b(csv|json|xml|data|dataset)\b",
        r"\bsql\b|\bquery\b|\bdatabase\b",
        r"\b(chart|graph|visuali[sz]e|plot)\b",
        r"\bdata (pipeline|transformation|migration)\b",
    ],
    "research": [
        r"\b(research|investigate|survey|find out about|look into)\b",
        r"\b(compare|contrast|benchmark)\b.{0,40}\b(and|vs\.?|versus|against)\b",
        r"\bsummarise\b|\bsummarize\b",
        r"\b(latest|recent|current)\b.{0,20}\b(news|development|trend|release)\b",
    ],
    "translation": [
        r"\btranslate\b",
        r"\b(in|into|to)\b.{1,30}\b(french|spanish|german|portuguese|italian|chinese|japanese|korean|arabic|russian)\b",
        r"\blocaliz[sz]e\b",
    ],
    "creative": [
        r"\b(write|draft|compose)\b.{1,40}\b(blog|article|story|poem|essay|email|newsletter|ad)\b",
        r"\b(marketing|copywriting|slogan|tagline)\b",
        r"\b(creative|fictional|narrative)\b",
    ],
    "documentation": [
        r"\b(document|docs|readme|docstring|comment)\b",
        r"\bwrite.{1,40}documentation\b",
        r"\b(api|technical) (documentation|reference|guide)\b",
    ],
    "analysis": [
        r"\b(review|evaluate|assess|audit)\b",
        r"\b(pros and cons|compare|contrast|trade.?off)\b",
        r"\b(security|performance|code) (review|audit|analysis)\b",
    ],
    "brainstorm": [
        r"\b(brainstorm|ideas?|suggest|propose|recommend)\b",
        r"\bwhat (should|could|would)\b",
        r"\b(alternatives|options|approaches)\b",
    ],
    "qa": [
        r"^(what|who|where|when|why|how|is|are|do|does|can|could|would|should).{0,80}\?$",
        r"\b(quick question|simple question)\b",
        r"\b(define|definition of)\b",
    ],
}

# Default model routing per category
_CATEGORY_MODEL: dict[str, ModelRecommendation] = {
    "code": "standard",
    "bug_fix": "standard",
    "refactor": "standard",
    "data": "standard",
    "research": "standard",
    "translation": "chat",
    "creative": "standard",
    "documentation": "standard",
    "analysis": "standard",
    "brainstorm": "chat",
    "qa": "chat",
    "mixed": "standard",
}

# Patterns that signal a task is genuinely complex (→ Max mode)
# Each pattern counts independently; score ≥ 2 triggers Max mode.
_COMPLEXITY_SIGNALS: list[str] = [
    r"\b(entire|full|complete)\b.{1,30}\b(app|application|system|platform|architecture)\b",
    r"\b(multi.?step|multi.?stage|pipeline)\b",
    r"\b(20|30|40|50|\d{3,})\b.{1,20}\b(file|function|class|endpoint|table|feature|service|microservice|module)\b",
    r"\bmicroservice\b",
    r"\bdistributed\b.{0,30}\b(system|architecture|service|platform)\b",
    r"\bscalable\b.{0,30}\b(system|architecture|service|platform)\b",
    r"\bproduction.?grade\b",
    r"\benterprise.?grade\b",
    r"\b(machine learning|deep learning|neural network|llm|transformer)\b",
    r"\b(from scratch|end.?to.?end|full.?stack)\b",
]

# Patterns that signal genuine Max-level complexity in research
_RESEARCH_MAX_SIGNALS: list[str] = [
    r"\b(comprehensive|exhaustive|in.?depth)\b.*\b(report|analysis|survey)\b",
    r"\b(compare|contrast)\b.{1,40}\b(and|vs\.?|versus)\b.{1,40}\b(across|over|from)\b",
    r"\bmeta.?analysis\b",
]


def _score_complexity(prompt: str) -> int:
    """Return 0 (simple), 1 (medium), 2 (complex) based on complexity signals."""
    low = prompt.lower()
    score = 0
    for pattern in _COMPLEXITY_SIGNALS:
        if re.search(pattern, low):
            score += 1
    return min(score, 2)


def classify_intent(prompt: str) -> IntentCategory:
    """Classify the intent of *prompt* into one of 12 categories.

    Args:
        prompt: The user prompt to classify.

    Returns:
        One of: code, research, creative, data, translation, bug_fix,
        documentation, analysis, qa, brainstorm, refactor, mixed.
    """
    low = prompt.lower()
    scores: dict[str, int] = {cat: 0 for cat in _INTENT_PATTERNS}
    for category, patterns in _INTENT_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, low):
                scores[category] += 1

    best = max(scores, key=lambda c: scores[c])
    if scores[best] == 0:
        return "mixed"
    # If two categories tie at >= 2, call it "mixed"
    top_score = scores[best]
    top_categories = [c for c, s in scores.items() if s == top_score]
    if len(top_categories) >= 2 and top_score >= 2:
        return "mixed"
    return best  # type: ignore[return-value]


def recommend_model(prompt: str) -> dict:
    """Determine the cheapest Manus AI model that delivers identical quality.

    Applies the Quality Veto Rule: if saving credits would reduce quality,
    the recommendation falls back to a more capable model automatically.

    Args:
        prompt: The user prompt to analyse.

    Returns:
        A dict with keys: intent, model, reason, estimated_savings_pct.
    """
    intent = classify_intent(prompt)
    base_model: ModelRecommendation = _CATEGORY_MODEL[intent]
    complexity = _score_complexity(prompt)

    # Upgrade model based on complexity
    if base_model == "chat" and complexity >= 1:
        base_model = "standard"
    if base_model == "standard" and complexity >= 2:
        base_model = "max"

    # Research tasks with exhaustive/comprehensive language → Max
    if intent == "research":
        low = prompt.lower()
        for pattern in _RESEARCH_MAX_SIGNALS:
            if re.search(pattern, low):
                base_model = "max"
                break

    savings_map: dict[str, int] = {"chat": 100, "standard": 60, "max": 0}
    reason_map = {
        "chat": (
            "This task is a simple Q&A / translation / brainstorm that Manus "
            "handles in Chat Mode at zero credit cost."
        ),
        "standard": (
            "The task complexity fits the Standard model — identical results at "
            "roughly 60% lower cost than Max."
        ),
        "max": (
            "Complexity signals indicate this task genuinely requires Max mode "
            "to deliver full quality (Quality Veto Rule applied)."
        ),
    }

    return {
        "intent": intent,
        "model": base_model,
        "reason": reason_map[base_model],
        "estimated_savings_pct": savings_map[base_model],
    }


def optimize_prompt(prompt: str, max_tokens: int = 1500) -> dict:
    """Compress a prompt to reduce token costs while preserving meaning.

    Applies lightweight heuristics:
    - Removes duplicate whitespace and blank lines.
    - Strips filler phrases that add no semantic value.
    - Truncates very long prompts to *max_tokens* approximate characters.

    Args:
        prompt: The original prompt text.
        max_tokens: Soft character limit (approx. 4 chars ≈ 1 token).

    Returns:
        A dict with keys: original_length, optimized_prompt, optimized_length,
        reduction_pct.
    """
    original_length = len(prompt)

    # Remove duplicate whitespace
    optimized = re.sub(r"\n{3,}", "\n\n", prompt)
    optimized = re.sub(r" {2,}", " ", optimized)

    # Strip common filler phrases (case-insensitive)
    filler_phrases = [
        r"\bplease\b\s?",
        r"\bkindly\b\s?",
        r"\bcould you\b\s?",
        r"\bcan you\b\s?",
        r"\bwould you\b\s?",
        r"\bI was wondering if\b\s?",
        r"\bI need you to\b\s?",
        r"\bI want you to\b\s?",
        r"\bI would like you to\b\s?",
        r"\bAs an AI\b.*?\.\s?",
        r"\bNote that\b.*?\.\s?",
        r"\bRemember that\b.*?\.\s?",
    ]
    for phrase in filler_phrases:
        optimized = re.sub(phrase, "", optimized, flags=re.IGNORECASE)

    # Trim trailing/leading whitespace
    optimized = optimized.strip()

    # Hard truncate if still too long (preserve last sentence boundary)
    char_limit = max_tokens * 4
    if len(optimized) > char_limit:
        truncated = optimized[:char_limit]
        # Try to cut at the last sentence-ending punctuation
        last_sentence = max(
            truncated.rfind(". "),
            truncated.rfind("! "),
            truncated.rfind("? "),
        )
        if last_sentence > char_limit // 2:
            optimized = truncated[: last_sentence + 1]
        else:
            optimized = truncated + "…"

    optimized_length = len(optimized)
    reduction_pct = round((1 - optimized_length / original_length) * 100, 1) if original_length else 0.0

    return {
        "original_length": original_length,
        "optimized_prompt": optimized,
        "optimized_length": optimized_length,
        "reduction_pct": reduction_pct,
    }


def estimate_credits(prompt: str, model: str | None = None) -> dict:
    """Estimate the Manus credit cost for executing a given prompt.

    Uses approximate token counts and Manus credit-per-token rates (as of
    mid-2025 public pricing).  Figures are estimates; actual costs vary.

    Manus approximate rates:
        Max mode    — ~1 credit per 100 tokens
        Standard    — ~0.4 credits per 100 tokens
        Chat Mode   — $0 (no credit deduction)

    Args:
        prompt: The prompt text to estimate credits for.
        model: Override the recommended model ("chat", "standard", "max").
               If omitted, the recommendation from recommend_model() is used.

    Returns:
        A dict with keys: tokens_approx, model, credits_approx,
        recommended_model, potential_savings_pct.
    """
    tokens_approx = max(1, len(prompt) // 4)

    recommendation = recommend_model(prompt)
    recommended_model: ModelRecommendation = recommendation["model"]

    resolved_model: ModelRecommendation
    if model in ("chat", "standard", "max"):
        resolved_model = model  # type: ignore[assignment]
    else:
        resolved_model = recommended_model

    rate_per_100: dict[str, float] = {"chat": 0.0, "standard": 0.4, "max": 1.0}
    credits_approx = round(tokens_approx * rate_per_100[resolved_model] / 100, 4)

    credits_if_max = round(tokens_approx * rate_per_100["max"] / 100, 4)
    potential_savings_pct = (
        round((1 - credits_approx / credits_if_max) * 100, 1)
        if credits_if_max > 0
        else 100.0
    )

    return {
        "tokens_approx": tokens_approx,
        "model": resolved_model,
        "credits_approx": credits_approx,
        "recommended_model": recommended_model,
        "potential_savings_pct": potential_savings_pct,
    }


def analyze_batch(prompts: list[str]) -> dict:
    """Analyse a list of prompts and return a consolidated optimisation plan.

    Groups prompts by intent, recommends batching where appropriate, and
    returns per-prompt recommendations plus an aggregate summary.

    Args:
        prompts: List of prompt strings to analyse.

    Returns:
        A dict with keys: total_prompts, items (list of per-prompt dicts),
        total_estimated_savings_pct, batching_suggestion.
    """
    if not prompts:
        return {
            "total_prompts": 0,
            "items": [],
            "total_estimated_savings_pct": 0,
            "batching_suggestion": None,
        }

    items = []
    for idx, p in enumerate(prompts):
        rec = recommend_model(p)
        est = estimate_credits(p, model=rec["model"])
        items.append(
            {
                "index": idx,
                "intent": rec["intent"],
                "model": rec["model"],
                "reason": rec["reason"],
                "estimated_savings_pct": rec["estimated_savings_pct"],
                "credits_approx": est["credits_approx"],
            }
        )

    # Aggregate savings
    avg_savings = round(sum(i["estimated_savings_pct"] for i in items) / len(items), 1)

    # Batching suggestion: group same-intent tasks
    intent_counts: dict[str, int] = {}
    for i in items:
        intent_counts[i["intent"]] = intent_counts.get(i["intent"], 0) + 1
    dominant_intent = max(intent_counts, key=lambda k: intent_counts[k])
    batching_suggestion = None
    if intent_counts[dominant_intent] >= 3:
        batching_suggestion = (
            f"Consider batching the {intent_counts[dominant_intent]} "
            f"'{dominant_intent}' tasks into a single prompt to reduce "
            f"per-task overhead credits."
        )

    return {
        "total_prompts": len(prompts),
        "items": items,
        "total_estimated_savings_pct": avg_savings,
        "batching_suggestion": batching_suggestion,
    }
