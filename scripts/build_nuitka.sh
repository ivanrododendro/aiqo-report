#!/usr/bin/env bash

set -euo pipefail

TARGET_OS=${1:-}

if [[ -z "${TARGET_OS}" ]]; then
  echo "Usage: $0 <linux|linux-centos6|macos-silicon|windows>" >&2
  exit 1
fi

if ! command -v poetry >/dev/null 2>&1; then
  echo "Poetry is required on the build machine." >&2
  exit 1
fi

export PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENTRY_POINT="src/aiqo_pg_ai_report/pg_autoexplain_analyzer.py"
OUTPUT_BASENAME="pg_aiqo_report"
TARGET_DIST_DIR="dist/${TARGET_OS}"

export PYTHONPATH="src:${PYTHONPATH:-}"
export NUITKA_CACHE_DIR="${NUITKA_CACHE_DIR:-${PROJECT_ROOT}/.nuitka-cache}"
export NUITKA_CACHE_DIR_CCACHE="${NUITKA_CACHE_DIR_CCACHE:-${NUITKA_CACHE_DIR}/ccache}"
mkdir -p "${NUITKA_CACHE_DIR_CCACHE}"

if command -v ccache >/dev/null 2>&1; then
  export NUITKA_CCACHE_BINARY="${NUITKA_CCACHE_BINARY:-$(command -v ccache)}"
  echo "Using ccache from ${NUITKA_CCACHE_BINARY}"
else
  echo "ccache not found in PATH; Nuitka will build without compiler cache."
fi


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
  "--standalone"
  "--include-package=aiqo_pg_ai_report"
  "--include-package=litellm"
  "--include-package-data=litellm"
  "--nofollow-import-to=pytest"
  "--no-deployment-flag=self-execution"
  "--include-data-file=${VERSION_FILE}=aiqo_pg_ai_report/_version_generated.txt"
  "--no-debug-c-warnings"
  "--include-data-dir=src/aiqo_pg_ai_report/prompts=prompts"
  "--include-data-dir=src/aiqo_pg_ai_report/report_templates=report_templates"
  "--output-dir=${TARGET_DIST_DIR}"
)

mkdir -p "$TARGET_DIST_DIR"

case "$TARGET_OS" in
  linux)
    poetry run python -m nuitka "${COMMON_ARGS[@]}" \
      --onefile \
      --output-filename="${OUTPUT_BASENAME}" "$ENTRY_POINT"
    ;;
  linux-centos6)
    if [[ "$(getconf GNU_LIBC_VERSION 2>/dev/null || true)" != "glibc 2.17" ]]; then
      echo "The linux-centos6 target must be built in the pinned manylinux2014 container." >&2
      echo "Run scripts/build_nuitka_centos6.sh instead." >&2
      exit 1
    fi

    poetry run python -m nuitka "${COMMON_ARGS[@]}" \
      --output-filename="${OUTPUT_BASENAME}.bin" "$ENTRY_POINT"
    bash scripts/package_centos6_runtime.sh "$TARGET_DIST_DIR" "${OUTPUT_BASENAME}.bin"
    ;;
  macos-silicon)
    poetry run python -m nuitka "${COMMON_ARGS[@]}" \
      --onefile \
      --macos-target-arch=arm64 \
      --output-filename="${OUTPUT_BASENAME}" "$ENTRY_POINT"
    ;;
  windows)
    poetry run python -m nuitka "${COMMON_ARGS[@]}" \
      --onefile \
      --assume-yes-for-downloads \
      --output-filename="${OUTPUT_BASENAME}.exe" "$ENTRY_POINT"
    ;;
  *)
    echo "Unsupported target: $TARGET_OS (use linux, linux-centos6, macos-silicon, or windows)" >&2
    exit 1
    ;;
esac

cat <<INFO

Build complete for $TARGET_OS. Check ${TARGET_DIST_DIR}/ for the generated binary.
INFO
