"""Tests for Critic — LLM + programmatic checks."""

import pytest
from core.critic import Critic
from core.cost_guard import CostGuard
from core.llm.base import LLMClient
from core.models import CriticOutput


class StubCriticLLM(LLMClient):
    """Returns a valid critic response."""

    def __init__(self, response: dict = None):
        self._response = response or {
            "is_valid": True,
            "issues": [],
            "missing_filters": [],
            "hallucination_risk": "low",
            "fixed_sql": "",
            "reason": "Query corretta.",
        }

    def complete_json(self, system_prompt: str, user_prompt: str) -> dict:
        return self._response

    def complete_text(self, system_prompt: str, user_prompt: str) -> str:
        return ""


class EmptyLLM(LLMClient):
    def complete_json(self, system_prompt, user_prompt):
        return {}
    def complete_text(self, system_prompt, user_prompt):
        return ""


def _make_context():
    return {
        "ingredients": [
            {
                "name": "fact_signups",
                "description": "signups",
                "required_filters": ["date"],
            }
        ],
        "recipes": [],
        "rules": "Le analisi devono includere un filtro su date.",
        "table_schemas": "## fact_signups\nColonne: date, country_id, signups",
    }


class TestCriticWithLLM:
    def test_valid_query_passes(self):
        critic = Critic(StubCriticLLM(), CostGuard())
        result = critic.review(
            "SELECT date, signups FROM fact_signups WHERE date > '2024-01-01'",
            "Trend signups?",
            _make_context(),
        )
        assert isinstance(result, CriticOutput)
        assert result.is_valid

    def test_llm_detects_issues(self):
        llm = StubCriticLLM({
            "is_valid": False,
            "issues": ["La query non filtra per data"],
            "missing_filters": ["date"],
            "hallucination_risk": "medium",
            "fixed_sql": "SELECT * FROM fact_signups WHERE date > '2024-01-01'",
            "reason": "Manca filtro data.",
        })
        critic = Critic(llm, CostGuard())
        result = critic.review(
            "SELECT * FROM fact_signups",
            "Trend signups?",
            _make_context(),
        )
        assert not result.is_valid
        assert len(result.issues) > 0
        assert result.fixed_sql  # Should have a fix


class TestCriticProgrammatic:
    def test_detects_missing_required_filter(self):
        critic = Critic(EmptyLLM(), CostGuard())
        result = critic.review(
            "SELECT signups FROM fact_signups",
            "Quanti signups?",
            _make_context(),
        )
        # Programmatic check should find missing 'date' filter
        assert any("date" in f.lower() for f in result.missing_filters)

    def test_flags_fact_table_without_where(self):
        critic = Critic(EmptyLLM(), CostGuard())
        result = critic.review(
            "SELECT * FROM fact_signups",
            "Mostra signups",
            _make_context(),
        )
        assert any("WHERE" in i or "where" in i.lower() or "filtro" in i.lower() for i in result.issues)

    def test_empty_sql(self):
        critic = Critic(EmptyLLM(), CostGuard())
        result = critic.review("", "Test?", _make_context())
        assert not result.is_valid
        assert result.hallucination_risk == "high"


class TestCriticMerge:
    def test_programmatic_escalates_risk(self):
        """Programmatic checks should escalate risk even if LLM says low."""
        llm = StubCriticLLM({
            "is_valid": True,
            "issues": [],
            "missing_filters": [],
            "hallucination_risk": "low",
            "fixed_sql": "",
            "reason": "Tutto ok.",
        })
        critic = Critic(llm, CostGuard())
        # Query without WHERE on fact table — programmatic should flag it
        result = critic.review(
            "SELECT * FROM fact_signups",
            "Mostra tutto",
            _make_context(),
        )
        # Programmatic should have added issues even though LLM said valid
        assert result.hallucination_risk in ("medium", "high")
