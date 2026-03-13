from types import SimpleNamespace
from pathlib import Path

import pytest

from aiqo_pg_ai_report import pg_autoexplain_analyzer


def _build_log_entry(timestamp: str, query_name: str = "-- Task Sample") -> dict:
    return {
        "query_text": "select * from demo where id = 1",
        "query_name": query_name,
        "job_name": "-- Job: TEST",
        "execution_plan": '{"Plan": {"Node Type": "Seq Scan"}}',
        "timestamp": timestamp,
        "duration": 12.5,
        "cost": 42.0,
        "rows": 1,
        "buffers": None,
        "wal": None,
    }


def test_ai_call_invoked_with_filter_and_limit(monkeypatch):
    log_path = Path("tests/data/full-text-plan.log")
    filter_code = "ABCDEF"

    # Ensure model info and token counter succeed without hitting external services.
    monkeypatch.setattr(
        pg_autoexplain_analyzer.litellm,
        "get_model_info",
        lambda model: {"max_input_tokens": 128000, "litellm_provider": "openai"},
    )
    monkeypatch.setattr(pg_autoexplain_analyzer.litellm, "token_counter", lambda **kwargs: 10)

    completion_calls = []

    class DummyUsage:
        def __init__(self) -> None:
            self.prompt_tokens = 5
            self.completion_tokens = 2

    class DummyMessage:
        def __init__(self, content: str) -> None:
            self.content = content

    class DummyChoice:
        def __init__(self, content: str) -> None:
            self.message = DummyMessage(content)

    class DummyResponse:
        def __init__(self, content: str) -> None:
            self.usage = DummyUsage()
            self.choices = [DummyChoice(content)]

    def fake_completion(**kwargs):
        completion_calls.append(kwargs)
        return DummyResponse("ok")

    monkeypatch.setattr(pg_autoexplain_analyzer.litellm, "completion", fake_completion)
    monkeypatch.setattr(pg_autoexplain_analyzer.litellm, "completion_cost", lambda completion_response: 0.0)

    # Avoid filesystem output and heavy context loading during the test.
    monkeypatch.setattr(pg_autoexplain_analyzer.ReportGenerator, "generate_report", lambda *args, **kwargs: None)
    monkeypatch.setattr(pg_autoexplain_analyzer.ContextLoader, "load_all_contexts", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        pg_autoexplain_analyzer.ContextLoader,
        "build_full_prompt_with_optimizations",
        lambda self, **kwargs: "prompt",
    )
    monkeypatch.setattr(pg_autoexplain_analyzer.ContextLoader, "get_query_optimizations", lambda *args, **kwargs: None)

    # Force the query code to match the filter.
    monkeypatch.setattr(pg_autoexplain_analyzer.SQLUtils, "get_query_code", lambda *_: filter_code)

    args = pg_autoexplain_analyzer.parse_cli_arguments([str(log_path), "-l", "1", "-f", filter_code, "-m", "gpt-4o"])
    analyzer = pg_autoexplain_analyzer.PGAutoExplainAnalyzer(args)

    # Seed minimal context attributes used when generating reports.
    analyzer.context_loader.query_optimizations_cache = {}
    analyzer.context_loader.server_optimizations = []
    analyzer.context_loader.event_optimizations = []
    analyzer.context_loader.ddl_context = None
    analyzer.context_loader.server_configuration_context = None
    analyzer.context_loader.project_context = None

    analyzer.run()

    assert len(completion_calls) == 1
    assert completion_calls[0]["model"] == "gpt-4o"


def test_report_generation_is_skipped_when_no_queries_are_parsed(monkeypatch, caplog):
    log_path = Path("tests/data/full-text-plan.log")
    generated_reports = []

    monkeypatch.setattr(
        pg_autoexplain_analyzer.ContextLoader,
        "load_all_contexts",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        pg_autoexplain_analyzer.ReportGenerator,
        "generate_report",
        lambda *args, **kwargs: generated_reports.append(args),
    )
    monkeypatch.setattr(
        pg_autoexplain_analyzer.TextLogParser,
        "parse_log_file",
        lambda self, log_file_path: iter(()),
    )

    args = pg_autoexplain_analyzer.parse_cli_arguments([str(log_path), "--skip_ai_analysis"])
    analyzer = pg_autoexplain_analyzer.PGAutoExplainAnalyzer(args)

    analyzer.context_loader.query_optimizations_cache = {}
    analyzer.context_loader.server_optimizations = []
    analyzer.context_loader.event_optimizations = []
    analyzer.context_loader.ddl_context = None
    analyzer.context_loader.server_configuration_context = None
    analyzer.context_loader.project_context = None

    with caplog.at_level("INFO"):
        analyzer.run()

    assert generated_reports == []
    assert "No queries were analyzed for the selected log input. Report generation will be skipped." in caplog.text


def test_disable_provider_cache_flag_is_parsed_and_forwarded(monkeypatch):
    log_path = Path("tests/data/full-text-plan.log")

    monkeypatch.setattr(
        pg_autoexplain_analyzer.ContextLoader,
        "load_all_contexts",
        lambda *args, **kwargs: None,
    )

    args = pg_autoexplain_analyzer.parse_cli_arguments([str(log_path), "--disable-provider-cache"])
    analyzer = pg_autoexplain_analyzer.PGAutoExplainAnalyzer(args)

    assert args.disable_provider_cache is True
    assert analyzer.ai_caller.disable_provider_cache is True


def test_ai_analysis_runs_once_per_query_by_default_and_reuses_hints(monkeypatch):
    log_path = Path("tests/data/full-text-plan.log")
    completion_calls = []

    monkeypatch.setattr(
        pg_autoexplain_analyzer.litellm,
        "get_model_info",
        lambda model: {"max_input_tokens": 128000, "litellm_provider": "openai"},
    )
    monkeypatch.setattr(pg_autoexplain_analyzer.litellm, "token_counter", lambda **kwargs: 10)

    class DummyUsage:
        def __init__(self) -> None:
            self.prompt_tokens = 5
            self.completion_tokens = 2

    class DummyMessage:
        def __init__(self, content: str) -> None:
            self.content = content

    class DummyChoice:
        def __init__(self, content: str) -> None:
            self.message = DummyMessage(content)

    class DummyResponse:
        def __init__(self, content: str) -> None:
            self.usage = DummyUsage()
            self.choices = [DummyChoice(content)]

    def fake_completion(**kwargs):
        completion_calls.append(kwargs)
        return DummyResponse("shared hints")

    monkeypatch.setattr(pg_autoexplain_analyzer.litellm, "completion", fake_completion)
    monkeypatch.setattr(pg_autoexplain_analyzer.litellm, "completion_cost", lambda completion_response: 0.0)
    monkeypatch.setattr(pg_autoexplain_analyzer.ReportGenerator, "generate_report", lambda *args, **kwargs: None)
    monkeypatch.setattr(pg_autoexplain_analyzer.ContextLoader, "load_all_contexts", lambda *args, **kwargs: None)
    monkeypatch.setattr(pg_autoexplain_analyzer.ContextLoader, "get_query_optimizations", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        pg_autoexplain_analyzer.TextLogParser,
        "parse_log_file",
        lambda self, log_file_path: iter(
            [
                _build_log_entry("2025-11-26 14:42:44 CET", "-- Task First"),
                _build_log_entry("2025-11-26 14:43:44 CET", "-- Task Second"),
            ]
        ),
    )
    monkeypatch.setattr(pg_autoexplain_analyzer.SQLUtils, "get_query_code", lambda *_: "ABCDEF123456")

    args = pg_autoexplain_analyzer.parse_cli_arguments([str(log_path), "-m", "gpt-4o"])
    analyzer = pg_autoexplain_analyzer.PGAutoExplainAnalyzer(args)
    analyzer.context_loader.query_optimizations_cache = {}
    analyzer.context_loader.server_optimizations = []
    analyzer.context_loader.event_optimizations = []
    analyzer.context_loader.ddl_context = None
    analyzer.context_loader.server_configuration_context = None
    analyzer.context_loader.project_context = None

    analyzer.run()

    assert len(completion_calls) == 1
    assert len(analyzer.data_processor.all_reports) == 2
    assert analyzer.data_processor.all_reports[0]["ai_hints"] == "shared hints"
    assert analyzer.data_processor.all_reports[1]["ai_hints"] == (
        "AI analysis skipped, same query was already analyzed earlier."
    )


def test_analyze_all_queries_flag_forces_ai_call_for_each_occurrence(monkeypatch):
    log_path = Path("tests/data/full-text-plan.log")
    completion_calls = []

    monkeypatch.setattr(
        pg_autoexplain_analyzer.litellm,
        "get_model_info",
        lambda model: {"max_input_tokens": 128000, "litellm_provider": "openai"},
    )
    monkeypatch.setattr(pg_autoexplain_analyzer.litellm, "token_counter", lambda **kwargs: 10)

    class DummyUsage:
        def __init__(self) -> None:
            self.prompt_tokens = 5
            self.completion_tokens = 2

    class DummyMessage:
        def __init__(self, content: str) -> None:
            self.content = content

    class DummyChoice:
        def __init__(self, content: str) -> None:
            self.message = DummyMessage(content)

    class DummyResponse:
        def __init__(self, content: str) -> None:
            self.usage = DummyUsage()
            self.choices = [DummyChoice(content)]

    def fake_completion(**kwargs):
        completion_calls.append(kwargs)
        return DummyResponse(f"hints {len(completion_calls)}")

    monkeypatch.setattr(pg_autoexplain_analyzer.litellm, "completion", fake_completion)
    monkeypatch.setattr(pg_autoexplain_analyzer.litellm, "completion_cost", lambda completion_response: 0.0)
    monkeypatch.setattr(pg_autoexplain_analyzer.ReportGenerator, "generate_report", lambda *args, **kwargs: None)
    monkeypatch.setattr(pg_autoexplain_analyzer.ContextLoader, "load_all_contexts", lambda *args, **kwargs: None)
    monkeypatch.setattr(pg_autoexplain_analyzer.ContextLoader, "get_query_optimizations", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        pg_autoexplain_analyzer.TextLogParser,
        "parse_log_file",
        lambda self, log_file_path: iter(
            [
                _build_log_entry("2025-11-26 14:42:44 CET", "-- Task First"),
                _build_log_entry("2025-11-26 14:43:44 CET", "-- Task Second"),
            ]
        ),
    )
    monkeypatch.setattr(pg_autoexplain_analyzer.SQLUtils, "get_query_code", lambda *_: "ABCDEF123456")

    args = pg_autoexplain_analyzer.parse_cli_arguments([str(log_path), "-m", "gpt-4o", "--analyze-all-queries"])
    analyzer = pg_autoexplain_analyzer.PGAutoExplainAnalyzer(args)
    analyzer.context_loader.query_optimizations_cache = {}
    analyzer.context_loader.server_optimizations = []
    analyzer.context_loader.event_optimizations = []
    analyzer.context_loader.ddl_context = None
    analyzer.context_loader.server_configuration_context = None
    analyzer.context_loader.project_context = None

    analyzer.run()

    assert args.analyze_all_queries is True
    assert len(completion_calls) == 2
    assert analyzer.data_processor.all_reports[0]["ai_hints"] == "hints 1"
    assert analyzer.data_processor.all_reports[1]["ai_hints"] == "hints 2"
