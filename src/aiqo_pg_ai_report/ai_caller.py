import logging
from types import SimpleNamespace
import litellm

logger = logging.getLogger(__name__)

DEFAULT_TOKEN_LIMIT = 8192
DEFAULT_AI_CALL_TIMEOUT = 90

class AiCaller:
    def __init__(self, model, ai_call_timeout, lang, prompts, debug):
        self.model = model
        self.ai_call_timeout = ai_call_timeout
        self.lang = lang
        self.prompts = prompts
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.total_cost = 0.0
        self.call_count = 0
        self.token_limit = self._get_model_token_limit()
        self.debug = debug
        self.streaming_enabled = True  # Default to streaming; fallback to non-streaming on failure
 
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

    def _perform_ai_call(self, prompt):
        messages = [{"role": "user", "content": prompt}]
        # Add a system prompt for chat models, similar to the old call_chatgpt logic
        if (
            "gpt" in self.model or "o1" in self.model or "gemini" in self.model or "claude" in self.model
        ):  # Heuristic for chat models
            messages.insert(0, {"role": "system", "content": "You are a PostgreSQL optimization expert."})

        # Ensure Gemini models use the Google AI Studio API via "gemini/" prefix
        effective_model = self.model
        if self.model.startswith("gemini-"):
            effective_model = "gemini/" + self.model
            logger.info(f"Using Google AI Studio provider for model: {effective_model}")

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
            # Retrieve model information to check the provider
            model_info = litellm.get_model_info(effective_model)
            is_openai_model = model_info.get("litellm_provider") == "openai" if model_info else False

            # Set parameters conditionally based on the provider
            response_params = {
                "model": effective_model,
                "messages": messages,
                "request_timeout": self.ai_call_timeout,
                "temperature": 1.0,
                "seed": 42,
                "drop_params": True,
            }

            # Only set top_k if not an OpenAI model
            if not is_openai_model:
                response_params["top_k"] = 1

            # Try streaming first; fall back to standard completion if unsupported or fails.
            response = None
            if self.streaming_enabled:
                response_params["stream"] = True
                try:
                    response = litellm.completion(**response_params)
                    if self._is_streaming_response(response):
                        return self._handle_streaming_response(response)
                    logger.debug("Model %s did not return a streaming iterator; disabling streaming.", self.model)
                    self.streaming_enabled = False
                except Exception as exc:
                    logger.warning(
                        "Streaming not available for model %s (%s). Falling back to non-streaming.", self.model, exc
                    )
                    self.streaming_enabled = False

            response_params.pop("stream", None)
            if response is None:
                response = litellm.completion(**response_params)

            self._accumulate_usage(response)

            # LiteLLM response structure is similar to OpenAI's
            if response.choices and response.choices[0].message and response.choices[0].message.content:
                text_content = self._extract_text_from_content(response.choices[0].message.content)
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

    def _handle_streaming_response(self, response_stream):
        """Consume a streaming LiteLLM response and return aggregated content."""
        content_parts = []
        last_usage = None

        try:
            for chunk in response_stream:
                choice = chunk.choices[0] if getattr(chunk, "choices", None) else None
                if not choice:
                    continue

                delta = getattr(choice, "delta", None)
                message = getattr(choice, "message", None)

                # Collect content from delta or message fields
                text_piece = None
                if delta is not None:
                    text_piece = self._extract_text_from_content(getattr(delta, "content", None))
                    if not text_piece:
                        text_piece = self._extract_text_from_content(getattr(delta, "text", None))
                if not text_piece and message is not None:
                    text_piece = self._extract_text_from_content(getattr(message, "content", None))
                    if not text_piece:
                        text_piece = self._extract_text_from_content(getattr(message, "text", None))
                if not text_piece:
                    text_piece = self._extract_text_from_content(getattr(choice, "text", None))

                if text_piece:
                    content_parts.append(text_piece)

                # Capture usage if provided on streaming chunks
                usage = getattr(chunk, "usage", None)
                if usage:
                    last_usage = usage
        except Exception as exc:
            logger.error("Error while reading streaming response for model %s: %s", self.model, exc)
            raise

        full_content = "".join(content_parts).strip()
        if last_usage:
            self._accumulate_usage(SimpleNamespace(usage=last_usage, choices=[]))

        if not full_content:
            logger.warning("Received empty streaming content for model %s.", self.model)
            return f"No analysis content found in LiteLLM response for model {self.model}."
        return full_content

    @staticmethod
    def _is_streaming_response(response) -> bool:
        """Return True if the object looks like a streaming iterator."""
        return hasattr(response, "__iter__") and not isinstance(response, (str, bytes, dict))

    def _accumulate_usage(self, response):
        """Aggregate token usage and cost from a LiteLLM response."""
        usage = getattr(response, "usage", None)
        if usage and getattr(usage, "prompt_tokens", None) is not None:
            self.total_input_tokens += usage.prompt_tokens
        if usage and getattr(usage, "completion_tokens", None) is not None:
            self.total_output_tokens += usage.completion_tokens

        try:
            cost = litellm.completion_cost(completion_response=response)
            if cost is not None:
                self.total_cost += cost
        except Exception as e:
            logger.warning(f"Could not calculate cost for the API call: {e}")

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

    def call_ai_provider(self, prompt):
        logger.info("Calling AI Model for plan analysis...")
        self.call_count += 1  # Increment call count when AI call is initiated
        return self._perform_ai_call(prompt)

    def show_stats(self):
        """Logs the final statistics of AI API usage."""
        if self.call_count > 0:
            logger.info("--- AI Usage Statistics ---")
            logger.info(f"Total AI calls made: {self.call_count}")
            logger.info(f"Total input tokens processed: {self.total_input_tokens}")
            logger.info(f"Total output tokens processed: {self.total_output_tokens}")
            logger.info(f"Estimated total cost: ${self.total_cost:.4f}")
            logger.info("---------------------------")
        else:
            logger.info("No AI calls were made during this run.")
