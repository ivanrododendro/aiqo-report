# PostgreSQL Auto Explain Log AI Analysis Tool

This tool analyzes PostgreSQL auto_explain log files using AI (OpenAI GPT or Google Gemini) to provide optimization recommendations and generate interactive HTML reports.

## Features

- Analyzes PostgreSQL execution plans from auto_explain logs
- Leverages AI (GPT-4/3.5 or Gemini) to provide optimization recommendations in different languages
- Generates a unique hashcode for each query for identification and tracking over multiple analysis
- Generates interactive HTML reports with:
    - Query execution plans visualization using pev2
    - AI-powered optimization suggestions
    - Query occurrence statistics
    - Overall analysis summary
- Supports token limit management for different AI models
- Handles multiple queries in a single log file
- Provides optimization recommendations


## Requirements

### Python Dependencies

```bash
pip install requests tiktoken google-generativeai asyncio logging hashlib collections argparse
```

### API Keys

You need to set up API keys for either:
- OpenAI GPT (for gpt-4, gpt-3.5-turbo models)
- Google Gemini (for gemini-2.0-flash-exp and other Gemini models)

### PostgreSQL Configuration

Your PostgreSQL instance must be configured with auto_explain to generate execution plans in the log files.
Settings must be logged in order for the script to identify the end of the plan.

## Configuration Files

### prompts_*.txt

Those file contain the prompts used for AI analysis. It should include the following prompts:

- `PLAN_ANALYSIS`: The main prompt for analyzing execution plans.
- `FINAL_ANALYSIS`: The prompt for the final analysis

Ensure that these prompts are properly defined in the file for accurate AI analysis.

### api_keys.txt

This file should contain your API keys for OpenAI and Google Gemini. The file should have the following structure:
- openai_key=your_openai_api_key_here
- gemini_key=your_google_api_key_here

Replace `your_openai_api_key_here` and `your_google_api_key_here` with your actual API keys.

**Important:** Keep this file secure and do not share it publicly. Add it to your .gitignore file to prevent accidental commits.

## Notes

- Ensure both `prompts.txt` and `api_keys.txt` are in the same directory as the script.
- The script will automatically read these files when executed.
- If you're using a specific AI model (OpenAI or Google Gemini), you only need to provide the corresponding API key.

## Usage

### Basic Usage

```bash
python analyze_pg_logs.py path/to/postgresql.log
```

### Advanced Options

```bash
python analyze_pg_logs.py path/to/postgresql.log -m MODEL_NAME -c MAX_AI_CALLS
```

#### Parameters

- `log_filename`: Path to the PostgreSQL log file containing execution plans
- `-m, --model`: AI model to use for analysis (default: gemini-2.0-flash-exp)
    - Supported models:
        - OpenAI: gpt-4o, gpt-4o-mini, gpt-3.5-turbo
        - Gemini: gemini-2.0-flash-exp, gemini-1.5-flash, gemini-1.5-pro
- `-c, --max-ai-calls`: Maximum number of AI API calls to make (default: -1 for unlimited)
- `-l, --lang` : Language, (default fr)

### Example

```bash
python analyze_pg_logs.py postgresql.log -m gpt-4o -c 10
```

This will:
1. Process the first 10 execution plans from postgresql.log
2. Use GPT-4o for analysis
3. Generate an HTML report at postgresql.log_report.html

## Output

The tool generates an HTML report containing:
- Individual query analysis with:
    - Unique query hashcode for identification
    - Execution timestamp
    - Query name/description
    - AI-generated optimization recommendations
    - Interactive execution plan visualization
- Summary section with:
    - Query occurrence statistics (using hashcodes for unique identification)
    - Most common optimization patterns
    - Overall recommendations

You can have the analysis in you own language by providing a custom prompt file. 

## Notes

- The tool expects log entries to contain both query text and execution plans
- AI analysis is provided in French
- Token limits are enforced based on the selected model
- API keys should be properly configured before running the tool
- Each query is assigned a unique hashcode for identification and tracking across multiple executions

