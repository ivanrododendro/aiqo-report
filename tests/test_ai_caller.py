import types

import pytest

from aiqo_pg_ai_report.ai_caller import (
    AiCaller,
    DEFAULT_AI_CALL_TIMEOUT,
    DEFAULT_TOKEN_LIMIT,
)


class DummyUsage:
    def __init__(self, prompt_tokens: int | None, completion_tokens: int | None):
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens


class DummyMessage:
    def __init__(self, content: str):
        self.content = content


class DummyChoice:
    def __init__(self, content: str):
        self.message = DummyMessage(content)


class DummyResponse:
    def __init__(self, prompt_tokens: int | None, completion_tokens: int | None, content: str):
        self.usage = DummyUsage(prompt_tokens, completion_tokens)
        self.choices = [DummyChoice(content)]


@pytest.fixture(autouse=True)
def reset_litellm(monkeypatch):
    # Prevent real LiteLLM calls and provide predictable defaults
    monkeypatch.setattr("aiqo_pg_ai_report.ai_caller.litellm.get_model_info", lambda model: {"max_input_tokens": 100})
    monkeypatch.setattr("aiqo_pg_ai_report.ai_caller.litellm._turn_on_debug", lambda: None)
    yield


def test_get_model_token_limit_from_litellm(monkeypatch):
    monkeypatch.setattr(
        "aiqo_pg_ai_report.ai_caller.litellm.get_model_info", lambda model: {"max_input_tokens": 321}
    )
    caller = AiCaller(model="gpt-test", ai_call_timeout=10, lang="en", prompts={}, debug=False)
    assert caller.token_limit == 321


def test_get_model_token_limit_fallback(monkeypatch):
    monkeypatch.setattr("aiqo_pg_ai_report.ai_caller.litellm.get_model_info", lambda model: {})
    caller = AiCaller(model="gpt-test", ai_call_timeout=10, lang="en", prompts={}, debug=False)
    assert caller.token_limit == DEFAULT_TOKEN_LIMIT


def test_call_ai_provider_success(monkeypatch):
    # Arrange mocks
    monkeypatch.setattr("aiqo_pg_ai_report.ai_caller.litellm.token_counter", lambda **kwargs: 10)
    monkeypatch.setattr(
        "aiqo_pg_ai_report.ai_caller.litellm.get_model_info",
        lambda model: {"max_input_tokens": 100, "litellm_provider": "openai"},
    )
    completion_calls: list[dict] = []

    def fake_completion(**kwargs):
        completion_calls.append(kwargs)
        return DummyResponse(prompt_tokens=7, completion_tokens=3, content=" result ")

    monkeypatch.setattr("aiqo_pg_ai_report.ai_caller.litellm.completion", fake_completion)
    monkeypatch.setattr("aiqo_pg_ai_report.ai_caller.litellm.completion_cost", lambda completion_response: 0.5)

    caller = AiCaller(model="gpt-test", ai_call_timeout=5, lang="en", prompts={}, debug=False)

    # Act
    result = caller.call_ai_provider("prompt text")

    # Assert
    assert result == "result"
    assert caller.call_count == 1
    assert caller.total_input_tokens == 7
    assert caller.total_output_tokens == 3
    assert caller.total_cost == 0.5
    assert completion_calls, "completion should be invoked"
    assert completion_calls[0]["model"] == "gpt-test"
    assert completion_calls[0]["request_timeout"] == 5
    assert "top_k" not in completion_calls[0]


def test_call_ai_provider_over_limit(monkeypatch):
    monkeypatch.setattr("aiqo_pg_ai_report.ai_caller.litellm.token_counter", lambda **kwargs: 500)
    caller = AiCaller(model="gpt-test", ai_call_timeout=5, lang="en", prompts={}, debug=False)
    caller.token_limit = 100

    result = caller.call_ai_provider("prompt text")

    assert "exceeds the model limit" in result
    assert caller.total_input_tokens == 0
    assert caller.total_output_tokens == 0
    assert caller.call_count == 1


def test_call_ai_provider_token_counter_failure(monkeypatch):
    def raising_counter(**kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr("aiqo_pg_ai_report.ai_caller.litellm.token_counter", raising_counter)
    caller = AiCaller(model="gpt-test", ai_call_timeout=5, lang="en", prompts={}, debug=False)

    result = caller.call_ai_provider("prompt text")

    assert "AI analysis skipped" in result
    assert caller.call_count == 1


def test_call_ai_provider_timeout(monkeypatch):
    monkeypatch.setattr("aiqo_pg_ai_report.ai_caller.litellm.token_counter", lambda **kwargs: 10)
    monkeypatch.setattr(
        "aiqo_pg_ai_report.ai_caller.litellm.get_model_info",
        lambda model: {"max_input_tokens": 100, "litellm_provider": "openai"},
    )

    class DummyTimeout(Exception):
        pass

    # Replace the Timeout exception class used by ai_caller to avoid importing real litellm exceptions
    monkeypatch.setattr(
        "aiqo_pg_ai_report.ai_caller.litellm.exceptions",
        types.SimpleNamespace(Timeout=DummyTimeout),
    )

    def raise_timeout(**kwargs):
        raise DummyTimeout("timeout")

    monkeypatch.setattr("aiqo_pg_ai_report.ai_caller.litellm.completion", raise_timeout)

    caller = AiCaller(model="gpt-test", ai_call_timeout=DEFAULT_AI_CALL_TIMEOUT, lang="en", prompts={}, debug=False)

    result = caller.call_ai_provider("prompt text")

    assert result is None
    assert caller.call_count == 1


def test_call_ai_provider_gemini_prefers_google_and_sets_top_k(monkeypatch):
    captured_completion: dict = {}

    def fake_completion(**kwargs):
        captured_completion.update(kwargs)
        return DummyResponse(prompt_tokens=None, completion_tokens=None, content="ok")

    monkeypatch.setattr("aiqo_pg_ai_report.ai_caller.litellm.token_counter", lambda **kwargs: 5)
    monkeypatch.setattr(
        "aiqo_pg_ai_report.ai_caller.litellm.get_model_info",
        lambda model: {"max_input_tokens": 50, "litellm_provider": "google"},
    )
    monkeypatch.setattr("aiqo_pg_ai_report.ai_caller.litellm.completion", fake_completion)
    monkeypatch.setattr("aiqo_pg_ai_report.ai_caller.litellm.completion_cost", lambda completion_response: 0.0)

    caller = AiCaller(model="gemini-1.5", ai_call_timeout=15, lang="en", prompts={}, debug=False)

    result = caller.call_ai_provider("prompt text")

    assert result == "ok"
    assert captured_completion["model"] == "gemini/gemini-1.5"
    assert captured_completion["top_k"] == 1
    assert captured_completion["request_timeout"] == 15
    messages = captured_completion["messages"]
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"


def test_call_ai_provider_handles_list_content(monkeypatch):
    monkeypatch.setattr("aiqo_pg_ai_report.ai_caller.litellm.token_counter", lambda **kwargs: 8)
    monkeypatch.setattr(
        "aiqo_pg_ai_report.ai_caller.litellm.get_model_info",
        lambda model: {"max_input_tokens": 100, "litellm_provider": "openai"},
    )
    monkeypatch.setattr("aiqo_pg_ai_report.ai_caller.litellm.completion_cost", lambda completion_response: 0.0)

    combined_content = [{"text": "first part "}, {"text": "second"}]
    response = DummyResponse(prompt_tokens=2, completion_tokens=6, content=combined_content)
    monkeypatch.setattr("aiqo_pg_ai_report.ai_caller.litellm.completion", lambda **kwargs: response)

    caller = AiCaller(model="gpt-test", ai_call_timeout=5, lang="en", prompts={}, debug=False)

    result = caller.call_ai_provider("prompt text")

    assert result == "first part second"
    assert caller.total_input_tokens == 2
    assert caller.total_output_tokens == 6


def test_call_ai_provider_streaming_objects(monkeypatch):
    monkeypatch.setattr("aiqo_pg_ai_report.ai_caller.litellm.token_counter", lambda **kwargs: 8)
    monkeypatch.setattr(
        "aiqo_pg_ai_report.ai_caller.litellm.get_model_info",
        lambda model: {"max_input_tokens": 100, "litellm_provider": "openai"},
    )
    monkeypatch.setattr("aiqo_pg_ai_report.ai_caller.litellm.completion_cost", lambda completion_response: 0.0)

    class ChunkChoice:
        def __init__(self, content):
            self.delta = types.SimpleNamespace(content=content)
            self.message = None

    class Chunk:
        def __init__(self, content, usage=None):
            self.choices = [ChunkChoice(content)]
            self.usage = usage

    def fake_completion(**kwargs):
        return [
            Chunk(content=[types.SimpleNamespace(text="alpha "), types.SimpleNamespace(text="beta")]),
            Chunk(content=[types.SimpleNamespace(text=" gamma")], usage=DummyUsage(4, 3)),
        ]

    monkeypatch.setattr("aiqo_pg_ai_report.ai_caller.litellm.completion", fake_completion)

    caller = AiCaller(model="gpt-test", ai_call_timeout=5, lang="en", prompts={}, debug=False)

    result = caller.call_ai_provider("prompt text")

    assert result == "alpha beta gamma"
    assert caller.total_input_tokens == 4
    assert caller.total_output_tokens == 3


def test_call_ai_provider_streaming_delta_text(monkeypatch):
    monkeypatch.setattr("aiqo_pg_ai_report.ai_caller.litellm.token_counter", lambda **kwargs: 8)
    monkeypatch.setattr(
        "aiqo_pg_ai_report.ai_caller.litellm.get_model_info",
        lambda model: {"max_input_tokens": 100, "litellm_provider": "google"},
    )
    monkeypatch.setattr("aiqo_pg_ai_report.ai_caller.litellm.completion_cost", lambda completion_response: 0.0)

    class ChunkChoice:
        def __init__(self, text):
            self.delta = types.SimpleNamespace(text=text)
            self.message = None

    class Chunk:
        def __init__(self, text, usage=None):
            self.choices = [ChunkChoice(text)]
            self.usage = usage

    def fake_completion(**kwargs):
        return [
            Chunk(text="prima "),
            Chunk(text="parte", usage=DummyUsage(2, 5)),
        ]

    monkeypatch.setattr("aiqo_pg_ai_report.ai_caller.litellm.completion", fake_completion)

    caller = AiCaller(model="gemini-3-flash-preview", ai_call_timeout=5, lang="en", prompts={}, debug=False)

    result = caller.call_ai_provider("prompt text")

    assert result == "prima parte"
    assert caller.total_input_tokens == 2
    assert caller.total_output_tokens == 5
