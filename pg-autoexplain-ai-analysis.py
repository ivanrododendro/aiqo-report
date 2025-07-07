#!/usr/bin/env python

import argparse
import hashlib
import io
import logging
import re
from collections import defaultdict
from pathlib import Path

import litellm
import sqlparse
from ratelimit import limits, sleep_and_retry
import gzip
import zipfile
from jinja2 import Environment, FileSystemLoader, select_autoescape

DEFAULT_FREE_TPM = 10
QUERY_NAME_LIMIT = 140

DEFAULT_LANG = "fr" # Default language for output, not for prompt file selection
DEFAULT_AI_CALL_TIMEOUT = 90
DEFAULT_TOKEN_LIMIT = 8192
DEFAULT_MODEL_TEMPERATURE = 0.5
DEFAULT_MODEL = "gemini-2.0-flash"

DEFAULT_MAX_AI_CALLS_UNLIMITED = -1

FREE_TIER_RATE_LIMITS = {
    "gpt-4o": (10, 60),
    "gpt-4o-mini": (10, 60),
    "gpt-3.5-turbo": (10, 60),
    "o1": (10, 60),
    "o1-mini": (10, 60),
    "gemini-2.0-flash": (15, 60),
    "gemini-1.5-flash": (15, 60),
    "gemini-1.5-flash-8b": (15, 60),
    "gemini-1.5-pro": (15, 60)
}

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Global rate limit variables, set once in main based on chosen model
# These are used by the @limits decorator, which requires global or class-level constants
g_calls = DEFAULT_FREE_TPM
g_period = 60


def normalize_sql(sql):
    # Formater le SQL avec sqlparse
    formatted_sql = sqlparse.format(sql, strip_comments=True, reindent=True, strip_whitespace=True)

    # Remplacer les constantes numériques et les chaînes de caractères par '?'
    formatted_sql = re.sub(r'\b\d+\b', '?', formatted_sql)  # Nombres
    formatted_sql = re.sub(r"'[^']*'", '?', formatted_sql)  # Chaînes de caractères

    return formatted_sql


def parse_log_entry(log_entry_text):
    duration_ms = None
    first_line = log_entry_text.splitlines()[0]
    duration_match = re.search(r"duration: (\d+\.?\d*) ms", first_line)
    if duration_match:
        try:
            duration_ms = float(duration_match.group(1))
        except ValueError:
            logger.warning(f"Could not parse duration from line: {first_line}")
            duration_ms = None # Ensure it's None if parsing fails

    # Extract the timestamp from the first 23 characters of the log entry
    timestamp = log_entry_text[:23].strip()
    # Extract the block from "Query Text:" to "Settings:"
    match = re.search(r"Query Text:(.*?)$", log_entry_text, re.DOTALL)
    if not match:
        raise ValueError("Could not parse log entry: Missing query text or execution plan.")

    # Extract the full block
    full_block = match.group(1).strip()
    lines = full_block.splitlines()

    # Extract the title (first one or two lines of the query)
    if len(lines) >= 2 and lines[0].strip().startswith("--") and lines[1].strip().startswith("--"):
        job_name = lines[0]
        query_name = lines[1]
        start_index = 2  # Skip the title lines for further processing
    else:
        job_name = ""
        query_name = [" ".join(lines[0:])]
        start_index = 0

    job_name = "\n".join(job_name).strip().replace("\t", "").replace("\n", "")
    query_name = "\n".join(query_name).strip().replace("\t", "").replace("\n", "")

    # Split based on the first occurrence of "cost="
    query_lines = []
    plan_lines = []
    found_plan = False

    for line in lines[start_index:]:  # Start from the appropriate index
        if not found_plan and "cost=" in line:
            found_plan = True
        if found_plan:
            plan_lines.append(line)
        else:
            query_lines.append(line)

    if not plan_lines:
        raise ValueError("No execution plan found in the log entry.")

    return {
        "timestamp": timestamp,
        "query_name": query_name,
        "job_name": job_name,
        "query_text": "\n".join(query_lines).strip(),
        "execution_plan": "\n".join(plan_lines).strip(),
        "duration" : duration_ms
    }


def get_query_code(query):
    normalized_query = normalize_sql(query)
    value_str = str(normalized_query).encode('utf-8')
    return hashlib.sha256(value_str).hexdigest().upper()


def extract_plan_starting_at_line(file_iterator, first_line):
    """
    Extracts a full PostgreSQL autoexplain plan block starting from first_line
    until a line starting with "Settings:" is found.
    """
    plan_lines = [first_line]
    for line in file_iterator:
        plan_lines.append(line)
        if line.strip().startswith("Settings:"):
            break
    return "".join(plan_lines)


class AiCaller:
    def __init__(self, model, temperature, ai_call_timeout, lang, prompts):
        self.model = model
        self.temperature = temperature
        self.ai_call_timeout = ai_call_timeout
        self.lang = lang
        self.prompts = prompts
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.total_cost = 0.0
        self.call_count = 0
        self.token_limit = self._get_model_token_limit() # Set token limit internally

    def _get_model_token_limit(self):
        model_info = litellm.get_model_info(self.model)
        if model_info and 'max_input_tokens' in model_info and model_info['max_input_tokens'] is not None:
            logger.info(f"Using input token limit for model {self.model}: {model_info['max_input_tokens']}")
            return model_info['max_input_tokens']
        else:
            logger.warning(f"Could not determine input token limit for model {self.model} from litellm. Falling back to default: {DEFAULT_TOKEN_LIMIT}")
            return DEFAULT_TOKEN_LIMIT

    @sleep_and_retry
    @limits(calls=g_calls, period=g_period) # Uses global g_calls, g_period set in main()
    def call_ai_provider(self, prompt):
        logger.info("Calling AI Model for plan analysis...")

        messages = [{"role": "user", "content": prompt}]
        # Add a system prompt for chat models, similar to the old call_chatgpt logic
        if "gpt" in self.model or "o1" in self.model or "gemini" in self.model or "claude" in self.model: # Heuristic for chat models
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
            logger.warning(f"Could not estimate token count for model {effective_model} using litellm.token_counter: {e}. Skipping AI analysis.")
            return f"Could not estimate token count for model {effective_model}. AI analysis skipped."

        if estimated_tokens > self.token_limit:
            ai_hints = f"Token count ({estimated_tokens}) exceeds the model limit ({self.token_limit}). AI analysis skipped."
            return ai_hints

        try:
            response = litellm.completion(
                model=effective_model,
                messages=messages,
                temperature=self.temperature,
                request_timeout=self.ai_call_timeout
            )
            
            # Accumulate actual input tokens from the response
            if response.usage and hasattr(response.usage, 'prompt_tokens') and response.usage.prompt_tokens is not None:
                self.total_input_tokens += response.usage.prompt_tokens
            
            # Accumulate actual output tokens from the response
            if response.usage and hasattr(response.usage, 'completion_tokens') and response.usage.completion_tokens is not None:
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

    def call_ai_for_plan_analysis(self, plan, custom_prompt=None, ddl_context=None):
        static_prompt = self.prompts.get('PLAN_ANALYSIS', '')
        full_prompt = static_prompt
        if ddl_context:
            full_prompt += "\n\nDDL context:\n" + ddl_context
        if custom_prompt:
            full_prompt += "\n\n" + custom_prompt
        full_prompt += "\n\n" + plan
        # Add language instruction to the prompt
        full_prompt += f"\n\nPlease provide the analysis in {self.lang}."
        self.call_count += 1
        return self.call_ai_provider(full_prompt)

    def call_ai_for_final_analysis(self, reports):
        logger.info("Creating final analysis...")

        # Concatenate only actual chatgpt_hints, excluding "skipped" messages
        all_hints = "\n\n".join([report["chatgpt_hints"] for report in reports if report["chatgpt_hints"] and not report["chatgpt_hints"].startswith("AI analysis skipped")])

        # Prepare the prompt for identifying most frequent optimization hints
        prompt_template = self.prompts.get('FINAL_ANALYSIS', '')
        prompt = prompt_template.format(all_hints=all_hints)
        # Add language instruction to the prompt
        prompt += f"\n\nPlease provide the analysis in {self.lang}."
        self.call_count += 1
        # Call ChatGPT API with the concatenated hints
        return self.call_ai_provider(prompt)


class LogParser:
    def __init__(self):
        pass

    def _process_plain_text_file(self, file_obj, log_file_path):
        logger.info(f'Processing plain text file {file_obj.name} from {log_file_path}')
        line_number = 0
        for line in file_obj:
            line_number += 1
            if 'plan:' in line:
                try:
                    # Pass the file_obj (iterator) and the current line
                    log_entry_text = extract_plan_starting_at_line(file_obj, line)
                    yield parse_log_entry(log_entry_text)
                except ValueError as e:
                    logger.warning(f"Skipping log entry at line {line_number} in {log_file_path} due to parsing error: {e}")
                    continue
                except Exception as e:
                    logger.error(f"Unexpected error processing log entry at line {line_number} in {log_file_path}: {e}")
                    continue

    def parse_log_file(self, log_file_path):
        if str(log_file_path).endswith('.gz'):
            logger.info(f'Uncompressing and parsing gzip file: {log_file_path}')
            with gzip.open(log_file_path, 'rt', encoding='utf-8') as f:
                yield from self._process_plain_text_file(f, log_file_path)
        elif str(log_file_path).endswith('.zip'):
            logger.info(f'Uncompressing and parsing zip file: {log_file_path}')
            with zipfile.ZipFile(log_file_path, 'r') as zip_ref:
                for file_name in zip_ref.namelist():
                    with zip_ref.open(file_name) as raw_f:
                        # Wrap the raw bytes file with TextIOWrapper for UTF-8 decoding
                        f = io.TextIOWrapper(raw_f, encoding='utf-8', errors='replace')
                        yield from self._process_plain_text_file(f, log_file_path)
        else:
            logger.info(f'Parsing plain text log file: {log_file_path}')
            with open(log_file_path, 'r', encoding='utf-8') as f:
                yield from self._process_plain_text_file(f, log_file_path)


class ReportGenerator:
    def __init__(self, template_base_path):
        self.env = Environment(
            loader=FileSystemLoader(str(template_base_path)),
            autoescape=select_autoescape(['html', 'xml'])
        )
        self.template = self.env.get_template("report_templates/report_template.html")

    def generate_report(self, output_path, title, frequent_hints_analysis, model, query_stats, reports_by_day):
        logger.info(f"Generating HTML report in {output_path}")

        html_report = self.template.render(
            title=title,
            frequent_hints_analysis=frequent_hints_analysis,
            model=model,
            query_stats=query_stats,
            reports_by_day=reports_by_day,
            QUERY_NAME_LIMIT=QUERY_NAME_LIMIT
        )
        Path(output_path).write_text(html_report, encoding="utf-8")


class PGAutoExplainAnalyzer:
    def __init__(self, args):
        self.args = args
        self.model = args.model
        self.skip_ai_analysis = args.skip_ai_analysis
        self.limit_ai_calls = args.limit_ai_calls
        self.ai_call_timeout = args.ai_call_timeout
        self.language = args.language
        self.temperature = args.temperature
        self.only_seq_scan_ai_analysis = args.only_seq_scan_ai_analysis
        self.filter_strings = args.filter
        self.custom_prompt = args.custom_prompt
        self.ddl_context = self._load_ddl_context(args.sql_context_file)
        self.target_query_mode = args.target_query_mode

        self.prompts = self._load_prompts()
        if not self.prompts:
            logger.error("Failed to load prompts. Exiting.")
            exit(1)

        self.ai_caller = AiCaller( # Renamed from AIClient
            model=self.model,
            temperature=self.temperature,
            ai_call_timeout=self.ai_call_timeout,
            lang=self.language,
            prompts=self.prompts
        )
        self.log_parser = LogParser()
        self.report_generator = ReportGenerator(Path(__file__).parent)

        self.all_reports = []
        self.reports_by_day = defaultdict(list)
        self.all_query_stats_dict = {}
        self.final_analysis_result = ""

    def _load_ddl_context(self, sql_context_file):
        if sql_context_file:
            try:
                with open(sql_context_file, "r", encoding="utf-8") as ddl_file:
                    ddl_context = ddl_file.read()
                logger.info(f"Loaded DDL context from: {sql_context_file}")
                return ddl_context
            except Exception as e:
                logger.error(f"Could not read DDL context file '{sql_context_file}': {e}")
        return None

    def _load_prompts(self):
        current_prompts = {}
        current_prompt = None
        current_content = []
        lang_file_path = Path(__file__).parent / 'prompts/prompts.txt'

        try:
            with open(lang_file_path, 'r') as file:
                for line in file:
                    line = line.strip()
                    if line.startswith('[') and line.endswith(']'):
                        if current_prompt:
                            current_prompts[current_prompt] = '\n'.join(current_content).strip()
                        current_prompt = line[1:-1]
                        current_content = []
                    else:
                        current_content.append(line)

            if current_prompt:
                current_prompts[current_prompt] = '\n'.join(current_content).strip()

            if not current_prompts:
                logger.error(f"Failed to load prompts from: {lang_file_path}. Exiting.")
                exit(1)
        except FileNotFoundError:
            logger.error(f"Prompts file not found: {lang_file_path}")
            exit(1)
        except Exception as e:
            logger.error(f"Error reading prompts file: {e}")
            exit(1)
        return current_prompts


    def _process_parsed_log_entry(self, parsed_result):
        query_name = parsed_result["query_name"]
        job_name = parsed_result["job_name"]
        query_text = parsed_result["query_text"]
        query_code = get_query_code(query_text)

        title = job_name + " " + query_name
        execution_plan = parsed_result["execution_plan"]
        timestamp = parsed_result["timestamp"]
        day = timestamp[:10]
        query = query_text
        ai_hints = "" # Initialize to empty string
        seq_scan_indicator = (execution_plan.find("Seq Scan") != -1)

        should_perform_ai_call = True # Flag to control if AI call should be made

        # 1. Check if AI analysis is globally skipped
        if self.skip_ai_analysis:
            ai_hints = "AI analysis skipped (CLI flag --skip_ai_analysis)."
            should_perform_ai_call = False
            logger.debug("Skipping AI analysis (skip_ai_analysis flag is true)")

        # 2. Check filter criteria (if not already skipped globally)
        if should_perform_ai_call and self.filter_strings:
            match_found = False
            for filter_str in self.filter_strings:
                if (filter_str.lower() in job_name.lower() or
                    filter_str.lower() in query_name.lower() or
                    filter_str.lower() in query_text.lower() or
                    filter_str.lower() in query_code.lower()):
                    match_found = True
                    break
            if not match_found:
                ai_hints = "AI analysis skipped due to filter criteria."
                should_perform_ai_call = False
                logger.info(f"Skipping AI analysis for query (code: {query_code[:6]}) as it does not match filter criteria.")

        # 3. Check max AI calls limit (if not already skipped)
        if should_perform_ai_call and self.limit_ai_calls != -1 and (self.ai_caller.call_count >= self.limit_ai_calls): # Updated ai_client to ai_caller
            ai_hints = "AI analysis skipped (AI call limit reached)."
            should_perform_ai_call = False
            logger.warning(f"AI call limit reached. Skipping AI analysis for query")

        # 4. Check AI only for Seq Scan (if not already skipped)
        if should_perform_ai_call and self.only_seq_scan_ai_analysis and not seq_scan_indicator:
            ai_hints = "AI analysis skipped (only for Seq Scan queries)."
            should_perform_ai_call = False
            logger.info("Skipping AI analysis for query without Seq Scan (only_seq_scan_ai_analysis is true)")

        # 5. Perform AI call if all conditions allow
        if should_perform_ai_call:
            ai_hints_result = self.ai_caller.call_ai_for_plan_analysis( # Updated ai_client to ai_caller
                parsed_result["execution_plan"], custom_prompt=self.custom_prompt, ddl_context=self.ddl_context
            )
            if ai_hints_result is None:
                ai_hints = "AI analysis failed or timed out."
            else:
                ai_hints = ai_hints_result

        report = {
            "title": title,
            "chatgpt_hints": ai_hints,
            "plan": execution_plan,
            "query_text": query,
            "query_timestamp": timestamp,
            "query_name": query_name,
            "job_name": job_name,
            "code": query_code,
            "day": day,
            "seq_scan_indicator": seq_scan_indicator,
            "duration" : parsed_result["duration"]
        }

        self.all_reports.append(report)
        self.reports_by_day[report["day"]].append(report)

        # Update query_stats in-place
        if query_code not in self.all_query_stats_dict:
            self.all_query_stats_dict[query_code] = {
                "code": query_code,
                "name": report["query_name"],
                "count": 1,
                "cumulated_time": report["duration"]
            }
        else:
            self.all_query_stats_dict[query_code]["count"] += 1
            self.all_query_stats_dict[query_code]["cumulated_time"] += report["duration"]


    def run(self):
        global g_calls, g_period # Set global rate limit variables for the @limits decorator
        g_calls, g_period = FREE_TIER_RATE_LIMITS.get(self.model, (10, 60))

        if self.args.directory_mode:
            directory = Path(self.args.log_filename)
            if not directory.is_dir():
                logger.error(f"Specified directory does not exist: {self.args.log_filename}")
                exit(1)

            log_files = list(directory.glob("*.log")) + list(directory.glob("*.gz")) + list(directory.glob("*.zip"))
            if not log_files:
                logger.error(f"No .log, .gz or .zip files found in directory: {self.args.log_filename}")
                exit(1)

            logger.info(f"Processing directory: {self.args.log_filename}")
            logger.info(f"Found files: {[str(f) for f in log_files]}")
            
            if self.args.report_filename:
                report_filename = self.args.report_filename
            else:
                report_filename = str(directory / f"{directory.name}_report.html")

        else: # Single file mode
            log_file_path = Path(self.args.log_filename)
            if not log_file_path.is_file():
                logger.error(f"Specified log file does not exist: {self.args.log_filename}")
                exit(1)
            log_files = [log_file_path]

            report_filename = self.args.report_filename if self.args.report_filename else f"{self.args.log_filename}_report.html"
            logger.info(f"Processing PostgreSQL log file {self.args.log_filename}")

        resolved_report_filename = Path(report_filename).resolve()
        logger.info(f"Output report: {resolved_report_filename}")

        if self.skip_ai_analysis:
            logger.info("Skipping AI Analysis")
        else:
            logger.info(f"Using model: {self.model}")
            logger.info(f"Maximum AI calls: {self.limit_ai_calls if self.limit_ai_calls != -1 else 'Unlimited'}")
            logger.info(f"AI API call timeout: {self.ai_call_timeout} seconds")
            logger.info(f"Language for AI output: {self.language}")
            logger.info(f"Model temperature : {self.temperature}")
            logger.info(f"AI Analysis only for Seq Scan queries : {self.only_seq_scan_ai_analysis}")
            if self.custom_prompt:
                logger.info(f"Custom prompt provided: {self.custom_prompt}")
            if self.ddl_context:
                logger.info(f"DDL context loaded from file: {self.args.sql_context_file}")
        
        if self.target_query_mode:
            logger.info("Target Query Mode is ENABLED.")

        if self.filter_strings:
            logger.info(f"AI analysis will be filtered by: {', '.join(self.filter_strings)}. All queries will still be reported.")

        for log_file in log_files:
            for parsed_entry in self.log_parser.parse_log_file(log_file):
                self._process_parsed_log_entry(parsed_entry)

        if not self.skip_ai_analysis:
            self.final_analysis_result = self.ai_caller.call_ai_for_final_analysis(self.all_reports) # Updated ai_client to ai_caller
        else:
            self.final_analysis_result = ""

        # Convert query_stats dict to sorted list for the report
        query_stats_list = sorted(self.all_query_stats_dict.values(), key=lambda x: x["cumulated_time"], reverse=True)

        report_title = "PostgreSQL Auto Explain Report" if self.skip_ai_analysis else f"PostgreSQL Auto Explain AI Report ({self.model}) "
        self.report_generator.generate_report(
            str(resolved_report_filename),
            report_title,
            self.final_analysis_result,
            self.model,
            query_stats_list,
            self.reports_by_day
        )


def parse_cli_arguments():
    parser = argparse.ArgumentParser(description="Process PostgreSQL log file and generate an analysis report.")
    parser.add_argument("log_filename", nargs="?", help="Path to the PostgreSQL log file")
    parser.add_argument("-m", "--model", default=DEFAULT_MODEL,
                        help=f"AI model to use for analysis (default: ${DEFAULT_MODEL})")
    parser.add_argument("-l", "--limit-ai-calls", type=int, default=DEFAULT_MAX_AI_CALLS_UNLIMITED,
                        help=f"Maximum number of AI calls to make. Use -1 for unlimited (default: ${DEFAULT_MAX_AI_CALLS_UNLIMITED})")
    parser.add_argument( "--ai-call-timeout", type=int, default=DEFAULT_AI_CALL_TIMEOUT,
                        help=f"Timeout for AI API calls in seconds (default: ${DEFAULT_AI_CALL_TIMEOUT})")
    parser.add_argument("--language", default=DEFAULT_LANG,
                        help=f"Language for AI output (default: ${DEFAULT_LANG})") # Updated description
    parser.add_argument("--temperature", type=float, default=DEFAULT_MODEL_TEMPERATURE,
                        help=f"Temperature for the AI model (default: ${DEFAULT_MODEL_TEMPERATURE})")
    parser.add_argument("-s", "--skip_ai_analysis", action="store_true",
                        help="Skips the AI analysis and only generates the HTML report (default: false)")
    parser.add_argument("-o", "--only-seq-scan-ai-analysis", action="store_true",
                        help="Enables AI Analysis only for queries with Seq Scan (default: false)")
    parser.add_argument("-f", "--filter", action="append",
                        help="Perform AI analysis only for queries that contain the specified string in the comment, SQL, or query code. Can be specified multiple times. All queries will still be included in the report.")
    parser.add_argument("-c", "--custom-prompt", type=str, default=None,
                        help="Add a custom prompt to the default AI prompt (optional)")
    parser.add_argument("--sql-context-file", type=str, default=None,
                        help="Specify a DDL SQL file whose content will be added to the prompt (optional)")
    parser.add_argument("-r", "--report-filename", type=str, default=None,
                        help="Override the HTML report filename (optional)")
    parser.add_argument("-d","--directory-mode", action="store_true", default=False,
                        help="Process all .log and .zip files in the directory specified as the main positional argument")
    parser.add_argument("--target-query-mode", action="store_true", default=False,
                        help="Enables target query mode for analysis (default: false)")

    args, unknown_args = parser.parse_known_args()

    if unknown_args:
        logger.warning(f"Unrecognized arguments: {unknown_args}. These will be ignored.")

    return args


def main():
    args = parse_cli_arguments()
    analyzer = PGAutoExplainAnalyzer(args)
    analyzer.run()

    logger.info(f"Total input tokens processed: {analyzer.ai_caller.total_input_tokens}") # Updated ai_client to ai_caller
    logger.info(f"Total output tokens processed: {analyzer.ai_caller.total_output_tokens}") # Updated ai_client to ai_caller
    logger.info(f"Estimated total cost: ${analyzer.ai_caller.total_cost:.4f}") # Updated ai_client to ai_caller


if __name__ == "__main__":
    main()
