"""
Multi-turn conversation manager.

Maintains conversation history and formats context for the planner
so it can understand follow-up questions like "e per paese?" or
"scendi nel dettaglio sull'Italia".
"""

import json
import logging
from typing import Any, Dict, List, Optional

from .cost_guard import CostGuard
from .llm.base import LLMClient
from .models import AgentResult, ConversationTurn
from .utils import parse_json_text

logger = logging.getLogger(__name__)

FOLLOW_UP_SYSTEM_PROMPT = """\
Sei un analista business. Basandoti sulla domanda, i dati ottenuti e l'analisi svolta, \
suggerisci esattamente 3 domande follow-up che l'utente potrebbe voler fare.

Le domande devono essere:
- In italiano
- Specifiche e azionabili (non generiche)
- Basate sui dati e dimensioni disponibili
- Utili per approfondire o estendere l'analisi
- Diverse tra loro (una di drill-down, una di confronto, una di correlazione)

Rispondi ESCLUSIVAMENTE con un JSON array di 3 stringhe:
["domanda 1", "domanda 2", "domanda 3"]"""


class ConversationManager:
    """Manages multi-turn conversation state."""

    def __init__(self):
        self.turns: List[ConversationTurn] = []

    @property
    def turn_count(self) -> int:
        return len(self.turns)

    @property
    def is_follow_up(self) -> bool:
        return len(self.turns) > 0

    def add_turn(self, result: AgentResult, question: str, follow_ups: List[str]) -> None:
        """Record a completed turn."""
        key_findings = ""
        if result.iterations:
            last = result.iterations[-1]
            if last.reflector_output:
                key_findings = last.reflector_output.summary

        turn = ConversationTurn(
            question=question,
            answer=result.answer[:500],  # truncate for context efficiency
            tables_used=result.tables_used,
            sqls=result.executed_sqls,
            confidence=result.confidence,
            key_findings=key_findings,
            follow_ups=follow_ups,
            chart_spec=result.chart_spec,
        )
        self.turns.append(turn)

    def get_context_for_planner(self, max_turns: int = 3) -> str:
        """Format recent conversation history as context for the planner."""
        if not self.turns:
            return ""

        recent = self.turns[-max_turns:]
        parts = ["CONVERSAZIONE PRECEDENTE:"]
        for i, turn in enumerate(recent, 1):
            parts.append(f"\n--- Turno {i} ---")
            parts.append(f"Domanda: {turn.question}")
            parts.append(f"Tabelle usate: {', '.join(turn.tables_used)}")
            if turn.key_findings:
                parts.append(f"Risultato chiave: {turn.key_findings}")
            if turn.sqls:
                parts.append(f"SQL eseguita: {turn.sqls[-1][:200]}")
            parts.append(f"Confidenza: {turn.confidence}")

        parts.append(
            "\nUSA QUESTO CONTESTO per comprendere domande di follow-up "
            "come 'e per paese?', 'scendi nel dettaglio', 'confronta con...'. "
            "La nuova query deve essere coerente con l'analisi precedente."
        )
        return "\n".join(parts)

    def clear(self) -> None:
        """Reset conversation."""
        self.turns.clear()

    def generate_follow_ups(
        self,
        question: str,
        result: AgentResult,
        llm: LLMClient,
        cost_guard: CostGuard,
    ) -> List[str]:
        """Generate follow-up suggestions using LLM."""
        user_prompt = (
            f"DOMANDA: {question}\n\n"
            f"TABELLE USATE: {', '.join(result.tables_used)}\n"
            f"CONFIDENZA: {result.confidence}\n"
            f"RISULTATO: {result.answer[:300]}\n\n"
            f"DIMENSIONI DISPONIBILI NEI DATI: "
            f"{', '.join(result.final_columns) if result.final_columns else 'non note'}\n"
        )

        cost_guard.register_prompt(FOLLOW_UP_SYSTEM_PROMPT + user_prompt)
        cost_guard.register_llm_call()

        raw = llm.complete_json(FOLLOW_UP_SYSTEM_PROMPT, user_prompt)
        cost_guard.register_response(json.dumps(raw) if raw else "")

        # LLM should return a list directly
        if isinstance(raw, list):
            return [str(s) for s in raw[:3]]

        # Sometimes it wraps in an object
        if isinstance(raw, dict):
            for key in ("follow_ups", "questions", "suggestions", "domande"):
                if key in raw and isinstance(raw[key], list):
                    return [str(s) for s in raw[key][:3]]

        # Fallback: rule-based suggestions
        return self._rule_based_follow_ups(question, result)

    def _rule_based_follow_ups(
        self, question: str, result: AgentResult
    ) -> List[str]:
        """Generate follow-up suggestions without LLM."""
        suggestions = []
        tables = set(result.tables_used)
        q_lower = question.lower()

        # Suggest dimension drill-downs
        if "dim_country" not in tables and any(
            w in q_lower for w in ("signups", "ordini", "orders", "trend", "calo")
        ):
            suggestions.append("Qual è il breakdown per paese?")
        elif "country" in " ".join(result.final_columns):
            suggestions.append("Quali paesi hanno guidato il trend?")

        if "dim_device" not in tables or "device" not in q_lower:
            suggestions.append("Il mobile ha performato diversamente dal desktop?")

        # Suggest cross-metric analysis
        if "fact_orders" not in tables:
            suggestions.append("Gli ordini hanno seguito lo stesso trend?")
        elif "fact_signups" not in tables:
            suggestions.append("I signups mostrano lo stesso pattern?")

        # Suggest time comparison
        if "settimana" in q_lower or "week" in q_lower:
            suggestions.append("Com'era il trend nelle 2 settimane precedenti?")
        else:
            suggestions.append("Qual è il trend degli ultimi 14 giorni?")

        return suggestions[:3]
