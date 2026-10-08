#!/usr/bin/env bash

set -euo pipefail

PACKAGE_DIR=${1:?Package directory is required}
LOADER="$PACKAGE_DIR/app/ld-linux-x86-64.so.2"
EXECUTABLE="$PACKAGE_DIR/app/pg_aiqo_report.bin"

for required_path in "$PACKAGE_DIR/pg_aiqo_report" "$LOADER" "$EXECUTABLE" "$PACKAGE_DIR/runtime/libc.so.6"; do
  if [[ ! -e "$required_path" ]]; then
    echo "Missing required bundle file: $required_path" >&2
    exit 1
  fi
done

if "$LOADER" --list "$EXECUTABLE" 2>&1 | grep -q 'not found'; then
  echo "The CentOS 6 bundle contains unresolved shared libraries." >&2
  "$LOADER" --list "$EXECUTABLE" >&2
  exit 1
fi

while IFS= read -r elf_file; do
  if ldd "$elf_file" 2>&1 | grep -q 'not found'; then
    echo "Unresolved dependency in $elf_file:" >&2
    ldd "$elf_file" >&2
    exit 1
  fi
done < <(find "$PACKAGE_DIR/app" "$PACKAGE_DIR/runtime" -type f -exec file {} + | awk -F: '/ELF/{print $1}')

MAX_GLIBC_VERSION="$(
  find "$PACKAGE_DIR/app" -type f -exec readelf --version-info {} + 2>/dev/null \
    | grep -oE 'GLIBC_[0-9]+\.[0-9]+' \
    | sort -V \
    | tail -n 1 \
    || true
)"
if [[ -n "$MAX_GLIBC_VERSION" ]] && [[ "$(printf '%s\n' "$MAX_GLIBC_VERSION" GLIBC_2.17 | sort -V | tail -n 1)" != "GLIBC_2.17" ]]; then
  echo "Application requires $MAX_GLIBC_VERSION, which exceeds the bundled GLIBC_2.17 baseline." >&2
  exit 1
fi

echo "CentOS 6 runtime bundle verified (maximum application requirement: ${MAX_GLIBC_VERSION:-none})."
