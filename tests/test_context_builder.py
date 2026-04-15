"""Tests for ContextBuilder — context selection logic."""

import pytest
from pathlib import Path
from core.context_builder import ContextBuilder
from core.cost_guard import CostGuard
from core.memory_loader import MemoryLoader


@pytest.fixture
def builder(tmp_path):
    """Create a ContextBuilder with test cookbook data."""
    cookbook_dir = tmp_path / "cookbooks" / "default"
    cookbook_dir.mkdir(parents=True)

    import yaml

    ingredients = [
        {
            "name": "fact_signups",
            "description": "Tabella signups giornalieri",
            "columns": ["date", "country_id", "device_id", "signups"],
            "required_filters": ["date"],
            "joins": [{"table": "dim_country", "key": "country_id"}],
            "preferred_dimensions": ["country"],
            "example_questions": ["Perché i signups sono scesi?"],
        },
        {
            "name": "fact_orders",
            "description": "Tabella ordini giornalieri",
            "columns": ["date", "country_id", "device_id", "orders", "revenue"],
            "required_filters": ["date"],
            "joins": [{"table": "dim_country", "key": "country_id"}],
            "preferred_dimensions": ["country"],
            "example_questions": ["Come vanno gli ordini?"],
        },
    ]
    with (cookbook_dir / "ingredients.yaml").open("w") as f:
        yaml.safe_dump(ingredients, f)

    recipes = [
        {"recipe_name": "Trend signups", "triggers": ["signups", "calo"]},
        {"recipe_name": "Order analysis", "triggers": ["ordini", "revenue"]},
    ]
    with (cookbook_dir / "recipes.yaml").open("w") as f:
        yaml.safe_dump(recipes, f)

    (cookbook_dir / "rules.md").write_text("Usare sempre filtro su date.")
    (cookbook_dir / "examples.sql").write_text("SELECT * FROM fact_signups LIMIT 10;")

    patterns = {"patterns": [
        {"question_pattern": "signups scesi", "correct_table_choices": ["fact_signups"]},
    ]}
    with (tmp_path / "learned_patterns.yaml").open("w") as f:
        yaml.safe_dump(patterns, f)

    loader = MemoryLoader(tmp_path)
    return ContextBuilder(loader, CostGuard())


def test_selects_relevant_ingredients(builder):
    ctx = builder.build("Perché i signups sono scesi?")
    names = [i["name"] for i in ctx["ingredients"]]
    assert "fact_signups" in names


def test_selects_relevant_recipes(builder):
    ctx = builder.build("Mostra il calo dei signups")
    recipe_names = [r["recipe_name"] for r in ctx["recipes"]]
    assert "Trend signups" in recipe_names


def test_matches_learned_patterns(builder):
    ctx = builder.build("I signups sono scesi")
    assert len(ctx["learned_patterns"]) >= 1


def test_includes_table_schemas(builder):
    ctx = builder.build("Signups?")
    assert "table_schemas" in ctx
    assert "fact_signups" in ctx["table_schemas"]


def test_fallback_on_no_match(builder):
    ctx = builder.build("qualcosa di completamente diverso")
    # Should fallback to first N ingredients
    assert len(ctx["ingredients"]) > 0
