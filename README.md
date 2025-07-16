# PostgreSQL Auto Explain AI Analysis Tool

This tool automates the analysis of PostgreSQL `auto_explain` log files using AI (OpenAI GPT or Google Gemini). It provides optimization recommendations and generates interactive HTML reports, helping DBAs and developers quickly identify and address performance bottlenecks.

## Features

*   **Automated Analysis:** Parses PostgreSQL `auto_explain` logs to extract query execution plans.
*   **AI-Powered Recommendations:** Uses [LiteLLM](https://github.com/BerriAI/litellm) to access multiple AI providers (OpenAI, Google Gemini, Claude, etc.) for context-aware optimization suggestions.
*   **Multi-Language Support:** Supports analysis and recommendations in multiple languages via customizable prompts.
*   **Query Fingerprinting:** Generates a unique hashcode for each query to facilitate tracking and comparison across multiple analyses.
*   **Interactive HTML Reports:** Creates comprehensive HTML reports with:
    *   Query execution plans visualized using `pev2`.
    *   AI-generated optimization recommendations with links to PostgreSQL documentation.
    *   Query occurrence statistics and performance metrics.
    *   Overall analysis summary highlighting common optimization opportunities.
*   **Token Limit Management:** Enforces token limits for different AI models to control costs.
*   **Flexible Configuration:** Allows customization of AI model, temperature, prompts, and more via command-line arguments and configuration files.
*   **Directory Mode:** Analyze all `.log` and `.zip` files in a directory in a single run.
*   **Advanced Filtering:** Restrict AI analysis to queries matching specific patterns or containing sequential scans.

## Requirements

### Python Dependencies

This tool requires Python 3.8+ and the following dependencies:

```bash
pip install litellm sqlparse ratelimit
```

Other dependencies (such as requests, tiktoken, etc.) are handled by LiteLLM as needed.

### API Keys and LiteLLM Configuration

This tool uses [LiteLLM](https://github.com/BerriAI/litellm) to access AI models. You must set your API keys as environment variables according to the LiteLLM documentation. For example:

```bash
export OPENAI_API_KEY=your_openai_api_key
export GOOGLE_API_KEY=your_google_api_key
```

You can also use a `.env` file or other configuration methods supported by LiteLLM. See [LiteLLM docs](https://docs.litellm.ai/docs/providers/) for details.

**Important:** Do not commit your API keys to version control.

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
python pg-autoexplain-ai-analysis.py path/to/postgresql.log [options]
```

#### Key Parameters

*   `log_filename`: Path to the PostgreSQL log file (or directory if using `--directory-mode`).
*   `-m, --model`: AI model to use for analysis (default: `gemini-2.0-flash-exp`). Supported models depend on your LiteLLM configuration (e.g., `gpt-4o`, `gpt-3.5-turbo`, `gemini-1.5-pro`, etc.).
*   `-l, --limit-ai-calls`: Maximum number of AI calls to make. Use `-1` for unlimited (default: `-1`).
*   `--ai-call-timeout`: Timeout for AI API calls in seconds (default: `90`).
*   `--language`: Language for prompts and output (default: `fr`). Must have a corresponding `prompts_<lang>.txt` file.
*   `-s, --skip_ai_analysis`: Skip AI analysis and only generate the HTML report.
*   `-o, --only-seq-scan-ai-analysis`: Only perform AI analysis for queries with Seq Scan.
*   `-f, --filter`: Restrict AI analysis to queries containing the specified string (can be used multiple times).
*   `-c, --custom-prompt`: Add a custom prompt to the default AI prompt.
*   `--sql-context-file`: Add the content of a DDL SQL file to the prompt.
*   `-r, --report-filename`: Override the HTML report filename.
*   `-d, --directory-mode`: Process all `.log` and `.zip` files in the specified directory.

### Examples

1.  Analyze `postgresql.log` using the GPT-4o model, limiting the analysis to 10 AI calls:

    ```bash
    python pg-autoexplain-ai-analysis.py postgresql.log -m gpt-4o -l 10
    ```

2.  Analyze all `.log` and `.zip` files in a directory, using Gemini 1.5 Pro, with a timeout of 120 seconds and generate the report in English:

    ```bash
    python pg-autoexplain-ai-analysis.py /path/to/logs/dir -d -m gemini-1.5-pro --ai-call-timeout 120 --language en
    ```

3.  Analyze only queries containing "Seq Scan" and skip AI analysis for others:

    ```bash
    python pg-autoexplain-ai-analysis.py postgresql.log --only-seq-scan-ai-analysis
    ```

4.  Add a custom prompt and DDL context to the AI analysis:

    ```bash
    python pg-autoexplain-ai-analysis.py postgresql.log -c "Focus on index usage" --sql-context-file schema.sql
    ```

This will:

1.  Process execution plans from the specified log file(s).
2.  Use the selected AI model for analysis.
3.  Limit the number of AI API calls if specified.
4.  Generate an HTML report (e.g., `postgresql.log_report.html`).

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

