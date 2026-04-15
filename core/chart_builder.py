"""
Auto-chart builder: detects data shape and generates the right visualization.

Detection logic:
  date + numeric                    → line chart
  date + numeric + categorical      → multi-line (one line per category)
  categorical + numeric             → horizontal bar chart
  fallback                          → table only
"""

import logging
import re
from typing import Any, Dict, List, Optional

from .models import ChartSpec

logger = logging.getLogger(__name__)

# Keywords that hint at which categorical column to use for color
COUNTRY_HINTS = {"paese", "paesi", "country", "countries", "geografica", "nazione"}
DEVICE_HINTS = {"device", "mobile", "desktop", "dispositivo", "canale"}


class ChartBuilder:
    def detect(
        self,
        rows: List[Dict[str, Any]],
        columns: List[str],
        question: str = "",
    ) -> Optional[ChartSpec]:
        """Analyze result data and return a ChartSpec, or None if no chart makes sense."""
        if not rows or len(rows) < 2 or not columns:
            return None

        date_cols = self._detect_date_columns(rows, columns)
        numeric_cols = self._detect_numeric_columns(rows, columns)
        # Exclude date columns from categorical detection
        non_date_cols = [c for c in columns if c not in date_cols]
        categorical_cols = self._detect_categorical_columns(rows, non_date_cols)

        if not numeric_cols:
            return None

        title = self._auto_title(question)
        primary_y = numeric_cols[0]

        # Time series
        if date_cols:
            x = date_cols[0]
            if categorical_cols:
                color = self._pick_color_column(categorical_cols, question, rows)
                return ChartSpec(
                    chart_type="multi_line",
                    title=title,
                    x_col=x,
                    y_cols=[primary_y],
                    color_col=color,
                )
            return ChartSpec(
                chart_type="line",
                title=title,
                x_col=x,
                y_cols=numeric_cols[:2],
            )

        # Categorical comparison
        if categorical_cols:
            return ChartSpec(
                chart_type="bar",
                title=title,
                x_col=categorical_cols[0],
                y_cols=[primary_y],
            )

        return None

    def _detect_date_columns(
        self, rows: List[dict], columns: List[str]
    ) -> List[str]:
        """Find columns that look like dates."""
        date_cols = []
        date_pattern = re.compile(r"^\d{4}-\d{2}-\d{2}")
        for col in columns:
            sample = str(rows[0].get(col, ""))
            if date_pattern.match(sample):
                date_cols.append(col)
            elif col.lower() in ("date", "day", "month", "week", "data", "giorno"):
                date_cols.append(col)
        return date_cols

    def _detect_numeric_columns(
        self, rows: List[dict], columns: List[str]
    ) -> List[str]:
        """Find columns with numeric values (excluding IDs)."""
        numeric = []
        id_patterns = {"id", "key", "fk", "pk"}
        for col in columns:
            if col.lower() in id_patterns or col.lower().endswith("_id"):
                continue
            val = rows[0].get(col)
            if isinstance(val, (int, float)):
                numeric.append(col)
        return numeric

    def _detect_categorical_columns(
        self, rows: List[dict], columns: List[str]
    ) -> List[str]:
        """Find string columns with reasonable cardinality for charting."""
        categorical = []
        for col in columns:
            val = rows[0].get(col)
            if not isinstance(val, str):
                continue
            unique = len(set(r.get(col) for r in rows))
            if 2 <= unique <= 12:
                categorical.append(col)
        return categorical

    def _pick_color_column(
        self,
        cat_cols: List[str],
        question: str,
        rows: List[dict],
    ) -> str:
        """Pick the best categorical column for color grouping based on question context."""
        q_lower = question.lower()

        # Check question for hints
        for col in cat_cols:
            col_lower = col.lower()
            if any(h in q_lower for h in COUNTRY_HINTS) and any(
                h in col_lower for h in ("country", "paese", "nazione", "name")
            ):
                return col
            if any(h in q_lower for h in DEVICE_HINTS) and any(
                h in col_lower for h in ("device", "dispositivo", "name")
            ):
                return col

        # Default: pick the one with fewest unique values (cleaner chart)
        best = cat_cols[0]
        best_cardinality = len(set(r.get(best) for r in rows))
        for col in cat_cols[1:]:
            card = len(set(r.get(col) for r in rows))
            if card < best_cardinality:
                best = col
                best_cardinality = card
        return best

    def _auto_title(self, question: str) -> str:
        """Generate a chart title from the question."""
        if not question:
            return "Risultati"
        # Clean and shorten
        title = question.strip().rstrip("?").strip()
        if len(title) > 60:
            title = title[:57] + "..."
        return title
