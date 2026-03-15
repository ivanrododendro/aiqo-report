import types

import pytest

from aiqo_pg_ai_report.ai_caller import (
    AiCaller,
    DEFAULT_AI_CALL_TIMEOUT,
    DEFAULT_TOKEN_LIMIT,
)
from aiqo_pg_ai_report.provider_strategies import (
    AnthropicProviderStrategy,
    GeminiProviderStrategy,
    GenericProviderStrategy,
    OpenAIProviderStrategy,
    build_provider_strategy,
)


class DummyUsage:
    def __init__(
        self,
        prompt_tokens: int | None,
        completion_tokens: int | None,
        prompt_tokens_details: dict | None = None,
        input_tokens_details: dict | None = None,
        cache_creation_input_tokens: int | None = None,
        cache_read_input_tokens: int | None = None,
    ):
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens
        self.prompt_tokens_details = prompt_tokens_details
        self.input_tokens_details = input_tokens_details
        self.cache_creation_input_tokens = cache_creation_input_tokens
        self.cache_read_input_tokens = cache_read_input_tokens


class DummyUsageDetails:
    def __init__(
        self,
        cached_tokens: int | None = None,
        cache_creation_tokens: int | None = None,
    ):
        self.cached_tokens = cached_tokens
        self.cache_creation_tokens = cache_creation_tokens


class DummyMessage:
    def __init__(self, content: str):
        self.content = content


class DummyChoice:
    def __init__(self, content: str):
        self.message = DummyMessage(content)


class DummyResponse:
    def __init__(
        self,
        prompt_tokens: int | None,
        completion_tokens: int | None,
        content,
        prompt_tokens_details: dict | None = None,
        input_tokens_details: dict | None = None,
        cache_creation_input_tokens: int | None = None,
        cache_read_input_tokens: int | None = None,
    ):
        self.usage = DummyUsage(
            prompt_tokens,
            completion_tokens,
            prompt_tokens_details=prompt_tokens_details,
            input_tokens_details=input_tokens_details,
            cache_creation_input_tokens=cache_creation_input_tokens,
            cache_read_input_tokens=cache_read_input_tokens,
        )
        self.choices = [DummyChoice(content)]


@pytest.fixture(autouse=True)
def reset_litellm(monkeypatch):
    # Prevent real LiteLLM calls and provide predictable defaults
    monkeypatch.setattr("aiqo_pg_ai_report.ai_caller.litellm.get_model_info", lambda model: {"max_input_tokens": 100})
    monkeypatch.setattr("aiqo_pg_ai_report.ai_caller.litellm._turn_on_debug", lambda: None)
    yield


def test_get_model_token_limit_from_litellm(monkeypatch):
    monkeypatch.setattr("aiqo_pg_ai_report.ai_caller.litellm.get_model_info", lambda model: {"max_input_tokens": 321})
    caller = AiCaller(model="gpt-test", ai_call_timeout=10, lang="en", prompts={}, debug=False)
    assert caller.token_limit == 321


def test_get_model_token_limit_fallback(monkeypatch):
    monkeypatch.setattr("aiqo_pg_ai_report.ai_caller.litellm.get_model_info", lambda model: {})
    caller = AiCaller(model="gpt-test", ai_call_timeout=10, lang="en", prompts={}, debug=False)
    assert caller.token_limit == DEFAULT_TOKEN_LIMIT


def test_build_provider_strategy_returns_expected_strategy_for_each_provider():
    assert isinstance(build_provider_strategy(None), GenericProviderStrategy)
    assert isinstance(build_provider_strategy("openai"), OpenAIProviderStrategy)
    assert isinstance(build_provider_strategy("anthropic"), AnthropicProviderStrategy)
    assert isinstance(build_provider_strategy("gemini"), GeminiProviderStrategy)
    assert isinstance(build_provider_strategy("google"), GeminiProviderStrategy)
    assert isinstance(build_provider_strategy("vertex_ai-language-models", model="gemini-2.5-flash"), GeminiProviderStrategy)


def test_call_ai_provider_success(monkeypatch):
    # Arrange mocks
    monkeypatch.setattr("aiqo_pg_ai_report.ai_caller.litellm.token_counter", lambda **kwargs: 10)
    monkeypatch.setattr(
        "aiqo_pg_ai_report.ai_caller.litellm.get_model_info",
        lambda model: {"max_input_tokens": 100, "litellm_provider": "openai", "supports_prompt_caching": True},
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


def test_call_ai_provider_openai_sets_prompt_cache_key(monkeypatch):
    captured_completion: dict = {}

    def fake_completion(**kwargs):
        captured_completion.update(kwargs)
        return DummyResponse(
            prompt_tokens=7,
            completion_tokens=3,
            content=" result ",
            prompt_tokens_details={"cached_tokens": 5},
        )

    def fake_token_counter(**kwargs):
        if "text" in kwargs:
            return 1024
        return 10

    monkeypatch.setattr("aiqo_pg_ai_report.ai_caller.litellm.token_counter", fake_token_counter)
    monkeypatch.setattr(
        "aiqo_pg_ai_report.ai_caller.litellm.get_model_info",
        lambda model: {"max_input_tokens": 100, "litellm_provider": "openai", "supports_prompt_caching": True},
    )
    monkeypatch.setattr("aiqo_pg_ai_report.ai_caller.litellm.completion", fake_completion)
    monkeypatch.setattr("aiqo_pg_ai_report.ai_caller.litellm.completion_cost", lambda completion_response: 0.0)

    caller = AiCaller(model="gpt-test", ai_call_timeout=5, lang="en", prompts={}, debug=False)

    result = caller.call_ai_provider(
        "static prompt\n\ndynamic",
        cacheable_prefix="static prompt",
        dynamic_suffix="\n\ndynamic",
        has_static_context=True,
    )

    assert result == "result"
    assert captured_completion["prompt_cache_key"].startswith("gpt-test:")
    assert caller.total_cached_input_tokens == 5


def test_call_ai_provider_falls_back_to_estimated_usage_when_provider_usage_missing(monkeypatch):
    monkeypatch.setattr(
        "aiqo_pg_ai_report.ai_caller.litellm.get_model_info",
        lambda model: {"max_input_tokens": 100, "litellm_provider": "gemini", "supports_prompt_caching": True},
    )

    def fake_token_counter(**kwargs):
        if "messages" in kwargs:
            return 11
        if kwargs.get("text") == "ok":
            return 4
        return 0

    captured_cost_call: dict = {}

    def fake_completion_cost(**kwargs):
        captured_cost_call.update(kwargs)
        return 0.123

    monkeypatch.setattr("aiqo_pg_ai_report.ai_caller.litellm.token_counter", fake_token_counter)
    monkeypatch.setattr(
        "aiqo_pg_ai_report.ai_caller.litellm.completion",
        lambda **kwargs: DummyResponse(prompt_tokens=0, completion_tokens=0, content="ok"),
    )
    monkeypatch.setattr("aiqo_pg_ai_report.ai_caller.litellm.completion_cost", fake_completion_cost)

    caller = AiCaller(model="gemini-2.5-flash", ai_call_timeout=5, lang="en", prompts={}, debug=False)

    result = caller.call_ai_provider("prompt text")

    assert result == "ok"
    assert caller.total_input_tokens == 11
    assert caller.total_output_tokens == 4
    assert caller.total_cost == 0.123
    assert captured_cost_call["model"] == "gemini/gemini-2.5-flash"
    assert captured_cost_call["completion"] == "ok"


def test_build_messages_generic_chat_model_adds_system_message(monkeypatch):
    monkeypatch.setattr(
        "aiqo_pg_ai_report.ai_caller.litellm.get_model_info",
        lambda model: {"max_input_tokens": 100, "litellm_provider": "custom"},
    )

    caller = AiCaller(model="claude-compatible", ai_call_timeout=5, lang="en", prompts={}, debug=False)

    messages = caller._build_messages(
        prompt="prompt text",
        provider="custom",
        model_info={"litellm_provider": "custom"},
        cacheable_prefix="",
        dynamic_suffix="",
        has_static_context=False,
        cacheable_prefix_token_count=0,
    )

    assert messages == [
        {"role": "system", "content": "You are a PostgreSQL optimization expert."},
        {"role": "user", "content": "prompt text"},
    ]


def test_build_messages_openai_uses_generic_message_shape(monkeypatch):
    monkeypatch.setattr(
        "aiqo_pg_ai_report.ai_caller.litellm.get_model_info",
        lambda model: {"max_input_tokens": 100, "litellm_provider": "openai"},
    )

    caller = AiCaller(model="gpt-4o-mini", ai_call_timeout=5, lang="en", prompts={}, debug=False)

    messages = caller._build_messages(
        prompt="prompt text",
        provider="openai",
        model_info={"litellm_provider": "openai"},
        cacheable_prefix="static prompt",
        dynamic_suffix="\n\ndynamic",
        has_static_context=True,
        cacheable_prefix_token_count=1024,
    )

    assert messages == [
        {"role": "system", "content": "You are a PostgreSQL optimization expert."},
        {"role": "user", "content": "prompt text"},
    ]


def test_get_effective_model_uses_gemini_strategy_normalization(monkeypatch):
    monkeypatch.setattr(
        "aiqo_pg_ai_report.ai_caller.litellm.get_model_info",
        lambda model: {"max_input_tokens": 100, "litellm_provider": "gemini", "supports_prompt_caching": True},
    )

    caller = AiCaller(model="gemini-2.5-flash", ai_call_timeout=5, lang="en", prompts={}, debug=False)

    assert caller._get_effective_model() == "gemini/gemini-2.5-flash"


def test_get_effective_model_normalizes_bare_gemini_when_litellm_reports_vertex_provider(monkeypatch):
    monkeypatch.setattr(
        "aiqo_pg_ai_report.ai_caller.litellm.get_model_info",
        lambda model: {"max_input_tokens": 100, "litellm_provider": "vertex_ai-language-models"},
    )

    caller = AiCaller(model="gemini-2.5-flash", ai_call_timeout=5, lang="en", prompts={}, debug=False)

    assert caller._get_effective_model() == "gemini/gemini-2.5-flash"


def test_build_response_params_openai_uses_prompt_cache_key_and_omits_top_k(monkeypatch):
    monkeypatch.setattr(
        "aiqo_pg_ai_report.ai_caller.litellm.get_model_info",
        lambda model: {"max_input_tokens": 100, "litellm_provider": "openai", "supports_prompt_caching": True},
    )

    caller = AiCaller(model="gpt-4o-mini", ai_call_timeout=7, lang="en", prompts={}, debug=False)

    response_params = caller._build_response_params(
        effective_model="gpt-4o-mini",
        provider="openai",
        model_info={"litellm_provider": "openai", "supports_prompt_caching": True},
        messages=[{"role": "user", "content": "prompt"}],
        cacheable_prefix="static prompt",
        has_static_context=True,
        cacheable_prefix_token_count=1024,
    )

    assert response_params["model"] == "gpt-4o-mini"
    assert response_params["request_timeout"] == 7
    assert response_params["prompt_cache_key"].startswith("gpt-4o-mini:")
    assert "top_k" not in response_params


def test_build_response_params_gemini_sets_top_k_and_omits_prompt_cache_key(monkeypatch):
    monkeypatch.setattr(
        "aiqo_pg_ai_report.ai_caller.litellm.get_model_info",
        lambda model: {"max_input_tokens": 100, "litellm_provider": "gemini", "supports_prompt_caching": True},
    )

    caller = AiCaller(model="gemini-2.5-flash", ai_call_timeout=7, lang="en", prompts={}, debug=False)

    response_params = caller._build_response_params(
        effective_model="gemini/gemini-2.5-flash",
        provider="gemini",
        model_info={"litellm_provider": "gemini", "supports_prompt_caching": True},
        messages=[{"role": "user", "content": "prompt"}],
        cacheable_prefix="static prompt",
        has_static_context=True,
        cacheable_prefix_token_count=1024,
    )

    assert response_params["model"] == "gemini/gemini-2.5-flash"
    assert response_params["request_timeout"] == 7
    assert response_params["top_k"] == 1
    assert "prompt_cache_key" not in response_params


def test_call_ai_provider_openai_does_not_set_prompt_cache_key_when_disabled(monkeypatch):
    captured_completion: dict = {}

    def fake_completion(**kwargs):
        captured_completion.update(kwargs)
        return DummyResponse(prompt_tokens=7, completion_tokens=3, content="result")

    def fake_token_counter(**kwargs):
        if "text" in kwargs:
            return 1024
        return 10

    monkeypatch.setattr("aiqo_pg_ai_report.ai_caller.litellm.token_counter", fake_token_counter)
    monkeypatch.setattr(
        "aiqo_pg_ai_report.ai_caller.litellm.get_model_info",
        lambda model: {"max_input_tokens": 100, "litellm_provider": "openai"},
    )
    monkeypatch.setattr("aiqo_pg_ai_report.ai_caller.litellm.completion", fake_completion)
    monkeypatch.setattr("aiqo_pg_ai_report.ai_caller.litellm.completion_cost", lambda completion_response: 0.0)

    caller = AiCaller(
        model="gpt-test",
        ai_call_timeout=5,
        lang="en",
        prompts={},
        debug=False,
        disable_provider_cache=True,
    )

    result = caller.call_ai_provider(
        "static prompt\n\ndynamic",
        cacheable_prefix="static prompt",
        dynamic_suffix="\n\ndynamic",
        has_static_context=True,
    )

    assert result == "result"
    assert "prompt_cache_key" not in captured_completion


def test_build_response_params_openai_omits_prompt_cache_key_when_model_does_not_support_it(monkeypatch):
    monkeypatch.setattr(
        "aiqo_pg_ai_report.ai_caller.litellm.get_model_info",
        lambda model: {"max_input_tokens": 100, "litellm_provider": "openai", "supports_prompt_caching": False},
    )

    caller = AiCaller(model="gpt-test", ai_call_timeout=7, lang="en", prompts={}, debug=False)

    response_params = caller._build_response_params(
        effective_model="gpt-test",
        provider="openai",
        model_info={"litellm_provider": "openai", "supports_prompt_caching": False},
        messages=[{"role": "user", "content": "prompt"}],
        cacheable_prefix="static prompt",
        has_static_context=True,
        cacheable_prefix_token_count=1024,
    )

    assert "prompt_cache_key" not in response_params


def test_call_ai_provider_openai_reads_cached_tokens_from_input_tokens_details(monkeypatch):
    def fake_completion(**kwargs):
        return DummyResponse(
            prompt_tokens=7,
            completion_tokens=3,
            content="result",
            input_tokens_details={"cached_tokens": 4},
        )

    def fake_token_counter(**kwargs):
        if "text" in kwargs:
            return 1024
        return 10

    monkeypatch.setattr("aiqo_pg_ai_report.ai_caller.litellm.token_counter", fake_token_counter)
    monkeypatch.setattr(
        "aiqo_pg_ai_report.ai_caller.litellm.get_model_info",
        lambda model: {"max_input_tokens": 100, "litellm_provider": "openai", "supports_prompt_caching": True},
    )
    monkeypatch.setattr("aiqo_pg_ai_report.ai_caller.litellm.completion", fake_completion)
    monkeypatch.setattr("aiqo_pg_ai_report.ai_caller.litellm.completion_cost", lambda completion_response: 0.0)

    caller = AiCaller(model="gpt-test", ai_call_timeout=5, lang="en", prompts={}, debug=False)

    result = caller.call_ai_provider("prompt text", cacheable_prefix="prompt text", has_static_context=True)

    assert result == "result"
    assert caller.total_cached_input_tokens == 4


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


def test_call_ai_provider_gemini_marks_cacheable_prefix_and_sets_top_k(monkeypatch):
    captured_completion: dict = {}

    def fake_completion(**kwargs):
        captured_completion.update(kwargs)
        return DummyResponse(prompt_tokens=None, completion_tokens=None, content="ok")

    def fake_token_counter(**kwargs):
        if "text" in kwargs:
            return 1024
        return 5

    monkeypatch.setattr("aiqo_pg_ai_report.ai_caller.litellm.token_counter", fake_token_counter)
    monkeypatch.setattr(
        "aiqo_pg_ai_report.ai_caller.litellm.get_model_info",
        lambda model: {"max_input_tokens": 50, "litellm_provider": "gemini", "supports_prompt_caching": True},
    )
    monkeypatch.setattr("aiqo_pg_ai_report.ai_caller.litellm.completion", fake_completion)
    monkeypatch.setattr("aiqo_pg_ai_report.ai_caller.litellm.completion_cost", lambda completion_response: 0.0)

    caller = AiCaller(model="gemini-1.5", ai_call_timeout=15, lang="en", prompts={}, debug=False)

    result = caller.call_ai_provider(
        "shared prefix\n\ndynamic suffix",
        cacheable_prefix="shared prefix",
        dynamic_suffix="\n\ndynamic suffix",
        has_static_context=True,
    )

    assert result == "ok"
    assert captured_completion["model"] == "gemini/gemini-1.5"
    assert captured_completion["top_k"] == 1
    assert captured_completion["request_timeout"] == 15
    messages = captured_completion["messages"]
    assert messages[0]["role"] == "user"
    assert messages[0]["content"][0]["cache_control"] == {"type": "ephemeral", "ttl": "3600s"}
    assert messages[0]["content"][0]["text"] == "You are a PostgreSQL optimization expert.\n\nshared prefix"
    assert messages[1]["role"] == "user"
    assert messages[1]["content"] == "\n\ndynamic suffix"


def test_call_ai_provider_claude_marks_cacheable_prefix(monkeypatch):
    captured_completion: dict = {}

    def fake_completion(**kwargs):
        captured_completion.update(kwargs)
        return DummyResponse(
            prompt_tokens=9,
            completion_tokens=4,
            content="ok",
            cache_creation_input_tokens=6,
            cache_read_input_tokens=2,
        )

    def fake_token_counter(**kwargs):
        if "text" in kwargs:
            return 1024
        return 5

    monkeypatch.setattr("aiqo_pg_ai_report.ai_caller.litellm.token_counter", fake_token_counter)
    monkeypatch.setattr(
        "aiqo_pg_ai_report.ai_caller.litellm.get_model_info",
        lambda model: {"max_input_tokens": 50, "litellm_provider": "anthropic"},
    )
    monkeypatch.setattr("aiqo_pg_ai_report.ai_caller.litellm.completion", fake_completion)
    monkeypatch.setattr("aiqo_pg_ai_report.ai_caller.litellm.completion_cost", lambda completion_response: 0.0)

    caller = AiCaller(model="claude-3-7-sonnet", ai_call_timeout=15, lang="en", prompts={}, debug=False)

    result = caller.call_ai_provider(
        "shared prefix\n\ndynamic suffix",
        cacheable_prefix="shared prefix",
        dynamic_suffix="\n\ndynamic suffix",
        has_static_context=True,
    )

    assert result == "ok"
    assert caller.total_cached_input_tokens == 2
    assert caller.total_cache_creation_input_tokens == 6
    messages = captured_completion["messages"]
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"
    assert messages[1]["content"][0]["cache_control"] == {"type": "ephemeral"}


def test_accumulate_usage_reads_anthropic_cache_tokens_from_prompt_token_details():
    caller = AiCaller(model="claude-3-7-sonnet", ai_call_timeout=15, lang="en", prompts={}, debug=False)

    response = DummyResponse(
        prompt_tokens=9,
        completion_tokens=4,
        content="ok",
    )
    response.usage.prompt_tokens_details = DummyUsageDetails(
        cached_tokens=8,
        cache_creation_tokens=5,
    )
    response.usage.cache_read_input_tokens = None
    response.usage.cache_creation_input_tokens = None

    caller._accumulate_usage(response)

    assert caller.total_cached_input_tokens == 8
    assert caller.total_cache_creation_input_tokens == 5


def test_accumulate_usage_reads_anthropic_cache_tokens_from_private_usage_attrs():
    caller = AiCaller(model="claude-3-7-sonnet", ai_call_timeout=15, lang="en", prompts={}, debug=False)

    response = DummyResponse(
        prompt_tokens=9,
        completion_tokens=4,
        content="ok",
    )
    response.usage.cache_read_input_tokens = None
    response.usage.cache_creation_input_tokens = None
    response.usage._cache_read_input_tokens = 7
    response.usage._cache_creation_input_tokens = 3

    caller._accumulate_usage(response)

    assert caller.total_cached_input_tokens == 7
    assert caller.total_cache_creation_input_tokens == 3


def test_call_ai_provider_gemini_does_not_mark_cacheable_prefix_when_disabled(monkeypatch):
    captured_completion: dict = {}

    def fake_completion(**kwargs):
        captured_completion.update(kwargs)
        return DummyResponse(prompt_tokens=None, completion_tokens=None, content="ok")

    def fake_token_counter(**kwargs):
        if "text" in kwargs:
            return 1024
        return 5

    monkeypatch.setattr("aiqo_pg_ai_report.ai_caller.litellm.token_counter", fake_token_counter)
    monkeypatch.setattr(
        "aiqo_pg_ai_report.ai_caller.litellm.get_model_info",
        lambda model: {"max_input_tokens": 50, "litellm_provider": "gemini", "supports_prompt_caching": True},
    )
    monkeypatch.setattr("aiqo_pg_ai_report.ai_caller.litellm.completion", fake_completion)
    monkeypatch.setattr("aiqo_pg_ai_report.ai_caller.litellm.completion_cost", lambda completion_response: 0.0)

    caller = AiCaller(
        model="gemini-1.5",
        ai_call_timeout=15,
        lang="en",
        prompts={},
        debug=False,
        disable_provider_cache=True,
    )

    result = caller.call_ai_provider(
        "shared prefix\n\ndynamic suffix",
        cacheable_prefix="shared prefix",
        dynamic_suffix="\n\ndynamic suffix",
        has_static_context=True,
    )

    assert result == "ok"
    messages = captured_completion["messages"]
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"
    assert messages[1]["content"] == "shared prefix\n\ndynamic suffix"


def test_call_ai_provider_gemini_does_not_mark_cacheable_prefix_when_prompt_caching_is_unsupported(monkeypatch):
    captured_completion: dict = {}

    def fake_completion(**kwargs):
        captured_completion.update(kwargs)
        return DummyResponse(prompt_tokens=6, completion_tokens=2, content="ok")

    def fake_token_counter(**kwargs):
        if "text" in kwargs:
            return 1024
        return 5

    monkeypatch.setattr("aiqo_pg_ai_report.ai_caller.litellm.token_counter", fake_token_counter)
    monkeypatch.setattr(
        "aiqo_pg_ai_report.ai_caller.litellm.get_model_info",
        lambda model: {"max_input_tokens": 50, "litellm_provider": "gemini", "supports_prompt_caching": False},
    )
    monkeypatch.setattr("aiqo_pg_ai_report.ai_caller.litellm.completion", fake_completion)
    monkeypatch.setattr("aiqo_pg_ai_report.ai_caller.litellm.completion_cost", lambda completion_response: 0.0)

    caller = AiCaller(model="gemini-1.5", ai_call_timeout=15, lang="en", prompts={}, debug=False)

    result = caller.call_ai_provider(
        "shared prefix\n\ndynamic suffix",
        cacheable_prefix="shared prefix",
        dynamic_suffix="\n\ndynamic suffix",
        has_static_context=True,
    )

    assert result == "ok"
    messages = captured_completion["messages"]
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"
    assert messages[1]["content"] == "shared prefix\n\ndynamic suffix"


def test_call_ai_provider_gemini_does_not_mark_cacheable_prefix_without_static_context(monkeypatch):
    captured_completion: dict = {}

    def fake_completion(**kwargs):
        captured_completion.update(kwargs)
        return DummyResponse(prompt_tokens=6, completion_tokens=2, content="ok")

    def fake_token_counter(**kwargs):
        if "text" in kwargs:
            return 4096
        return 5

    monkeypatch.setattr("aiqo_pg_ai_report.ai_caller.litellm.token_counter", fake_token_counter)
    monkeypatch.setattr(
        "aiqo_pg_ai_report.ai_caller.litellm.get_model_info",
        lambda model: {"max_input_tokens": 50, "litellm_provider": "gemini", "supports_prompt_caching": True},
    )
    monkeypatch.setattr("aiqo_pg_ai_report.ai_caller.litellm.completion", fake_completion)
    monkeypatch.setattr("aiqo_pg_ai_report.ai_caller.litellm.completion_cost", lambda completion_response: 0.0)

    caller = AiCaller(model="gemini-1.5", ai_call_timeout=15, lang="en", prompts={}, debug=False)

    result = caller.call_ai_provider(
        "shared prefix\n\ndynamic suffix",
        cacheable_prefix="shared prefix",
        dynamic_suffix="\n\ndynamic suffix",
        has_static_context=False,
    )

    assert result == "ok"
    messages = captured_completion["messages"]
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"
    assert messages[1]["content"] == "shared prefix\n\ndynamic suffix"


def test_build_response_params_openai_omits_prompt_cache_key_below_threshold(monkeypatch):
    monkeypatch.setattr(
        "aiqo_pg_ai_report.ai_caller.litellm.get_model_info",
        lambda model: {"max_input_tokens": 100, "litellm_provider": "openai", "supports_prompt_caching": True},
    )

    caller = AiCaller(model="gpt-4o-mini", ai_call_timeout=7, lang="en", prompts={}, debug=False)

    response_params = caller._build_response_params(
        effective_model="gpt-4o-mini",
        provider="openai",
        model_info={"litellm_provider": "openai", "supports_prompt_caching": True},
        messages=[{"role": "user", "content": "prompt"}],
        cacheable_prefix="static prompt",
        has_static_context=True,
        cacheable_prefix_token_count=512,
    )

    assert "prompt_cache_key" not in response_params


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
        lambda model: {"max_input_tokens": 100, "litellm_provider": "gemini", "supports_prompt_caching": True},
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
