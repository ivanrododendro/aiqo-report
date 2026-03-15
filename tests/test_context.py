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
