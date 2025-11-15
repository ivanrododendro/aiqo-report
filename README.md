# AIQO PostgreSQL AI Report Generator

The AIQO PostgreSQL AI Report Generator is a powerful command-line tool designed to analyze PostgreSQL `auto_explain` logs using Artificial Intelligence. It provides actionable insights and optimization suggestions to improve database performance, presenting its findings in a comprehensive HTML report.

## Features

*   **AI-Powered Analysis**: Leverages large language models (LLMs) to analyze `EXPLAIN` plans from PostgreSQL logs and identify performance bottlenecks.
*   **Optimization Suggestions**: Provides concrete recommendations for query, server, and infrastructure optimizations based on AI analysis.
*   **Comprehensive HTML Reports**: Generates detailed, easy-to-read HTML reports summarizing performance metrics, AI findings, and optimization opportunities.
*   **Customizable AI Models**: Supports various AI providers and models (e.g., GPT-4o, Gemini 1.5 Flash, O1) via `litellm`.
*   **Flexible Contextualization**: Allows users to provide DDL, server configuration, infrastructure details, and custom prompts to enhance AI analysis accuracy.
*   **Targeted Analysis**: Option to focus AI analysis specifically on queries performing sequential scans.
*   **Query Code Tracking**: Generates a unique "query code" (hash) for each normalized SQL query, enabling consistent tracking and application of query-specific optimizations across different log executions.
*   **Query Filtering**: Filter log entries based on specific strings to analyze only relevant queries.
*   **Multilingual Output**: Supports generating reports in different languages.
*   **Reproducible Outputs**: When using ChatGPT models, analyses can be reproduced by providing the same input and context, ensuring consistent results across runs.

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

> **_NOTE:_** when auto_explain.log_timing parameter is on, per-plan-node timing occurs for all statements executed, whether or not they run long enough to actually get logged. This can have an extremely negative impact on performance. Turning off auto_explain.log_timing ameliorates the performance cost, at the price of obtaining less information. See https://www.postgresql.org/docs/current/auto-explain.html

After modifying `postgresql.conf`, restart your PostgreSQL server for the changes to take effect. The tool expects standard text-based PostgreSQL log files.

## Context Files & Location

The tool can be provided with additional context to enhance the AI's understanding and the relevance of its suggestions. Contexts are loaded in a specific order: if a custom `--context-folder` is specified, the tool will first look for context files within that folder. If a file is not found in the custom folder, or if no custom folder is provided, the tool will fall back to its internal default contexts (where applicable).

The available context types include:

*   **AI Instruction Prompts**: These define the AI's behavior and desired output format.
    *   **Default Locations**: `SYSTEM.txt`, `FORMAT.txt`, and `target-query-prompts.txt` have default implementations located in `src/aiqo_pg_ai_report/prompts/`.
    *   `SYSTEM.txt`: Defines the AI's persona and general instructions.
    *   `FORMAT.txt`: Specifies the desired output format for the AI's analysis.
    *   `target-query-prompts.txt`: Contains specific prompts for analyzing individual queries.

*   **Additional Contexts (User-Provided)**: For the following contexts, the tool *does not provide default files*. They must be supplied by the user within a custom `--context-folder` to be active.
    *   `DDL Context` (`DDL.txt`): Database schema definitions.
    *   `Server Configuration Context` (`CONFIG.txt`): Details about your PostgreSQL server settings.
    *   `Infrastructure Context` (`INFRA.txt`): Information about the underlying hardware and environment.
    *   `Server Optimizations` (`SERVER.txt`): General server-level optimization rules.
    *   `Event Optimizations` (`EVENTS.txt`): Optimizations related to specific database events.
    *   `Query Optimizations` (`QUERIES/<query_code_prefix>.txt`): Specific query-level optimization rules, where `<query_code_prefix>` refers to the first 6 characters of the query code (normalized query hash). These files provide context for optimizations that have already been applied to a particular query.

To use custom contexts, create a folder (e.g., `my_custom_contexts/`) and place your context files within it according to the following structure:

```
my_custom_contexts/
├── DDL.txt
├── CONFIG.txt
├── INFRA.txt
├── SERVER.txt
├── EVENTS.txt
└── QUERIES/
    ├── <query_code_prefix_1>.txt
    ├── <query_code_prefix_2>.txt
    └── ...
```

To specify your custom context folder, use the `--context-folder` argument. For example:

```bash
poetry run python src/aiqo_pg_ai_report/pg_autoexplain_analyzer.py \
    --context-folder "./my_custom_contexts" \
    /path/to/your/postgresql.log
```

## Usage

Navigate to the project's root directory.

### Basic Usage

To analyze a PostgreSQL log file with default settings:

```bash
poetry run python src/aiqo_pg_ai_report/pg_autoexplain_analyzer.py /path/to/your/postgresql.log
```

This will generate an HTML report in the current working directory (or `output/` if it exists), named similarly to `pg-ai-report_<timestamp>.html`.

## Building Standalone Executables with Nuitka

To distribute the analyzer as a single binary per platform without requiring a system-wide Python installation, we rely on [Nuitka](https://nuitka.net/). Install dev dependencies (which now include Nuitka) and run the platform-specific build on the corresponding operating system:

```bash
poetry install --with dev
./scripts/build_nuitka.sh <linux|macos-silicon|windows>
```

The script wraps the Nuitka invocation, bundles the prompt/template assets, and writes binaries to `dist/`. **Run the script on the same OS you are targeting** (e.g., run it on Windows to produce `pg_autoexplain.exe`).

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

*   **`--model <MODEL>`** (`-m`):
    *   Specify the AI model to use for analysis (e.g., `gpt-4o`, `gemini-1.5-pro`, `o1-mini`).
    *   Default: `gemini-2.5-flash`

*   **`--limit-ai-calls <NUMBER>`** (`-l`):
    *   Limits the maximum number of AI calls made during the analysis. Use `-1` for unlimited calls.
    *   Default: `-1` (unlimited)

*   **`--ai-call-timeout <SECONDS>`**:
    *   Sets the timeout duration for each individual AI call in seconds.
    *   Default: `90` seconds

*   **`--language <LANG>`**:
    *   Set the output language for the generated report and AI analysis.
    *   Default: `fr` (French)
    *   Example: `--language en` for English output.

*   **`--skip-ai-analysis`** (`-s`):
    *   If set, the AI analysis step will be skipped entirely. A report will still be generated, but without AI-driven insights.
    *   This is a flag, no value needed.
    *   Default: `False`

*   **`--only-seq-scan-ai-analysis`** (`-o`):
    *   If set, the AI analysis will only be performed on queries that are identified as performing sequential scans. This helps focus the AI's efforts on specific performance issues.
    *   This is a flag, no value needed.
    *   Default: `False`

*   **`--filter <STRING>`** (`-f`):
    *   Filter log entries. Only log entries containing the specified string in the query name, job name, SQL text, or query code will be processed for AI analysis. All queries will still be included in the report. Can be specified multiple times. Case-sensitive.
    *   Example: `--filter "public.users"` or `--filter "2a3b4c"` (to filter by a query code)
    *   Default: `None` (no filter)

*   **`--custom-prompt <PROMPT>`** (`-c`):
    *   Provide an additional custom prompt or instruction to the AI for its analysis. This prompt will be appended to the standard prompts.
    *   Example: `--custom-prompt "Pay special attention to JOIN operations."`
    *   Default: `None`

*   **`--report-filename <PATH>`** (`-r`):
    *   Override the HTML report filename.
    *   Example: `--report-filename my_custom_report.html`
    *   Default: Automatically generated based on log filename

*   **`--target-query-mode`**:
    *   Enables target query mode for analysis.
    *   This is a flag, no value needed.
    *   Default: `False`

*   **`--context-folder <PATH>`** (`-cf`):
    *   Path to a directory containing context files (DDL, server config, optimizations, custom prompts).
    *   Example: `--context-folder /home/user/my_db_contexts`
    *   Default: A CONTEXT folder in the same directory containing the file being analyzed

*   **`--debug`** (`-d`):
    *   Enable debug logging.
    *   This is a flag, no value needed.
    *   Default: `False`

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
