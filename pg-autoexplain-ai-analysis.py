#!/usr/bin/env python

import argparse
import hashlib
import html
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

DEFAULT_FREE_TPM = 10
QUERY_NAME_LIMIT = 140

DEFAULT_LANG = "fr"
DEFAULT_AI_CALL_TIMEOUT = 90
DEFAULT_TOKEN_LIMIT = 8192
DEFAULT_MODEL_TEMPERATURE = 0.5
DEFAULT_MODEL = "gemini-2.0-flash-exp"
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

g_calls = DEFAULT_FREE_TPM
g_period = 60
g_skip_ai_analysis = False
g_model_temperature = DEFAULT_MODEL_TEMPERATURE
g_model_token_limit = DEFAULT_TOKEN_LIMIT
g_prompts = {}
g_total_input_tokens = 0
g_total_output_tokens = 0
g_total_cost = 0.0
g_ai_call_count = 0
g_ai_only_for_seq_scan = False


def normalize_sql(sql):
    # Formater le SQL avec sqlparse
    formatted_sql = sqlparse.format(sql, strip_comments=True, reindent=True, strip_whitespace=True)

    # Remplacer les constantes numériques et les chaînes de caractères par '?'
    formatted_sql = re.sub(r'\b\d+\b', '?', formatted_sql)  # Nombres
    formatted_sql = re.sub(r"'[^']*'", '?', formatted_sql)  # Chaînes de caractères

    return formatted_sql


def load_prompts(lang):
    global g_prompts
    current_prompt = None
    current_content = []
    base_path = Path(__file__).parent / 'prompts'

    lang_file_path = f"{base_path}_{lang}.txt"

    try:
        with open(lang_file_path, 'r') as file:
            for line in file:
                line = line.strip()
                if line.startswith('[') and line.endswith(']'):
                    if current_prompt:
                        g_prompts[current_prompt] = '\n'.join(current_content).strip()
                    current_prompt = line[1:-1]
                    current_content = []
                else:
                    current_content.append(line)

        if current_prompt:
            g_prompts[current_prompt] = '\n'.join(current_content).strip()

        if not g_prompts:
            logger.error(f"Failed to load prompts for language: {lang}. Exiting.")
            exit(1)
    except FileNotFoundError:
        logger.error(f"Prompts file not found: {lang_file_path}")
    except Exception as e:
        logger.error(f"Error reading prompts file: {e}")

    return None


def call_ai_for_plan_analysis(plan, model, timeout):
    static_prompt = g_prompts.get('PLAN_ANALYSIS', '')
    full_prompt = static_prompt + "\n\n" + plan

    return call_ai_provider(full_prompt, model, timeout)


@sleep_and_retry
@limits(calls=g_calls, period=g_period)
def call_ai_provider(prompt, model, timeout):
    global g_total_input_tokens, g_total_output_tokens, g_total_cost
    logger.info("Calling AI Model for plan analysis...")

    messages = [{"role": "user", "content": prompt}]
    # Add a system prompt for chat models, similar to the old call_chatgpt logic
    # This might need adjustment based on how model types are identified with LiteLLM
    if "gpt" in model or "o1" in model or "gemini" in model or "claude" in model: # Heuristic for chat models
        messages.insert(0, {"role": "system", "content": "You are a PostgreSQL optimization expert."})

    # Ensure Gemini models use the Google AI Studio API via "gemini/" prefix
    effective_model = model
    if model.startswith("gemini-"):
        effective_model = "gemini/" + model
        logger.info(f"Using Google AI Studio provider for model: {effective_model}")
    
    try:
        # Estimate tokens using litellm.token_counter with the constructed messages
        estimated_tokens = litellm.token_counter(model=effective_model, messages=messages)
    except Exception as e:
        logger.warning(f"Could not estimate token count for model {effective_model} using litellm.token_counter: {e}. Skipping AI analysis.")
        # Consider if a more specific error message or fallback is needed
        return f"Could not estimate token count for model {effective_model}. AI analysis skipped."

    if estimated_tokens > g_model_token_limit:
        ai_hints = f"Token count ({estimated_tokens}) exceeds the model limit ({g_model_token_limit}). AI analysis skipped."
        return ai_hints

    try:
        response = litellm.completion(
            model=effective_model,
            messages=messages,
            temperature=g_model_temperature,
            request_timeout=timeout
        )
        
        # Accumulate actual input tokens from the response
        if response.usage and hasattr(response.usage, 'prompt_tokens') and response.usage.prompt_tokens is not None:
            g_total_input_tokens += response.usage.prompt_tokens
        
        # Accumulate actual output tokens from the response
        if response.usage and hasattr(response.usage, 'completion_tokens') and response.usage.completion_tokens is not None:
            g_total_output_tokens += response.usage.completion_tokens

        # Calculate and accumulate cost
        try:
            cost = litellm.completion_cost(completion_response=response)
            if cost is not None:
                g_total_cost += cost
        except Exception as e:
            logger.warning(f"Could not calculate cost for the API call: {e}")

        # LiteLLM response structure is similar to OpenAI's
        if response.choices and response.choices[0].message and response.choices[0].message.content:
            return response.choices[0].message.content.strip()
        else:
            logger.warning(f"No analysis content found in LiteLLM response for model {model}.")
            return f"No analysis content found in LiteLLM response for model {model}."
    except litellm.exceptions.Timeout as e:
        logger.error(f"Timeout while communicating with LiteLLM API for model {model}: {e}")
        return None
    except Exception as e:
        logger.error(f"Error communicating with LiteLLM API for model {model}: {e}")
        # Log more details if available, e.g., response from LiteLLM
        if hasattr(e, "response"):
             logger.error(f"LiteLLM Response content: {e.response.text}")
        return None


def parse_log_entry(log_entry):
    # Extract the timestamp from the first 23 characters of the log entry
    timestamp = log_entry[:23].strip()
    # Extract the block from "Query Text:" to "Settings:"
    match = re.search(r"Query Text:(.*?)$", log_entry, re.DOTALL)
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
        query_name = [lines[0]]
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
        "execution_plan": "\n".join(plan_lines).strip()
    }


# Function to generate an HTML report
def generate_html_report(output_path, frequent_hints_analysis, model, query_count_by_code, reports_by_day,
                         query_names_by_code):
    logger.info(f"Generating HTML report in {output_path}")

    if g_skip_ai_analysis:
        title = "PostgreSQL Auto Explain Report"
    else:
        title = f"PostgreSQL Auto Explain AI Report ({model}) "

    html_template = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <script src="https://unpkg.com/vue@3.2.45/dist/vue.global.prod.js"></script>
    <script src="https://unpkg.com/pev2/dist/pev2.umd.js"></script>
    <link href="https://unpkg.com/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet"/>
    <script src="https://code.jquery.com/jquery-3.2.1.slim.min.js" integrity="sha384-KJ3o2DKtIkvYIK3UENzmM7KCkRr/rE9/Qpg6aAZGJwFDMVNA/GpGFF93hXpG5KkN" crossorigin="anonymous"></script>
    <script src="https://cdn.jsdelivr.net/npm/popper.js@1.12.9/dist/umd/popper.min.js" integrity="sha384-ApNbgh9B+Y1QKtv3Rn7W3mgPxhU9K/ScQsAP7hUibX39j7fakFPskvXusvfa0b4Q" crossorigin="anonymous"></script>
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@4.0.0/dist/js/bootstrap.min.js" integrity="sha384-JZR6Spejh4U02d8jOt6vLEHfe/JQGiRRSQQxSfFWpi1MquVdAyjUar5+76PVCmYl" crossorigin="anonymous"></script>
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons/font/bootstrap-icons.css">
    <link rel="stylesheet" href="https://unpkg.com/pev2/dist/pev2.css" />
    <style>.icon {{{{color: red !important;}}}}</style>
    </head>
    <body class="container-fluid">
        <script>
            const {{{{ createApp }}}} = Vue;
        </script>
        <h1 class="mb-4">{title}</h1>
        <h2>Requêtes</h2>
        {{content}}
    </body>
    </html>
    """
    content = ""
    sorted_days = sorted(reports_by_day.keys())

    for day in sorted_days:
        content += f"""
            <a data-toggle="collapse" href="#collapseDay-{day}" role="button" aria-expanded="false" aria-controls="collapseDay-{day}">
                <h3>{day}</h3>
            </a>
            <div class="collapse" id="collapseDay-{day}">
            <div class="card card-body">
        """

        for i, report in enumerate(reports_by_day[day]):
            # Generate unique IDs for each Vue app instance
            app_id = f"app-{day}-{i}"
            content += f"""
                <a data-toggle="collapse" href="#collapseExample-{app_id}" role="button" aria-expanded="false" aria-controls="collapseExample-{app_id}">
                <h5>{report['query_timestamp']} : {report['title']} ({report['code'][:6]})
            """

            if report['seq_scan_indicator']:
                content += """ <i class="bi bi-database-exclamation icon" title="La requête contient un Seq Scan"></i>"""

            content += f"""
            </h5>
            </a>
            <div class="collapse" id="collapseExample-{app_id}">
            <div class="card card-body">
            {report['chatgpt_hints']}
            <div id="{app_id}">
                <pev2 :plan-source="plan" :plan-query="query" style="display: block;  aspect-ratio: 16 / 9; width: 100%;"></pev2>
            </div>
            <script>
                $('#collapseExample-{app_id}').on('shown.bs.collapse', function () {{
                    createApp({{
                        data() {{
                            return {{
                                plan: `{report['plan']}`,
                                query: `{report['query_text']}`
                            }};
                        }}
                    }}).component("pev2", pev2.Plan).mount("#{app_id}");
                }});
            </script>
            </div>
            </div>      
            """
        content += "</div></div>"

    content += "<h2>Synthèse</h2>"
    content += """
        <a data-toggle="collapse" href="#requestCollapse" role="button" aria-expanded="false" aria-controls="requestCollapse">
            <h3>Requêtes</h3>
        </a>
          <div class="collapse" id="requestCollapse">
        <div class="card card-body">
            <table class='table-striped' >
                <thead>
                    <tr>
                        <th scope='col'>Requête</th><th scope='col'># occurrences</th>
                    </tr>
                </thead>
                <tbody>
                """

    for (query_code, count) in query_count_by_code.items():
        content += f"<tr scope='row'><td>{query_names_by_code[query_code][:QUERY_NAME_LIMIT]} ({query_code[:6]})</td><td>{count}</td></tr>"

    content += "</tbody> </table> </div></div>"
    content += f"{frequent_hints_analysis}"

    html_report = html_template.format(content=content, model=model)
    Path(output_path).write_text(html_report, encoding="utf-8")


def get_query_code(query):
    normalized_query = normalize_sql(query)
    value_str = str(normalized_query).encode('utf-8')
    return hashlib.sha256(value_str).hexdigest().upper()


def call_ai_for_final_analysis(reports, model, timeout):
    logger.info("Creating final analysis...")

    # Concatenate all chatgpt_hints
    all_hints = "\n\n".join([report["chatgpt_hints"] for report in reports if report["chatgpt_hints"]])

    # Prepare the prompt for identifying most frequent optimization hints
    prompt_template = g_prompts.get('FINAL_ANALYSIS', '')
    prompt = prompt_template.format(all_hints=all_hints)

    # Call ChatGPT API with the concatenated hints
    return call_ai_provider(prompt, model, timeout)


def parse_cli_arguments():
    parser = argparse.ArgumentParser(description="Process PostgreSQL log file and generate an analysis report.")
    parser.add_argument("log_filename", help="Path to the PostgreSQL log file")
    parser.add_argument("-m", "--model", default=DEFAULT_MODEL,
                        help=f"AI model to use for analysis (default: ${DEFAULT_MODEL})")
    parser.add_argument("-c", "--max-ai-calls", type=int, default=DEFAULT_MAX_AI_CALLS_UNLIMITED,
                        help=f"Maximum number of AI calls to make. Use -1 for unlimited (default: ${DEFAULT_MAX_AI_CALLS_UNLIMITED})")
    parser.add_argument("-t", "--timeout", type=int, default=DEFAULT_AI_CALL_TIMEOUT,
                        help=f"Timeout for AI API calls in seconds (default: ${DEFAULT_AI_CALL_TIMEOUT})")
    parser.add_argument("-l", "--lang", default=DEFAULT_LANG,
                        help=f"Language for prompts and output (default: ${DEFAULT_LANG})")
    parser.add_argument("-p", "--temperature", type=float, default=DEFAULT_MODEL_TEMPERATURE,
                        help=f"Temperature for the AI model (default: ${DEFAULT_MODEL_TEMPERATURE})")
    parser.add_argument("-s", "--skip_ai_analysis", action="store_true",
                        help="Skips the AI analysis and only generates the HTML report (default: false)")
    parser.add_argument("-o", "--ai_only_for_seq_scan", action="store_true",
                        help="Enables AI Analysis only for queries with Seq Scan (default: false)")

    return parser.parse_args()


def process_log_file(log_file_path, model, max_ai_calls, timeout):
    reports, reports_by_day, query_count_by_code, query_names_by_code = [], defaultdict(list), {}, {}

    def process_plain_text_file(file):
        logger.info(f'Process plain text file {file.name} at {log_file_path}')

        for line_number, line in enumerate(file, 1):
            if 'plan:' in line:
                plan_lines = "".join(extract_plan_lines(file, line))
                parsed_result = parse_log_entry(plan_lines)

                logger.info(f"Analyzing query at line {line_number}")

                report = process_parsed_result(parsed_result, plan_lines, model, timeout, max_ai_calls)

                if report:
                    reports.append(report)

                    query_code = report["code"]
                    reports_by_day[report["day"]].append(report)
                    query_count_by_code[query_code] = query_count_by_code.get(query_code, 0) + 1
                    query_names_by_code[query_code] = report["query_name"]

    if log_file_path.endswith('.gz'):
        logger.info('Uncompressing gzip file...')
        with gzip.open(log_file_path, 'rt', encoding='utf-8') as f:
            process_plain_text_file(f)
    elif log_file_path.endswith('.zip'):
        logger.info('Uncompressing zip file...')
        with zipfile.ZipFile(log_file_path, 'r') as zip_ref:
            for file_name in zip_ref.namelist():
                with zip_ref.open(file_name) as raw_f:
                    # Wrap the raw bytes file with TextIOWrapper for UTF-8 decoding
                    f = io.TextIOWrapper(raw_f, encoding='utf-8', errors='replace')
                    process_plain_text_file(f)
    else:
        with open(log_file_path, 'r', encoding='utf-8') as f:
            process_plain_text_file(f)

    return reports, reports_by_day, query_count_by_code, query_names_by_code


def extract_plan_lines(file, first_line):
    plan_lines = [first_line]
    for line in file:
        plan_lines.append(line)
        if line.strip().startswith("Settings:"):
            break
    return plan_lines


def process_parsed_result(parsed_result, plan_lines, model, timeout, max_ai_calls):
    global g_ai_call_count

    query_name = parsed_result["query_name"]
    title = parsed_result["job_name"] + query_name
    execution_plan = parsed_result["execution_plan"]
    timestamp = parsed_result["timestamp"]
    day = timestamp[:10]
    query_code = get_query_code(parsed_result["query_text"])
    query = html.escape(parsed_result["query_text"])
    ai_hints = ""
    seq_scan_indicator = (execution_plan.find("Seq Scan") != -1)

    if not g_skip_ai_analysis:
        if max_ai_calls == -1 or (g_ai_call_count < max_ai_calls):
            if (g_ai_only_for_seq_scan and seq_scan_indicator) or not g_ai_only_for_seq_scan:
                ai_hints = call_ai_for_plan_analysis(plan_lines, model, timeout)
                g_ai_call_count += 1
            else:
                logger.info("Skipping AI analysis for query without Seq Scan")
        else:
            logger.warning(f"AI call limit reached. Skipping AI analysis for query")
    else:
        logger.debug("Skipping AI analysis")

    report = {
        "title": title,
        "chatgpt_hints": ai_hints,
        "plan": execution_plan,
        "query_text": query,
        "query_timestamp": timestamp,
        "query_name": query_name,
        "job_name": parsed_result["job_name"],
        "code": query_code,
        "day": day,
        "seq_scan_indicator": seq_scan_indicator
    }

    return report


def main():
    args = parse_cli_arguments()

    global g_prompts, g_model_token_limit, g_model_temperature, g_skip_ai_analysis, g_calls, g_period, g_ai_only_for_seq_scan

    logger.info(f"Processing PostgreSQL log file {args.log_filename}")
    logger.info(f"Output report: {args.log_filename}_report.html")

    if args.skip_ai_analysis:
        logger.info("Skipping AI Analysis")
        g_skip_ai_analysis = True
    else:
        logger.info(f"Using model: {args.model}")
        logger.info(f"Maximum AI calls: {args.max_ai_calls if args.max_ai_calls != -1 else 'Unlimited'}")
        logger.info(f"AI API call timeout: {args.timeout} seconds")
        logger.info(f"Language: {args.lang}")
        logger.info(f"Model temperature : {args.temperature}")
        logger.info(f"AI Analysis only for Seq Scan queries : {args.ai_only_for_seq_scan}")

    g_calls, g_period = FREE_TIER_RATE_LIMITS.get(args.model, (10, 60))  # Default to 10 calls per minute if model not found

    load_prompts(args.lang)

    if not g_prompts:
        logger.error(f"Failed to load prompts for language: {args.lang}. Exiting.")
        exit(1)

    # API keys are now expected to be set as environment variables for LiteLLM
    # load_api_keys() is removed.

    # Get model input token limit from litellm, fallback to DEFAULT_TOKEN_LIMIT
    model_info = litellm.get_model_info(args.model)
    if model_info and 'max_input_tokens' in model_info and model_info['max_input_tokens'] is not None:
        g_model_token_limit = model_info['max_input_tokens']
        logger.info(f"Using input token limit for model {args.model}: {g_model_token_limit}")
    else:
        g_model_token_limit = DEFAULT_TOKEN_LIMIT
        logger.warning(f"Could not determine input token limit for model {args.model} from litellm. Falling back to default: {DEFAULT_TOKEN_LIMIT}")

    g_model_temperature = args.temperature
    g_ai_only_for_seq_scan = args.ai_only_for_seq_scan

    reports, days, query_occurrences, query_codes = process_log_file(
        args.log_filename, args.model, args.max_ai_calls, args.timeout
    )

    if not g_skip_ai_analysis:
        analysis = call_ai_for_final_analysis(reports, args.model, args.timeout)
    else:
        analysis = ""

    generate_html_report(f"{args.log_filename}_report.html", analysis, args.model, query_occurrences, days,
                         query_codes)

    logger.info(f"Total input tokens processed: {g_total_input_tokens}")
    logger.info(f"Total output tokens processed: {g_total_output_tokens}")
    logger.info(f"Estimated total cost: ${g_total_cost:.4f}")


if __name__ == "__main__":
    main()
