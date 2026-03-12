import hashlib
import logging

import litellm

logger = logging.getLogger(__name__)

DEFAULT_TOKEN_LIMIT = 8192
DEFAULT_AI_CALL_TIMEOUT = 90
GEMINI_CONTEXT_CACHE_TTL = "3600s"
POSTGRESQL_OPTIMIZATION_SYSTEM_PROMPT = "You are a PostgreSQL optimization expert."


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
    def _build_prompt_cache_key(model: str, cacheable_prefix: str) -> str:
        digest = hashlib.sha256(cacheable_prefix.encode("utf-8")).hexdigest()
        return f"{model}:{digest}"

    @staticmethod
    def _is_chat_model(model: str) -> bool:
        return "gpt" in model or "o1" in model or "gemini" in model or "claude" in model

    def _get_effective_model(self) -> str:
        if self.model.startswith("gemini-"):
            effective_model = "gemini/" + self.model
            logger.info(f"Using Google AI Studio provider for model: {effective_model}")
            return effective_model
        return self.model

    @staticmethod
    def _get_provider_name(model_info) -> str | None:
        if not model_info:
            return None
        return model_info.get("litellm_provider")

    @staticmethod
    def _supports_prompt_caching(model_info) -> bool:
        if not model_info:
            return False
        return bool(model_info.get("supports_prompt_caching"))

    def _should_mark_cacheable_prefix(
        self,
        provider: str | None,
        model_info,
        cacheable_prefix: str,
    ) -> bool:
        if self.disable_provider_cache or not cacheable_prefix:
            return False

        if provider == "anthropic":
            return True

        if provider == "gemini" and self._supports_prompt_caching(model_info):
            return True

        return False

    def _build_provider_cache_messages(
        self,
        provider: str | None,
        model_info,
        cacheable_prefix: str,
        dynamic_suffix: str,
        system_prompt: str | None = None,
    ):
        if not self._should_mark_cacheable_prefix(
            provider=provider,
            model_info=model_info,
            cacheable_prefix=cacheable_prefix,
        ):
            return None

        cache_control = {"type": "ephemeral"}
        if provider == "gemini":
            cache_control["ttl"] = GEMINI_CONTEXT_CACHE_TTL

        prefix_text = cacheable_prefix
        if provider == "gemini" and system_prompt:
            prefix_text = f"{system_prompt}\n\n{prefix_text}"

        cached_message = {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": prefix_text,
                    "cache_control": cache_control,
                }
            ],
        }

        if provider == "gemini":
            messages = [cached_message]
            if dynamic_suffix:
                messages.append({"role": "user", "content": dynamic_suffix})
            return messages

        user_content = cached_message["content"]
        if dynamic_suffix:
            user_content.append({"type": "text", "text": dynamic_suffix})

        return [cached_message]

    def _build_messages(
        self,
        prompt: str,
        provider: str | None,
        model_info,
        cacheable_prefix: str,
        dynamic_suffix: str,
    ):
        system_prompt = POSTGRESQL_OPTIMIZATION_SYSTEM_PROMPT if self._is_chat_model(self.model) else None
        messages = self._build_provider_cache_messages(
            provider=provider,
            model_info=model_info,
            cacheable_prefix=cacheable_prefix,
            dynamic_suffix=dynamic_suffix,
            system_prompt=system_prompt,
        )
        if messages is None:
            messages = [{"role": "user", "content": prompt}]

        if system_prompt and not (
            provider == "gemini"
            and self._should_mark_cacheable_prefix(
                provider=provider,
                model_info=model_info,
                cacheable_prefix=cacheable_prefix,
            )
        ):
            messages.insert(0, {"role": "system", "content": system_prompt})

        return messages

    def _build_response_params(self, effective_model: str, provider: str | None, messages, cacheable_prefix: str):
        response_params = {
            "model": effective_model,
            "messages": messages,
            "request_timeout": self.ai_call_timeout,
            "temperature": 1.0,
            "seed": 42,
            "drop_params": True,
        }

        if provider != "openai":
            response_params["top_k"] = 1

        if not self.disable_provider_cache and provider == "openai" and cacheable_prefix:
            response_params["prompt_cache_key"] = self._build_prompt_cache_key(effective_model, cacheable_prefix)

        return response_params

    def _perform_ai_call(self, prompt, cacheable_prefix: str = "", dynamic_suffix: str = ""):
        effective_model = self._get_effective_model()
        model_info = litellm.get_model_info(effective_model)
        provider = self._get_provider_name(model_info)
        messages = self._build_messages(
            prompt=prompt,
            provider=provider,
            model_info=model_info,
            cacheable_prefix=cacheable_prefix,
            dynamic_suffix=dynamic_suffix,
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
                messages=messages,
                cacheable_prefix=cacheable_prefix,
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
        if prompt_tokens_details is not None:
            self.total_cached_input_tokens += self._get_usage_value(prompt_tokens_details, "cached_tokens", 0)

        self.total_cached_input_tokens += self._get_usage_value(usage, "cache_read_input_tokens", 0)
        self.total_cache_creation_input_tokens += self._get_usage_value(usage, "cache_creation_input_tokens", 0)

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

    def call_ai_provider(self, prompt, cacheable_prefix: str = "", dynamic_suffix: str = ""):
        logger.info("Calling AI Model for plan analysis...")
        self.call_count += 1  # Increment call count when AI call is initiated
        return self._perform_ai_call(
            prompt,
            cacheable_prefix=cacheable_prefix,
            dynamic_suffix=dynamic_suffix,
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
