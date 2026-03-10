from aiqo_pg_ai_report.sql_utils import SQLUtils


def test_get_query_code_ignores_whitespace_comments_and_trailing_semicolon():
    query_a = """
    -- comment
    SELECT  *
    FROM customers
    WHERE id = 123
      AND status = 'ACTIVE';
    """
    query_b = "select * from customers where id = 456 and status = 'PENDING'"

    assert SQLUtils.get_query_code(query_a) == SQLUtils.get_query_code(query_b)


def test_get_query_code_normalizes_unicode_and_line_endings():
    query_a = "select * from cafe\u0301 where note = 'ok'\r\nand score = 42;"
    query_b = "SELECT * FROM caf\u00e9 WHERE note = 'ko'\nand score = 77"

    assert SQLUtils.get_query_code(query_a) == SQLUtils.get_query_code(query_b)


def test_get_query_code_normalizes_decimal_and_dollar_quoted_literals():
    query_a = "select $$first value$$ as payload, -12.5e3 as amount from events"
    query_b = "select $$second value$$ as payload, 900 as amount from events"

    assert SQLUtils.get_query_code(query_a) == SQLUtils.get_query_code(query_b)
