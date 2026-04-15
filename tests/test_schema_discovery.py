"""Tests for SchemaDiscovery — auto schema detection from SQLite."""

import sqlite3
import pytest
from pathlib import Path
from unittest.mock import patch

from core.schema_discovery import SchemaDiscovery


@pytest.fixture
def demo_db(tmp_path):
    """Create a small test database."""
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE dim_region (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL
        )
    """)
    cursor.execute("""
        CREATE TABLE fact_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            region_id INTEGER NOT NULL,
            events INTEGER NOT NULL,
            FOREIGN KEY(region_id) REFERENCES dim_region(id)
        )
    """)
    cursor.execute("INSERT INTO dim_region VALUES (1, 'North'), (2, 'South')")
    cursor.execute(
        "INSERT INTO fact_events(date, region_id, events) VALUES "
        "('2026-01-01', 1, 100), ('2026-01-02', 1, 110), "
        "('2026-01-01', 2, 80), ('2026-01-02', 2, 85)"
    )
    conn.commit()
    conn.close()
    return str(db_path)


def test_discovers_tables(demo_db):
    with patch("core.schema_discovery.SQLITE_PATH", demo_db):
        with patch("core.schema_discovery.DB_BACKEND", "sqlite"):
            discovery = SchemaDiscovery()
            schemas = discovery.discover()

    names = [s.name for s in schemas]
    assert "dim_region" in names
    assert "fact_events" in names


def test_detects_columns(demo_db):
    with patch("core.schema_discovery.SQLITE_PATH", demo_db):
        with patch("core.schema_discovery.DB_BACKEND", "sqlite"):
            schemas = SchemaDiscovery().discover()

    fact = next(s for s in schemas if s.name == "fact_events")
    col_names = [c["name"] for c in fact.columns]
    assert "date" in col_names
    assert "events" in col_names
    assert "region_id" in col_names


def test_detects_foreign_keys(demo_db):
    with patch("core.schema_discovery.SQLITE_PATH", demo_db):
        with patch("core.schema_discovery.DB_BACKEND", "sqlite"):
            schemas = SchemaDiscovery().discover()

    fact = next(s for s in schemas if s.name == "fact_events")
    assert len(fact.foreign_keys) >= 1
    fk = fact.foreign_keys[0]
    assert fk["to_table"] == "dim_region"


def test_detects_fact_vs_dim(demo_db):
    with patch("core.schema_discovery.SQLITE_PATH", demo_db):
        with patch("core.schema_discovery.DB_BACKEND", "sqlite"):
            schemas = SchemaDiscovery().discover()

    fact = next(s for s in schemas if s.name == "fact_events")
    dim = next(s for s in schemas if s.name == "dim_region")
    assert fact.is_fact
    assert not dim.is_fact


def test_detects_date_columns(demo_db):
    with patch("core.schema_discovery.SQLITE_PATH", demo_db):
        with patch("core.schema_discovery.DB_BACKEND", "sqlite"):
            schemas = SchemaDiscovery().discover()

    fact = next(s for s in schemas if s.name == "fact_events")
    assert "date" in fact.date_columns


def test_generates_ingredients(demo_db):
    with patch("core.schema_discovery.SQLITE_PATH", demo_db):
        with patch("core.schema_discovery.DB_BACKEND", "sqlite"):
            discovery = SchemaDiscovery()
            schemas = discovery.discover()
            ingredients = discovery.to_ingredients(schemas)

    assert len(ingredients) == 2
    fact_ing = next(i for i in ingredients if i["name"] == "fact_events")
    assert fact_ing["grain"] == "daily"
    assert "date" in fact_ing.get("required_filters", [])
    assert len(fact_ing["joins"]) >= 1
    assert fact_ing["joins"][0]["table"] == "dim_region"


def test_saves_ingredients_yaml(demo_db, tmp_path):
    with patch("core.schema_discovery.SQLITE_PATH", demo_db):
        with patch("core.schema_discovery.DB_BACKEND", "sqlite"):
            with patch("core.schema_discovery.MEMORY_PATH", tmp_path / "memory"):
                discovery = SchemaDiscovery()
                schemas = discovery.discover()
                path = discovery.save_ingredients(schemas, "test_cookbook")

    assert path.exists()
    assert path.name == "ingredients.yaml"


def test_generates_allowlist(demo_db):
    with patch("core.schema_discovery.SQLITE_PATH", demo_db):
        with patch("core.schema_discovery.DB_BACKEND", "sqlite"):
            discovery = SchemaDiscovery()
            schemas = discovery.discover()
            allowlist = discovery.get_allowlist(schemas)

    assert "fact_events" in allowlist
    assert "dim_region" in allowlist
