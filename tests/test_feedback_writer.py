"""Tests for FeedbackWriter — persistence and learned patterns."""

import json
import pytest
from core.feedback_writer import FeedbackWriter
from core.utils import safe_load_yaml


def test_saves_feedback_entry(tmp_path):
    memory_path = tmp_path / "memory"
    writer = FeedbackWriter(memory_path)
    writer.save_feedback(
        question="Perché i signups sono scesi?",
        system_answer="I signups sono scesi del 20%.",
        user_feedback="Utile",
    )

    feedback_file = memory_path / "user_feedback.jsonl"
    assert feedback_file.exists()

    with feedback_file.open("r") as f:
        entry = json.loads(f.readline())

    assert entry["question"] == "Perché i signups sono scesi?"
    assert entry["user_feedback"] == "Utile"
    assert entry["timestamp"]


def test_saves_multiple_entries(tmp_path):
    memory_path = tmp_path / "memory"
    writer = FeedbackWriter(memory_path)
    writer.save_feedback("Q1", "A1", "Utile")
    writer.save_feedback("Q2", "A2", "Non utile")

    feedback_file = memory_path / "user_feedback.jsonl"
    lines = feedback_file.read_text().strip().split("\n")
    assert len(lines) == 2


def test_updates_learned_patterns_on_correction(tmp_path):
    memory_path = tmp_path / "memory"
    writer = FeedbackWriter(memory_path)
    writer.save_feedback(
        question="Trend ordini",
        system_answer="...",
        user_feedback="Non utile",
        corrected_sql="SELECT * FROM fact_orders WHERE date > '2024-01-01'",
        corrected_tables=["fact_orders"],
    )

    patterns = safe_load_yaml(memory_path / "learned_patterns.yaml")
    assert "patterns" in patterns
    assert len(patterns["patterns"]) == 1
    assert patterns["patterns"][0]["correct_table_choices"] == ["fact_orders"]
    assert len(patterns["patterns"][0]["preferred_sql_snippets"]) == 1


def test_no_pattern_update_without_correction(tmp_path):
    memory_path = tmp_path / "memory"
    writer = FeedbackWriter(memory_path)
    writer.save_feedback(
        question="Test",
        system_answer="...",
        user_feedback="Utile",
    )

    patterns_file = memory_path / "learned_patterns.yaml"
    # Should not create patterns file if no correction
    if patterns_file.exists():
        patterns = safe_load_yaml(patterns_file)
        assert len(patterns.get("patterns", [])) == 0
