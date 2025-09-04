# AIQO PostgreSQL AI Report Generator

The AIQO PostgreSQL AI Report Generator is a powerful command-line tool designed to analyze PostgreSQL `auto_explain` logs using Artificial Intelligence. It provides actionable insights and optimization suggestions to improve database performance, presenting its findings in a comprehensive HTML report.

## Features

*   **AI-Powered Analysis**: Leverages large language models (LLMs) to analyze `EXPLAIN` plans from PostgreSQL logs and identify performance bottlenecks.
*   **Optimization Suggestions**: Provides concrete recommendations for query, server, and infrastructure optimizations based on AI analysis.
*   **Comprehensive HTML Reports**: Generates detailed, easy-to-read HTML reports summarizing performance metrics, AI findings, and optimization opportunities.
*   **Customizable AI Models**: Supports various AI providers and models (e.g., GPT-4o, Gemini 1.5 Flash, O1) via `litellm`.
*   **Flexible Contextualization**: Allows users to provide DDL, server configuration, infrastructure details, and custom prompts to enhance AI analysis accuracy.
*   **Targeted Analysis**: Option to focus AI analysis specifically on queries performing sequential scans.
*   **Query Filtering**: Filter log entries based on specific strings to analyze only relevant queries.
*   **Multilingual Output**: Supports generating reports in different languages.

## Dependencies & Requirements

*   Python 3.8+
*   The project uses `poetry` for dependency management.
*   Key Python packages: `litellm`, `sqlparse`, `Jinja2`.

To install the required dependencies, navigate to the project root and run:

```bash
poetry install
```

## API Keys and LiteLLM Configuration

This tool uses `litellm` to interface with various AI providers. You must configure your API keys as environment variables.

For example, for OpenAI models:

```bash
set OPENAI_API_KEY="your_openai_api_key_here"
```

For Gemini models:

```bash
set GEMINI_API_KEY="your_gemini_api_key_here"
```

You can also use a generic `LITELLM_API_KEY` if you are using a provider that `litellm` supports via this generic key. Refer to the [LiteLLM documentation](https://litellm.ai/docs/providers) for specific provider configurations.

**Default Models**:
The default model is `gemini-2.5-flash`. You can specify a different model using the `--model` CLI argument.

## PostgreSQL Configuration

To generate the necessary log files for analysis, your PostgreSQL instance must be configured to use `auto_explain`. Here's a typical configuration to add to your `postgresql.conf`:

```ini
# auto_explain settings
shared_preload_libraries = 'auto_explain'
auto_explain.log_min_duration = 0 # Log all queries, or set a threshold like 250ms
auto_explain.log_analyze = on # Include EXPLAIN ANALYZE output
auto_explain.log_buffers = on # Include buffer usage
auto_explain.log_timing = on # Include timing information
auto_explain.log_nested_pages = on # For nested queries
auto_explain.log_verbose = on # For verbose output
auto_explain.log_format = text # Or json, but the tool expects text for now
log_destination = 'stderr' # Or 'csvlog' if preferred
logging_collector = on
log_directory = 'pg_log' # Directory for log files
log_filename = 'postgresql-%Y-%m-%d_%H%M%S.log' # Log file naming convention
```

After modifying `postgresql.conf`, restart your PostgreSQL server for the changes to take effect. The tool expects standard text-based PostgreSQL log files.

## Context Files & Location

The tool can be provided with additional context to enhance the AI's understanding and the relevance of its suggestions. These contexts include:

*   **AI Instruction Prompts**: Default system and format prompts are located in `src/aiqo_pg_ai_report/prompts/`.
    *   `SYSTEM.txt`: Defines the AI's persona and general instructions.
    *   `FORMAT.txt`: Specifies the desired output format for the AI's analysis.
    *   `target-query-prompts.txt`: Contains specific prompts for analyzing individual queries.
*   **Optimization Contexts**:
    *   `DDL Context`: Database schema definitions.
    *   `Server Configuration Context`: Details about your PostgreSQL server settings.
    *   `Infrastructure Context`: Information about the underlying hardware and environment.
    *   `Server Optimizations`: General server-level optimization rules.
    *   `Event Optimizations`: Optimizations related to specific database events.
    *   `Query Optimizations`: Specific query-level optimization rules.

You can create a custom context folder containing these files. The tool will then load these custom files, overriding the defaults if present.

Example structure for a custom context folder (`my_custom_contexts/`):

```
my_custom_contexts/
├── ddl_context.sql
├── infra_context.txt
├── server_configuration.txt
├── optimizations/
│   ├── server_optimizations.txt
│   ├── event_optimizations.txt
│   └── query_optimizations.txt
└── prompts/
    ├── SYSTEM.txt
    ├── FORMAT.txt
    └── target-query-prompts.txt
```

To use a custom context folder, specify its path with the `--context-folder` argument.

## Usage

Navigate to the project's root directory.

### Basic Usage

To analyze a PostgreSQL log file with default settings:

```bash
poetry run python src/aiqo_pg_ai_report/pg_autoexplain_analyzer.py /path/to/your/postgresql.log
```

This will generate an HTML report in the current working directory (or `output/` if it exists), named similarly to `pg-ai-report_<timestamp>.html`.

### Advanced Usage

You can customize the analysis using various command-line arguments:

```bash
poetry run python src/aiqo_pg_ai_report/pg_autoexplain_analyzer.py \
    --model "gpt-4o-mini" \
    --language "en" \
    --context-folder "./my_custom_contexts" \
    --custom-prompt "Focus on index usage." \
    --only-seq-scan-ai-analysis \
    --filter "SELECT * FROM users" \
    --limit-ai-calls 5 \
    --ai-call-timeout 120 \
    /path/to/your/postgresql.log
```

### Full CLI Parameters Explanation

*   **`log_file_path`** (positional argument):
    *   The full path to the PostgreSQL `auto_explain` log file to be analyzed.
    *   Example: `/var/log/postgresql/postgresql-2023-01-01.log`

*   **`--model <MODEL>`**:
    *   Specify the AI model to use for analysis (e.g., `gpt-4o`, `gemini-1.5-pro`, `o1-mini`).
    *   Default: `gemini-2.5-flash`

*   **`--language <LANG>`**:
    *   Set the output language for the generated report and AI analysis.
    *   Default: `fr` (French)
    *   Example: `--language en` for English output.

*   **`--context-folder <PATH>`**:
    *   Specify a custom directory containing context files (DDL, server config, optimizations, custom prompts).
    *   Example: `--context-folder /home/user/my_db_contexts`

*   **`--custom-prompt <PROMPT>`**:
    *   Provide an additional custom prompt or instruction to the AI for its analysis. This prompt will be appended to the standard prompts.
    *   Example: `--custom-prompt "Pay special attention to JOIN operations."`

*   **`--only-seq-scan-ai-analysis`**:
    *   If set, the AI analysis will only be performed on queries that are identified as performing sequential scans. This helps focus the AI's efforts on specific performance issues.
    *   This is a flag, no value needed.

*   **`--filter <STRING>`**:
    *   Filter log entries. Only log entries containing the specified string will be processed. Case-sensitive.
    *   Example: `--filter "public.users"`

*   **`--skip-ai-analysis`**:
    *   If set, the AI analysis step will be skipped entirely. A report will still be generated, but without AI-driven insights.
    *   This is a flag, no value needed.

*   **`--limit-ai-calls <NUMBER>`**:
    *   Limits the maximum number of AI calls made during the analysis. Use `-1` for unlimited calls.
    *   Default: `-1` (unlimited)

*   **`--ai-call-timeout <SECONDS>`**:
    *   Sets the timeout duration for each individual AI call in seconds.
    *   Default: `90` seconds

## Output Report

The tool generates a single, self-contained HTML report. This report typically includes:

*   **Summary Dashboard**: Overview of analyzed queries, AI calls, and total costs.
*   **Daily Statistics**: Breakdown of query activity and AI analysis per day.
*   **Query Statistics**: Aggregated information about normalized queries, including frequency and average execution times.
*   **Detailed Query Analysis**: For each significant query (especially those identified with issues like sequential scans or based on AI analysis), a dedicated section will provide:
    *   The original SQL query.
    *   The `EXPLAIN ANALYZE` plan.
    *   The AI's summary of the plan's performance characteristics.
    *   AI-generated optimization recommendations specific to that query.
*   **General Optimization Suggestions**: Broader recommendations based on the overall log analysis and pre-defined optimization contexts (if provided).

The report is designed to be easily shareable and provides a clear path to understanding and addressing PostgreSQL performance issues.
