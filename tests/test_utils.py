"""Tests for utility functions."""

from pathlib import Path
from core.utils import parse_json_text, safe_load_yaml, safe_read_text, truncate_rows_for_prompt


class TestParseJsonText:
    def test_valid_json(self):
        assert parse_json_text('{"a": 1}') == {"a": 1}

    def test_json_in_code_block(self):
        text = '```json\n{"a": 1}\n```'
        assert parse_json_text(text) == {"a": 1}

    def test_json_in_plain_code_block(self):
        text = '```\n{"a": 1}\n```'
        assert parse_json_text(text) == {"a": 1}

    def test_json_with_surrounding_text(self):
        text = 'Here is the result: {"a": 1} done.'
        assert parse_json_text(text) == {"a": 1}

    def test_empty_string(self):
        assert parse_json_text("") == {}

    def test_invalid_json(self):
        assert parse_json_text("not json at all") == {}

    def test_none_like_input(self):
        assert parse_json_text("   ") == {}

    def test_json_array_direct(self):
        assert parse_json_text('["a", "b", "c"]') == ["a", "b", "c"]

    def test_json_array_in_code_block(self):
        text = '```json\n["a", "b"]\n```'
        assert parse_json_text(text) == ["a", "b"]

    def test_json_array_with_surrounding_text(self):
        text = 'Ecco i follow-up: ["q1", "q2", "q3"] fine.'
        result = parse_json_text(text)
        assert isinstance(result, list)
        assert len(result) == 3


class TestSafeFileOps:
    def test_safe_load_yaml_missing_file(self, tmp_path):
        result = safe_load_yaml(tmp_path / "nonexistent.yaml")
        assert result == {}

    def test_safe_read_text_missing_file(self, tmp_path):
        result = safe_read_text(tmp_path / "nonexistent.txt")
        assert result == ""

    def test_safe_load_yaml_valid(self, tmp_path):
        f = tmp_path / "test.yaml"
        f.write_text("key: value\n")
        assert safe_load_yaml(f) == {"key": "value"}


class TestTruncateRows:
    def test_empty_rows(self):
        assert "(nessun risultato)" in truncate_rows_for_prompt([])

    def test_formats_rows(self):
        rows = [{"a": 1, "b": 2}, {"a": 3, "b": 4}]
        result = truncate_rows_for_prompt(rows, max_rows=10)
        assert "a" in result
        assert "1" in result

    def test_truncates_long_list(self):
        rows = [{"x": i} for i in range(50)]
        result = truncate_rows_for_prompt(rows, max_rows=5)
        assert "omesse" in result
