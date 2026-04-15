import json
import logging
from typing import Any, Dict

from .config import DB_BACKEND
from .cost_guard import CostGuard
from .llm.base import LLMClient
from .models import PlannerOutput

logger = logging.getLogger(__name__)

PLANNER_SYSTEM_PROMPT = """\
Sei un planner di analytics enterprise. Il tuo compito è:
1. Comprendere la domanda business dell'utente.
2. Scegliere le tabelle corrette dallo schema disponibile.
3. Generare UNA query SQL precisa per rispondere alla domanda.

Regole:
- Genera solo SELECT o WITH ... SELECT.
- Usa sempre alias leggibili.
- Aggiungi sempre LIMIT (max 200) alle query esplorative.
- Rispetta i filtri obbligatori indicati nello schema.
- Usa i JOIN indicati nello schema, non inventare relazioni.
- Se la domanda parla di trend temporali, ordina per data.
- Genera SQL compatibile con il dialetto indicato nel contesto.

Rispondi ESCLUSIVAMENTE con JSON valido, senza testo aggiuntivo, in questo formato:
{
  "goal": "obiettivo analitico chiaro",
  "intent": "tipo di analisi (trend, comparison, breakdown, anomaly, etc.)",
  "candidate_tables": ["tabella1", "tabella2"],
  "sql": "SELECT ...",
  "reason": "perché questa query risponde alla domanda",
  "expected_result_shape": "colonne attese nel risultato",
  "needs_followup": false,
  "followup_goal": ""
}"""


def _build_user_prompt(
    question: str,
    context: Dict[str, Any],
    previous_feedback: str = "",
    conversation_context: str = "",
) -> str:
    sql_dialect = "SQLite" if DB_BACKEND == "sqlite" else "PostgreSQL"
    parts = [f"DOMANDA: {question}", f"\nDIALETTO SQL: {sql_dialect}"]

    if conversation_context:
        parts.append(f"\n{conversation_context}")

    table_schemas = context.get("table_schemas", "")
    if table_schemas:
        parts.append(f"\nSCHEMA TABELLE DISPONIBILI:\n{table_schemas}")

    rules = context.get("rules", "")
    if rules:
        parts.append(f"\nREGOLE BUSINESS:\n{rules}")

    examples = context.get("examples", "")
    if examples:
        parts.append(f"\nESEMPI SQL:\n{examples}")

    patterns = context.get("learned_patterns", [])
    if patterns:
        patterns_text = json.dumps(patterns, ensure_ascii=False, indent=2)
        parts.append(f"\nPATTERN APPRESI:\n{patterns_text}")

    recipes = context.get("recipes", [])
    if recipes:
        for r in recipes:
            name = r.get("recipe_name", "")
            steps = ", ".join(r.get("analysis_steps", []))
            parts.append(f"\nRICETTA '{name}': {steps}")

    if previous_feedback:
        parts.append(f"\nFEEDBACK DALL'ITERAZIONE PRECEDENTE:\n{previous_feedback}")
        parts.append("Usa questo feedback per correggere e migliorare la query.")

    return "\n".join(parts)


class Planner:
    def __init__(self, llm: LLMClient, cost_guard: CostGuard):
        self.llm = llm
        self.cost_guard = cost_guard

    def plan(
        self,
        question: str,
        context: Dict[str, Any],
        previous_feedback: str = "",
        conversation_context: str = "",
    ) -> PlannerOutput:
        user_prompt = _build_user_prompt(
            question, context, previous_feedback, conversation_context
        )

        self.cost_guard.register_prompt(PLANNER_SYSTEM_PROMPT + user_prompt)
        self.cost_guard.register_llm_call()

        raw = self.llm.complete_json(PLANNER_SYSTEM_PROMPT, user_prompt)
        self.cost_guard.register_response(json.dumps(raw) if raw else "")

        if raw and raw.get("sql"):
            return self._parse_output(raw)

        # LLM failed — use heuristic fallback
        logger.warning("LLM non ha prodotto un piano valido, uso fallback euristico.")
        return self._fallback_plan(question, context)

    def _parse_output(self, data: dict) -> PlannerOutput:
        return PlannerOutput(
            goal=data.get("goal", ""),
            intent=data.get("intent", ""),
            candidate_tables=data.get("candidate_tables", []),
            sql=data.get("sql", ""),
            reason=data.get("reason", ""),
            expected_result_shape=data.get("expected_result_shape", ""),
            needs_followup=data.get("needs_followup", False),
            followup_goal=data.get("followup_goal", ""),
        )

    def _fallback_plan(self, question: str, context: Dict[str, Any]) -> PlannerOutput:
        """Rule-based fallback when LLM is unavailable."""
        lower = question.lower()
        ingredients = context.get("ingredients", [])

        # Pick tables based on keyword matching
        if any(w in lower for w in ("ordini", "orders", "revenue", "fatturato", "ricavi")):
            tables = ["fact_orders", "dim_country", "dim_device"]
            sql = (
                "SELECT fo.date, c.name AS country, d.name AS device, "
                "fo.orders, fo.revenue "
                "FROM fact_orders fo "
                "LEFT JOIN dim_country c ON fo.country_id = c.id "
                "LEFT JOIN dim_device d ON fo.device_id = d.id "
                "ORDER BY fo.date DESC LIMIT 200"
            )
            goal = "Analizzare trend ordini e revenue"
        else:
            tables = ["fact_signups", "dim_country", "dim_device"]
            sql = (
                "SELECT fs.date, c.name AS country, d.name AS device, fs.signups "
                "FROM fact_signups fs "
                "LEFT JOIN dim_country c ON fs.country_id = c.id "
                "LEFT JOIN dim_device d ON fs.device_id = d.id "
                "ORDER BY fs.date DESC LIMIT 200"
            )
            goal = "Analizzare trend signups"

        return PlannerOutput(
            goal=goal,
            intent="trend analysis",
            candidate_tables=tables,
            sql=sql,
            reason="Query generata via fallback euristico (LLM non disponibile).",
            expected_result_shape="date, country, device, metric",
            needs_followup=True,
            followup_goal="Approfondire con filtri specifici se necessario",
        )
