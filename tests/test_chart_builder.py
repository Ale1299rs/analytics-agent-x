"""Tests for ChartBuilder — auto chart detection."""

import pytest
from core.chart_builder import ChartBuilder


@pytest.fixture
def builder():
    return ChartBuilder()


def _time_series_rows():
    """Rows that look like a time series."""
    return [
        {"date": "2026-04-01", "country": "Italia", "signups": 100},
        {"date": "2026-04-01", "country": "Germania", "signups": 80},
        {"date": "2026-04-02", "country": "Italia", "signups": 95},
        {"date": "2026-04-02", "country": "Germania", "signups": 85},
        {"date": "2026-04-03", "country": "Italia", "signups": 90},
        {"date": "2026-04-03", "country": "Germania", "signups": 82},
    ]


def _bar_rows():
    """Rows for a categorical comparison."""
    return [
        {"country": "Italia", "total_signups": 500},
        {"country": "Germania", "total_signups": 400},
        {"country": "Francia", "total_signups": 350},
        {"country": "USA", "total_signups": 300},
    ]


class TestChartDetection:
    def test_detects_multi_line_for_time_series_with_category(self, builder):
        rows = _time_series_rows()
        cols = ["date", "country", "signups"]
        spec = builder.detect(rows, cols, "Trend signups per paese")
        assert spec is not None
        assert spec.chart_type == "multi_line"
        assert spec.x_col == "date"
        assert spec.color_col == "country"

    def test_detects_line_for_simple_time_series(self, builder):
        rows = [
            {"date": "2026-04-01", "signups": 100},
            {"date": "2026-04-02", "signups": 95},
            {"date": "2026-04-03", "signups": 90},
        ]
        spec = builder.detect(rows, ["date", "signups"], "Trend signups")
        assert spec is not None
        assert spec.chart_type == "line"

    def test_detects_bar_for_categorical(self, builder):
        rows = _bar_rows()
        spec = builder.detect(rows, ["country", "total_signups"], "Signups per paese")
        assert spec is not None
        assert spec.chart_type == "bar"

    def test_returns_none_for_empty(self, builder):
        assert builder.detect([], [], "") is None

    def test_returns_none_for_single_row(self, builder):
        rows = [{"a": 1}]
        assert builder.detect(rows, ["a"], "") is None

    def test_returns_none_for_no_numeric_columns(self, builder):
        rows = [{"a": "x", "b": "y"}, {"a": "z", "b": "w"}]
        assert builder.detect(rows, ["a", "b"], "") is None

    def test_skips_id_columns(self, builder):
        rows = [
            {"id": 1, "date": "2026-04-01", "country_id": 1, "signups": 100},
            {"id": 2, "date": "2026-04-02", "country_id": 1, "signups": 95},
        ]
        spec = builder.detect(rows, ["id", "date", "country_id", "signups"], "Trend")
        assert spec is not None
        # id and country_id should not be picked as y_cols
        assert "id" not in spec.y_cols
        assert "country_id" not in spec.y_cols
        assert "signups" in spec.y_cols


class TestColorPicking:
    def test_picks_country_when_question_mentions_paese(self, builder):
        rows = _time_series_rows()
        spec = builder.detect(rows, ["date", "country", "signups"], "Breakdown per paese")
        assert spec.color_col == "country"

    def test_picks_device_when_question_mentions_mobile(self, builder):
        rows = [
            {"date": "2026-04-01", "device": "mobile", "signups": 50},
            {"date": "2026-04-01", "device": "desktop", "signups": 70},
            {"date": "2026-04-02", "device": "mobile", "signups": 48},
            {"date": "2026-04-02", "device": "desktop", "signups": 72},
        ]
        spec = builder.detect(rows, ["date", "device", "signups"], "Mobile vs desktop")
        assert spec.color_col == "device"


class TestAutoTitle:
    def test_generates_title(self, builder):
        title = builder._auto_title("Perche i signups sono scesi?")
        assert "signups" in title.lower()
        assert "?" not in title

    def test_truncates_long_title(self, builder):
        long_q = "a" * 100
        title = builder._auto_title(long_q)
        assert len(title) <= 63
