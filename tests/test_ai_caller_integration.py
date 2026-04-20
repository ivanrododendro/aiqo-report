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

    args = pg_autoexplain_analyzer.parse_cli_arguments(
        [str(log_path), "-m", "gpt-4o", "--analyze-all-queries", "--disable-general-hints-synthesis"]
    )
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


def test_general_hints_synthesis_runs_when_at_least_two_queries_are_analyzed(monkeypatch):
    log_path = Path("tests/data/full-text-plan.log")
    completion_calls = []
    captured_reports = []

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
        messages = kwargs["messages"]
        prompt_text = messages[-1]["content"]
        completion_calls.append(prompt_text)
        if "GENERAL HINTS SYNTHESIS" in prompt_text:
            return DummyResponse("<p>generic synthesis</p>")
        return DummyResponse(f"<p>hint {len(completion_calls)}</p>")

    monkeypatch.setattr(pg_autoexplain_analyzer.litellm, "completion", fake_completion)
    monkeypatch.setattr(pg_autoexplain_analyzer.litellm, "completion_cost", lambda completion_response: 0.0)
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
    monkeypatch.setattr(
        pg_autoexplain_analyzer.SQLUtils,
        "get_query_code",
        lambda *_: f"CODE{len(captured_reports) + len(completion_calls)}",
    )

    def fake_generate_report(*args, **kwargs):
        captured_reports.append(args)

    monkeypatch.setattr(pg_autoexplain_analyzer.ReportGenerator, "generate_report", fake_generate_report)

    args = pg_autoexplain_analyzer.parse_cli_arguments([str(log_path), "-m", "gpt-4o", "--analyze-all-queries"])
    analyzer = pg_autoexplain_analyzer.PGAutoExplainAnalyzer(args)
    analyzer.context_loader.query_optimizations_cache = {}
    analyzer.context_loader.server_optimizations = []
    analyzer.context_loader.event_optimizations = []
    analyzer.context_loader.ddl_context = None
    analyzer.context_loader.server_configuration_context = None
    analyzer.context_loader.project_context = None

    analyzer.run()

    assert len(completion_calls) == 3
    assert any("GENERAL HINTS SYNTHESIS" in prompt for prompt in completion_calls)
    assert captured_reports[0][-1] == "<p>generic synthesis</p>"


def test_general_hints_synthesis_does_not_consume_query_ai_call_limit(monkeypatch):
    log_path = Path("tests/data/full-text-plan.log")
    completion_calls = []
    captured_reports = []

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
        prompt_text = kwargs["messages"][-1]["content"]
        completion_calls.append(prompt_text)
        if "GENERAL HINTS SYNTHESIS" in prompt_text:
            return DummyResponse("<p>generic synthesis</p>")
        return DummyResponse(f"<p>hint {len(completion_calls)}</p>")

    monkeypatch.setattr(pg_autoexplain_analyzer.litellm, "completion", fake_completion)
    monkeypatch.setattr(pg_autoexplain_analyzer.litellm, "completion_cost", lambda completion_response: 0.0)
    monkeypatch.setattr(pg_autoexplain_analyzer.ContextLoader, "load_all_contexts", lambda *args, **kwargs: None)
    monkeypatch.setattr(pg_autoexplain_analyzer.ContextLoader, "get_query_optimizations", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        pg_autoexplain_analyzer.TextLogParser,
        "parse_log_file",
        lambda self, log_file_path: iter(
            [
                _build_log_entry("2025-11-26 14:42:44 CET", "-- Task First"),
                _build_log_entry("2025-11-26 14:43:44 CET", "-- Task Second"),
                _build_log_entry("2025-11-26 14:44:44 CET", "-- Task Third"),
            ]
        ),
    )
    query_codes = iter(["CODE1", "CODE2", "CODE3"])
    monkeypatch.setattr(pg_autoexplain_analyzer.SQLUtils, "get_query_code", lambda *_: next(query_codes))
    monkeypatch.setattr(
        pg_autoexplain_analyzer.ReportGenerator,
        "generate_report",
        lambda *args, **kwargs: captured_reports.append(args),
    )

    args = pg_autoexplain_analyzer.parse_cli_arguments(
        [str(log_path), "-m", "gpt-4o", "--analyze-all-queries", "-l", "3"]
    )
    analyzer = pg_autoexplain_analyzer.PGAutoExplainAnalyzer(args)
    analyzer.context_loader.query_optimizations_cache = {}
    analyzer.context_loader.server_optimizations = []
    analyzer.context_loader.event_optimizations = []
    analyzer.context_loader.ddl_context = None
    analyzer.context_loader.server_configuration_context = None
    analyzer.context_loader.project_context = None

    analyzer.run()

    assert len(completion_calls) == 4
    assert "GENERAL HINTS SYNTHESIS" in completion_calls[-1]
    assert analyzer.data_processor.all_reports[0]["ai_hints"] == "<p>hint 1</p>"
    assert analyzer.data_processor.all_reports[1]["ai_hints"] == "<p>hint 2</p>"
    assert analyzer.data_processor.all_reports[2]["ai_hints"] == "<p>hint 3</p>"
    assert captured_reports[0][-1] == "<p>generic synthesis</p>"


def test_general_hints_synthesis_can_be_disabled_via_cli(monkeypatch):
    log_path = Path("tests/data/full-text-plan.log")
    completion_calls = []
    captured_reports = []

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
        prompt_text = kwargs["messages"][-1]["content"]
        completion_calls.append(prompt_text)
        return DummyResponse("<p>hint</p>")

    monkeypatch.setattr(pg_autoexplain_analyzer.litellm, "completion", fake_completion)
    monkeypatch.setattr(pg_autoexplain_analyzer.litellm, "completion_cost", lambda completion_response: 0.0)
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
    query_codes = iter(["CODE1", "CODE2"])
    monkeypatch.setattr(pg_autoexplain_analyzer.SQLUtils, "get_query_code", lambda *_: next(query_codes))
    monkeypatch.setattr(
        pg_autoexplain_analyzer.ReportGenerator,
        "generate_report",
        lambda *args, **kwargs: captured_reports.append(args),
    )

    args = pg_autoexplain_analyzer.parse_cli_arguments(
        [str(log_path), "-m", "gpt-4o", "--analyze-all-queries", "--disable-general-hints-synthesis"]
    )
    analyzer = pg_autoexplain_analyzer.PGAutoExplainAnalyzer(args)
    analyzer.context_loader.query_optimizations_cache = {}
    analyzer.context_loader.server_optimizations = []
    analyzer.context_loader.event_optimizations = []
    analyzer.context_loader.ddl_context = None
    analyzer.context_loader.server_configuration_context = None
    analyzer.context_loader.project_context = None

    analyzer.run()

    assert args.disable_general_hints_synthesis is True
    assert len(completion_calls) == 2
    assert all("GENERAL HINTS SYNTHESIS" not in prompt for prompt in completion_calls)
    assert captured_reports[0][-1] is None


def test_general_hints_synthesis_uses_cacheable_segments_with_shared_context(monkeypatch):
    log_path = Path("tests/data/full-text-plan.log")
    captured_ai_calls = []

    monkeypatch.setattr(
        pg_autoexplain_analyzer.ContextLoader,
        "load_all_contexts",
        lambda *args, **kwargs: None,
    )
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
    query_codes = iter(["CODE1", "CODE2"])
    monkeypatch.setattr(pg_autoexplain_analyzer.SQLUtils, "get_query_code", lambda *_: next(query_codes))
    monkeypatch.setattr(pg_autoexplain_analyzer.ReportGenerator, "generate_report", lambda *args, **kwargs: None)

    args = pg_autoexplain_analyzer.parse_cli_arguments([str(log_path), "--analyze-all-queries"])
    analyzer = pg_autoexplain_analyzer.PGAutoExplainAnalyzer(args)
    analyzer.context_loader.query_optimizations_cache = {}
    analyzer.context_loader.server_optimizations = []
    analyzer.context_loader.event_optimizations = []
    analyzer.context_loader.ddl_context = None
    analyzer.context_loader.optimization_base_path = Path("tests/data/CONTEXT")
    analyzer.context_loader.server_configuration_context = "shared config"
    analyzer.context_loader.project_context = "shared project"

    def fake_call_ai_provider(prompt, **kwargs):
        captured_ai_calls.append({"prompt": prompt, **kwargs})
        if "GENERAL HINTS SYNTHESIS" in prompt:
            return "<p>generic synthesis</p>"
        return "<p>query hint</p>"

    monkeypatch.setattr(analyzer.ai_caller, "call_ai_provider", fake_call_ai_provider)

    analyzer.run()

    synthesis_call = captured_ai_calls[-1]
    assert "GENERAL HINTS SYNTHESIS" in synthesis_call["cacheable_prefix"]
    assert "shared config" in synthesis_call["cacheable_prefix"]
    assert "shared project" in synthesis_call["cacheable_prefix"]
    assert "HINTS LIST" in synthesis_call["dynamic_suffix"]
    assert synthesis_call["has_static_context"] is True


def test_target_query_argument_is_normalized_and_incompatible_with_filter():
    log_path = Path("tests/data/full-text-plan.log")

    args = pg_autoexplain_analyzer.parse_cli_arguments([str(log_path), "-tq", "ab12ef"])

    assert args.target_query == "AB12EF"

    with pytest.raises(SystemExit) as exc:
        pg_autoexplain_analyzer.parse_cli_arguments([str(log_path), "-tq", "ABCDEF", "-f", "ABCDEF"])

    assert exc.value.code == 2


def test_target_query_mode_aggregates_matching_occurrences_and_prints_to_stdout(monkeypatch, capsys):
    log_path = Path("tests/data/full-text-plan.log")
    completion_prompts = []
    generated_standard_reports = []
    generated_target_reports = []
    target_sql = "select * from demo where id = 1"
    other_sql = "select * from demo where status = 'ok'"
    target_code = pg_autoexplain_analyzer.SQLUtils.get_short_query_code(target_sql)

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
        completion_prompts.append(kwargs["messages"][-1]["content"])
        return DummyResponse("aggregated target analysis")

    monkeypatch.setattr(pg_autoexplain_analyzer.litellm, "completion", fake_completion)
    monkeypatch.setattr(pg_autoexplain_analyzer.litellm, "completion_cost", lambda completion_response: 0.0)
    monkeypatch.setattr(pg_autoexplain_analyzer.ContextLoader, "load_all_contexts", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        pg_autoexplain_analyzer.ContextLoader,
        "get_query_optimizations",
        lambda *args, **kwargs: [{"date": "2025-11-26", "text": "Added covering index"}],
    )
    monkeypatch.setattr(
        pg_autoexplain_analyzer.TextLogParser,
        "parse_log_file",
        lambda self, log_file_path: iter(
            [
                {
                    **_build_log_entry("2025-11-26 14:42:44 CET", "-- Task First"),
                    "query_text": target_sql,
                    "execution_plan": "Plan A\nSeq Scan on demo",
                },
                {
                    **_build_log_entry("2025-11-26 14:43:44 CET", "-- Task Other"),
                    "query_text": other_sql,
                    "execution_plan": "Plan OTHER",
                },
                {
                    **_build_log_entry("2025-11-27 14:42:44 CET", "-- Task Second"),
                    "query_text": target_sql,
                    "execution_plan": "Plan B\nIndex Scan using demo_idx",
                },
            ]
        ),
    )
    monkeypatch.setattr(
        pg_autoexplain_analyzer.ReportGenerator,
        "generate_report",
        lambda *args, **kwargs: generated_standard_reports.append(args),
    )
    monkeypatch.setattr(
        pg_autoexplain_analyzer.ReportGenerator,
        "generate_target_query_report",
        lambda *args, **kwargs: generated_target_reports.append(args),
    )

    args = pg_autoexplain_analyzer.parse_cli_arguments([str(log_path), "-m", "gpt-4o", "-tq", target_code])
    analyzer = pg_autoexplain_analyzer.PGAutoExplainAnalyzer(args)
    analyzer.context_loader.server_optimizations = [
        {"date": "2025-11-25", "text": "Ignored work_mem outside target range"},
        {"date": "2025-11-27", "text": "Raised work_mem"},
    ]
    analyzer.context_loader.event_optimizations = [
        {"date": "2025-11-24", "text": "Vacuum freeze completed outside target range"},
        {"date": "2025-11-26", "text": "Vacuum analyze completed"},
    ]
    analyzer.context_loader.ddl_context = "CREATE INDEX demo_idx ON demo(id);"
    analyzer.context_loader.server_configuration_context = "shared_buffers = 8GB"
    analyzer.context_loader.project_context = "nightly ETL workload"

    analyzer.run()

    output = capsys.readouterr().out
    assert "Target Query Analysis" in output
    assert f"Short query code: {target_code}" in output
    assert "Occurrences: 2" in output
    assert target_sql in output
    assert "HTML report:" in output
    assert "aggregated target analysis" not in output
    assert generated_standard_reports == []
    assert len(generated_target_reports) == 1
    assert f"_{target_code}.html" in generated_target_reports[0][1]
    assert len(completion_prompts) == 1
    assert "Plan A" in completion_prompts[0]
    assert "Plan B" in completion_prompts[0]
    assert target_sql in completion_prompts[0]
    assert "Raised work_mem" in completion_prompts[0]
    assert "Vacuum analyze completed" in completion_prompts[0]
    assert "Added covering index" in completion_prompts[0]
    assert "Ignored work_mem outside target range" not in completion_prompts[0]
    assert "Vacuum freeze completed outside target range" not in completion_prompts[0]


def test_target_query_payload_keeps_aggregated_ai_hints_on_every_occurrence():
    target_sql = "select * from demo where id = 1"
    target_code = pg_autoexplain_analyzer.SQLUtils.get_query_code(target_sql)
    target_entries = [
        {
            **_build_log_entry("2025-11-26 14:42:44 CET", "-- Task First"),
            "query_text": target_sql,
            "execution_plan": "Plan A",
        },
        {
            **_build_log_entry("2025-11-27 14:42:44 CET", "-- Task Second"),
            "query_text": target_sql,
            "execution_plan": "Plan B",
        },
    ]

    payload = pg_autoexplain_analyzer.PGAutoExplainAnalyzer._build_target_query_report_payload(
        target_code,
        target_entries,
        "aggregated target analysis",
    )

    reports = [
        report
        for reports_for_day in payload["reports_by_day"].values()
        for report in reports_for_day
    ]
    assert len(reports) == 2
    assert {report["ai_hints"] for report in reports} == {"aggregated target analysis"}


def test_target_query_mode_limit_ai_calls_limits_considered_occurrences(monkeypatch, capsys):
    log_path = Path("tests/data/full-text-plan.log")
    completion_prompts = []
    generated_target_reports = []
    target_sql = "select * from demo where id = 1"
    target_code = pg_autoexplain_analyzer.SQLUtils.get_short_query_code(target_sql)

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
        completion_prompts.append(kwargs["messages"][-1]["content"])
        return DummyResponse("limited target analysis")

    monkeypatch.setattr(pg_autoexplain_analyzer.litellm, "completion", fake_completion)
    monkeypatch.setattr(pg_autoexplain_analyzer.litellm, "completion_cost", lambda completion_response: 0.0)
    monkeypatch.setattr(pg_autoexplain_analyzer.ContextLoader, "load_all_contexts", lambda *args, **kwargs: None)
    monkeypatch.setattr(pg_autoexplain_analyzer.ContextLoader, "get_query_optimizations", lambda *args, **kwargs: [])
    monkeypatch.setattr(
        pg_autoexplain_analyzer.TextLogParser,
        "parse_log_file",
        lambda self, log_file_path: iter(
            [
                {
                    **_build_log_entry("2025-11-26 14:42:44 CET", "-- Task First"),
                    "query_text": target_sql,
                    "execution_plan": "Plan A",
                },
                {
                    **_build_log_entry("2025-11-27 14:42:44 CET", "-- Task Second"),
                    "query_text": target_sql,
                    "execution_plan": "Plan B",
                },
                {
                    **_build_log_entry("2025-11-28 14:42:44 CET", "-- Task Third"),
                    "query_text": target_sql,
                    "execution_plan": "Plan C",
                },
            ]
        ),
    )
    monkeypatch.setattr(
        pg_autoexplain_analyzer.ReportGenerator,
        "generate_target_query_report",
        lambda *args, **kwargs: generated_target_reports.append(args),
    )

    args = pg_autoexplain_analyzer.parse_cli_arguments([str(log_path), "-m", "gpt-4o", "-tq", target_code, "-l", "2"])
    analyzer = pg_autoexplain_analyzer.PGAutoExplainAnalyzer(args)
    analyzer.context_loader.server_optimizations = []
    analyzer.context_loader.event_optimizations = []
    analyzer.context_loader.ddl_context = None
    analyzer.context_loader.server_configuration_context = None
    analyzer.context_loader.project_context = None

    analyzer.run()

    output = capsys.readouterr().out
    assert "Occurrences: 2" in output
    assert len(completion_prompts) == 1
    assert "Occurrences: 2" in completion_prompts[0]
    assert "Plan A" in completion_prompts[0]
    assert "Plan B" in completion_prompts[0]
    assert "Plan C" not in completion_prompts[0]
    assert len(generated_target_reports) == 1
    assert len(generated_target_reports[0][6]) == 2


def test_target_query_mode_exits_when_no_query_matches(monkeypatch):
    log_path = Path("tests/data/full-text-plan.log")

    monkeypatch.setattr(pg_autoexplain_analyzer.ContextLoader, "load_all_contexts", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        pg_autoexplain_analyzer.TextLogParser,
        "parse_log_file",
        lambda self, log_file_path: iter(
            [
                {
                    **_build_log_entry("2025-11-26 14:42:44 CET", "-- Task Other"),
                    "query_text": "select * from demo where status = 'ok'",
                }
            ]
        ),
    )

    args = pg_autoexplain_analyzer.parse_cli_arguments([str(log_path), "-tq", "ABCDEF"])
    analyzer = pg_autoexplain_analyzer.PGAutoExplainAnalyzer(args)

    with pytest.raises(SystemExit) as exc:
        analyzer.run()

    assert exc.value.code == 1
