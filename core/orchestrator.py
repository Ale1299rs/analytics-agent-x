"""
Agent Orchestrator — the explicit, readable agentic pipeline.

Flow:
    Question Intake
    -> Context Builder (+ conversation history)
    -> Loop (max N iterations):
        -> Planner (with conv context + iteration feedback)
        -> Critic (LLM + programmatic)
        -> SQL Validator
        -> Executor
        -> Reflector
    -> Answer Builder
    -> Chart Builder (auto-detect)
    -> Follow-up Generator
    -> Log Run
"""

import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from .answer_builder import AnswerBuilder
from .chart_builder import ChartBuilder
from .config import LOG_PATH, MAX_AGENT_LOOPS, MEMORY_PATH, TABLE_ALLOWLIST
from .context_builder import ContextBuilder
from .conversation import ConversationManager
from .cost_guard import CostGuard
from .critic import Critic
from .executor import Executor
from .feedback_writer import FeedbackWriter
from .llm.factory import create_llm_client
from .memory_loader import MemoryLoader
from .models import AgentResult, ExecutionResult, IterationRecord
from .planner import Planner
from .reflector import Reflector
from .sql_validator import SQLValidator
from .utils import append_jsonl, timestamp_iso

logger = logging.getLogger(__name__)


class AgentOrchestrator:
    """Coordinates the full agentic analytics pipeline."""

    def __init__(self, conversation: Optional[ConversationManager] = None):
        self.llm = create_llm_client()
        self.cost_guard = CostGuard(
            max_llm_calls=MAX_AGENT_LOOPS * 5, max_queries=MAX_AGENT_LOOPS
        )
        self.memory_loader = MemoryLoader(MEMORY_PATH)
        self.context_builder = ContextBuilder(self.memory_loader, self.cost_guard)
        self.planner = Planner(self.llm, self.cost_guard)
        self.critic = Critic(self.llm, self.cost_guard)
        self.executor = Executor()
        self.reflector = Reflector(self.llm, self.cost_guard)
        self.answer_builder = AnswerBuilder(self.llm, self.cost_guard)
        self.chart_builder = ChartBuilder()
        self.feedback_writer = FeedbackWriter(MEMORY_PATH)
        self.conversation = conversation or ConversationManager()

        # Build dynamic allowlist from ingredients
        self._allowlist = list(TABLE_ALLOWLIST)  # start with config default
        self.validator = SQLValidator(self._allowlist)

    def run(self, question: str, cookbook_name: str = "default") -> AgentResult:
        run_start = time.monotonic()
        logger.info("Avvio analisi: %s", question[:100])

        # 1. Build context
        context = self.context_builder.build(question, cookbook_name)

        # Update allowlist from loaded ingredients
        ingredient_tables = [
            i.get("name") for i in context.get("ingredients", []) if i.get("name")
        ]
        if ingredient_tables:
            combined = set(self._allowlist) | set(ingredient_tables)
            self.validator = SQLValidator(list(combined))

        # 2. Get conversation context for follow-ups
        conv_context = self.conversation.get_context_for_planner()

        # 3. Agentic loop
        iterations = self._run_loop(question, context, conv_context)

        # 4. Build answer
        answer = self.answer_builder.build(question, iterations, context)

        # 5. Collect result
        last_iter = iterations[-1] if iterations else None
        final_exec = last_iter.execution_result if last_iter else None
        final_refl = last_iter.reflector_output if last_iter else None

        all_tables = set()
        all_sqls = []
        for it in iterations:
            if it.planner_output:
                all_tables.update(it.planner_output.candidate_tables)
            if it.validator_result and it.validator_result.sql:
                all_sqls.append(it.validator_result.sql)

        # 6. Auto-chart
        chart_spec = None
        if final_exec and final_exec.rows:
            chart_spec = self.chart_builder.detect(
                final_exec.rows, final_exec.columns, question
            )

        result = AgentResult(
            answer=answer,
            confidence=final_refl.confidence if final_refl else "low",
            tables_used=sorted(all_tables),
            executed_sqls=all_sqls,
            iterations=iterations,
            warnings=self.cost_guard.warnings,
            cost_summary=self.cost_guard.summary(),
            context=context,
            final_rows=final_exec.rows if final_exec else [],
            final_columns=final_exec.columns if final_exec else [],
            chart_spec=chart_spec,
        )

        # 7. Generate follow-up suggestions
        follow_ups = self.conversation.generate_follow_ups(
            question, result, self.llm, self.cost_guard
        )
        result.follow_ups = follow_ups

        # 8. Record turn in conversation
        self.conversation.add_turn(result, question, follow_ups)

        # 9. Log run
        elapsed = round(time.monotonic() - run_start, 2)
        self._log_run(question, result, elapsed)

        return result

    def _run_loop(
        self,
        question: str,
        context: Dict[str, Any],
        conv_context: str,
    ) -> List[IterationRecord]:
        iterations = []
        feedback = ""

        for i in range(1, MAX_AGENT_LOOPS + 1):
            logger.info("--- Iterazione %d/%d ---", i, MAX_AGENT_LOOPS)
            record = self._run_iteration(
                question, context, feedback, conv_context, i
            )
            iterations.append(record)

            if record.reflector_output and not record.reflector_output.needs_more_analysis:
                logger.info("Reflector soddisfatto, esco dal loop.")
                break

            feedback = self._build_iteration_feedback(record)
            logger.info("Feedback per prossima iterazione: %s", feedback[:200])

        return iterations

    def _run_iteration(
        self,
        question: str,
        context: Dict[str, Any],
        previous_feedback: str,
        conv_context: str,
        iteration: int,
    ) -> IterationRecord:
        record = IterationRecord(iteration=iteration)

        # Plan
        plan = self.planner.plan(
            question, context, previous_feedback, conv_context
        )
        record.planner_output = plan

        # Critic
        critique = self.critic.review(plan.sql, question, context)
        record.critic_output = critique

        # Validate
        sql_to_validate = critique.fixed_sql if critique.fixed_sql else plan.sql
        validation = self.validator.validate_sql(sql_to_validate)
        record.validator_result = validation

        # Execute
        if validation.is_valid:
            execution = self.executor.execute(validation.sql)
            self.cost_guard.register_query()
        else:
            execution = ExecutionResult(error=validation.error)
        record.execution_result = execution

        # Reflect
        reflection = self.reflector.reflect(
            question, plan, critique, execution, iteration, MAX_AGENT_LOOPS
        )
        record.reflector_output = reflection

        return record

    def _build_iteration_feedback(self, record: IterationRecord) -> str:
        parts = []
        if record.execution_result and record.execution_result.error:
            parts.append("ERRORE SQL: %s" % record.execution_result.error)
        if record.execution_result and record.execution_result.row_count == 0:
            parts.append("La query ha restituito ZERO risultati.")
        if record.critic_output:
            if record.critic_output.issues:
                parts.append("PROBLEMI: %s" % "; ".join(record.critic_output.issues))
            if record.critic_output.missing_filters:
                parts.append(
                    "FILTRI MANCANTI: %s"
                    % ", ".join(record.critic_output.missing_filters)
                )
        if record.reflector_output:
            if record.reflector_output.next_goal:
                parts.append("PROSSIMO OBIETTIVO: %s" % record.reflector_output.next_goal)
            if record.reflector_output.reason:
                parts.append("MOTIVO: %s" % record.reflector_output.reason)
        if record.validator_result and record.validator_result.sql:
            parts.append("QUERY PRECEDENTE: %s" % record.validator_result.sql)
        return "\n".join(parts) if parts else ""

    def _log_run(self, question: str, result: AgentResult, elapsed: float) -> None:
        log_record = {
            "timestamp": timestamp_iso(),
            "question": question,
            "selected_tables": result.tables_used,
            "executed_sql": result.executed_sqls,
            "iterations": len(result.iterations),
            "confidence": result.confidence,
            "final_status": "answered" if result.confidence != "low" else "partial",
            "warnings": result.warnings,
            "elapsed_seconds": elapsed,
            "cost_estimate": result.cost_summary,
            "follow_ups": result.follow_ups,
            "has_chart": result.chart_spec is not None,
        }
        try:
            append_jsonl(Path(LOG_PATH), log_record)
        except Exception as exc:
            logger.error("Errore scrittura log: %s", exc)
