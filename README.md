# PostgreSQL Auto Explain AI Analysis Tool

This tool automates the analysis of PostgreSQL `auto_explain` log files using AI (OpenAI GPT or Google Gemini). It provides optimization recommendations and generates interactive HTML reports, helping DBAs and developers quickly identify and address performance bottlenecks.

## Features

*   **Automated Analysis:** Parses PostgreSQL `auto_explain` logs to extract query execution plans.
*   **AI-Powered Recommendations:** Leverages AI (GPT-4o, GPT-3.5 Turbo, Gemini) to provide context-aware optimization suggestions.
*   **Multi-Language Support:** Supports analysis and recommendations in multiple languages via customizable prompts.
*   **Query Fingerprinting:** Generates a unique hashcode for each query to facilitate tracking and comparison across multiple analyses.
*   **Interactive HTML Reports:** Creates comprehensive HTML reports with:
    *   Query execution plans visualized using `pev2`.
    *   AI-generated optimization recommendations with links to PostgreSQL documentation.
    *   Query occurrence statistics and performance metrics.
    *   Overall analysis summary highlighting common optimization opportunities.
*   **Token Limit Management:** Enforces token limits for different AI models to control costs.
*   **Flexible Configuration:** Allows customization of AI model, temperature, API keys, and prompts via command-line arguments and configuration files.

## Requirements

### Python Dependencies

```bash
pip install requests tiktoken google-generativeai asyncio logging hashlib collections argparse ratelimit
```

### API Keys

You need API keys for either:

*   **OpenAI GPT:** For `gpt-4o`, `gpt-3.5-turbo` models.
*   **Google Gemini:** For `gemini-2.0-flash-exp`, `gemini-1.5-flash`, and other Gemini models.

### PostgreSQL Configuration

Your PostgreSQL instance must be configured with `auto_explain` to generate execution plans in the log files. Ensure that the following settings are enabled and that the output is included in the logs:

```postgresql
auto_explain.log_min_duration = 0  -- Log all statements
auto_explain.log_analyze = true       -- Include EXPLAIN ANALYZE output
auto_explain.log_verbose = true       -- Include verbose EXPLAIN output
auto_explain.log_format = json       -- Use JSON format for EXPLAIN output
log_line_prefix = '%t [%p]: '          -- Include timestamp and process ID in log messages
```

These settings ensure that the necessary information for analysis is captured in the logs.

## Configuration Files

### prompts\_\*.txt

These files contain the prompts used for AI analysis. The tool uses different prompts for different stages of the analysis:

*   `PLAN_ANALYSIS`: The main prompt for analyzing individual execution plans and generating optimization recommendations.
*   `FINAL_ANALYSIS`: The prompt for summarizing the most frequent optimization opportunities across all analyzed queries.

You can customize these prompts to tailor the analysis to your specific needs. The tool supports multiple languages by using different prompt files (e.g., `prompts_en.txt`, `prompts_fr.txt`).

### api\_keys.txt

This file should contain your API keys for OpenAI and Google Gemini. The file should have the following structure:

```text
openai_key=your_openai_api_key_here
gemini_key=your_google_api_key_here
```

Replace `your_openai_api_key_here` and `your_google_api_key_here` with your actual API keys.

**Important:** Keep this file secure and do not share it publicly. Add it to your `.gitignore` file to prevent accidental commits.

## Usage

### Basic Usage

```bash
python pg-autoexplain-ai-analysis.py path/to/postgresql.log
```

This command analyzes the specified PostgreSQL log file using the default AI model (`gemini-2.0-flash-exp`) and generates an HTML report.

### Advanced Options

```bash
python pg-autoexplain-ai-analysis.py path/to/postgresql.log -m <MODEL_NAME> -c <MAX_AI_CALLS> -l <LANGUAGE> -t <TIMEOUT> -p <TEMPERATURE>
```

#### Parameters

*   `log_filename`: Path to the PostgreSQL log file containing execution plans.
*   `-m, --model`: AI model to use for analysis (default: `gemini-2.0-flash-exp`). Supported models:
    *   OpenAI: `gpt-4o`, `gpt-4o-mini`, `gpt-3.5-turbo`
    *   Gemini: `gemini-2.0-flash-exp`, `gemini-1.5-flash`, `gemini-1.5-pro`
*   `-c, --max-ai-calls`: Maximum number of AI API calls to make (default: `-1` for unlimited).
*   `-l, --lang`: Language for analysis and recommendations (default: `fr`).  Must have a corresponding `prompts_<lang>.txt` file.
*   `-t, --timeout`: Timeout in seconds for each AI API call (default: `90`).
*   `-p, --temperature`:  Model temperature, (default 0.5).
*   `--ai-only-for-seq-scan`:  Only call AI for queries with Seq Scan.

### Examples

1.  Analyze `postgresql.log` using the GPT-4o model, limiting the analysis to 10 AI calls:

    ```bash
    python pg-autoexplain-ai-analysis.py postgresql.log -m gpt-4o -c 10
    ```

2.  Analyze `postgresql.log` using the Gemini 1.5 Pro model with a timeout of 120 seconds and generate the report in English:

    ```bash
    python pg-autoexplain-ai-analysis.py postgresql.log -m gemini-1.5-pro -t 120 -l en
    ```

This will:

1.  Process execution plans from `postgresql.log`.
2.  Use the specified AI model for analysis.
3.  Limit the number of AI API calls.
4.  Generate an HTML report at `postgresql.log_report.html`.

## Output

The tool generates an HTML report (e.g., `postgresql.log_report.html`) containing the following sections:

*   **Individual Query Analysis:**
    *   Unique query hashcode for identification.
    *   Execution timestamp.
    *   Normalized query text.
    *   AI-generated optimization recommendations with links to relevant PostgreSQL documentation.
    *   Interactive execution plan visualization using `pev2`.
*   **Summary Section:**
    *   Query occurrence statistics (using hashcodes for unique identification).
    *   Most common optimization patterns identified across all analyzed queries.
    *   Overall recommendations for improving database performance.

The HTML report provides a user-friendly interface for exploring the analysis results and identifying actionable optimization opportunities.

## Notes

*   The tool expects log entries to contain both query text and execution plans in JSON format.
*   Ensure that the `prompts_*.txt` file for the specified language is available in the same directory as the script.
*   Token limits are enforced based on the selected model to prevent excessive API usage.
*   API keys should be properly configured before running the tool.
*   Each query is assigned a unique hashcode for identification and tracking across multiple executions.
*   Consider using a dedicated PostgreSQL user with limited privileges for running `auto_explain` to enhance security.
*   For large log files, consider increasing the AI call timeout to avoid errors.
*   Customize the prompts in `prompts_*.txt` to tailor the analysis to your specific environment and requirements.

