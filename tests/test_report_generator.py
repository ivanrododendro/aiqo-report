from pathlib import Path

from aiqo_pg_ai_report.report_generator import ReportGenerator


def _minimal_report(code="ABC123DEF456", timestamp="2026-04-18 09:30:00"):
    return {
        "code": code,
        "short_code": code[:6],
        "title": "Target query title",
        "query_text": "select * from demo",
        "query_name": "demo query",
        "job_name": "demo job",
        "query_timestamp": timestamp,
        "day": timestamp[:10],
        "query_start_utc": None,
        "query_end_utc": None,
        "seq_scan_indicator": False,
        "duration": 1500,
        "cost": 10,
        "rows": 1,
        "buffers": None,
        "wal": None,
        "ai_hints": "",
        "plan": "No execution plan available",
    }


def test_head_template_embeds_svg_favicon():
    template_base_path = Path(__file__).resolve().parents[1] / "src" / "aiqo_pg_ai_report"
    generator = ReportGenerator(template_base_path, debug=True)

    rendered = generator.env.get_template("_head.html").render(metadata={"title": "Test report"}, context_json="{}")

    assert 'rel="icon"' in rendered
    assert 'rel="shortcut icon"' in rendered
    assert "data:image/svg+xml;base64," in rendered


def test_standard_report_header_shows_auto_explain_log_min_duration_from_server_config(tmp_path):
    template_base_path = Path(__file__).resolve().parents[1] / "src" / "aiqo_pg_ai_report"
    generator = ReportGenerator(template_base_path, debug=True)
    report = _minimal_report()
    output_path = tmp_path / "report.html"

    generator.generate_report(
        output_path=output_path,
        title="PostgreSQL Auto Explain Report",
        model=None,
        app_version="test",
        query_stats=[{"code": report["code"], "name": "demo query", "count": 1, "cumulated_time": 1500}],
        reports_by_day={report["day"]: [report]},
        daily_query_stats={
            report["day"]: {
                "total_queries": 1,
                "cumulated_time": 1500,
                "queries_by_code": {report["code"]: 1500},
            }
        },
        query_optimizations={},
        server_optimizations=[],
        event_optimizations=[],
        ddl_context=None,
        server_config_context="auto_explain.log_min_duration = '1500ms'",
        project_context=None,
        skip_ai_analysis=True,
        general_hints_synthesis=None,
    )

    rendered = output_path.read_text(encoding="utf-8")
    assert "auto_explain.log_min_duration: 1.5 seconds" in rendered
    assert "Only queries exceeding this threshold are displayed in the report." in rendered


def test_standard_query_details_show_query_optimizations_under_trend_without_opts_tab(tmp_path):
    template_base_path = Path(__file__).resolve().parents[1] / "src" / "aiqo_pg_ai_report"
    generator = ReportGenerator(template_base_path, debug=True)
    report = _minimal_report()
    output_path = tmp_path / "report.html"

    generator.generate_report(
        output_path=output_path,
        title="PostgreSQL Auto Explain Report",
        model=None,
        app_version="test",
        query_stats=[{"code": report["code"], "name": "demo query", "count": 1, "cumulated_time": 1500}],
        reports_by_day={report["day"]: [report]},
        daily_query_stats={
            report["day"]: {
                "total_queries": 1,
                "cumulated_time": 1500,
                "queries_by_code": {report["code"]: 1500},
            }
        },
        query_optimizations={report["code"]: [{"date": "2026-04-18", "text": "Added covering index"}]},
        server_optimizations=[],
        event_optimizations=[],
        ddl_context=None,
        server_config_context=None,
        project_context=None,
        skip_ai_analysis=True,
        general_hints_synthesis=None,
    )

    rendered = output_path.read_text(encoding="utf-8")
    assert 'data-qd-tab="opts"' not in rendered
    assert 'data-qd-pane="opts"' not in rendered
    assert 'id="under-chart-query-list-app-2026-04-18-0"' in rendered
    assert 'id="opt-list-app-2026-04-18-0"' in rendered
    assert "Added covering index" in rendered


def test_standard_query_details_hide_query_optimization_card_when_absent(tmp_path):
    template_base_path = Path(__file__).resolve().parents[1] / "src" / "aiqo_pg_ai_report"
    generator = ReportGenerator(template_base_path, debug=True)
    report = _minimal_report()
    output_path = tmp_path / "report.html"

    generator.generate_report(
        output_path=output_path,
        title="PostgreSQL Auto Explain Report",
        model=None,
        app_version="test",
        query_stats=[{"code": report["code"], "name": "demo query", "count": 1, "cumulated_time": 1500}],
        reports_by_day={report["day"]: [report]},
        daily_query_stats={
            report["day"]: {
                "total_queries": 1,
                "cumulated_time": 1500,
                "queries_by_code": {report["code"]: 1500},
            }
        },
        query_optimizations={},
        server_optimizations=[],
        event_optimizations=[],
        ddl_context=None,
        server_config_context=None,
        project_context=None,
        skip_ai_analysis=True,
        general_hints_synthesis=None,
    )

    rendered = output_path.read_text(encoding="utf-8")
    assert 'id="under-chart-query-list-app-2026-04-18-0"' not in rendered
    assert 'id="opt-list-app-2026-04-18-0"' not in rendered
    assert "Added covering index" not in rendered


def test_target_query_template_hides_selected_execution_card_and_keeps_selected_report_details():
    template_base_path = Path(__file__).resolve().parents[1] / "src" / "aiqo_pg_ai_report"
    generator = ReportGenerator(template_base_path, debug=True)

    rendered = generator.target_query_template.render(
        metadata={
            "model": None,
            "skip_ai_analysis": True,
            "timestamp": "2026-04-18 10:00:00",
            "version": "test",
            "auto_explain_log_min_duration": "2 minutes",
        },
        target_query={
            "short_code": "ABC123",
            "occurrences": 2,
            "selected_day": "2026-04-18",
            "selected_index": 1,
            "selected_report": {
                "code": "ABC123DEF456",
                "short_code": "ABC123",
                "title": "Target query title",
                "query_timestamp": "2026-04-18 09:30:00",
                "query_start_utc": None,
                "query_end_utc": None,
                "ai_hints": "",
                "plan": "No execution plan available",
            },
        },
        reports={
            "by_day": {
                "2026-04-17": [
                    {
                        "code": "ABC123DEF456",
                        "short_code": "ABC123",
                        "title": "Older execution",
                        "query_timestamp": "2026-04-17 09:00:00",
                        "query_start_utc": None,
                        "query_end_utc": None,
                        "ai_hints": "",
                        "plan": "No execution plan available",
                    }
                ],
                "2026-04-18": [
                    {
                        "code": "ABC123DEF456",
                        "short_code": "ABC123",
                        "title": "Newest execution",
                        "query_timestamp": "2026-04-18 09:15:00",
                        "query_start_utc": None,
                        "query_end_utc": None,
                        "ai_hints": "",
                        "plan": "No execution plan available",
                    },
                    {
                        "code": "ABC123DEF456",
                        "short_code": "ABC123",
                        "title": "Target query title",
                        "query_timestamp": "2026-04-18 09:30:00",
                        "query_start_utc": None,
                        "query_end_utc": None,
                        "ai_hints": "",
                        "plan": "No execution plan available",
                    },
                ],
            }
        },
        contexts={
            "ddl": "CREATE TABLE demo(id int);",
            "server_config": None,
            "project": None,
        },
        optimizations={
            "query": {},
            "annotations": {"legend_entries": {"generic": []}},
        },
    )

    assert "Selected execution" in rendered
    assert 'id="selectedExecutionLabel"' in rendered
    assert "2026-04-18 09:30:00" in rendered
    assert "auto_explain.log_min_duration: 2 minutes" in rendered
    assert "Only queries exceeding this threshold are displayed in the report." in rendered
    assert ">Target Query<" in rendered
    assert ">Occurrences<" in rendered
    assert "col-12 col-lg-4" in rendered
    assert 'id="targetQueryContextSection"' in rendered
    assert ">Context<" in rendered
    assert "Target query details" in rendered
    assert "Execution plan" in rendered
    assert 'id="planCompareModal"' in rendered
    assert 'id="query-tab-2026-04-17-0"' in rendered
    assert 'id="query-content-2026-04-17-0"' in rendered
    assert "query-content-2026-04-18-1" in rendered
    assert "Target query title" in rendered
    assert rendered.index("Target query details") < rendered.index(">Context<")


def test_target_query_template_optimizations_follow_standard_visibility_rule():
    template_base_path = Path(__file__).resolve().parents[1] / "src" / "aiqo_pg_ai_report"
    generator = ReportGenerator(template_base_path, debug=True)

    base_context = {
        "metadata": {
            "model": None,
            "skip_ai_analysis": True,
            "timestamp": "2026-04-18 10:00:00",
            "version": "test",
        },
        "target_query": {
            "short_code": "ABC123",
            "occurrences": 2,
            "selected_day": "2026-04-18",
            "selected_index": 1,
            "selected_report": {
                "code": "ABC123DEF456",
                "short_code": "ABC123",
                "title": "Target query title",
                "query_timestamp": "2026-04-18 09:30:00",
                "query_start_utc": None,
                "query_end_utc": None,
                "ai_hints": "",
                "plan": "No execution plan available",
            },
        },
        "reports": {
            "by_day": {
                "2026-04-18": [
                    {
                        "code": "ABC123DEF456",
                        "short_code": "ABC123",
                        "title": "Older execution",
                        "query_timestamp": "2026-04-18 09:15:00",
                        "query_start_utc": None,
                        "query_end_utc": None,
                        "ai_hints": "",
                        "plan": "No execution plan available",
                    },
                    {
                        "code": "ABC123DEF456",
                        "short_code": "ABC123",
                        "title": "Target query title",
                        "query_timestamp": "2026-04-18 09:30:00",
                        "query_start_utc": None,
                        "query_end_utc": None,
                        "ai_hints": "",
                        "plan": "No execution plan available",
                    },
                ]
            }
        },
        "contexts": {
            "ddl": None,
            "server_config": None,
            "project": None,
        },
    }

    rendered_without_optimizations = generator.target_query_template.render(
        **base_context,
        optimizations={
            "query": {},
            "annotations": {"legend_entries": {"generic": []}},
        },
    )

    rendered_with_optimizations = generator.target_query_template.render(
        **base_context,
        optimizations={
            "query": {
                "ABC123DEF456": [
                    {"date": "2026-04-17", "text": "Added covering index"},
                ]
            },
            "annotations": {"legend_entries": {"generic": []}},
        },
    )

    assert 'id="heading-queryopt-app-2026-04-18-1"' not in rendered_without_optimizations
    assert 'id="heading-queryopt-app-2026-04-18-1"' in rendered_with_optimizations
    assert "Added covering index" in rendered_with_optimizations


def test_target_query_template_shows_server_optimizations_and_events_by_default():
    template_base_path = Path(__file__).resolve().parents[1] / "src" / "aiqo_pg_ai_report"
    generator = ReportGenerator(template_base_path, debug=True)

    rendered = generator.target_query_template.render(
        metadata={
            "model": None,
            "skip_ai_analysis": True,
            "timestamp": "2026-04-18 10:00:00",
            "version": "test",
        },
        target_query={
            "short_code": "ABC123",
            "occurrences": 1,
            "selected_day": "2026-04-18",
            "selected_index": 0,
            "selected_report": {
                "code": "ABC123DEF456",
                "short_code": "ABC123",
                "title": "Target query title",
                "query_timestamp": "2026-04-18 09:30:00",
                "query_start_utc": None,
                "query_end_utc": None,
                "ai_hints": "",
                "plan": "No execution plan available",
            },
        },
        reports={
            "by_day": {
                "2026-04-18": [
                    {
                        "code": "ABC123DEF456",
                        "short_code": "ABC123",
                        "title": "Target query title",
                        "query_timestamp": "2026-04-18 09:30:00",
                        "query_start_utc": None,
                        "query_end_utc": None,
                        "ai_hints": "",
                        "plan": "No execution plan available",
                    }
                ]
            }
        },
        contexts={
            "ddl": None,
            "server_config": None,
            "project": None,
        },
        optimizations={
            "query": {},
            "annotations": {
                "legend_entries": {
                    "generic": [
                        {
                            "id": "S1",
                            "type": "Server",
                            "date": "2026-04-18",
                            "text": "Raised work_mem",
                        },
                        {
                            "id": "E1",
                            "type": "Event",
                            "date": "2026-04-18",
                            "text": "Vacuum freeze completed",
                        },
                    ]
                }
            },
        },
    )

    assert (
        'id="toggle-ann-server-app-2026-04-18-0" data-query-annotation-key="includeServer" checked'
        in rendered
    )
    assert (
        'id="toggle-ann-generic-app-2026-04-18-0" data-query-annotation-key="includeGeneric" checked'
        in rendered
    )
    assert 'class="card card-body mt-3 fade-toggle is-shown" id="under-chart-server-list-app-2026-04-18-0"' in rendered
    assert 'class="card card-body mt-3 fade-toggle is-shown" id="under-chart-event-list-app-2026-04-18-0"' in rendered
    assert 'class="card card-body mt-3 fade-toggle is-hidden" id="under-chart-server-list-app-2026-04-18-0"' not in rendered
    assert 'class="card card-body mt-3 fade-toggle is-hidden" id="under-chart-event-list-app-2026-04-18-0"' not in rendered
