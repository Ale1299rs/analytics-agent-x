"""
Schema Auto-Discovery: connects to the database, reads table metadata,
and generates ingredients.yaml automatically.

Supports SQLite and Postgres.
"""

import logging
import re
import sqlite3
from pathlib import Path
from typing import Dict, List, Optional

import yaml

from .config import (
    DB_BACKEND,
    MEMORY_PATH,
    POSTGRES_DB,
    POSTGRES_HOST,
    POSTGRES_PASSWORD,
    POSTGRES_PORT,
    POSTGRES_USER,
    SQLITE_PATH,
)
from .models import TableSchema

logger = logging.getLogger(__name__)


class SchemaDiscovery:
    """Discovers database schema and generates ingredients.yaml."""

    def discover(self) -> List[TableSchema]:
        """Discover all tables from the configured database."""
        if DB_BACKEND == "postgres":
            return self._discover_postgres()
        return self._discover_sqlite()

    def _discover_sqlite(self) -> List[TableSchema]:
        conn = sqlite3.connect(SQLITE_PATH)
        schemas = []
        try:
            cursor = conn.cursor()

            # Get all tables
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
            tables = [row[0] for row in cursor.fetchall()]

            for table_name in tables:
                schema = TableSchema(name=table_name)

                # Get columns
                cursor.execute(f"PRAGMA table_info('{table_name}')")
                for row in cursor.fetchall():
                    # row: (cid, name, type, notnull, dflt_value, pk)
                    schema.columns.append({
                        "name": row[1],
                        "type": row[2] or "TEXT",
                        "primary_key": bool(row[5]),
                    })

                # Get foreign keys
                cursor.execute(f"PRAGMA foreign_key_list('{table_name}')")
                for row in cursor.fetchall():
                    # row: (id, seq, table, from, to, ...)
                    schema.foreign_keys.append({
                        "from_column": row[3],
                        "to_table": row[2],
                        "to_column": row[4],
                    })

                # Get row count
                cursor.execute(f"SELECT COUNT(*) FROM '{table_name}'")
                schema.row_count = cursor.fetchone()[0]

                # Detect fact vs dim
                schema.is_fact = self._is_fact_table(schema)

                # Detect date columns
                schema.date_columns = self._detect_dates(schema, conn, table_name)

                schemas.append(schema)
        finally:
            conn.close()

        logger.info("Discovered %d tables from SQLite", len(schemas))
        return schemas

    def _discover_postgres(self) -> List[TableSchema]:
        try:
            import psycopg2
        except ImportError:
            raise RuntimeError("psycopg2 richiesto per discovery Postgres")

        conn = psycopg2.connect(
            host=POSTGRES_HOST,
            port=POSTGRES_PORT,
            database=POSTGRES_DB,
            user=POSTGRES_USER,
            password=POSTGRES_PASSWORD,
        )
        schemas = []
        try:
            cursor = conn.cursor()

            # Get tables
            cursor.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'public' ORDER BY table_name"
            )
            tables = [row[0] for row in cursor.fetchall()]

            for table_name in tables:
                schema = TableSchema(name=table_name)

                # Get columns
                cursor.execute(
                    "SELECT column_name, data_type, is_nullable "
                    "FROM information_schema.columns "
                    "WHERE table_name = %s ORDER BY ordinal_position",
                    (table_name,),
                )
                for row in cursor.fetchall():
                    schema.columns.append({
                        "name": row[0],
                        "type": row[1],
                        "primary_key": False,
                    })

                # Get foreign keys
                cursor.execute("""
                    SELECT
                        kcu.column_name,
                        ccu.table_name AS to_table,
                        ccu.column_name AS to_column
                    FROM information_schema.table_constraints tc
                    JOIN information_schema.key_column_usage kcu
                        ON tc.constraint_name = kcu.constraint_name
                    JOIN information_schema.constraint_column_usage ccu
                        ON tc.constraint_name = ccu.constraint_name
                    WHERE tc.constraint_type = 'FOREIGN KEY'
                        AND tc.table_name = %s
                """, (table_name,))
                for row in cursor.fetchall():
                    schema.foreign_keys.append({
                        "from_column": row[0],
                        "to_table": row[1],
                        "to_column": row[2],
                    })

                # Row count
                cursor.execute(f'SELECT COUNT(*) FROM "{table_name}"')
                schema.row_count = cursor.fetchone()[0]

                schema.is_fact = self._is_fact_table(schema)
                schema.date_columns = [
                    c["name"] for c in schema.columns
                    if c["type"] in ("date", "timestamp", "timestamp without time zone",
                                     "timestamp with time zone")
                ]

                schemas.append(schema)
        finally:
            conn.close()

        logger.info("Discovered %d tables from Postgres", len(schemas))
        return schemas

    def _is_fact_table(self, schema: TableSchema) -> bool:
        """Heuristic: fact tables have 'fact_' prefix, or many rows + foreign keys."""
        name = schema.name.lower()
        if name.startswith("fact_") or name.startswith("fct_"):
            return True
        if schema.row_count > 100 and len(schema.foreign_keys) >= 2:
            return True
        return False

    def _detect_dates(
        self, schema: TableSchema, conn: sqlite3.Connection, table_name: str
    ) -> List[str]:
        """Detect date columns by checking data patterns."""
        date_cols = []
        date_pattern = re.compile(r"^\d{4}-\d{2}-\d{2}")

        for col in schema.columns:
            col_name = col["name"]
            col_type = col["type"].upper()

            # Type-based detection
            if col_type in ("DATE", "DATETIME", "TIMESTAMP"):
                date_cols.append(col_name)
                continue

            # Name-based detection
            if col_name.lower() in ("date", "day", "created_at", "updated_at", "event_date"):
                date_cols.append(col_name)
                continue

            # Content-based detection (sample first row)
            if col_type == "TEXT":
                cursor = conn.cursor()
                cursor.execute(
                    f"SELECT \"{col_name}\" FROM \"{table_name}\" LIMIT 1"
                )
                row = cursor.fetchone()
                if row and row[0] and date_pattern.match(str(row[0])):
                    date_cols.append(col_name)

        return date_cols

    def to_ingredients(self, schemas: List[TableSchema]) -> List[dict]:
        """Convert discovered schemas to ingredients.yaml format."""
        ingredients = []
        for schema in schemas:
            col_names = [c["name"] for c in schema.columns]

            # Build joins from foreign keys
            joins = []
            for fk in schema.foreign_keys:
                joins.append({
                    "table": fk["to_table"],
                    "key": fk["from_column"],
                    "target_key": fk["to_column"],
                })

            # Detect required filters
            required_filters = []
            if schema.date_columns and schema.is_fact:
                required_filters = [schema.date_columns[0]]

            # Detect preferred dimensions from FK targets
            preferred_dims = []
            for fk in schema.foreign_keys:
                dim_name = fk["to_table"].replace("dim_", "").replace("d_", "")
                preferred_dims.append(dim_name)

            # Determine grain
            grain = "reference"
            if schema.is_fact:
                grain = "daily" if schema.date_columns else "transactional"

            ingredient = {
                "name": schema.name,
                "description": self._generate_description(schema),
                "grain": grain,
                "columns": col_names,
                "joins": joins,
                "required_filters": required_filters,
                "preferred_dimensions": preferred_dims,
                "example_questions": [],
            }
            if schema.date_columns:
                ingredient["date_column"] = schema.date_columns[0]

            ingredients.append(ingredient)

        return ingredients

    def save_ingredients(
        self,
        schemas: List[TableSchema],
        cookbook_name: str = "default",
    ) -> Path:
        """Save discovered schema as ingredients.yaml."""
        ingredients = self.to_ingredients(schemas)
        path = MEMORY_PATH / "cookbooks" / cookbook_name / "ingredients.yaml"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            yaml.safe_dump(ingredients, f, sort_keys=False, allow_unicode=True)
        logger.info("Ingredients salvati in %s (%d tabelle)", path, len(ingredients))
        return path

    def get_allowlist(self, schemas: List[TableSchema]) -> List[str]:
        """Return list of table names for the SQL validator allowlist."""
        return [s.name for s in schemas]

    def _generate_description(self, schema: TableSchema) -> str:
        """Generate a human-readable description of the table."""
        col_count = len(schema.columns)
        table_type = "Fact table" if schema.is_fact else "Dimension table"
        return (
            f"{table_type} con {col_count} colonne e "
            f"{schema.row_count:,} righe."
        )
