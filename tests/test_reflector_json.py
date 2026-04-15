"""Tests for Reflector — LLM + rule-based fallback."""

import pytest
from core.reflector import Reflector
from core.cost_guard import CostGuard
from core.llm.base import LLMClient
from core.models import CriticOutput, ExecutionResult, PlannerOutput, ReflectorOutput


class StubReflectorLLM(LLMClient):
    def __init__(self, response: dict = None):
        self._response = response

    def complete_json(self, system_prompt, user_prompt):
        return self._response or {}

    def complete_text(self, system_prompt, user_prompt):
        return ""


class EmptyLLM(LLMClient):
    def complete_json(self, system_prompt, user_prompt):
        return {}
    def complete_text(self, system_prompt, user_prompt):
        return ""


def _make_planner():
    return PlannerOutput(
        goal="Test",
        intent="analysis",
        candidate_tables=["fact_signups"],
        sql="SELECT * FROM fact_signups LIMIT 100",
        reason="Test",
    )


def _make_critic(is_valid=True, risk="low", missing=None):
    return CriticOutput(
        is_valid=is_valid,
        hallucination_risk=risk,
        missing_filters=missing or [],
    )


class TestReflectorRuleBased:
    """Test rule-based fallback (when LLM is unavailable)."""

    def test_success_case(self):
        reflector = Reflector(EmptyLLM(), CostGuard())
        result = reflector.reflect(
            "Test?", _make_planner(), _make_critic(),
            ExecutionResult(rows=[{"a": 1}], columns=["a"], row_count=1, elapsed_seconds=0.1),
            iteration=1,
        )
        assert isinstance(result, ReflectorOutput)
        assert result.question_answered
        assert not result.needs_more_analysis
        assert result.confidence == "high"

    def test_error_triggers_retry(self):
        reflector = Reflector(EmptyLLM(), CostGuard())
        result = reflector.reflect(
            "Test?", _make_planner(), _make_critic(),
            ExecutionResult(error="no such table: foo"),
            iteration=1,
        )
        assert not result.question_answered
        assert result.needs_more_analysis
        assert result.confidence == "low"

    def test_empty_results_trigger_retry(self):
        reflector = Reflector(EmptyLLM(), CostGuard())
        result = reflector.reflect(
            "Test?", _make_planner(), _make_critic(),
            ExecutionResult(),
            iteration=1,
        )
        assert not result.question_answered
        assert result.needs_more_analysis

    def test_high_risk_triggers_retry(self):
        reflector = Reflector(EmptyLLM(), CostGuard())
        result = reflector.reflect(
            "Test?", _make_planner(), _make_critic(risk="high"),
            ExecutionResult(rows=[{"a": 1}], columns=["a"], row_count=1, elapsed_seconds=0.1),
            iteration=1,
        )
        assert not result.question_answered
        assert result.confidence == "low"

    def test_missing_filters_trigger_retry(self):
        reflector = Reflector(EmptyLLM(), CostGuard())
        result = reflector.reflect(
            "Test?", _make_planner(), _make_critic(missing=["date"]),
            ExecutionResult(rows=[{"a": 1}], columns=["a"], row_count=1, elapsed_seconds=0.1),
            iteration=1,
        )
        assert result.needs_more_analysis

    def test_iteration_limit_stops_loop(self):
        reflector = Reflector(EmptyLLM(), CostGuard())
        result = reflector.reflect(
            "Test?", _make_planner(), _make_critic(),
            ExecutionResult(error="syntax error"),
            iteration=3, max_iterations=3,
        )
        # At max iteration, should stop even on error
        assert not result.needs_more_analysis


class TestReflectorWithLLM:
    def test_uses_llm_response(self):
        llm = StubReflectorLLM({
            "question_answered": True,
            "needs_more_analysis": False,
            "next_goal": "",
            "confidence": "high",
            "reason": "I dati rispondono alla domanda.",
            "summary": "Trovati 50 signups in calo.",
        })
        reflector = Reflector(llm, CostGuard())
        result = reflector.reflect(
            "Test?", _make_planner(), _make_critic(),
            ExecutionResult(rows=[{"a": 1}], columns=["a"], row_count=1, elapsed_seconds=0.1),
            iteration=1,
        )
        assert result.question_answered
        assert result.summary == "Trovati 50 signups in calo."

    def test_enforces_iteration_limit_on_llm(self):
        llm = StubReflectorLLM({
            "question_answered": False,
            "needs_more_analysis": True,
            "next_goal": "Drill down",
            "confidence": "low",
            "reason": "Non basta",
            "summary": "",
        })
        reflector = Reflector(llm, CostGuard())
        result = reflector.reflect(
            "Test?", _make_planner(), _make_critic(),
            ExecutionResult(error="error"),
            iteration=3, max_iterations=3,
        )
        # Even if LLM says needs more, iteration limit should stop it
        assert not result.needs_more_analysis
