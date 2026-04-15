"""Tests for CostGuard — budget tracking and warnings."""

from core.cost_guard import CostGuard


def test_tracks_llm_calls():
    guard = CostGuard(max_llm_calls=3)
    guard.register_llm_call()
    guard.register_llm_call()
    assert guard._llm_calls == 2
    assert not guard.budget_exceeded


def test_warns_on_excess_llm_calls():
    guard = CostGuard(max_llm_calls=2)
    guard.register_llm_call()
    guard.register_llm_call()
    guard.register_llm_call()  # over limit
    assert guard.budget_exceeded
    assert any("limite" in w.lower() for w in guard.warnings)


def test_tracks_queries():
    guard = CostGuard(max_queries=2)
    guard.register_query()
    guard.register_query()
    guard.register_query()  # over limit
    assert any("query" in w.lower() for w in guard.warnings)


def test_warns_on_long_prompt():
    guard = CostGuard()
    guard.register_prompt("x" * 6000)
    assert any("lungo" in w.lower() for w in guard.warnings)


def test_summary_structure():
    guard = CostGuard()
    guard.register_prompt("test prompt")
    guard.register_response("test response")
    guard.register_llm_call()
    guard.register_query()
    s = guard.summary()
    assert "estimated_prompt_chars" in s
    assert "estimated_response_chars" in s
    assert "number_of_llm_calls" in s
    assert s["number_of_llm_calls"] == 1
    assert s["number_of_queries"] == 1


def test_no_warnings_when_within_limits():
    guard = CostGuard()
    guard.register_prompt("short")
    guard.register_llm_call()
    guard.register_query()
    assert len(guard.warnings) == 0
