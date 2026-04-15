import os
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
# Helpers
# ---------------------------------------------------------------------------
def _rerun():
    if hasattr(st, "rerun"):
        st.rerun()
    else:
        st.experimental_rerun()


def _ensure_demo_db():
    if Path(SQLITE_PATH).exists():
        return
    try:
        from db.seed_demo_data import main as seed_main
        seed_main()
    except Exception as exc:
        st.error(f"Impossibile creare il database demo: {exc}")
        st.stop()


def _init_session():
    defaults = {
        "conversation": ConversationManager(),
        "messages": [],
        "pending_question": "",
        "schema_cache": None,
        "cookbook_name": "default",
        "debug": False,
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val


def _apply_db_config(overrides):
    """Patch core.config module attributes at runtime."""
    from core import config as cfg
    for key, val in overrides.items():
        if hasattr(cfg, key):
            setattr(cfg, key, val)
        os.environ[key] = str(val)


def _discover_schema():
    """Run schema discovery and cache results."""
    try:
        discovery = SchemaDiscovery()
        schemas = discovery.discover()
        if schemas:
            st.session_state.schema_cache = schemas
            discovery.save_ingredients(schemas, st.session_state.cookbook_name)
        return schemas
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
def _render_sidebar():
    with st.sidebar:
        st.title("Analytics Agent X")

        # --- Database connection ---
        st.subheader("Database")
        from core import config as cfg

        if cfg.DB_BACKEND == "sqlite":
            st.caption(f"SQLite: **{Path(cfg.SQLITE_PATH).name}**")
        else:
            st.caption(f"Postgres: **{cfg.POSTGRES_DB}@{cfg.POSTGRES_HOST}**")

        with st.expander("Cambia database", expanded=False):
            backend = st.radio("Tipo", ["SQLite", "PostgreSQL"], horizontal=True, key="db_type_radio")
            if backend == "SQLite":
                path = st.text_input("Percorso file .db", value=cfg.SQLITE_PATH, key="sqlite_path_input")
                if st.button("Connetti", key="btn_connect_sqlite"):
                    _apply_db_config({"DB_BACKEND": "sqlite", "SQLITE_PATH": path})
                    st.session_state.schema_cache = None
                    _rerun()
            else:
                pg_host = st.text_input("Host", value="localhost", key="pg_host")
                pg_port = st.text_input("Porta", value="5432", key="pg_port")
                pg_db = st.text_input("Database", key="pg_db")
                pg_user = st.text_input("Utente", value="postgres", key="pg_user")
                pg_pw = st.text_input("Password", type="password", key="pg_pw")
                if st.button("Connetti", key="btn_connect_pg"):
                    _apply_db_config({
                        "DB_BACKEND": "postgres",
                        "POSTGRES_HOST": pg_host,
                        "POSTGRES_PORT": int(pg_port),
                        "POSTGRES_DB": pg_db,
                        "POSTGRES_USER": pg_user,
                        "POSTGRES_PASSWORD": pg_pw,
                    })
                    st.session_state.schema_cache = None
                    _rerun()

        # --- Schema browser ---
        st.subheader("Tabelle")
        schemas = st.session_state.schema_cache
        if schemas is None:
            schemas = _discover_schema()

        if schemas:
            for s in schemas:
                tag = "FACT" if s.is_fact else "DIM"
                with st.expander(f"[{tag}] {s.name}  ({s.row_count:,} righe)", expanded=False):
                    for col in s.columns:
                        parts = [f"`{col['name']}`", col.get("type", "")]
                        if col.get("primary_key"):
                            parts.append("PK")
                        if col["name"] in s.date_columns:
                            parts.append("date")
                        st.caption(" ".join(parts))
                    if s.foreign_keys:
                        st.caption("---")
                        for fk in s.foreign_keys:
                            st.caption(f"{fk['from_column']} -> {fk['to_table']}.{fk['to_column']}")
        else:
            st.caption("Nessuna tabella trovata.")

        if st.button("Riscopri schema", key="btn_rediscover"):
            st.session_state.schema_cache = None
            _rerun()

        st.markdown("---")

        # --- Settings ---
        st.subheader("Impostazioni")
        memory_loader = MemoryLoader(MEMORY_PATH)
        cookbooks = memory_loader.list_cookbooks()
        st.session_state.cookbook_name = st.selectbox("Cookbook", cookbooks, index=0)
        st.session_state.debug = st.checkbox("Debug mode", value=False)

        st.markdown("---")
        conv = st.session_state.conversation
        st.caption(f"Conversazione: {conv.turn_count} turni")
        if st.button("Nuova conversazione", key="btn_new_conv"):
            st.session_state.conversation = ConversationManager()
            st.session_state.messages = []
            st.session_state.pending_question = ""
            _rerun()


# ---------------------------------------------------------------------------
# Chart rendering
# ---------------------------------------------------------------------------
def _render_chart(chart_spec, rows):
    if not chart_spec or not rows:
        return
    try:
        import pandas as pd
        import plotly.express as px

        df = pd.DataFrame(rows)
        fig = None

        if chart_spec.chart_type == "line":
            df = df.sort_values(chart_spec.x_col)
            fig = px.line(df, x=chart_spec.x_col, y=chart_spec.y_cols[0], title=chart_spec.title)

        elif chart_spec.chart_type == "multi_line":
            gcols = [chart_spec.x_col]
            if chart_spec.color_col:
                gcols.append(chart_spec.color_col)
            agg = df.groupby(gcols, as_index=False)[chart_spec.y_cols].sum()
            agg = agg.sort_values(chart_spec.x_col)
            fig = px.line(agg, x=chart_spec.x_col, y=chart_spec.y_cols[0],
                          color=chart_spec.color_col, title=chart_spec.title)

        elif chart_spec.chart_type == "bar":
            agg = df.groupby(chart_spec.x_col, as_index=False)[chart_spec.y_cols].sum()
            agg = agg.sort_values(chart_spec.y_cols[0], ascending=True)
            fig = px.bar(agg, x=chart_spec.y_cols[0], y=chart_spec.x_col,
                         orientation="h", title=chart_spec.title)

        if fig:
            fig.update_layout(
                template="plotly_white",
                height=380,
                margin=dict(l=20, r=20, t=50, b=20),
            )
            st.plotly_chart(fig, use_container_width=True)

    except ImportError:
        st.info("Installa plotly per i chart: pip install plotly")
    except Exception as exc:
        st.warning(f"Errore chart: {exc}")


# ---------------------------------------------------------------------------
# Assistant message rendering
# ---------------------------------------------------------------------------
def _render_assistant_content(result, msg_idx):
    """Render the full content of an assistant response."""
    if not result:
        return

    # Chart first
    if result.chart_spec:
        _render_chart(result.chart_spec, result.final_rows)

    # Answer
    st.markdown(result.answer)

    # Metrics row
    c1, c2, c3 = st.columns(3)
    conf_label = {"high": "Alta", "medium": "Media", "low": "Bassa"}
    c1.metric("Confidenza", conf_label.get(result.confidence, "?"))
    c2.metric("Iterazioni", len(result.iterations))
    c3.metric("Righe", len(result.final_rows))

    # SQL
    if result.executed_sqls:
        with st.expander("SQL eseguite"):
            for sql in result.executed_sqls:
                st.code(sql, language="sql")

    # Data preview
    if result.final_rows:
        with st.expander("Anteprima dati"):
            st.dataframe(result.final_rows)

    # Warnings
    for w in result.warnings:
        st.warning(w)

    # Debug
    if st.session_state.debug:
        with st.expander("Debug"):
            st.json(result.cost_summary)
            if result.chart_spec:
                st.json(result.chart_spec.__dict__)
            for it in result.iterations:
                st.json(it.to_dict())

    # Follow-ups — only on the last assistant message
    is_last = msg_idx == len(st.session_state.messages) - 1
    if is_last and result.follow_ups:
        st.markdown("**Vuoi approfondire?**")
        cols = st.columns(len(result.follow_ups))
        for j, suggestion in enumerate(result.follow_ups):
            with cols[j]:
                if st.button(suggestion, key=f"fu_{msg_idx}_{j}"):
                    st.session_state.pending_question = suggestion
                    _rerun()

    # Feedback — only on last
    if is_last:
        with st.expander("Feedback"):
            user_q = ""
            if msg_idx > 0:
                user_q = st.session_state.messages[msg_idx - 1].get("content", "")
            fc = st.columns([1, 1, 4])
            with fc[0]:
                if st.button("Utile", key=f"fb_up_{msg_idx}"):
                    FeedbackWriter(MEMORY_PATH).save_feedback(user_q, result.answer, "Utile")
                    st.success("Grazie!")
            with fc[1]:
                if st.button("Non utile", key=f"fb_dn_{msg_idx}"):
                    FeedbackWriter(MEMORY_PATH).save_feedback(user_q, result.answer, "Non utile")
                    st.info("Salvato.")


# ---------------------------------------------------------------------------
# Analysis runner
# ---------------------------------------------------------------------------
def _run_analysis(question):
    """Execute the agent pipeline and store the assistant response."""
    orch = AgentOrchestrator(conversation=st.session_state.conversation)
    result = orch.run(question.strip(), st.session_state.cookbook_name)
    st.session_state.messages.append({
        "role": "assistant",
        "content": result.answer,
        "result": result,
    })


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    st.set_page_config(page_title="Analytics Agent X", page_icon="📊", layout="wide")
    _ensure_demo_db()
    _init_session()
    _render_sidebar()

    # Auto-discover schema on first load
    if st.session_state.schema_cache is None:
        _discover_schema()

    st.title("Analytics Agent X")
    st.caption("Chiedi ai tuoi dati in linguaggio naturale")

    # --- Handle pending follow-up (before rendering) ---
    if st.session_state.pending_question:
        prompt = st.session_state.pending_question
        st.session_state.pending_question = ""
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.spinner("Analisi in corso..."):
            _run_analysis(prompt)

    # --- Welcome message ---
    if not st.session_state.messages:
        with st.chat_message("assistant"):
            schemas = st.session_state.schema_cache
            if schemas:
                names = ", ".join(f"**{s.name}**" for s in schemas)
                st.markdown(
                    f"Connesso al database con {len(schemas)} tabelle: {names}.\n\n"
                    "Chiedimi qualsiasi cosa sui tuoi dati."
                )
            else:
                st.markdown("Configura un database dal pannello laterale per iniziare.")

    # --- Render chat history ---
    for i, msg in enumerate(st.session_state.messages):
        with st.chat_message(msg["role"]):
            if msg["role"] == "user":
                st.markdown(msg["content"])
            else:
                _render_assistant_content(msg.get("result"), i)

    # --- Chat input ---
    if prompt := st.chat_input("Chiedi ai tuoi dati..."):
        # User message
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        # Assistant response
        with st.chat_message("assistant"):
            with st.spinner("Analisi in corso..."):
                _run_analysis(prompt)
            _render_assistant_content(
                st.session_state.messages[-1].get("result"),
                len(st.session_state.messages) - 1,
            )


if __name__ == "__main__":
    main()
