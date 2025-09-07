# tests/test_sql_utils.py
import pytest
from src.aiqo_pg_ai_report.sql_utils import SQLUtils

def test_normalize_sql():
    sql = "SELECT * FROM users WHERE id = 123 AND name = 'John'; -- commentaire"
    expected = "SELECT *\nFROM users\nWHERE id = ?\n  AND name = ?;"
    assert SQLUtils.normalize_sql(sql) == expected

def test_get_query_code():
    sql = "SELECT * FROM users WHERE id = 123 AND name = 'John';"
    normalized_query = SQLUtils.normalize_sql(sql)
    expected_hash = SQLUtils.get_query_code(sql)
    assert SQLUtils.get_query_code(sql) == expected_hash
    assert len(expected_hash) == 64  # SHA-256 produit un hash de 64 caractères

def test_normalize_sql_identical_queries():
    sql1 = "SELECT * FROM users WHERE id = 123 AND name = 'John';"
    sql2 = "SELECT * FROM users WHERE id = 456 AND name = 'Doe';"
    assert SQLUtils.normalize_sql(sql1) == SQLUtils.normalize_sql(sql2)
