import logging
import sqlite3
import time
from typing import Dict, List

from .config import (
    DB_BACKEND,
    POSTGRES_DB,
    POSTGRES_HOST,
    POSTGRES_PASSWORD,
    POSTGRES_PORT,
    POSTGRES_USER,
    SQLITE_PATH,
)
from .models import ExecutionResult

logger = logging.getLogger(__name__)


class Executor:
    """Executes validated SQL against SQLite or Postgres."""

    def __init__(self):
        self.backend = DB_BACKEND
        self._psycopg2 = None
        if self.backend == "postgres":
            try:
                import psycopg2
                self._psycopg2 = psycopg2
            except ImportError:
                raise RuntimeError(
                    "psycopg2 non installato. Esegui: pip install psycopg2-binary"
                )

    def execute(self, sql: str) -> ExecutionResult:
        if self.backend == "postgres":
            return self._execute_postgres(sql)
        return self._execute_sqlite(sql)

    def _execute_sqlite(self, sql: str) -> ExecutionResult:
        start = time.monotonic()
        conn = None
        try:
            conn = sqlite3.connect(SQLITE_PATH)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(sql)
            raw_rows = cursor.fetchall()
            columns = list(raw_rows[0].keys()) if raw_rows else []
            rows = [dict(row) for row in raw_rows]
            elapsed = time.monotonic() - start
            return ExecutionResult(
                rows=rows,
                columns=columns,
                row_count=len(rows),
                elapsed_seconds=round(elapsed, 4),
            )
        except Exception as exc:
            elapsed = time.monotonic() - start
            logger.error("Errore esecuzione SQLite: %s", exc)
            return ExecutionResult(
                elapsed_seconds=round(elapsed, 4),
                error=str(exc),
            )
        finally:
            if conn:
                conn.close()

    def _execute_postgres(self, sql: str) -> ExecutionResult:
        start = time.monotonic()
        conn = None
        try:
            conn = self._psycopg2.connect(
                host=POSTGRES_HOST,
                port=POSTGRES_PORT,
                database=POSTGRES_DB,
                user=POSTGRES_USER,
                password=POSTGRES_PASSWORD,
            )
            cursor = conn.cursor()
            cursor.execute(sql)
            raw_rows = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description] if cursor.description else []
            rows = [dict(zip(columns, row)) for row in raw_rows]
            elapsed = time.monotonic() - start
            return ExecutionResult(
                rows=rows,
                columns=columns,
                row_count=len(rows),
                elapsed_seconds=round(elapsed, 4),
            )
        except Exception as exc:
            elapsed = time.monotonic() - start
            logger.error("Errore esecuzione Postgres: %s", exc)
            return ExecutionResult(
                elapsed_seconds=round(elapsed, 4),
                error=str(exc),
            )
        finally:
            if conn:
                conn.close()
