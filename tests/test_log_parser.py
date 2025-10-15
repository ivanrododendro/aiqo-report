import pytest
from src.aiqo_pg_ai_report import log_parser

def test_parse_log_entry_basic():
    log_entry = (
        "2023-09-06 12:34:56.789 duration: 123.45 ms\n"
        "Query Text:\n"
        "-- JobName\n"
        "-- QueryName\n"
        "SELECT * FROM users WHERE id = 1;\n"
        "Seq Scan on users  (cost=0.00..1.01 rows=1 width=4)\n"
        "Settings: some_setting=on\n"
    )
    result = log_parser.parse_log_entry(log_entry)
    assert result["timestamp"] == "2023-09-06 12:34:56.789"
    assert result["duration"] == 123.45
    assert result["job_name"] == "-- JobName"
    assert result["query_name"] == "-- QueryName"
    assert "SELECT * FROM users" in result["query_text"]
    assert "Seq Scan on users" in result["execution_plan"]
    assert result["startup_cost"] == 0.00
    assert result["cost"] == 1.01
    assert result["rows"] == 1


def test_parse_log_entry_missing_duration():
    log_entry = (
        "2023-09-06 12:34:56.789\n"
        "Query Text:\n"
        "SELECT * FROM users;\n"
        "Seq Scan on users  (cost=0.00..1.01 rows=1 width=4)\n"
        "Settings: some_setting=on\n"
    )
    result = log_parser.parse_log_entry(log_entry)
    assert result["duration"] is None
    assert result["timestamp"] == "2023-09-06 12:34:56.789"
    assert "SELECT * FROM users" in result["query_text"]
    assert "Seq Scan on users" in result["execution_plan"]
    assert result["startup_cost"] == 0.00
    assert result["cost"] == 1.01
    assert result["rows"] == 1


def test_parse_log_entry_no_plan():
    log_entry = (
        "2023-09-06 12:34:56.789 duration: 123.45 ms\n"
        "Query Text:\n"
        "SELECT * FROM users;\n"
        "Settings: some_setting=on\n"
    )
    with pytest.raises(ValueError):
        log_parser.parse_log_entry(log_entry)


def test_extract_plan_starting_at_line():
    lines = [
        "Query Text:\n",
        "SELECT * FROM users;\n",
        "Seq Scan on users  (cost=0.00..1.01 rows=1 width=4)\n",
        "Settings: some_setting=on\n",
        "Other line\n"
    ]
    file_iter = iter(lines[1:])
    result = log_parser.extract_plan_starting_at_line(file_iter, lines[0])
    assert result.startswith("Query Text:")
    assert "Settings: some_setting=on" in result


def test_logparser_process_plain_text_file(monkeypatch):
    # Simule un fichier avec deux entrées plan
    lines = [
        "Some line\n",
        "plan: Query Text:\n",
        "SELECT * FROM users;\n",
        "Seq Scan on users  (cost=0.00..1.01 rows=1 width=4)\n",
        "Settings: some_setting=on\n",
        "plan: Query Text:\n",
        "SELECT * FROM products;\n",
        "Seq Scan on products  (cost=0.00..1.01 rows=1 width=4)\n",
        "Settings: some_setting=on\n"
    ]
    class DummyFile:
        def __init__(self, lines):
            self.lines = lines
            self.name = "dummy.log"
        def __iter__(self):
            return iter(self.lines)
    parser = log_parser.LogParser()
    results = list(parser._process_plain_text_file(DummyFile(lines), "dummy.log"))
    assert len(results) == 2
    assert "users" in results[0]["query_text"]
    assert "products" in results[1]["query_text"]

