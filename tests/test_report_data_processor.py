from aiqo_pg_ai_report.report_data_processor import ReportDataProcessor


def test_enhance_reports_by_day_adds_query_time_bounds_and_sorts_by_start():
    processor = ReportDataProcessor()

    reports_by_day = {
        "2025-11-26": [
            {
                "code": "Q_LATE",
                "title": "Late query",
                "query_timestamp": "2025-11-26 14:10:00",
                "duration": 30_000,
                "ai_hints": "",
                "buffers": None,
                "wal": None,
            },
            {
                "code": "Q_EARLY",
                "title": "Early query",
                "query_timestamp": "2025-11-26 14:05:00",
                "duration": 120_000,
                "ai_hints": "",
                "buffers": None,
                "wal": None,
            },
        ]
    }

    enhanced = processor._enhance_reports_by_day(reports_by_day, {}, {})
    day_reports = enhanced["2025-11-26"]

    assert [report["code"] for report in day_reports] == ["Q_EARLY", "Q_LATE"]
    assert day_reports[0]["query_end_utc"] == day_reports[0]["query_timestamp_utc"]
    assert day_reports[0]["query_start_utc"] == day_reports[0]["query_end_utc"] - 120_000
    assert day_reports[1]["query_start_utc"] == day_reports[1]["query_end_utc"] - 30_000
