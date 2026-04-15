import json
import logging
from typing import Any, Dict, Optional

from .cost_guard import CostGuard
from .llm.base import LLMClient
from .models import CriticOutput, ExecutionResult, PlannerOutput, ReflectorOutput
from .utils import truncate_rows_for_prompt

logger = logging.getLogger(__name__)

REFLECTOR_SYSTEM_PROMPT = """\
Sei un reflector di analytics. Il tuo compito è valutare se i risultati ottenuti rispondono effettivamente alla domanda dell'utente.

Valuta:
1. I risultati sono vuoti? Se sì, suggerisci come modificare la query.
2. I risultati contengono i dati necessari per rispondere alla domanda?
3. Servono ulteriori analisi (drill-down, filtri diversi, confronti)?
4. Quale livello di confidenza hai nella risposta?

Rispondi ESCLUSIVAMENTE con JSON valido:
{
  "question_answered": true,
  "needs_more_analysis": false,
  "next_goal": "",
  "confidence": "high",
  "reason": "spiegazione della valutazione",
  "summary": "breve sintesi dei risultati chiave"
}

confidence può essere: "high", "medium", "low"."""


class Reflector:
    def __init__(self, llm: LLMClient, cost_guard: CostGuard):
        self.llm = llm
        self.cost_guard = cost_guard

    def reflect(
        self,
        question: str,
        planner_output: PlannerOutput,
        critic_output: CriticOutput,
        execution_result: ExecutionResult,
        iteration: int,
        max_iterations: int = 3,
    ) -> ReflectorOutput:
        # Try LLM reflection first
        llm_result = self._llm_reflect(
            question, planner_output, critic_output, execution_result,
            iteration, max_iterations,
        )

        if llm_result:
            # Enforce iteration limit
            if iteration >= max_iterations and llm_result.needs_more_analysis:
                llm_result.needs_more_analysis = False
                llm_result.next_goal = "Limite iterazioni raggiunto."
                if llm_result.confidence == "high":
                    llm_result.confidence = "medium"
            return llm_result

        # Fallback: rule-based reflection
        logger.warning("Reflector LLM non disponibile, uso fallback rule-based.")
        return self._rule_based_reflect(
            question, planner_output, critic_output, execution_result,
            iteration, max_iterations,
        )

    def _llm_reflect(
        self,
        question: str,
        planner: PlannerOutput,
        critic: CriticOutput,
        execution: ExecutionResult,
        iteration: int,
        max_iterations: int,
    ) -> Optional[ReflectorOutput]:
        data_preview = truncate_rows_for_prompt(execution.rows, max_rows=15)

        user_prompt = (
            f"DOMANDA ORIGINALE: {question}\n\n"
            f"ITERAZIONE: {iteration}/{max_iterations}\n\n"
            f"OBIETTIVO DEL PLANNER: {planner.goal}\n"
            f"QUERY ESEGUITA: {planner.sql}\n\n"
            f"VALUTAZIONE CRITIC:\n"
            f"- Valido: {critic.is_valid}\n"
            f"- Issues: {', '.join(critic.issues) if critic.issues else 'nessuno'}\n"
            f"- Rischio allucinazione: {critic.hallucination_risk}\n\n"
            f"RISULTATO QUERY:\n"
            f"- Righe: {execution.row_count}\n"
            f"- Errore: {execution.error or 'nessuno'}\n"
            f"- Dati:\n{data_preview}\n"
        )

        self.cost_guard.register_prompt(REFLECTOR_SYSTEM_PROMPT + user_prompt)
        self.cost_guard.register_llm_call()

        raw = self.llm.complete_json(REFLECTOR_SYSTEM_PROMPT, user_prompt)
        self.cost_guard.register_response(json.dumps(raw) if raw else "")

        if not raw:
            return None

        return ReflectorOutput(
            question_answered=raw.get("question_answered", False),
            needs_more_analysis=raw.get("needs_more_analysis", True),
            next_goal=raw.get("next_goal", ""),
            confidence=raw.get("confidence", "low"),
            reason=raw.get("reason", ""),
            summary=raw.get("summary", ""),
        )

    def _rule_based_reflect(
        self,
        question: str,
        planner: PlannerOutput,
        critic: CriticOutput,
        execution: ExecutionResult,
        iteration: int,
        max_iterations: int,
    ) -> ReflectorOutput:
        """Deterministic fallback when LLM is unavailable."""

        # Error in execution
        if execution.error:
            at_limit = iteration >= max_iterations
            return ReflectorOutput(
                question_answered=False,
                needs_more_analysis=not at_limit,
                next_goal="Correggere l'errore SQL e riprovare." if not at_limit else "Limite raggiunto.",
                confidence="low",
                reason=f"Errore di esecuzione: {execution.error}",
                summary="",
            )

        # Empty results
        if execution.row_count == 0:
            at_limit = iteration >= max_iterations
            return ReflectorOutput(
                question_answered=False,
                needs_more_analysis=not at_limit,
                next_goal="Ampliare i filtri o verificare le tabelle." if not at_limit else "Limite raggiunto.",
                confidence="medium" if at_limit else "low",
                reason="La query ha restituito zero risultati.",
                summary="",
            )

        # Critic flagged high risk
        if critic.hallucination_risk == "high":
            at_limit = iteration >= max_iterations
            return ReflectorOutput(
                question_answered=False,
                needs_more_analysis=not at_limit,
                next_goal="Riformulare la query con filtri più espliciti.",
                confidence="low",
                reason="Rischio allucinazione alto segnalato dal critic.",
                summary="",
            )

        # Critic found missing filters
        if critic.missing_filters:
            at_limit = iteration >= max_iterations
            return ReflectorOutput(
                question_answered=at_limit,
                needs_more_analysis=not at_limit,
                next_goal=f"Aggiungere filtri: {', '.join(critic.missing_filters)}",
                confidence="medium",
                reason="Filtri obbligatori mancanti.",
                summary=f"Risultato con {execution.row_count} righe, ma filtri incompleti.",
            )

        # Success
        return ReflectorOutput(
            question_answered=True,
            needs_more_analysis=False,
            next_goal="",
            confidence="high",
            reason="Query eseguita con successo, risultati coerenti.",
            summary=f"Ottenute {execution.row_count} righe di risultati.",
        )
