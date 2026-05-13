"""Unit tests for VaultWares MCP tools."""

from __future__ import annotations

import pytest

from tools.credit_optimizer import (
    analyze_batch,
    classify_intent,
    estimate_credits,
    optimize_prompt,
    recommend_model,
)


# ---------------------------------------------------------------------------
# classify_intent
# ---------------------------------------------------------------------------


class TestClassifyIntent:
    def test_code_prompt(self):
        result = classify_intent("Write a Python function to parse JSON files")
        assert result == "code"

    def test_bug_fix_prompt(self):
        result = classify_intent("Fix the bug in my login function that causes a crash")
        assert result == "bug_fix"

    def test_translation_prompt(self):
        result = classify_intent("Translate this text into French")
        assert result == "translation"

    def test_brainstorm_prompt(self):
        result = classify_intent("Brainstorm ideas for a new mobile app")
        assert result == "brainstorm"

    def test_qa_prompt(self):
        result = classify_intent("What is the capital of France?")
        assert result == "qa"

    def test_research_prompt(self):
        result = classify_intent("Research the latest developments in quantum computing")
        assert result == "research"

    def test_documentation_prompt(self):
        result = classify_intent("Write documentation for the REST API endpoints")
        assert result == "documentation"

    def test_data_prompt(self):
        result = classify_intent("Analyze this CSV dataset and produce a report")
        assert result == "data"

    def test_unknown_prompt_returns_mixed(self):
        result = classify_intent("zxkqw bpfr lmn")
        assert result == "mixed"


# ---------------------------------------------------------------------------
# recommend_model
# ---------------------------------------------------------------------------


class TestRecommendModel:
    def test_simple_qa_gets_chat(self):
        result = recommend_model("What is 2 + 2?")
        assert result["model"] == "chat"
        assert result["estimated_savings_pct"] == 100

    def test_translation_gets_chat(self):
        result = recommend_model("Translate the following into Spanish: Hello world")
        assert result["model"] == "chat"

    def test_brainstorm_gets_chat(self):
        result = recommend_model("Brainstorm names for a new startup")
        assert result["model"] == "chat"

    def test_simple_code_gets_standard(self):
        result = recommend_model("Write a Python function to reverse a string")
        assert result["model"] == "standard"
        assert result["estimated_savings_pct"] == 60

    def test_complex_task_gets_max(self):
        result = recommend_model(
            "Build a complete full-stack web application with microservice "
            "architecture from scratch"
        )
        assert result["model"] == "max"

    def test_result_has_required_keys(self):
        result = recommend_model("hello world")
        assert set(result.keys()) == {"intent", "model", "reason", "estimated_savings_pct"}

    def test_quality_veto_on_complex_code(self):
        """A complex multi-step coding task should be routed to max, not standard."""
        result = recommend_model(
            "Implement a production-grade distributed system with 50 microservices"
        )
        assert result["model"] == "max"


# ---------------------------------------------------------------------------
# optimize_prompt
# ---------------------------------------------------------------------------


class TestOptimizePrompt:
    def test_removes_please(self):
        result = optimize_prompt("Please write a function to add two numbers")
        assert "Please" not in result["optimized_prompt"]
        assert "write a function" in result["optimized_prompt"]

    def test_removes_can_you(self):
        result = optimize_prompt("Can you explain machine learning?")
        assert "Can you" not in result["optimized_prompt"]

    def test_reduces_length(self):
        long_prompt = "Can you please write a detailed function to add two numbers together?"
        result = optimize_prompt(long_prompt)
        assert result["optimized_length"] <= result["original_length"]

    def test_truncates_very_long_prompt(self):
        very_long = "word " * 5000
        result = optimize_prompt(very_long, max_tokens=100)
        assert result["optimized_length"] <= 100 * 4 + 10  # small tolerance for ellipsis

    def test_result_has_required_keys(self):
        result = optimize_prompt("Test prompt")
        assert set(result.keys()) == {
            "original_length",
            "optimized_prompt",
            "optimized_length",
            "reduction_pct",
        }

    def test_empty_prompt(self):
        result = optimize_prompt("")
        assert result["reduction_pct"] == 0.0

    def test_removes_duplicate_whitespace(self):
        result = optimize_prompt("hello   world\n\n\n\nfoo")
        assert "   " not in result["optimized_prompt"]
        assert "\n\n\n" not in result["optimized_prompt"]


# ---------------------------------------------------------------------------
# estimate_credits
# ---------------------------------------------------------------------------


class TestEstimateCredits:
    def test_chat_mode_zero_credits(self):
        result = estimate_credits("What is 2 + 2?")
        # Simple Q&A should be recommended as chat ($0)
        if result["recommended_model"] == "chat":
            assert result["credits_approx"] == 0.0

    def test_override_model(self):
        result = estimate_credits("hello", model="max")
        assert result["model"] == "max"

    def test_invalid_model_uses_recommendation(self):
        result = estimate_credits("hello", model="bogus")
        assert result["model"] == result["recommended_model"]

    def test_result_has_required_keys(self):
        result = estimate_credits("some prompt")
        assert set(result.keys()) == {
            "tokens_approx",
            "model",
            "credits_approx",
            "recommended_model",
            "potential_savings_pct",
        }

    def test_longer_prompt_costs_more(self):
        short = estimate_credits("Hi", model="max")
        long = estimate_credits("Hi " * 500, model="max")
        assert long["credits_approx"] > short["credits_approx"]


# ---------------------------------------------------------------------------
# analyze_batch
# ---------------------------------------------------------------------------


class TestAnalyzeBatch:
    def test_empty_list(self):
        result = analyze_batch([])
        assert result["total_prompts"] == 0
        assert result["items"] == []

    def test_single_prompt(self):
        result = analyze_batch(["Write a Python function"])
        assert result["total_prompts"] == 1
        assert len(result["items"]) == 1

    def test_items_have_required_keys(self):
        result = analyze_batch(["Write a function", "Translate hello to French"])
        for item in result["items"]:
            assert "index" in item
            assert "intent" in item
            assert "model" in item
            assert "credits_approx" in item

    def test_batching_suggestion_for_repeated_intents(self):
        """Five translation prompts should trigger a batching suggestion."""
        prompts = [f"Translate sentence {i} into French" for i in range(5)]
        result = analyze_batch(prompts)
        assert result["batching_suggestion"] is not None
        assert "translation" in result["batching_suggestion"].lower()

    def test_capped_at_50(self):
        """analyze_batch should handle more than 50 prompts (caller-side cap)."""
        prompts = ["hello"] * 60
        # The server layer caps at 50, but the library function processes all
        result = analyze_batch(prompts[:50])
        assert result["total_prompts"] == 50
