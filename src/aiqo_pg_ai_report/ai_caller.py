import logging
import litellm
from ratelimit import limits, sleep_and_retry

logger = logging.getLogger(__name__)

DEFAULT_TOKEN_LIMIT = 8192
DEFAULT_AI_CALL_TIMEOUT = 90

FREE_TIER_RATE_LIMITS = {
    "gpt-4o": (10, 60),
    "gpt-4o-mini": (10, 60),
    "gpt-3.5-turbo": (10, 60),
    "o1": (10, 60),
    "o1-mini": (10, 60),
    "gemini-2.0-flash": (15, 60),
    "gemini-1.5-flash": (15, 60),
    "gemini-1.5-flash-8b": (15, 60),
    "gemini-1.5-pro": (15, 60),
}


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

        if debug:
            litellm._turn_on_debug()
            logger.info("LiteLLM debug mode enabled.")

        # Determine rate limits based on the model
        self.calls_per_period, self.period_seconds = FREE_TIER_RATE_LIMITS.get(
            self.model, (10, 60)  # Default to 10 calls/min if model not in list
        )
        logger.info(
            f"AI Caller initialized with rate limit: {self.calls_per_period} calls per {self.period_seconds} seconds for model {self.model}"
        )

        # Create a rate-limited version of the internal _perform_ai_call method
        # This uses the 'limits' function (not decorator) to apply the rate limit dynamically
        self._rate_limited_perform_ai_call = limits(calls=self.calls_per_period, period=self.period_seconds)(
            self._perform_ai_call
        )

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

    # This is the actual method that performs the AI call logic.
    # It is NOT decorated with @limits directly.
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
            ai_hints = (
                f"Token count ({estimated_tokens}) exceeds the model limit ({self.token_limit}). AI analysis skipped."
            )
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
                "temperature": 0,
                "top_p": 0,
                "seed": 42,
                "drop_params": True,
            }

            # Only set top_k if not an OpenAI model
            if not is_openai_model:
                response_params["top_k"] = 1

            response = litellm.completion(**response_params)

            # Accumulate actual input tokens from the response
            if response.usage and hasattr(response.usage, "prompt_tokens") and response.usage.prompt_tokens is not None:
                self.total_input_tokens += response.usage.prompt_tokens

            # Accumulate actual output tokens from the response
            if (
                response.usage
                and hasattr(response.usage, "completion_tokens")
                and response.usage.completion_tokens is not None
            ):
                self.total_output_tokens += response.usage.completion_tokens

            # Calculate and accumulate cost
            try:
                cost = litellm.completion_cost(completion_response=response)
                if cost is not None:
                    self.total_cost += cost
            except Exception as e:
                logger.warning(f"Could not calculate cost for the API call: {e}")

            # LiteLLM response structure is similar to OpenAI's
            if response.choices and response.choices[0].message and response.choices[0].message.content:
                return response.choices[0].message.content.strip()
            else:
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

    # This is the public method that will be called by other classes.
    # It applies the sleep_and_retry logic to the rate-limited internal method.
    def call_ai_provider(self, prompt):
        logger.info("Calling AI Model for plan analysis...")
        self.call_count += 1  # Increment call count when AI call is initiated
        return sleep_and_retry(self._rate_limited_perform_ai_call)(prompt)

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
