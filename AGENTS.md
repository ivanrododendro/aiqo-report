# Repository Guidelines

## Project Structure & Module Organization
The CLI lives in `src/aiqo_pg_ai_report`, with `pg_autoexplain_analyzer.py` orchestrating log parsing, AI calls, and report generation. Supporting modules such as `log_parser.py`, `report_data_processor.py`, and `report_generator.py` sit alongside prompt assets in `prompts/` and HTML templates in `report_templates/`. Pytest suites reside in `tests/`, while Sphinx docs and template references are in `docs/`.

## Build, Test, and Development Commands
- `poetry install` — create the virtualenv and install all project and dev dependencies.
- `poetry run python src/aiqo_pg_ai_report/pg_autoexplain_analyzer.py /path/to/log` — run the analyzer to produce an HTML report (writes to `output/` if present).
- `poetry run pytest` — execute the Python unit tests.
- `poetry run black src tests` / `poetry run flake8 src tests` / `poetry run mypy src` — format, lint, and type-check the codebase.
- `poetry run sphinx-build docs docs/_build/html` — build the contributor documentation locally.

## Coding Style & Naming Conventions
Favor Python 3.8+ syntax with type hints; mypy runs in strict mode, so keep signatures and return types explicit. Adopt Black defaults (120-character lines) and respect the ignored rules in `.flake8`. Use snake_case for modules, functions, and variables, PascalCase for classes, and keep filenames descriptive (`report_data_processor.py`, `test_log_parser.py`). Template and prompt assets should mirror their runtime usage names.

## Testing Guidelines
Place new tests under `tests/` using the `test_*.py` pattern, grouping helpers via fixtures when needed. Exercise both successful parsing paths and failure branches (e.g., malformed log lines). Run `poetry run pytest -k <name>` for focused suites. When introducing AI-facing logic, mock `litellm` integrations to keep tests offline and deterministic.

## Commit & Pull Request Guidelines
Follow the existing Conventional Commit style (`feat:`, `fix:`, `chore:`, etc.) found in `git log`. Keep messages imperative and scoped to a single concern. Pull requests should describe the change, note any new CLI flags or prompts, and include before/after snippets or screenshots for report output modifications. Link relevant issues and call out manual steps (e.g., regenerating docs) so reviewers can verify easily.

## AI Provider Configuration
Document any required environment variables in the PR when they change. Typical local runs need keys such as `OPENAI_API_KEY`, `GEMINI_API_KEY`, or `LITELLM_API_KEY`. Prefer `.env` or shell exports outside the repo, and mention rate-limit considerations if a change increases AI call volume.
