import logging
from typing import List

import sqlglot
from sqlglot import exp

from .config import DANGEROUS_SQL_KEYWORDS, MAX_PREVIEW_ROWS
from .models import ValidatorResult

logger = logging.getLogger(__name__)


class SQLValidator:
    """Validates SQL for safety: whitelist tables, block dangerous commands, enforce LIMIT."""

    def __init__(self, allowed_tables: List[str]):
        self.allowed_tables = set(t.lower() for t in allowed_tables)

    def validate_sql(self, sql: str) -> ValidatorResult:
        if not sql or not sql.strip():
            return ValidatorResult(
                is_valid=False, sql=sql, error="Query SQL vuota."
            )

        trimmed = sql.strip().rstrip(";")

        # Block multiple statements
        if ";" in trimmed:
            return ValidatorResult(
                is_valid=False,
                sql=sql,
                error="Più di un'istruzione SQL non è permessa.",
            )

        # Block dangerous keywords
        words = set(trimmed.lower().split())
        blocked = words & DANGEROUS_SQL_KEYWORDS
        if blocked:
            return ValidatorResult(
                is_valid=False,
                sql=sql,
                error=f"Comandi SQL pericolosi bloccati: {', '.join(sorted(blocked))}.",
            )

        # Parse with SQLGlot
        try:
            expressions = sqlglot.parse(trimmed, read="sqlite")
        except Exception as exc:
            return ValidatorResult(
                is_valid=False, sql=sql, error=f"SQL non parseabile: {exc}"
            )

        if not expressions or len(expressions) != 1:
            return ValidatorResult(
                is_valid=False,
                sql=sql,
                error="Deve essere una singola query SELECT o WITH.",
            )

        root = expressions[0]
        if root is None:
            return ValidatorResult(
                is_valid=False, sql=sql, error="Parsing ha prodotto espressione vuota."
            )

        # Only SELECT and WITH allowed
        if not isinstance(root, (exp.Select, exp.Subquery)):
            # WITH wraps a Select, check the root type name
            root_type = type(root).__name__
            if root_type not in ("Select", "Union", "Intersect", "Except"):
                return ValidatorResult(
                    is_valid=False,
                    sql=sql,
                    error=f"Solo query SELECT/WITH sono consentite (trovato: {root_type}).",
                )

        # Extract and validate tables
        tables = self._extract_tables(root)
        if not tables:
            return ValidatorResult(
                is_valid=False,
                sql=sql,
                error="Impossibile determinare le tabelle usate.",
            )

        invalid = [t for t in tables if t.lower() not in self.allowed_tables]
        if invalid:
            return ValidatorResult(
                is_valid=False,
                sql=sql,
                error=f"Tabelle non autorizzate: {', '.join(invalid)}.",
                tables=tables,
            )

        # Add LIMIT if missing
        final_sql = trimmed
        if not self._has_limit(root):
            final_sql = f"{trimmed} LIMIT {MAX_PREVIEW_ROWS}"

        warnings = []
        if len(tables) > 5:
            warnings.append("Query con molte tabelle — verifica la necessità di tutti i join.")

        return ValidatorResult(
            is_valid=True,
            sql=final_sql,
            warnings=warnings,
            tables=tables,
        )

    def _extract_tables(self, expression: exp.Expression) -> List[str]:
        return list({
            table.name
            for table in expression.find_all(exp.Table)
            if table.name
        })

    def _has_limit(self, expression: exp.Expression) -> bool:
        return any(isinstance(node, exp.Limit) for node in expression.walk())
