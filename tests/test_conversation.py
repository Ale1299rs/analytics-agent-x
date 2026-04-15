"""Tests for ConversationManager — multi-turn state and follow-ups."""

import pytest
from core.conversation import ConversationManager
from core.cost_guard import CostGuard
from core.llm.base import LLMClient
from core.models import AgentResult, ChartSpec


class StubFollowUpLLM(LLMClient):
    def complete_json(self, system_prompt, user_prompt):
        return [
            "Qual e il breakdown per paese?",
            "Il mobile ha performato diversamente?",
            "Gli ordini hanno seguito lo stesso trend?",
        ]

    def complete_text(self, system_prompt, user_prompt):
        return ""


class EmptyLLM(LLMClient):
    def complete_json(self, system_prompt, user_prompt):
        return {}

    def complete_text(self, system_prompt, user_prompt):
        return ""


def _make_result(**kwargs):
    defaults = {
        "answer": "I signups sono calati.",
        "confidence": "high",
        "tables_used": ["fact_signups"],
        "executed_sqls": ["SELECT * FROM fact_signups"],
        "final_columns": ["date", "country", "signups"],
    }
    defaults.update(kwargs)
    return AgentResult(**defaults)


class TestConversationState:
    def test_empty_initially(self):
        conv = ConversationManager()
        assert conv.turn_count == 0
        assert not conv.is_follow_up

    def test_add_turn(self):
        conv = ConversationManager()
        result = _make_result()
        conv.add_turn(result, "Trend signups?", ["Follow 1"])
        assert conv.turn_count == 1
        assert conv.is_follow_up
        assert conv.turns[0].question == "Trend signups?"

    def test_clear(self):
        conv = ConversationManager()
        conv.add_turn(_make_result(), "Q1", [])
        conv.add_turn(_make_result(), "Q2", [])
        conv.clear()
        assert conv.turn_count == 0


class TestPlannerContext:
    def test_empty_when_no_history(self):
        conv = ConversationManager()
        assert conv.get_context_for_planner() == ""

    def test_includes_previous_questions(self):
        conv = ConversationManager()
        conv.add_turn(_make_result(), "Trend signups?", [])
        ctx = conv.get_context_for_planner()
        assert "Trend signups?" in ctx
        assert "fact_signups" in ctx

    def test_limits_to_max_turns(self):
        conv = ConversationManager()
        for i in range(5):
            conv.add_turn(_make_result(), f"Question {i}", [])
        ctx = conv.get_context_for_planner(max_turns=2)
        assert "Question 3" in ctx
        assert "Question 4" in ctx
        assert "Question 0" not in ctx


class TestFollowUpGeneration:
    def test_llm_follow_ups(self):
        conv = ConversationManager()
        result = _make_result()
        follow_ups = conv.generate_follow_ups(
            "Trend signups?", result, StubFollowUpLLM(), CostGuard()
        )
        assert len(follow_ups) == 3
        assert all(isinstance(s, str) for s in follow_ups)

    def test_rule_based_fallback(self):
        conv = ConversationManager()
        result = _make_result()
        follow_ups = conv.generate_follow_ups(
            "Trend signups?", result, EmptyLLM(), CostGuard()
        )
        assert len(follow_ups) >= 1
        assert all(isinstance(s, str) for s in follow_ups)

    def test_suggests_orders_when_only_signups_used(self):
        conv = ConversationManager()
        result = _make_result(tables_used=["fact_signups"])
        follow_ups = conv.generate_follow_ups(
            "Calo signups", result, EmptyLLM(), CostGuard()
        )
        assert any("ordin" in f.lower() for f in follow_ups)
