import pytest
from pg_autoexplain_ai_analysis import normalize_sql

def test_normalize_sql_simple_query():
    sql = "SELECT * FROM users WHERE id = 1;"
    expected = "SELECT *\nFROM users\nWHERE id = ?;"
    assert normalize_sql(sql) == expected

def test_normalize_sql_with_strings_and_numbers():
    sql = "INSERT INTO logs (message, level) VALUES ('Error message', 5);"
    expected = "INSERT INTO logs (message, level)\nVALUES (?, ?);"
    assert normalize_sql(sql) == expected

def test_normalize_sql_with_comments():
    sql = """
    -- This is a comment
    SELECT name, email -- Another comment
    FROM customers
    WHERE age > 30; -- Trailing comment
    """
    # sqlparse.format by default strips comments, which is what normalize_sql uses.
    # The expected output reflects this behavior.
    # Adjusted to match sqlparse's reindent style for multiple columns.
    expected = "SELECT name,\n       email\nFROM customers\nWHERE age > ?;"
    assert normalize_sql(sql) == expected

def test_normalize_sql_different_casing_and_spacing():
    sql = "  SeLeCt  column1,   column2 from  MY_TABLE where  column3 = 'test_value'  ;  "
    # Adjusted to match sqlparse's reindent style (keywords uppercased, specific indentation).
    expected = "SELECT column1,\n       column2\nFROM MY_TABLE\nWHERE column3 = ?;"
    assert normalize_sql(sql) == expected

def test_normalize_sql_no_changes_needed():
    sql = "SELECT * FROM products;"
    # Adjusted to reflect that reindent=True will likely add newlines.
    expected = "SELECT *\nFROM products;"
    assert normalize_sql(sql) == expected

def test_normalize_sql_multiple_numbers_and_strings():
    sql = "UPDATE orders SET quantity = 10, price = 25.99 WHERE product_id = 'ABC123' AND order_id = 456;"
    expected = "UPDATE orders\nSET quantity = ?,\n    price = ?\nWHERE product_id = ?\n  AND order_id = ?;"
    assert normalize_sql(sql) == expected
