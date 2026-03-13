from __future__ import annotations

import hashlib
from dataclasses import dataclass

GEMINI_CONTEXT_CACHE_TTL = "3600s"
POSTGRESQL_OPTIMIZATION_SYSTEM_PROMPT = "You are a PostgreSQL optimization expert."


@dataclass(frozen=True)
class ProviderStrategyContext:
    model: str
    provider: str | None
    model_info: dict | None
    prompt: str
    cacheable_prefix: str
    dynamic_suffix: str
    disable_provider_cache: bool
    ai_call_timeout: int

    @property
    def is_chat_model(self) -> bool:
        return any(name in self.model for name in ("gpt", "o1", "gemini", "claude"))

    @property
    def system_prompt(self) -> str | None:
        if self.is_chat_model:
            return POSTGRESQL_OPTIMIZATION_SYSTEM_PROMPT
        return None


class GenericProviderStrategy:
    def get_effective_model(self, context: ProviderStrategyContext) -> str:
        return context.model

    def build_messages(self, context: ProviderStrategyContext):
        messages = [{"role": "user", "content": context.prompt}]
        if context.system_prompt:
            messages.insert(0, {"role": "system", "content": context.system_prompt})
        return messages

    def build_response_params(self, context: ProviderStrategyContext, effective_model: str, messages):
        response_params = {
            "model": effective_model,
            "messages": messages,
            "request_timeout": context.ai_call_timeout,
            "temperature": 1.0,
            "seed": 42,
            "drop_params": True,
        }
        response_params["top_k"] = 1
        return response_params


class OpenAIProviderStrategy(GenericProviderStrategy):
    @staticmethod
    def _supports_prompt_caching(model_info: dict | None) -> bool:
        if not model_info:
            return False
        return bool(model_info.get("supports_prompt_caching"))

    @staticmethod
    def _build_prompt_cache_key(model: str, cacheable_prefix: str) -> str:
        digest = hashlib.sha256(cacheable_prefix.encode("utf-8")).hexdigest()
        return f"{model}:{digest}"

    def build_response_params(self, context: ProviderStrategyContext, effective_model: str, messages):
        response_params = {
            "model": effective_model,
            "messages": messages,
            "request_timeout": context.ai_call_timeout,
            "temperature": 1.0,
            "seed": 42,
            "drop_params": True,
        }
        if (
            not context.disable_provider_cache
            and context.cacheable_prefix
            and self._supports_prompt_caching(context.model_info)
        ):
            response_params["prompt_cache_key"] = self._build_prompt_cache_key(
                effective_model, context.cacheable_prefix
            )
        return response_params


class AnthropicProviderStrategy(GenericProviderStrategy):
    def build_messages(self, context: ProviderStrategyContext):
        if not self._should_mark_cacheable_prefix(context):
            return super().build_messages(context)

        messages = []
        if context.system_prompt:
            messages.append({"role": "system", "content": context.system_prompt})

        user_content = [
            {
                "type": "text",
                "text": context.cacheable_prefix,
                "cache_control": {"type": "ephemeral"},
            }
        ]
        if context.dynamic_suffix:
            user_content.append({"type": "text", "text": context.dynamic_suffix})

        messages.append({"role": "user", "content": user_content})
        return messages

    @staticmethod
    def _should_mark_cacheable_prefix(context: ProviderStrategyContext) -> bool:
        return not context.disable_provider_cache and bool(context.cacheable_prefix)


class GeminiProviderStrategy(GenericProviderStrategy):
    def get_effective_model(self, context: ProviderStrategyContext) -> str:
        if context.model.startswith("gemini-"):
            return "gemini/" + context.model
        return context.model

    def build_messages(self, context: ProviderStrategyContext):
        if not self._should_mark_cacheable_prefix(context):
            return super().build_messages(context)

        prefix_text = context.cacheable_prefix
        if context.system_prompt:
            prefix_text = f"{context.system_prompt}\n\n{prefix_text}"

        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": prefix_text,
                        "cache_control": {"type": "ephemeral", "ttl": GEMINI_CONTEXT_CACHE_TTL},
                    }
                ],
            }
        ]
        if context.dynamic_suffix:
            messages.append({"role": "user", "content": context.dynamic_suffix})
        return messages

    @staticmethod
    def _supports_prompt_caching(model_info: dict | None) -> bool:
        if not model_info:
            return False
        return bool(model_info.get("supports_prompt_caching"))

    def _should_mark_cacheable_prefix(self, context: ProviderStrategyContext) -> bool:
        return (
            not context.disable_provider_cache
            and bool(context.cacheable_prefix)
            and self._supports_prompt_caching(context.model_info)
        )


def build_provider_strategy(provider: str | None, model: str | None = None):
    if model and model.startswith("gemini-"):
        return GeminiProviderStrategy()

    normalized_provider = provider
    if normalized_provider == "google":
        normalized_provider = "gemini"

    if normalized_provider == "openai":
        return OpenAIProviderStrategy()
    if normalized_provider == "anthropic":
        return AnthropicProviderStrategy()
    if normalized_provider == "gemini":
        return GeminiProviderStrategy()
    return GenericProviderStrategy()
