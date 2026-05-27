import json
from pathlib import Path

import pytest

from aiqo_pg_ai_report.log_parser import (
    AbstractLogParser,
    JsonLogParser,
    TextLogParser,
    parse_json_log_entry,
)
from aiqo_pg_ai_report.pg_autoexplain_analyzer import PGAutoExplainAnalyzer


DATA_DIR = Path(__file__).parent / "data"


def test_parse_log_file_with_full_text_plan():
    log_path = DATA_DIR / "pg_ctl.log"
    entries = list(TextLogParser().parse_log_file(log_path))

    assert len(entries) == 1
    entry = entries[0]

    assert entry["timestamp"] == "2025-11-26 14:42:44 CET"
    assert entry["job_name"] == "-- Job: TELEDEP_RCMB"
    assert entry["query_name"] == (
        "-- Task /Enrich and Standardize Source External Data/Titulaire/AggregatedSemQLEnrichers_1 "
        "(SemQL)"
    )
    assert entry["query_text"].startswith("update SD_TITULAIRE T")
    assert entry["execution_plan"].lstrip().startswith("{")
    assert entry["duration"] == pytest.approx(1816878.605)
    assert entry["startup_cost"] == pytest.approx(7863332063.99)
    assert entry["cost"] == pytest.approx(266101313035.47)
    assert entry["rows"] == 2846
    assert entry["buffers"] == {
        "shared_hit": 143191,
        "shared_read": 16708215,
        "shared_dirtied": 6378,
        "shared_written": 179,
        "temp_read": 4983014,
        "temp_written": 4991091,
    }
    assert entry["wal"] == {
        "records": 21968,
        "fpi": 7587,
        "bytes": 26368760,
    }


def test_log_parser_is_subclass_of_abstract_base():
    assert issubclass(TextLogParser, AbstractLogParser)
    assert issubclass(JsonLogParser, AbstractLogParser)


def test_parse_log_file_with_full_json_plan():
    log_path = DATA_DIR / "full-json-plan.log"
    entries = list(JsonLogParser().parse_log_file(log_path))

    assert len(entries) == 1
    entry = entries[0]

    assert entry["timestamp"] == "2025-11-26 14:42:44 CET"
    assert entry["job_name"] == "-- Job: TELEDEP_RCMB"
    assert entry["query_name"] == (
        "-- Task /Enrich and Standardize Source External Data/Titulaire/AggregatedSemQLEnrichers_1 (SemQL)"
    )
    #assert entry["query_text"].startswith("update SD_TITULAIRE T\nset\n    ADRESSE1 = NULLIF(S.ARNVR, ''),\n    CD_COMMUNE = NULLIF(S.ARCCS, ''),\n    CD_POSTAL...tulaire' and TITUL.DELET is null\n  \n) S\nwhere T.B_LOADID = 64597 and T.B_PUBID = S.PUBID and T.B_SOURCEID = S.SOUID")
    assert entry["execution_plan"].lstrip().startswith("{")
    assert entry["duration"] == pytest.approx(1816878.605)
    assert entry["startup_cost"] == pytest.approx(7863332063.99)
    assert entry["cost"] == pytest.approx(266101313035.47)
    assert entry["rows"] == 2846
    assert entry["buffers"] == {
        "shared_hit": 143191,
        "shared_read": 16708215,
        "shared_dirtied": 6378,
        "shared_written": 179,
        "temp_read": 4983014,
        "temp_written": 4991091,
    }
    assert entry["wal"] == {
        "records": 21968,
        "fpi": 7587,
        "bytes": 26368760,
    }


def test_parse_log_file_with_full_json_plan_extracts_wal_stats():
    log_path = DATA_DIR / "full-json-plan.log"
    entries = list(JsonLogParser().parse_log_file(log_path))

    assert len(entries) == 1
    entry = entries[0]

    assert entry["wal"] == {
        "records": 21968,
        "fpi": 7587,
        "bytes": 26368760,
    }


def test_create_log_parser_resolves_json_and_text():
    assert isinstance(PGAutoExplainAnalyzer._create_log_parser("json"), JsonLogParser)
    assert isinstance(PGAutoExplainAnalyzer._create_log_parser("text"), TextLogParser)


def test_text_parser_counts_total_log_lines_processed():
    log_path = DATA_DIR / "pg_ctl.log"
    parser = TextLogParser()
    list(parser.parse_log_file(log_path))

    expected_lines = len(log_path.read_text().splitlines())
    assert parser.total_log_lines_processed == expected_lines


def test_json_parser_counts_total_log_lines_processed():
    log_path = DATA_DIR / "full-json-plan.log"
    parser = JsonLogParser()
    list(parser.parse_log_file(log_path))

    expected_lines = len(log_path.read_text().splitlines())
    assert parser.total_log_lines_processed == expected_lines

def test_create_log_parser_yaml_error():
    with pytest.raises(ValueError, match="format yaml unsupported\\."):
        PGAutoExplainAnalyzer._create_log_parser("yaml")


def test_text_parser_handles_json_plan_block(tmp_path):
    log_path = tmp_path / "json-in-text.log"
    log_path.write_text(
        """
2025-11-26 14:42:44 CET [11699]: [1-1] db=test,user=test,client=10.0.0.1 LOG:  duration: 12.34 ms  plan:
{
  "Query Text": "-- Job: TEST -- Task Sample update foo set bar = 1",
  "Plan": {
    "Node Type": "Result",
    "Startup Cost": 0.0,
    "Total Cost": 0.0,
    "Plan Rows": 1,
    "Plan Width": 4,
    "Actual Rows": 1
  }
}
2025-11-26 14:43:00 CET [11700]: [1-1] db=test,user=test LOG:  statement: select 1;
        """.strip()
    )

    entries = list(TextLogParser().parse_log_file(log_path))

    assert len(entries) == 1
    entry = entries[0]
    assert entry["job_name"] == "-- Job: TEST"
    assert entry["query_name"] == "-- Task Sample"
    assert entry["query_text"].startswith("update foo set bar = 1")
    assert entry["execution_plan"].lstrip().startswith("{")


def test_json_parser_uses_child_actual_rows_when_root_zero(tmp_path):
    log_path = tmp_path / "json-plan-child-rows.log"
    log_path.write_text(
        """
2025-11-26 15:00:00 CET [200]: [1-1] db=test,user=test LOG:  duration: 10.0 ms  plan:
{
  "Query Text": "-- Job: TEST -- Task Another select 1",
  "Plan": {
    "Node Type": "Result",
    "Actual Rows": 0,
    "Plans": [
      {
        "Node Type": "Seq Scan",
        "Actual Rows": 5
      }
    ]
  }
}
        """.strip()
    )

    entries = list(JsonLogParser().parse_log_file(log_path))

    assert len(entries) == 1
    entry = entries[0]
    assert entry["rows"] == 5


def test_json_parser_normalizes_workers_to_array():
    log_entry = """
2025-11-26 15:00:00 CET [200]: [1-1] db=test,user=test LOG:  duration: 10.0 ms  plan:
{
  "Query Text": "-- Job: TEST -- Task Another select 1",
  "Plan": {
    "Node Type": "Gather",
    "Workers Planned": 2,
    "Workers": {
      "Worker Number": 0,
      "Actual Rows": 3
    },
    "Plans": [
      {
        "Node Type": "Parallel Seq Scan",
        "Workers": {
          "Worker Number": 1,
          "Actual Rows": 2
        }
      }
    ]
  }
}
    """.strip()

    entry = parse_json_log_entry(log_entry)
    normalized_plan = json.loads(entry["execution_plan"])

    assert isinstance(normalized_plan["Plan"]["Workers"], list)
    assert normalized_plan["Plan"]["Workers"][0]["Worker Number"] == 0
    assert isinstance(normalized_plan["Plan"]["Plans"][0]["Workers"], list)
    assert normalized_plan["Plan"]["Plans"][0]["Workers"][0]["Worker Number"] == 1


def test_text_parser_handles_consecutive_json_plan_blocks(tmp_path):
    log_path = tmp_path / "consecutive-json-plans.log"
    log_path.write_text(
        """
2025-11-26 15:00:00 CET [200]: [1-1] db=test,user=test LOG:  duration: 10.0 ms  plan:
{
  "Query Text": "-- Job: TEST\\n-- Task First select 1",
  "Plan": {
    "Node Type": "Result",
    "Actual Rows": 1
  }
}
2025-11-26 15:01:00 CET [201]: [1-1] db=test,user=test LOG:  duration: 20.0 ms  plan:
{
  "Query Text": "-- Job: TEST\\n-- Task Second select 2",
  "Plan": {
    "Node Type": "Result",
    "Actual Rows": 2
  }
}
        """.strip()
    )

    entries = list(TextLogParser().parse_log_file(log_path))

    assert len(entries) == 2
    assert entries[0]["duration"] == 10.0
    assert entries[0]["query_name"] == "-- Task First select 1"
    assert entries[1]["duration"] == 20.0
    assert entries[1]["query_name"] == "-- Task Second select 2"


def test_text_parser_uses_nested_actual_rows_for_insert_root(tmp_path):
    log_path = tmp_path / "text-plan-insert-child-rows.log"
    log_path.write_text(
        """
2025-11-26 15:00:00 CET [200]: [1-1] db=test,user=test LOG:  duration: 10.0 ms  plan:
Query Text:
-- Job: TEST
-- Task Insert sample
insert into foo(id)
select id
from bar
Insert on foo  (cost=0.00..10.00 rows=0 width=0) (actual rows=0 loops=1)
  ->  Subquery Scan on src  (cost=0.00..10.00 rows=0 width=4) (actual rows=0 loops=1)
        ->  Seq Scan on bar  (cost=0.00..10.00 rows=7 width=4) (actual rows=7 loops=1)
Settings:
        """.strip()
    )

    entries = list(TextLogParser().parse_log_file(log_path))

    assert len(entries) == 1
    entry = entries[0]
    assert entry["rows"] == 7
