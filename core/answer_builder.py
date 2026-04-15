import json
import logging
from typing import Any, Dict, List, Optional

from .cost_guard import CostGuard
from .llm.base import LLMClient
from .models import IterationRecord
from .utils import truncate_rows_for_prompt

logger = logging.getLogger(__name__)

ANSWER_SYSTEM_PROMPT = """\
Sei un analista business senior. Scrivi una risposta chiara e professionale in ITALIANO.

Il tuo compito è interpretare i dati ottenuti dalle query SQL e rispondere alla domanda dell'utente.

La risposta DEVE seguire questa struttura (usa i titoli markdown esattamente come indicato):

#### Sintesi
Interpreta i dati concretamente. Indica numeri, trend, confronti. Non dire "ho analizzato", mostra cosa hai trovato.

#### Cosa ho verificato
Elenca i controlli effettuati e le validazioni.

#### SQL eseguite
Mostra le query eseguite (saranno aggiunte automaticamente, scrivi solo un riepilogo).

#### Tabelle usate
Lista le tabelle consultate.

#### Limiti / assunzioni
Indica eventuali limitazioni dei dati o assunzioni fatte.

#### Confidenza
Indica il livello (Alta/Media/Bassa) e perché."""


class AnswerBuilder:
    def __init__(self, llm: LLMClient, cost_guard: CostGuard):
        self.llm = llm
        self.cost_guard = cost_guard

    def build(
        self,
        question: str,
        iterations: List[IterationRecord],
        context: Dict[str, Any],
    ) -> str:
        # Collect data from all iterations
        all_sqls = []
        all_tables = set()
        final_rows = []
        final_confidence = "low"
        verification_notes = []

        for it in iterations:
            if it.validator_result and it.validator_result.sql:
                all_sqls.append(it.validator_result.sql)
            if it.planner_output:
                all_tables.update(it.planner_output.candidate_tables)
            if it.execution_result and it.execution_result.rows:
                final_rows = it.execution_result.rows
            if it.reflector_output:
                final_confidence = it.reflector_output.confidence
                if it.reflector_output.reason:
                    verification_notes.append(it.reflector_output.reason)
            if it.critic_output:
                if it.critic_output.issues:
                    verification_notes.extend(it.critic_output.issues)

        # Try LLM interpretation
        llm_answer = self._llm_build(
            question, final_rows, all_sqls, list(all_tables),
            final_confidence, verification_notes, context,
        )

        if llm_answer:
            return llm_answer

        # Fallback: structured template
        logger.warning("AnswerBuilder LLM non disponibile, uso template.")
        return self._template_build(
            question, final_rows, all_sqls, list(all_tables),
            final_confidence, verification_notes,
        )

    def _llm_build(
        self,
        question: str,
        rows: list,
        sqls: list,
        tables: list,
        confidence: str,
        notes: list,
        context: Dict[str, Any],
    ) -> Optional[str]:
        data_preview = truncate_rows_for_prompt(rows, max_rows=25)
        rules = context.get("rules", "")

        user_prompt = (
            f"DOMANDA UTENTE: {question}\n\n"
            f"DATI OTTENUTI:\n{data_preview}\n\n"
            f"QUERY ESEGUITE:\n" + "\n".join(f"- {s}" for s in sqls) + "\n\n"
            f"TABELLE USATE: {', '.join(tables)}\n\n"
            f"CONFIDENZA: {confidence}\n\n"
            f"NOTE DI VERIFICA: {'; '.join(notes) if notes else 'nessuna'}\n\n"
            f"REGOLE BUSINESS:\n{rules}"
        )

        self.cost_guard.register_prompt(ANSWER_SYSTEM_PROMPT + user_prompt)
        self.cost_guard.register_llm_call()

        answer = self.llm.complete_text(ANSWER_SYSTEM_PROMPT, user_prompt)
        self.cost_guard.register_response(answer)

        if answer and len(answer) > 50:
            return answer

        return None

    def _template_build(
        self,
        question: str,
        rows: list,
        sqls: list,
        tables: list,
        confidence: str,
        notes: list,
    ) -> str:
        """Deterministic fallback answer when LLM is unavailable."""

        # Build data summary
        if rows:
            row_count = len(rows)
            columns = list(rows[0].keys()) if rows else []
            # Try to find numeric trends
            summary_lines = [f"Ottenute **{row_count} righe** con colonne: {', '.join(columns)}."]

            # Simple numeric summary for each numeric column
            for col in columns:
                values = [r[col] for r in rows if isinstance(r.get(col), (int, float))]
                if values:
                    summary_lines.append(
                        f"- **{col}**: min={min(values)}, max={max(values)}, "
                        f"media={sum(values)/len(values):.1f}"
                    )
        else:
            summary_lines = ["La query non ha restituito risultati."]

        verifiche = "\n".join(f"- {n}" for n in notes) if notes else "- Nessun problema rilevato."
        sqls_formatted = "\n".join(f"```sql\n{s}\n```" for s in sqls) if sqls else "Nessuna."

        confidence_map = {"high": "Alta", "medium": "Media", "low": "Bassa"}
        conf_label = confidence_map.get(confidence, confidence.capitalize())

        return (
            f"#### Sintesi\n"
            f"Analisi per: *{question}*\n\n"
            f"{chr(10).join(summary_lines)}\n\n"
            f"#### Cosa ho verificato\n"
            f"{verifiche}\n\n"
            f"#### SQL eseguite\n"
            f"{sqls_formatted}\n\n"
            f"#### Tabelle usate\n"
            f"{', '.join(tables) if tables else 'Nessuna'}\n\n"
            f"#### Limiti / assunzioni\n"
            f"- Dati provenienti dal database di demo.\n"
            f"- Analisi basata sul contesto disponibile nella cookbook.\n"
            f"- LLM non disponibile per interpretazione avanzata.\n\n"
            f"#### Confidenza\n"
            f"**{conf_label}**"
        )
