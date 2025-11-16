#!/usr/bin/env bash

set -euo pipefail

TARGET_OS=${1:-}

if [[ -z "${TARGET_OS}" ]]; then
  echo "Usage: $0 <linux|macos-silicon|windows>" >&2
  exit 1
fi

if ! command -v poetry >/dev/null 2>&1; then
  echo "Poetry is required on the build machine." >&2
  exit 1
fi

ENTRY_POINT="src/aiqo_pg_ai_report/pg_autoexplain_analyzer.py"

export PYTHONPATH="src:${PYTHONPATH:-}"

COMMON_ARGS=(
  "--onefile"
  "--standalone"
  "--include-package=aiqo_pg_ai_report"
  "--include-module=litellm"
  "--no-debug-c-warnings"
  "--include-data-dir=src/aiqo_pg_ai_report/prompts=prompts"
  "--include-data-dir=src/aiqo_pg_ai_report/report_templates=report_templates"
  "--output-dir=dist"
)

mkdir -p dist

case "$TARGET_OS" in
  linux)
    poetry run python -m nuitka "${COMMON_ARGS[@]}" \
      --output-filename=aiqo-report-linux "$ENTRY_POINT"
    ;;
  macos-silicon)
    poetry run python -m nuitka "${COMMON_ARGS[@]}" \
      --macos-target-arch=arm64 \
      --output-filename=aiqo-report-macos-arm64 "$ENTRY_POINT"
    ;;
  windows)
    poetry run python -m nuitka "${COMMON_ARGS[@]}" \
      --output-filename=aiqo-report.exe "$ENTRY_POINT"
    ;;
  *)
    echo "Unsupported target: $TARGET_OS (use linux, macos-silicon, or windows)" >&2
    exit 1
    ;;
esac

cat <<INFO

Build complete for $TARGET_OS. Check the dist/ directory for the generated binary.
INFO
