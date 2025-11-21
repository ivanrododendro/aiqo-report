from pathlib import Path

import pytest

from aiqo_pg_ai_report.log_parser import LogParser


DATA_DIR = Path(__file__).parent / "data"


def test_parse_log_file_with_full_text_plan():
    log_path = DATA_DIR / "full-text-plan.log"
    entries = list(LogParser().parse_log_file(log_path))

    assert len(entries) == 1
    entry = entries[0]

    assert entry["timestamp"] == "2025-10-24 22:31:57 CES"
    assert entry["job_name"] == "-- Job: RDA"
    assert entry["query_name"] == (
        "-- Task /Match and Find Duplicates/Redevabilite/Notify referencing that my SDPK has changed/Notify "
        "Referencing MI AssocieInterloCoordRede that my Golden Id has changed"
    )
    assert entry["query_text"].startswith("update MI_ASSOCIE_INTERLO_COORD_RED as T")
    assert entry["execution_plan"].startswith(
        "Limit  (cost=29563.14..44521.37 rows=100 width=738) (actual rows=2 loops=1)"
    )
    assert entry["duration"] == pytest.approx(5830959.445)
    assert entry["startup_cost"] == pytest.approx(29563.14)
    assert entry["cost"] == pytest.approx(44521.37)
    assert entry["rows"] == 2
    assert entry["buffers"] == {
        "shared_hit": 17250,
        "shared_read": 0,
        "shared_dirtied": 0,
        "shared_written": 0,
        "temp_read": None,
        "temp_written": None,
    }
    assert entry["wal"] == {"records": None, "fpi": None, "bytes": None}
