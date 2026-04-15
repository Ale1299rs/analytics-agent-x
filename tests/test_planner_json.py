"""Tests for Planner — output structure validation."""

import pytest
from core.planner import Planner
from core.cost_guard import CostGuard
from core.llm.base import LLMClient
from core.models import PlannerOutput


class StubLLM(LLMClient):
    """Returns a valid planner JSON response."""

    def complete_json(self, system_prompt: str, user_prompt: str) -> dict:
        return {
            "goal": "Analizzare il trend dei signups",
            "intent": "trend analysis",
            "candidate_tables": ["fact_signups", "dim_country"],
            "sql": "SELECT fs.date, c.name, fs.signups FROM fact_signups fs LEFT JOIN dim_country c ON fs.country_id = c.id ORDER BY fs.date DESC LIMIT 100",
            "reason": "Query per analizzare trend signups per paese.",
            "expected_result_shape": "date, country, signups",
            "needs_followup": False,
            "followup_goal": "",
        }

    def complete_text(self, system_prompt: str, user_prompt: str) -> str:
        return "ok"


class EmptyLLM(LLMClient):
    """Simulates LLM failure — returns empty."""

    def complete_json(self, system_prompt: str, user_prompt: str) -> dict:
        return {}

    def complete_text(self, system_prompt: str, user_prompt: str) -> str:
        return ""


def _make_context():
    return {
        "ingredients": [{"name": "fact_signups", "description": "signups"}],
        "recipes": [],
        "rules": "",
        "examples": "",
        "learned_patterns": [],
        "table_schemas": "## fact_signups\nColonne: date, country_id, device_id, signups",
    }


class TestPlannerWithLLM:
    def test_produces_valid_output(self):
        planner = Planner(StubLLM(), CostGuard())
        result = planner.plan("Perché i signups sono scesi?", _make_context())
        assert isinstance(result, PlannerOutput)
        assert result.goal
        assert result.sql.upper().startswith("SELECT")
        assert isinstance(result.candidate_tables, list)
        assert len(result.candidate_tables) > 0

    def test_passes_feedback_to_prompt(self):
        """Verify previous_feedback is included in the prompt."""
        calls = []

        class SpyLLM(LLMClient):
            def complete_json(self, system_prompt, user_prompt):
                calls.append(user_prompt)
                return StubLLM().complete_json(system_prompt, user_prompt)

            def complete_text(self, system_prompt, user_prompt):
                return ""

        planner = Planner(SpyLLM(), CostGuard())
        planner.plan("Test?", _make_context(), previous_feedback="La query precedente era sbagliata")
        assert any("La query precedente era sbagliata" in c for c in calls)

    def test_includes_table_schemas_in_prompt(self):
        calls = []

        class SpyLLM(LLMClient):
            def complete_json(self, system_prompt, user_prompt):
                calls.append(user_prompt)
                return StubLLM().complete_json(system_prompt, user_prompt)

            def complete_text(self, system_prompt, user_prompt):
                return ""

        planner = Planner(SpyLLM(), CostGuard())
        planner.plan("Test?", _make_context())
        assert any("fact_signups" in c for c in calls)


class TestPlannerFallback:
    def test_fallback_on_empty_llm(self):
        planner = Planner(EmptyLLM(), CostGuard())
        result = planner.plan("Perché i signups sono scesi?", _make_context())
        assert isinstance(result, PlannerOutput)
        assert result.sql  # Should have a fallback SQL
        assert "fallback" in result.reason.lower()

    def test_fallback_selects_orders_for_order_question(self):
        planner = Planner(EmptyLLM(), CostGuard())
        result = planner.plan("Come vanno gli ordini?", _make_context())
        assert "fact_orders" in result.candidate_tables

    def test_cost_guard_is_called(self):
        guard = CostGuard()
        planner = Planner(StubLLM(), guard)
        planner.plan("Test?", _make_context())
        assert guard._llm_calls >= 1
        assert guard._prompt_chars > 0
