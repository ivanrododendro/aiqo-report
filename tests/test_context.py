from pathlib import Path

from aiqo_pg_ai_report.context import ContextLoader


def test_build_prompt_segments_keeps_query_optimizations_out_of_cacheable_prefix(monkeypatch):
    loader = ContextLoader(script_base_path=Path(__file__).resolve().parents[1] / "src/aiqo_pg_ai_report")
    loader.ddl_context = "ddl"
    loader.server_configuration_context = "config"
    loader.project_context = "project"
    loader.server_optimizations = [{"date": "2026-01-01", "text": "server opt"}]
    monkeypatch.setattr(
        loader,
        "get_query_optimizations",
        lambda query_code: [{"date": "2026-01-02", "text": "query opt"}],
    )

    prompt_segments = loader.build_prompt_segments_with_optimizations(
        plan="PLAN CONTENT",
        query_code="ABCDEF123456",
        custom_prompt="custom note",
        lang="it",
    )

    assert "server opt" in prompt_segments["cacheable_prefix"]
    assert "custom note" in prompt_segments["cacheable_prefix"]
    assert "query opt" not in prompt_segments["cacheable_prefix"]
    assert "query opt" in prompt_segments["dynamic_suffix"]
    assert "PLAN CONTENT" in prompt_segments["dynamic_suffix"]
    assert prompt_segments["has_static_context"] is True
    assert prompt_segments["dynamic_suffix"].endswith("Please provide the analysis in it.")


def test_build_prompt_segments_reports_no_static_context_when_only_base_prompts_are_present():
    loader = ContextLoader(script_base_path=Path(__file__).resolve().parents[1] / "src/aiqo_pg_ai_report")

    prompt_segments = loader.build_prompt_segments_with_optimizations(
        plan="PLAN CONTENT",
        query_code="ABCDEF123456",
        custom_prompt=None,
        lang="it",
    )

    assert prompt_segments["has_static_context"] is False


def test_build_general_hints_synthesis_prompt_segments_include_cacheable_context():
    loader = ContextLoader(script_base_path=Path(__file__).resolve().parents[1] / "src/aiqo_pg_ai_report")
    loader.server_configuration_context = "shared config"
    loader.project_context = "shared project"

    prompt_segments = loader.build_general_hints_synthesis_prompt_segments(
        ai_hints=["<p>hint one</p>", "<p>hint two</p>"],
        lang="it",
    )

    assert "GENERAL HINTS SYNTHESIS" in prompt_segments["cacheable_prefix"]
    assert "shared config" in prompt_segments["cacheable_prefix"]
    assert "shared project" in prompt_segments["cacheable_prefix"]
    assert "HINTS LIST" in prompt_segments["dynamic_suffix"]
    assert "<p>hint one</p>" in prompt_segments["dynamic_suffix"]
    assert "<p>hint two</p>" in prompt_segments["dynamic_suffix"]
    assert prompt_segments["dynamic_suffix"].endswith("Please provide the analysis in it.")
    assert prompt_segments["has_static_context"] is True


def test_target_query_prompt_segments_limit_optimizations_to_query_date_range(monkeypatch):
    loader = ContextLoader(script_base_path=Path(__file__).resolve().parents[1] / "src/aiqo_pg_ai_report")
    loader.server_optimizations = [
        {"date": "2026-01-04", "text": "server before range"},
        {"date": "2026-01-05", "text": "server inside range"},
        {"date": "2026-01-08", "text": "server after range"},
    ]
    loader.event_optimizations = [
        {"date": "2026-01-05", "text": "event inside range"},
        {"date": "2026-01-09", "text": "event after range"},
    ]
    monkeypatch.setattr(
        loader,
        "get_query_optimizations",
        lambda query_code: [
            {"date": "2026-01-04", "text": "query before range"},
            {"date": "2026-01-07", "text": "query inside range"},
        ],
    )
    loader.set_query_date_range_from_entries(
        [
            {"timestamp": "2026-01-05 10:00:00"},
            {"timestamp": "2026-01-07 12:00:00"},
        ]
    )

    prompt_segments = loader.build_target_query_prompt_segments(
        query_code="ABCDEF123456",
        query_text="select * from demo",
        occurrences=[{"timestamp": "2026-01-05 10:00:00", "execution_plan": "Seq Scan on demo"}],
        lang="it",
    )

    cacheable_prefix = prompt_segments["cacheable_prefix"]
    assert "server inside range" in cacheable_prefix
    assert "event inside range" in cacheable_prefix
    assert "query inside range" in cacheable_prefix
    assert "server before range" not in cacheable_prefix
    assert "server after range" not in cacheable_prefix
    assert "event after range" not in cacheable_prefix
    assert "query before range" not in cacheable_prefix
    assert prompt_segments["has_static_context"] is True


def test_target_query_prompt_segments_include_concise_output_constraints():
    loader = ContextLoader(script_base_path=Path(__file__).resolve().parents[1] / "src/aiqo_pg_ai_report")

    prompt_segments = loader.build_target_query_prompt_segments(
        query_code="ABCDEF123456",
        query_text="select * from demo",
        occurrences=[{"timestamp": "2026-01-05 10:00:00", "execution_plan": "Seq Scan on demo"}],
        lang="it",
    )

    cacheable_prefix = prompt_segments["cacheable_prefix"]
    assert "between 350 and 500 words" in cacheable_prefix
    assert "at most 2-3 short sentences or bullets per section" in cacheable_prefix
    assert "Do not repeat the full SQL, full execution plans, or raw metric lists" in cacheable_prefix
    assert "Prefer concise, decision-oriented analysis" in cacheable_prefix
    assert "duration, processed volume, execution plan changes, IO/WAL metrics" in cacheable_prefix
    assert "Treat SERVER OPTIMIZATIONS and EVENTS as candidate explanations" in cacheable_prefix
    assert "Do not mention table-specific optimizations for tables that do not appear" in cacheable_prefix
    assert "Do not add \"no impact\" statements for unrelated context" in cacheable_prefix
    assert "Evidence-backed drivers of change" in cacheable_prefix
    assert "Relevant factors ruled out" in cacheable_prefix
    assert prompt_segments["dynamic_suffix"].endswith("Please provide the analysis in it.")
