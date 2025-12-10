from pathlib import Path

import pytest

from aiqo_pg_ai_report.log_parser import AbstractLogParser, JsonLogParser, TextLogParser
from aiqo_pg_ai_report.pg_aiqo_report import PGAutoExplainAnalyzer


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
    assert entry["rows"] == 0
    assert entry["buffers"] == {
        "shared_hit": 143191,
        "shared_read": 16708215,
        "shared_dirtied": 6378,
        "shared_written": 179,
        "temp_read": 4983014,
        "temp_written": 4991091,
    }
    assert entry["wal"] == {"records": None, "fpi": None, "bytes": None}


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
    assert entry["rows"] == 0
    assert entry["buffers"] == {
        "shared_hit": 143191,
        "shared_read": 16708215,
        "shared_dirtied": 6378,
        "shared_written": 179,
        "temp_read": 4983014,
        "temp_written": 4991091,
    }
    assert entry["wal"] == {"records": None, "fpi": None, "bytes": None}


def test_create_log_parser_resolves_json_and_text():
    assert isinstance(PGAutoExplainAnalyzer._create_log_parser("json"), JsonLogParser)
    assert isinstance(PGAutoExplainAnalyzer._create_log_parser("text"), TextLogParser)


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
