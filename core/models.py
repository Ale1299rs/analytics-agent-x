from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class PlannerOutput:
    goal: str = ""
    intent: str = ""
    candidate_tables: List[str] = field(default_factory=list)
    sql: str = ""
    reason: str = ""
    expected_result_shape: str = ""
    needs_followup: bool = False
    followup_goal: str = ""


@dataclass
class CriticOutput:
    is_valid: bool = True
    issues: List[str] = field(default_factory=list)
    missing_filters: List[str] = field(default_factory=list)
    hallucination_risk: str = "low"
    fixed_sql: str = ""
    reason: str = ""


@dataclass
class ValidatorResult:
    is_valid: bool = False
    sql: str = ""
    error: Optional[str] = None
    warnings: List[str] = field(default_factory=list)
    tables: List[str] = field(default_factory=list)


@dataclass
class ExecutionResult:
    rows: List[Dict[str, Any]] = field(default_factory=list)
    columns: List[str] = field(default_factory=list)
    row_count: int = 0
    elapsed_seconds: float = 0.0
    error: Optional[str] = None


@dataclass
class ReflectorOutput:
    question_answered: bool = False
    needs_more_analysis: bool = True
    next_goal: str = ""
    confidence: str = "low"
    reason: str = ""
    summary: str = ""


@dataclass
class FeedbackEntry:
    question: str = ""
    system_answer: str = ""
    user_feedback: str = ""
    corrected_sql: Optional[str] = ""
    corrected_tables: List[str] = field(default_factory=list)
    timestamp: str = ""


@dataclass
class IterationRecord:
    iteration: int = 0
    planner_output: Optional[PlannerOutput] = None
    critic_output: Optional[CriticOutput] = None
    validator_result: Optional[ValidatorResult] = None
    execution_result: Optional[ExecutionResult] = None
    reflector_output: Optional[ReflectorOutput] = None

    def to_dict(self) -> dict:
        return {
            "iteration": self.iteration,
            "planner": self.planner_output.__dict__ if self.planner_output else {},
            "critic": self.critic_output.__dict__ if self.critic_output else {},
            "validator": self.validator_result.__dict__ if self.validator_result else {},
            "execution": {
                "columns": self.execution_result.columns if self.execution_result else [],
                "row_count": self.execution_result.row_count if self.execution_result else 0,
                "elapsed_seconds": self.execution_result.elapsed_seconds if self.execution_result else 0.0,
                "error": self.execution_result.error if self.execution_result else None,
            },
            "reflector": self.reflector_output.__dict__ if self.reflector_output else {},
            "sql": self.validator_result.sql if self.validator_result else "",
        }


@dataclass
class ChartSpec:
    """Specification for an auto-generated chart."""
    chart_type: str = "table"  # line, multi_line, bar, table
    title: str = ""
    x_col: str = ""
    y_cols: List[str] = field(default_factory=list)
    color_col: Optional[str] = None


@dataclass
class TableSchema:
    """Discovered database table schema."""
    name: str = ""
    columns: List[Dict[str, str]] = field(default_factory=list)
    foreign_keys: List[Dict[str, str]] = field(default_factory=list)
    row_count: int = 0
    is_fact: bool = False
    date_columns: List[str] = field(default_factory=list)


@dataclass
class ConversationTurn:
    """A single turn in a multi-turn conversation."""
    question: str = ""
    answer: str = ""
    tables_used: List[str] = field(default_factory=list)
    sqls: List[str] = field(default_factory=list)
    confidence: str = "low"
    key_findings: str = ""
    follow_ups: List[str] = field(default_factory=list)
    chart_spec: Optional[ChartSpec] = None


@dataclass
class AgentResult:
    answer: str = ""
    confidence: str = "low"
    tables_used: List[str] = field(default_factory=list)
    executed_sqls: List[str] = field(default_factory=list)
    iterations: List[IterationRecord] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    cost_summary: Dict[str, Any] = field(default_factory=dict)
    context: Dict[str, Any] = field(default_factory=dict)
    final_rows: List[Dict[str, Any]] = field(default_factory=list)
    final_columns: List[str] = field(default_factory=list)
    chart_spec: Optional[ChartSpec] = None
    follow_ups: List[str] = field(default_factory=list)
