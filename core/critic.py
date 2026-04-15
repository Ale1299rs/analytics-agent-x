import json
import logging
from typing import Any, Dict, List

from .cost_guard import CostGuard
from .llm.base import LLMClient
from .models import CriticOutput

logger = logging.getLogger(__name__)

CRITIC_SYSTEM_PROMPT = """\
Sei un critic esperto di analytics SQL. Il tuo compito è valutare una query SQL proposta da un planner e verificare che:

1. La query risponda effettivamente alla domanda dell'utente.
2. Le tabelle usate siano corrette e coerenti con lo schema.
3. I filtri obbligatori siano presenti (es. filtro su data).
4. I JOIN siano corretti e non inventati.
5. Non ci siano rischi di allucinazione (tabelle o colonne inesistenti).
6. La query sia logicamente plausibile.

Se trovi problemi, proponi una versione corretta della query nel campo "fixed_sql".
Se la query è buona, restituisci "fixed_sql" vuoto.

Rispondi ESCLUSIVAMENTE con JSON valido in questo formato:
{
  "is_valid": true,
  "issues": [],
  "missing_filters": [],
  "hallucination_risk": "low",
  "fixed_sql": "",
  "reason": "spiegazione della valutazione"
}

hallucination_risk può essere: "low", "medium", "high"."""


class Critic:
    def __init__(self, llm: LLMClient, cost_guard: CostGuard):
        self.llm = llm
        self.cost_guard = cost_guard

    def review(
        self, sql: str, question: str, context: Dict[str, Any]
    ) -> CriticOutput:
        # 1. LLM semantic review
        llm_review = self._llm_review(sql, question, context)

        # 2. Programmatic safety checks (always run as safety net)
        programmatic = self._programmatic_checks(sql, context)

        # Merge: programmatic checks can escalate but not downgrade
        return self._merge_reviews(llm_review, programmatic)

    def _llm_review(
        self, sql: str, question: str, context: Dict[str, Any]
    ) -> CriticOutput:
        table_schemas = context.get("table_schemas", "")
        rules = context.get("rules", "")

        user_prompt = (
            f"DOMANDA UTENTE: {question}\n\n"
            f"QUERY SQL DA VALUTARE:\n{sql}\n\n"
            f"SCHEMA TABELLE:\n{table_schemas}\n\n"
            f"REGOLE BUSINESS:\n{rules}"
        )

        self.cost_guard.register_prompt(CRITIC_SYSTEM_PROMPT + user_prompt)
        self.cost_guard.register_llm_call()

        raw = self.llm.complete_json(CRITIC_SYSTEM_PROMPT, user_prompt)
        self.cost_guard.register_response(json.dumps(raw) if raw else "")

        if raw:
            return CriticOutput(
                is_valid=raw.get("is_valid", True),
                issues=raw.get("issues", []),
                missing_filters=raw.get("missing_filters", []),
                hallucination_risk=raw.get("hallucination_risk", "low"),
                fixed_sql=raw.get("fixed_sql", ""),
                reason=raw.get("reason", ""),
            )

        # LLM unavailable — rely on programmatic checks only
        logger.warning("Critic LLM non disponibile, uso solo controlli programmatici.")
        return CriticOutput(is_valid=True, reason="LLM non disponibile, review programmatico.")

    def _programmatic_checks(
        self, sql: str, context: Dict[str, Any]
    ) -> CriticOutput:
        """Rule-based checks that always run as a safety net."""
        issues: List[str] = []
        missing_filters: List[str] = []
        risk = "low"
        sql_lower = sql.lower()

        if not sql.strip():
            return CriticOutput(
                is_valid=False,
                issues=["Nessuna query generata."],
                hallucination_risk="high",
                reason="Query vuota.",
            )

        # Check required filters from ingredients
        ingredients = context.get("ingredients", [])
        for ing in ingredients:
            table_name = ing.get("name", "")
            if table_name in sql_lower:
                for req_filter in ing.get("required_filters", []):
                    if req_filter not in sql_lower:
                        missing_filters.append(
                            f"{req_filter} (richiesto da {table_name})"
                        )

        # Check for missing WHERE on fact tables
        fact_tables = [
            ing.get("name", "")
            for ing in ingredients
            if ing.get("name", "").startswith("fact_")
        ]
        uses_fact = any(t in sql_lower for t in fact_tables)
        if uses_fact and "where" not in sql_lower:
            issues.append(
                "Query su tabella fact senza filtro WHERE — potrebbe essere troppo ampia."
            )
            risk = "medium"

        if missing_filters:
            risk = "medium"

        is_valid = not issues and not missing_filters
        return CriticOutput(
            is_valid=is_valid,
            issues=issues,
            missing_filters=missing_filters,
            hallucination_risk=risk,
            reason="Controlli programmatici completati.",
        )

    def _merge_reviews(
        self, llm: CriticOutput, prog: CriticOutput
    ) -> CriticOutput:
        """Merge LLM and programmatic reviews. Programmatic can escalate, not downgrade."""
        issues = list(set(llm.issues + prog.issues))
        missing = list(set(llm.missing_filters + prog.missing_filters))

        # Use the higher risk level
        risk_order = {"low": 0, "medium": 1, "high": 2}
        llm_risk = risk_order.get(llm.hallucination_risk, 0)
        prog_risk = risk_order.get(prog.hallucination_risk, 0)
        final_risk = llm.hallucination_risk if llm_risk >= prog_risk else prog.hallucination_risk

        # If programmatic found issues, mark as invalid regardless of LLM opinion
        is_valid = llm.is_valid and prog.is_valid

        return CriticOutput(
            is_valid=is_valid,
            issues=issues,
            missing_filters=missing,
            hallucination_risk=final_risk,
            fixed_sql=llm.fixed_sql,
            reason=llm.reason if llm.reason else prog.reason,
        )
