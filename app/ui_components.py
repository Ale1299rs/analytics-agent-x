"""Reusable Streamlit UI components."""

import streamlit as st
from typing import Any, List


def render_debug_json(title: str, data: Any) -> None:
    """Render a collapsible JSON block in debug mode."""
    with st.expander(title, expanded=False):
        st.json(data)


def render_execution_table(rows: List[dict], columns: List[str]) -> None:
    """Render query results as a dataframe."""
    if rows:
        st.dataframe(rows)
    else:
        st.info("Nessun risultato da mostrare.")


def render_confidence_badge(confidence: str) -> None:
    """Render a colored confidence indicator."""
    colors = {"high": "🟢", "medium": "🟡", "low": "🔴"}
    icon = colors.get(confidence, "⚪")
    st.markdown(f"{icon} **Confidenza: {confidence.capitalize()}**")
