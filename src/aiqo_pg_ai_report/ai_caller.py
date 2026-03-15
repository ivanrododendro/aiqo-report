import logging

import litellm
from aiqo_pg_ai_report.provider_strategies import ProviderStrategyContext, build_provider_strategy

logger = logging.getLogger(__name__)

DEFAULT_TOKEN_LIMIT = 8192
DEFAULT_AI_CALL_TIMEOUT = 90


class AiCaller:
    def __init__(self, model, ai_call_timeout, lang, prompts, debug, disable_provider_cache=False):
        self.model = model
        self.ai_call_timeout = ai_call_timeout
        self.lang = lang
        self.prompts = prompts
        self.disable_provider_cache = disable_provider_cache
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.total_cached_input_tokens = 0
        self.total_cache_creation_input_tokens = 0
        self.total_cost = 0.0
        self.call_count = 0
        self.token_limit = self._get_model_token_limit()
        self.debug = debug
        if debug:
            litellm._turn_on_debug()
            logger.info("LiteLLM debug mode enabled.")

    def _get_model_token_limit(self):
        model_info = litellm.get_model_info(self.model)
        if model_info and "max_input_tokens" in model_info and model_info["max_input_tokens"] is not None:
            logger.info(f"Using input token limit for model {self.model}: {model_info['max_input_tokens']}")
            return model_info["max_input_tokens"]
        else:
            logger.warning(
                f"Could not determine input token limit for model {self.model} from litellm. Falling back to default: {DEFAULT_TOKEN_LIMIT}"
            )
            return DEFAULT_TOKEN_LIMIT

    @staticmethod
    def _get_usage_value(usage, key, default=0):
        if usage is None:
            return default
        if isinstance(usage, dict):
            value = usage.get(key, default)
        else:
            value = getattr(usage, key, default)
        return default if value is None else value

    @staticmethod
    def _get_max_usage_value(sources, key: str) -> int:
        values: list[int] = []
        for source in sources:
            value = AiCaller._get_usage_value(source, key, None)
            if isinstance(value, int):
                values.append(value)
        return max(values, default=0)

    @staticmethod
    def _resolve_cached_usage(usage, prompt_tokens_details, input_tokens_details) -> tuple[int, int]:
        cache_read_tokens = AiCaller._get_max_usage_value(
            [prompt_tokens_details, input_tokens_details, usage],
            "cached_tokens",
        )
        if cache_read_tokens == 0:
            cache_read_tokens = AiCaller._get_max_usage_value(
                [usage, usage],
                "cache_read_input_tokens",
            )
        if cache_read_tokens == 0:
            cache_read_tokens = AiCaller._get_max_usage_value(
                [usage],
                "_cache_read_input_tokens",
            )

        cache_creation_tokens = AiCaller._get_max_usage_value(
            [prompt_tokens_details, usage],
            "cache_creation_tokens",
        )
        if cache_creation_tokens == 0:
            cache_creation_tokens = AiCaller._get_max_usage_value(
                [usage],
                "cache_creation_input_tokens",
            )
        if cache_creation_tokens == 0:
            cache_creation_tokens = AiCaller._get_max_usage_value(
                [usage],
                "_cache_creation_input_tokens",
            )

        return cache_read_tokens, cache_creation_tokens

    @staticmethod
    def _get_provider_name(model_info) -> str | None:
        if not model_info:
            return None
        return model_info.get("litellm_provider")

    def _build_provider_context(
        self,
        provider: str | None,
        model_info,
        prompt: str = "",
        cacheable_prefix: str = "",
        dynamic_suffix: str = "",
        has_static_context: bool = False,
        cacheable_prefix_token_count: int = 0,
    ):
        return ProviderStrategyContext(
            model=self.model,
            provider=provider,
            model_info=model_info,
            prompt=prompt,
            cacheable_prefix=cacheable_prefix,
            dynamic_suffix=dynamic_suffix,
            has_static_context=has_static_context,
            cacheable_prefix_token_count=cacheable_prefix_token_count,
            disable_provider_cache=self.disable_provider_cache,
            ai_call_timeout=self.ai_call_timeout,
        )

    def _get_effective_model(self) -> str:
        model_info = litellm.get_model_info(self.model)
        provider = self._get_provider_name(model_info)
        provider_context = self._build_provider_context(
            provider=provider,
            model_info=model_info,
        )
        strategy = build_provider_strategy(provider, model=self.model)
        effective_model = strategy.get_effective_model(provider_context)
        if effective_model != self.model and provider == "gemini":
            logger.info(f"Using Google AI Studio provider for model: {effective_model}")
        return effective_model

    def _build_messages(
        self,
        prompt: str,
        provider: str | None,
        model_info,
        cacheable_prefix: str,
        dynamic_suffix: str,
        has_static_context: bool,
        cacheable_prefix_token_count: int,
    ):
        context = self._build_provider_context(
            provider=provider,
            model_info=model_info,
            prompt=prompt,
            cacheable_prefix=cacheable_prefix,
            dynamic_suffix=dynamic_suffix,
            has_static_context=has_static_context,
            cacheable_prefix_token_count=cacheable_prefix_token_count,
        )
        strategy = build_provider_strategy(provider, model=self.model)
        return strategy.build_messages(context)

    def _build_response_params(
        self,
        effective_model: str,
        provider: str | None,
        model_info,
        messages,
        cacheable_prefix: str,
        has_static_context: bool,
        cacheable_prefix_token_count: int,
    ):
        provider_context = self._build_provider_context(
            provider=provider,
            model_info=model_info,
            cacheable_prefix=cacheable_prefix,
            has_static_context=has_static_context,
            cacheable_prefix_token_count=cacheable_prefix_token_count,
        )
        strategy = build_provider_strategy(provider, model=self.model)
        return strategy.build_response_params(
            context=provider_context,
            effective_model=effective_model,
            messages=messages,
        )

    def _estimate_cacheable_prefix_tokens(self, effective_model: str, cacheable_prefix: str) -> int:
        if not cacheable_prefix:
            return 0

        try:
            return litellm.token_counter(model=effective_model, text=cacheable_prefix)
        except Exception as e:
            logger.warning(
                f"Could not estimate cacheable prefix token count for model {effective_model}: {e}. Provider cache disabled for this call."
            )
            return 0

    def _perform_ai_call(
        self,
        prompt,
        cacheable_prefix: str = "",
        dynamic_suffix: str = "",
        has_static_context: bool = False,
    ):
        initial_model_info = litellm.get_model_info(self.model)
        initial_provider = self._get_provider_name(initial_model_info)
        provider_context = self._build_provider_context(
            provider=initial_provider,
            model_info=initial_model_info,
            prompt=prompt,
            cacheable_prefix=cacheable_prefix,
            dynamic_suffix=dynamic_suffix,
            has_static_context=has_static_context,
        )
        strategy = build_provider_strategy(initial_provider, model=self.model)
        effective_model = strategy.get_effective_model(provider_context)
        if effective_model != self.model and initial_provider == "gemini":
            logger.info(f"Using Google AI Studio provider for model: {effective_model}")
        model_info = litellm.get_model_info(effective_model)
        provider = self._get_provider_name(model_info)
        cacheable_prefix_token_count = self._estimate_cacheable_prefix_tokens(effective_model, cacheable_prefix)
        messages = self._build_messages(
            prompt=prompt,
            provider=provider,
            model_info=model_info,
            cacheable_prefix=cacheable_prefix,
            dynamic_suffix=dynamic_suffix,
            has_static_context=has_static_context,
            cacheable_prefix_token_count=cacheable_prefix_token_count,
        )

        try:
            # Estimate tokens using litellm.token_counter with the constructed messages
            estimated_tokens = litellm.token_counter(model=effective_model, messages=messages)
        except Exception as e:
            logger.warning(
                f"Could not estimate token count for model {effective_model} using litellm.token_counter: {e}. Skipping AI analysis."
            )
            return f"Could not estimate token count for model {effective_model}. AI analysis skipped."

        if estimated_tokens > self.token_limit:
            # Reuse the same message to avoid duplication
            message = (
                f"Token count ({estimated_tokens}) exceeds the model limit ({self.token_limit}). AI analysis skipped."
            )
            logger.warning(message)
            ai_hints = message
            return ai_hints

        try:
            response_params = self._build_response_params(
                effective_model=effective_model,
                provider=provider,
                model_info=model_info,
                messages=messages,
                cacheable_prefix=cacheable_prefix,
                has_static_context=has_static_context,
                cacheable_prefix_token_count=cacheable_prefix_token_count,
            )
            response = litellm.completion(**response_params)

            text_content = self._extract_text_from_response(
                response,
                effective_model=effective_model,
                messages=messages,
            )
            if text_content:
                return text_content.strip()
            logger.warning(f"No analysis content found in LiteLLM response for model {self.model}.")
            return f"No analysis content found in LiteLLM response for model {self.model}."
        except litellm.exceptions.Timeout as e:
            logger.error(f"Timeout while communicating with LiteLLM API for model {self.model}: {e}")
            return None
        except Exception as e:
            logger.error(f"Error communicating with LiteLLM API for model {self.model}: {e}")
            # Log more details if available, e.g., response from LiteLLM
            if hasattr(e, "response"):
                logger.error(f"LiteLLM Response content: {e.response.text}")
            return None

    def _accumulate_usage(
        self,
        response,
        effective_model: str | None = None,
        messages=None,
        completion_text: str = "",
        estimated_prompt_tokens: int | None = None,
    ):
        """Aggregate token usage and cost from a LiteLLM response."""
        usage = getattr(response, "usage", None)
        prompt_tokens = self._get_usage_value(usage, "prompt_tokens", None)
        completion_tokens = self._get_usage_value(usage, "completion_tokens", None)
        has_provider_usage = bool((prompt_tokens or 0) > 0 or (completion_tokens or 0) > 0)

        if not has_provider_usage and effective_model is not None:
            prompt_tokens = estimated_prompt_tokens
            if completion_text:
                try:
                    completion_tokens = litellm.token_counter(model=effective_model, text=completion_text)
                except Exception as e:
                    logger.warning(f"Could not estimate completion token count for model {effective_model}: {e}")
                    completion_tokens = 0

        if prompt_tokens is not None:
            self.total_input_tokens += prompt_tokens
        if completion_tokens is not None:
            self.total_output_tokens += completion_tokens

        prompt_tokens_details = self._get_usage_value(usage, "prompt_tokens_details", None)
        input_tokens_details = self._get_usage_value(usage, "input_tokens_details", None)
        cache_read_tokens, cache_creation_tokens = self._resolve_cached_usage(
            usage,
            prompt_tokens_details,
            input_tokens_details,
        )
        self.total_cached_input_tokens += cache_read_tokens
        self.total_cache_creation_input_tokens += cache_creation_tokens

        try:
            if has_provider_usage:
                cost = litellm.completion_cost(completion_response=response)
            else:
                cost = litellm.completion_cost(
                    model=effective_model,
                    messages=messages or [],
                    completion=completion_text,
                )
            if cost is not None:
                self.total_cost += cost
        except Exception as e:
            logger.warning(f"Could not calculate cost for the API call: {e}")

    def _extract_text_from_response(self, response, effective_model: str | None = None, messages=None) -> str:
        if isinstance(response, list):
            return self._extract_text_from_stream(response)

        text_content = self._extract_text_from_choice_message(response)
        estimated_prompt_tokens = None
        if effective_model is not None and messages is not None:
            try:
                estimated_prompt_tokens = litellm.token_counter(model=effective_model, messages=messages)
            except Exception:
                estimated_prompt_tokens = None

        self._accumulate_usage(
            response,
            effective_model=effective_model,
            messages=messages,
            completion_text=text_content,
            estimated_prompt_tokens=estimated_prompt_tokens,
        )
        return text_content

    def _extract_text_from_stream(self, response_chunks) -> str:
        parts: list[str] = []

        for chunk in response_chunks:
            self._accumulate_usage(chunk)

            if not getattr(chunk, "choices", None):
                continue

            choice = chunk.choices[0]
            delta = getattr(choice, "delta", None)
            message = getattr(choice, "message", None)

            if delta is not None:
                delta_content = getattr(delta, "content", None)
                if delta_content is not None:
                    parts.append(self._extract_text_from_content(delta_content))
                    continue

                delta_text = getattr(delta, "text", None)
                if delta_text is not None:
                    parts.append(str(delta_text))
                    continue

            if message is not None:
                message_content = getattr(message, "content", None)
                if message_content is not None:
                    parts.append(self._extract_text_from_content(message_content))

        return "".join(parts)

    def _extract_text_from_choice_message(self, response) -> str:
        if not getattr(response, "choices", None):
            return ""

        choice = response.choices[0]
        message = getattr(choice, "message", None)
        if message is None:
            return ""

        content = getattr(message, "content", None)
        if content is None:
            return ""

        return self._extract_text_from_content(content)

    @staticmethod
    def _extract_text_from_content(content) -> str:
        """Normalize LiteLLM/OpenAI content objects into a single text string."""
        if content is None:
            return ""

        if isinstance(content, str):
            return content

        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, dict):
                    text = item.get("text")
                    if text is not None:
                        parts.append(str(text))
                elif hasattr(item, "text"):
                    text = getattr(item, "text", None)
                    if text is not None:
                        parts.append(str(text))
                else:
                    parts.append(str(item))
            return "".join(parts)

        if hasattr(content, "text"):
            text_value = getattr(content, "text", None)
            return str(text_value) if text_value is not None else ""

        return str(content)

    def call_ai_provider(
        self,
        prompt,
        cacheable_prefix: str = "",
        dynamic_suffix: str = "",
        has_static_context: bool = False,
    ):
        logger.info("Calling AI Model for plan analysis...")
        self.call_count += 1  # Increment call count when AI call is initiated
        return self._perform_ai_call(
            prompt,
            cacheable_prefix=cacheable_prefix,
            dynamic_suffix=dynamic_suffix,
            has_static_context=has_static_context,
        )

    def show_stats(self):
        """Logs the final statistics of AI API usage."""
        if self.call_count > 0:
            logger.info("--- AI Usage Statistics ---")
            logger.info(f"Total AI calls made: {self.call_count}")
            logger.info(f"Total input tokens processed: {self.total_input_tokens}")
            logger.info(f"Total output tokens processed: {self.total_output_tokens}")
            logger.info(f"Total cached input tokens read: {self.total_cached_input_tokens}")
            logger.info(f"Total cached input tokens written: {self.total_cache_creation_input_tokens}")
            logger.info(f"Estimated total cost: ${self.total_cost:.4f}")
            logger.info("---------------------------")
        else:
            logger.info("No AI calls were made during this run.")
