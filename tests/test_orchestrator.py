"""Tests for AgentOrchestrator — end-to-end integration (with mock LLM)."""

import pytest
from unittest.mock import patch, MagicMock
from core.orchestrator import AgentOrchestrator
from core.models import AgentResult


class MockLLM:
    """Predictable LLM for integration testing."""

    def complete_json(self, system_prompt: str, user_prompt: str) -> dict:
        sp = system_prompt.lower()
        if "planner" in sp:
            return {
                "goal": "Analizzare signups",
                "intent": "trend",
                "candidate_tables": ["fact_signups", "dim_country"],
                "sql": "SELECT fs.date, c.name AS country, fs.signups FROM fact_signups fs LEFT JOIN dim_country c ON fs.country_id = c.id ORDER BY fs.date DESC LIMIT 100",
                "reason": "Baseline query.",
                "expected_result_shape": "date, country, signups",
                "needs_followup": False,
                "followup_goal": "",
            }
        if "critic" in sp:
            return {
                "is_valid": True,
                "issues": [],
                "missing_filters": [],
                "hallucination_risk": "low",
                "fixed_sql": "",
                "reason": "Query corretta.",
            }
        if "reflector" in sp:
            return {
                "question_answered": True,
                "needs_more_analysis": False,
                "next_goal": "",
                "confidence": "high",
                "reason": "Risultati coerenti.",
                "summary": "Signups in calo nell'ultima settimana.",
            }
        return {}

    def complete_text(self, system_prompt: str, user_prompt: str) -> str:
        return (
            "#### Sintesi\n"
            "I signups sono calati del 30% nell'ultima settimana.\n\n"
            "#### Cosa ho verificato\n"
            "- Query eseguita con successo\n\n"
            "#### SQL eseguite\n"
            "- SELECT ...\n\n"
            "#### Tabelle usate\n"
            "fact_signups, dim_country\n\n"
            "#### Limiti / assunzioni\n"
            "Dati demo.\n\n"
            "#### Confidenza\n"
            "Alta"
        )


@pytest.fixture
def orchestrator():
    with patch("core.orchestrator.create_llm_client", return_value=MockLLM()):
        orch = AgentOrchestrator()
        return orch


def test_full_run(orchestrator):
    result = orchestrator.run("Perché i signups sono scesi?")
    assert isinstance(result, AgentResult)
    assert result.answer
    assert result.confidence in ("high", "medium", "low")
    assert len(result.iterations) >= 1
    assert len(result.executed_sqls) >= 1


def test_stops_after_success(orchestrator):
    result = orchestrator.run("Mostra signups")
    # MockLLM reflector says question_answered=True on first try
    assert len(result.iterations) == 1


def test_cost_summary_populated(orchestrator):
    result = orchestrator.run("Test")
    assert "number_of_llm_calls" in result.cost_summary
    assert result.cost_summary["number_of_llm_calls"] >= 1
