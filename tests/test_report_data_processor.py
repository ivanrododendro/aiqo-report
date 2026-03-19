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
    assert day_reports[0]["plan_structure"] is None


def test_enhance_reports_by_day_exposes_plan_structure_for_text_plan():
    processor = ReportDataProcessor()

    reports_by_day = {
        "2025-11-26": [
            {
                "code": "Q_PLAN",
                "title": "Plan query",
                "query_timestamp": "2025-11-26 14:05:00",
                "duration": 120_000,
                "ai_hints": "",
                "buffers": None,
                "wal": None,
                "plan": "Nested Loop  (cost=10.00..20.00 rows=5 width=16) (actual time=0.100..0.400 rows=5 loops=1)\n"
                "  ->  Index Scan using idx_orders on orders  (cost=0.30..8.00 rows=5 width=8) "
                "(actual time=0.050..0.100 rows=5 loops=1)\n"
                "Settings:",
            }
        ]
    }

    enhanced = processor._enhance_reports_by_day(reports_by_day, {}, {})
    plan_structure = enhanced["2025-11-26"][0]["plan_structure"]

    assert plan_structure is not None
    assert plan_structure["Plan"]["Node Type"] == "Nested Loop"
    assert plan_structure["Plan"]["Plans"][0]["Node Type"] == "Index Scan"


def test_add_duplicate_ai_analysis_links_maps_skipped_query_to_first_analyzed_occurrence():
    processor = ReportDataProcessor()

    reports_by_day = {
        "2025-11-26": [
            {
                "code": "Q1",
                "title": "First query",
                "query_timestamp": "2025-11-26 10:00:00",
                "duration": 1000,
                "ai_hints": "AI hints available",
                "buffers": None,
                "wal": None,
            },
            {
                "code": "Q1",
                "title": "Duplicate query",
                "query_timestamp": "2025-11-26 10:05:00",
                "duration": 1000,
                "ai_hints": "AI analysis skipped, same query was already analyzed earlier.",
                "buffers": None,
                "wal": None,
            },
        ]
    }

    enhanced = processor._enhance_reports_by_day(reports_by_day, {}, {})
    processor._add_duplicate_ai_analysis_links(enhanced)

    assert enhanced["2025-11-26"][1]["duplicate_analysis_target"] == {"day": "2025-11-26", "index": 0}


def test_add_duplicate_ai_analysis_links_maps_skipped_query_to_first_analyzed_occurrence_across_days():
    processor = ReportDataProcessor()

    reports_by_day = {
        "2025-11-25": [
            {
                "code": "Q1",
                "title": "First query",
                "query_timestamp": "2025-11-25 23:55:00",
                "duration": 1000,
                "ai_hints": "AI hints available",
                "buffers": None,
                "wal": None,
            }
        ],
        "2025-11-26": [
            {
                "code": "Q1",
                "title": "Duplicate query",
                "query_timestamp": "2025-11-26 10:05:00",
                "duration": 1000,
                "ai_hints": "AI analysis skipped, same query was already analyzed earlier.",
                "buffers": None,
                "wal": None,
            }
        ],
    }

    enhanced = processor._enhance_reports_by_day(reports_by_day, {}, {})
    processor._add_duplicate_ai_analysis_links(enhanced)

    assert enhanced["2025-11-26"][0]["duplicate_analysis_target"] == {"day": "2025-11-25", "index": 0}


def test_attach_plan_comparisons_uses_previous_execution_of_same_query_code():
    processor = ReportDataProcessor()

    baseline_plan = """
    {
      "Plan": {
        "Node Type": "Hash Join",
        "Actual Rows": 10,
        "Plan Rows": 12,
        "Workers Planned": 2,
        "Plans": [
          {"Node Type": "Seq Scan", "Relation Name": "orders"},
          {"Node Type": "Index Scan", "Relation Name": "customers", "Index Name": "idx_customers_id"}
        ]
      }
    }
    """
    current_plan = """
    {
      "Plan": {
        "Node Type": "Nested Loop",
        "Actual Rows": 1000,
        "Plan Rows": 10,
        "Plans": [
          {"Node Type": "Seq Scan", "Relation Name": "orders"},
          {"Node Type": "Seq Scan", "Relation Name": "customers"}
        ]
      }
    }
    """

    reports_by_day = {
        "2025-11-26": [
            {
                "code": "Q1",
                "title": "First query",
                "query_timestamp": "2025-11-26 10:00:00",
                "duration": 1_000,
                "ai_hints": "",
                "buffers": {"shared_read": 5},
                "wal": {"bytes": 512},
                "plan": baseline_plan,
            },
            {
                "code": "Q1",
                "title": "Second query",
                "query_timestamp": "2025-11-26 10:05:00",
                "duration": 2_000,
                "ai_hints": "",
                "buffers": {"shared_read": 20, "temp_written": 10},
                "wal": {"bytes": 4096},
                "plan": current_plan,
            },
        ]
    }

    enhanced = processor._enhance_reports_by_day(reports_by_day, {}, {})
    processor._attach_plan_comparisons(enhanced)

    comparison = enhanced["2025-11-26"][1]["plan_comparison"]

    assert comparison["baseline"] == {
        "day": "2025-11-26",
        "index": 0,
        "title": "First query",
        "timestamp": "2025-11-26 10:00:00",
    }
    assert comparison["status"] == "regressed"
    assert comparison["comparison_scope"] == "metrics_and_structure"
    assert "Plan shape changed." in comparison["summary"]
    assert any(change == "Root node changed from Hash Join to Nested Loop." for change in comparison["structural_changes"])
    assert any(change == "Index Scan removed." for change in comparison["structural_changes"])
    assert any(change == "Seq Scan count increased from 1 to 2." for change in comparison["structural_changes"])
    assert any(
        highlight == "Row estimate drift worsened on the root plan node." for highlight in comparison["highlights"]
    )
    assert comparison["tree_summary"] == {
        "total": 3,
        "changed": 2,
        "added": 0,
        "removed": 0,
        "unchanged": 1,
    }
    assert comparison["tree"]["status"] == "changed"
    assert comparison["tree"]["title"] == "Nested Loop"
    assert comparison["tree"]["current_label"] == "Nested Loop"
    assert comparison["tree"]["semantic_annotation"] == "changed, was Hash Join"
    assert comparison["tree"]["children"][0]["status"] == "unchanged"
    assert comparison["tree"]["children"][0]["semantic_annotation"] == "same"
    assert comparison["tree"]["children"][1]["status"] == "changed"
    assert comparison["tree"]["children"][1]["current_label"] == "Seq Scan"
    assert comparison["tree"]["children"][1]["semantic_annotation"] == "changed, was Index Scan"
    assert comparison["tree"]["children"][1]["changes"] == ["Node type changed from Index Scan to Seq Scan."]


def test_attach_plan_comparisons_falls_back_to_metrics_only_when_plan_is_not_parsable():
    processor = ReportDataProcessor()

    reports_by_day = {
        "2025-11-26": [
            {
                "code": "Q1",
                "title": "First query",
                "query_timestamp": "2025-11-26 10:00:00",
                "duration": 1_000,
                "ai_hints": "",
                "buffers": None,
                "wal": None,
                "plan": "plain text without any recognizable execution plan node",
            },
            {
                "code": "Q1",
                "title": "Second query",
                "query_timestamp": "2025-11-26 10:05:00",
                "duration": 900,
                "ai_hints": "",
                "buffers": None,
                "wal": None,
                "plan": "still not a recognizable plan structure",
            },
        ]
    }

    enhanced = processor._enhance_reports_by_day(reports_by_day, {}, {})
    processor._attach_plan_comparisons(enhanced)

    comparison = enhanced["2025-11-26"][1]["plan_comparison"]

    assert comparison["comparison_scope"] == "metrics_only"
    assert comparison["structural_changes"] == []
    assert comparison["tree"] is None
    assert comparison["tree_summary"] is None
    assert any("could not be parsed" in highlight for highlight in comparison["highlights"])


def test_attach_plan_comparisons_parses_text_plans_for_tree_compare():
    processor = ReportDataProcessor()

    baseline_plan = """
Nested Loop  (cost=10.00..20.00 rows=5 width=16) (actual time=0.100..0.400 rows=5 loops=1)
  Buffers: shared hit=10 read=2
  ->  Index Scan using idx_orders on orders  (cost=0.30..8.00 rows=5 width=8) (actual time=0.050..0.100 rows=5 loops=1)
        Buffers: shared hit=4 read=1
  ->  Index Scan using idx_customers on customers  (cost=0.20..2.00 rows=1 width=8) (actual time=0.020..0.050 rows=1 loops=5)
        Buffers: shared hit=6 read=1
Settings:
    """.strip()

    current_plan = """
Hash Join  (cost=12.00..35.00 rows=50 width=16) (actual time=0.200..1.200 rows=50 loops=1)
  Buffers: shared hit=20 read=9
  ->  Seq Scan on orders  (cost=0.00..15.00 rows=50 width=8) (actual time=0.080..0.600 rows=50 loops=1)
        Buffers: shared hit=8 read=5
  ->  Hash  (cost=8.00..8.00 rows=10 width=8) (actual time=0.100..0.120 rows=10 loops=1)
        ->  Seq Scan on customers  (cost=0.00..8.00 rows=10 width=8) (actual time=0.050..0.080 rows=10 loops=1)
              Buffers: shared hit=12 read=4
Settings:
    """.strip()

    reports_by_day = {
        "2025-11-26": [
            {
                "code": "QTXT",
                "title": "Baseline text query",
                "query_timestamp": "2025-11-26 10:00:00",
                "duration": 500,
                "ai_hints": "",
                "buffers": {"shared_read": 2},
                "wal": None,
                "plan": baseline_plan,
            },
            {
                "code": "QTXT",
                "title": "Current text query",
                "query_timestamp": "2025-11-26 10:05:00",
                "duration": 1200,
                "ai_hints": "",
                "buffers": {"shared_read": 9},
                "wal": None,
                "plan": current_plan,
            },
        ]
    }

    enhanced = processor._enhance_reports_by_day(reports_by_day, {}, {})
    processor._attach_plan_comparisons(enhanced)

    comparison = enhanced["2025-11-26"][1]["plan_comparison"]

    assert comparison["comparison_scope"] == "metrics_and_structure"
    assert comparison["tree"] is not None
    assert comparison["tree_summary"]["changed"] >= 1
    assert comparison["tree"]["title"] == "Hash Join"
    assert comparison["tree"]["current_label"] == "Hash Join"
    assert comparison["tree"]["semantic_annotation"] == "changed, was Nested Loop"
    assert comparison["tree"]["changes"] == ["Node type changed from Nested Loop to Hash Join."]
