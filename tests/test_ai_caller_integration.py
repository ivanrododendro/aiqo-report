from types import SimpleNamespace
from pathlib import Path

import pytest

from aiqo_pg_ai_report import pg_autoexplain_analyzer


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

    args = pg_autoexplain_analyzer.parse_cli_arguments(
        [str(log_path), "-l", "1", "-f", filter_code, "-m", "gpt-4o"]
    )
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
