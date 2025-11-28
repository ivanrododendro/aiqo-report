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

export PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENTRY_POINT="src/aiqo_pg_ai_report/pg_autoexplain_analyzer.py"

export PYTHONPATH="src:${PYTHONPATH:-}"

# Precompute version for frozen builds to avoid setuptools_scm at runtime
export VERSION_FILE="$PROJECT_ROOT/src/aiqo_pg_ai_report/_version_generated.txt"
poetry run python - <<'PY'
import os
from importlib import import_module
from pathlib import Path

project_root = Path(os.environ["PROJECT_ROOT"])
version_file = Path(os.environ["VERSION_FILE"])

try:
    scm = import_module("setuptools_scm")
    version = scm.get_version(root=project_root, fallback_version="0.0.0")
except Exception as exc:  # noqa: BLE001
    print(f"Warning: could not compute version via setuptools_scm: {exc}")
    version = "0.0.0"

version_file.write_text(version, encoding="utf-8")
print(f"Wrote embedded version {version} to {version_file}")
PY

COMMON_ARGS=(
  "--onefile"
  "--standalone"
  "--include-package=aiqo_pg_ai_report"
  "--include-package=litellm"
  "--include-package-data=litellm"
  "--include-data-file=${VERSION_FILE}=aiqo_pg_ai_report/_version_generated.txt"
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
      --assume-yes-for-downloads \
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
