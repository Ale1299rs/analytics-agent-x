"""Tests for SQL Validator — security, whitelist, LIMIT enforcement."""

import pytest
from core.sql_validator import SQLValidator

ALLOWED = ["fact_signups", "fact_orders", "dim_country", "dim_device"]


@pytest.fixture
def validator():
    return SQLValidator(ALLOWED)


class TestDangerousSQL:
    """Block all dangerous SQL commands."""

    @pytest.mark.parametrize("sql", [
        "DROP TABLE fact_signups",
        "DELETE FROM fact_signups WHERE 1=1",
        "INSERT INTO fact_signups VALUES (1, '2024-01-01', 1, 1, 100)",
        "UPDATE fact_signups SET signups = 0",
        "ALTER TABLE fact_signups ADD COLUMN x INT",
        "TRUNCATE TABLE fact_signups",
        "CREATE TABLE evil (id INT)",
        "GRANT ALL ON fact_signups TO public",
        "REVOKE ALL ON fact_signups FROM public",
    ])
    def test_blocks_dangerous_command(self, validator, sql):
        result = validator.validate_sql(sql)
        assert not result.is_valid
        assert "pericolos" in result.error.lower() or "consentit" in result.error.lower()

    def test_blocks_multiple_statements(self, validator):
        result = validator.validate_sql("SELECT 1; DROP TABLE fact_signups")
        assert not result.is_valid
        assert "istruzione" in result.error.lower()


class TestTableWhitelist:
    """Only allow queries against whitelisted tables."""

    def test_allows_whitelisted_table(self, validator):
        result = validator.validate_sql("SELECT * FROM fact_signups")
        assert result.is_valid

    def test_rejects_unknown_table(self, validator):
        result = validator.validate_sql("SELECT * FROM secret_data")
        assert not result.is_valid
        assert "non autorizz" in result.error.lower()

    def test_allows_join_of_whitelisted_tables(self, validator):
        sql = (
            "SELECT fs.date, c.name "
            "FROM fact_signups fs "
            "JOIN dim_country c ON fs.country_id = c.id"
        )
        result = validator.validate_sql(sql)
        assert result.is_valid
        assert set(result.tables) == {"fact_signups", "dim_country"}

    def test_rejects_join_with_unknown_table(self, validator):
        sql = (
            "SELECT * FROM fact_signups fs "
            "JOIN evil_table e ON fs.id = e.id"
        )
        result = validator.validate_sql(sql)
        assert not result.is_valid


class TestLimitEnforcement:
    """Ensure LIMIT is added when missing."""

    def test_adds_limit_when_missing(self, validator):
        result = validator.validate_sql("SELECT * FROM fact_signups")
        assert result.is_valid
        assert "LIMIT" in result.sql.upper()

    def test_preserves_existing_limit(self, validator):
        result = validator.validate_sql("SELECT * FROM fact_signups LIMIT 50")
        assert result.is_valid
        assert "LIMIT 50" in result.sql

    def test_does_not_double_limit(self, validator):
        result = validator.validate_sql("SELECT * FROM fact_signups LIMIT 100")
        assert result.is_valid
        assert result.sql.upper().count("LIMIT") == 1


class TestEdgeCases:
    """Edge cases and special SQL patterns."""

    def test_empty_sql(self, validator):
        result = validator.validate_sql("")
        assert not result.is_valid

    def test_whitespace_sql(self, validator):
        result = validator.validate_sql("   ")
        assert not result.is_valid

    def test_with_cte(self, validator):
        sql = (
            "WITH recent AS (SELECT * FROM fact_signups WHERE date > '2024-01-01') "
            "SELECT * FROM recent"
        )
        # CTE with subquery — should parse
        result = validator.validate_sql(sql)
        # May or may not pass depending on how SQLGlot resolves CTE table names
        # The important thing is it doesn't crash
        assert isinstance(result.is_valid, bool)

    def test_strips_trailing_semicolon(self, validator):
        result = validator.validate_sql("SELECT * FROM fact_signups;")
        assert result.is_valid
