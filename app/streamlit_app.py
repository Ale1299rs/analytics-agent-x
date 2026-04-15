import sys
from pathlib import Path

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import streamlit as st

from core.config import MEMORY_PATH, SQLITE_PATH
from core.conversation import ConversationManager
from core.feedback_writer import FeedbackWriter
from core.memory_loader import MemoryLoader
from core.orchestrator import AgentOrchestrator
from core.schema_discovery import SchemaDiscovery


# ---------------------------------------------------------------------------
# Compat helper
# ---------------------------------------------------------------------------
def _rerun():
    """Cross-version rerun: st.rerun() (1.27+) or st.experimental_rerun()."""
    if hasattr(st, "rerun"):
        st.rerun()
    else:
        st.experimental_rerun()


# ---------------------------------------------------------------------------
# Auto-seed database if missing
# ---------------------------------------------------------------------------
def _ensure_demo_db():
    """Create demo DB on first run if it doesn't exist."""
    if Path(SQLITE_PATH).exists():
        return
    try:
        from db.seed_demo_data import main as seed_main
        seed_main()
    except Exception as exc:
        st.error(f"Impossibile creare il database demo: {exc}")
        st.stop()


# ---------------------------------------------------------------------------
# Session state initialization
# ---------------------------------------------------------------------------
def _init_session():
    if "conversation" not in st.session_state:
        st.session_state.conversation = ConversationManager()
    if "history" not in st.session_state:
        st.session_state.history = []  # list of (question, AgentResult)
    if "pending_question" not in st.session_state:
        st.session_state.pending_question = ""


# ---------------------------------------------------------------------------
# Chart rendering
# ---------------------------------------------------------------------------
def _render_chart(chart_spec, rows):
    """Render a chart from ChartSpec using plotly."""
    if not chart_spec or not rows:
        return

    try:
        import pandas as pd
        import plotly.express as px

        df = pd.DataFrame(rows)

        if chart_spec.chart_type == "line":
            df = df.sort_values(chart_spec.x_col)
            fig = px.line(
                df,
                x=chart_spec.x_col,
                y=chart_spec.y_cols[0],
                title=chart_spec.title,
            )

        elif chart_spec.chart_type == "multi_line":
            group_cols = [chart_spec.x_col]
            if chart_spec.color_col:
                group_cols.append(chart_spec.color_col)
            agg = df.groupby(group_cols, as_index=False)[chart_spec.y_cols].sum()
            agg = agg.sort_values(chart_spec.x_col)
            fig = px.line(
                agg,
                x=chart_spec.x_col,
                y=chart_spec.y_cols[0],
                color=chart_spec.color_col,
                title=chart_spec.title,
            )

        elif chart_spec.chart_type == "bar":
            agg = df.groupby(chart_spec.x_col, as_index=False)[chart_spec.y_cols].sum()
            agg = agg.sort_values(chart_spec.y_cols[0], ascending=True)
            fig = px.bar(
                agg,
                x=chart_spec.y_cols[0],
                y=chart_spec.x_col,
                orientation="h",
                title=chart_spec.title,
            )

        else:
            return

        fig.update_layout(
            template="plotly_white",
            height=400,
            margin=dict(l=20, r=20, t=50, b=20),
            font=dict(size=12),
        )
        st.plotly_chart(fig, use_container_width=True)

    except ImportError:
        st.info("Installa plotly per visualizzare i chart: pip install plotly")
    except Exception as exc:
        st.warning(f"Impossibile generare il chart: {exc}")


# ---------------------------------------------------------------------------
# Run analysis (extracted for reuse)
# ---------------------------------------------------------------------------
def _run_analysis(question, cookbook_name):
    """Execute the agent pipeline and store the result."""
    with st.spinner("Analisi in corso..."):
        orch = AgentOrchestrator(
            conversation=st.session_state.conversation
        )
        result = orch.run(question, cookbook_name)
        st.session_state.history.append((question, result))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    st.set_page_config(page_title="Analytics Agent X", layout="wide")
    _ensure_demo_db()
    _init_session()

    # --- Sidebar ---
    with st.sidebar:
        st.title("Analytics Agent X")

        memory_loader = MemoryLoader(MEMORY_PATH)
        cookbooks = memory_loader.list_cookbooks()
        cookbook_name = st.selectbox("Cookbook", cookbooks, index=0)

        debug = st.checkbox("Debug mode", value=False)

        st.markdown("---")

        # Schema Discovery
        st.subheader("Schema Discovery")
        if st.button("Scopri schema dal DB"):
            with st.spinner("Analisi dello schema..."):
                discovery = SchemaDiscovery()
                schemas = discovery.discover()
                if schemas:
                    discovery.save_ingredients(schemas, cookbook_name)
                    for s in schemas:
                        icon = "F" if s.is_fact else "D"
                        st.write(
                            f"[{icon}] **{s.name}** — "
                            f"{len(s.columns)} col, {s.row_count:,} righe"
                        )
                    st.success(
                        f"Schema salvato in ingredients.yaml ({len(schemas)} tabelle)."
                    )
                else:
                    st.warning("Nessuna tabella trovata.")

        st.markdown("---")

        # Conversation controls
        conv = st.session_state.conversation
        st.caption(f"Conversazione: {conv.turn_count} turni")
        if st.button("Nuova conversazione"):
            st.session_state.conversation = ConversationManager()
            st.session_state.history = []
            st.session_state.pending_question = ""
            _rerun()

    # --- Main area ---
    st.header("Chiedi ai tuoi dati")

    # Auto-run pending follow-up question
    if st.session_state.pending_question:
        question = st.session_state.pending_question
        st.session_state.pending_question = ""
        _run_analysis(question, cookbook_name)
        _rerun()

    # Input
    question = st.text_input(
        "Domanda",
        placeholder="Es: Perche i signups sono scesi la scorsa settimana?",
    )
    run_btn = st.button("Analizza")

    # --- Run analysis ---
    if run_btn and question.strip():
        _run_analysis(question.strip(), cookbook_name)

    # --- Render conversation history ---
    if not st.session_state.history:
        st.info("Fai una domanda per iniziare l'analisi.")
        return

    # Render all turns, latest last (most prominent)
    for turn_idx, (q, result) in enumerate(st.session_state.history):
        is_latest = turn_idx == len(st.session_state.history) - 1

        if not is_latest:
            # Older turns: collapsed
            with st.expander(f"Turno {turn_idx + 1}: {q}", expanded=False):
                st.markdown(result.answer)
        else:
            # Latest turn: full display
            st.markdown("---")
            st.markdown(f"**Tu:** {q}")
            st.markdown("")

            # Chart first — visual impact
            if result.chart_spec:
                _render_chart(result.chart_spec, result.final_rows)

            # Answer
            st.markdown(result.answer)

            # Metrics row
            col1, col2, col3 = st.columns(3)
            confidence_map = {"high": "Alta", "medium": "Media", "low": "Bassa"}
            col1.metric("Confidenza", confidence_map.get(result.confidence, "?"))
            col2.metric("Iterazioni", len(result.iterations))
            col3.metric("Righe", len(result.final_rows))

            # SQL
            if result.executed_sqls:
                with st.expander("SQL eseguite", expanded=False):
                    for i, sql in enumerate(result.executed_sqls, 1):
                        st.code(sql, language="sql")

            # Data preview
            if result.final_rows:
                with st.expander("Dati", expanded=False):
                    st.dataframe(result.final_rows)

            # Warnings
            if result.warnings:
                for w in result.warnings:
                    st.warning(w)

            # --- Follow-up suggestions ---
            if result.follow_ups:
                st.markdown("**Vuoi approfondire?**")
                fu_cols = st.columns(len(result.follow_ups))
                for i, suggestion in enumerate(result.follow_ups):
                    with fu_cols[i]:
                        if st.button(
                            suggestion,
                            key=f"fu_{turn_idx}_{i}",
                        ):
                            st.session_state.pending_question = suggestion
                            _rerun()

            # --- Debug ---
            if debug:
                st.markdown("---")
                st.subheader("Debug")
                with st.expander("Contesto", expanded=False):
                    debug_ctx = {
                        k: v
                        for k, v in result.context.items()
                        if k != "cookbook"
                    }
                    st.json(debug_ctx)
                with st.expander("Cost Guard", expanded=False):
                    st.json(result.cost_summary)
                if result.chart_spec:
                    with st.expander("Chart Spec", expanded=False):
                        st.json(result.chart_spec.__dict__)
                for it in result.iterations:
                    with st.expander(
                        f"Iterazione {it.iteration}", expanded=False
                    ):
                        st.json(it.to_dict())

            # --- Feedback ---
            st.markdown("---")
            with st.expander("Feedback", expanded=False):
                fb = st.radio(
                    "Utile?",
                    ["Utile", "Non utile"],
                    horizontal=True,
                    key=f"fb_{turn_idx}",
                )
                corr_sql = st.text_area(
                    "SQL corretta (facoltativo)",
                    key=f"corr_{turn_idx}",
                    height=80,
                )
                note = st.text_input("Nota", key=f"note_{turn_idx}")
                if st.button("Invia feedback", key=f"send_fb_{turn_idx}"):
                    writer = FeedbackWriter(MEMORY_PATH)
                    writer.save_feedback(
                        question=q,
                        system_answer=result.answer,
                        user_feedback=f"{fb}. {note}".strip(),
                        corrected_sql=corr_sql,
                    )
                    st.success("Feedback salvato!")


if __name__ == "__main__":
    main()
