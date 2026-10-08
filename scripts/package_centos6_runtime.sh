#!/usr/bin/env bash

set -euo pipefail

TARGET_DIST_DIR=${1:?Target distribution directory is required}
EXECUTABLE_NAME=${2:?Executable name is required}
PACKAGE_NAME="pg_aiqo_report-centos6.bundle"
PACKAGE_DIR="$TARGET_DIST_DIR/$PACKAGE_NAME"
APP_DIR="$PACKAGE_DIR/app"
RUNTIME_DIR="$PACKAGE_DIR/runtime"

STANDALONE_DIR="$(find "$TARGET_DIST_DIR" -maxdepth 2 -type f -name "$EXECUTABLE_NAME" -printf '%h\n' -quit)"
if [[ -z "$STANDALONE_DIR" ]]; then
  echo "Cannot find Nuitka standalone executable $EXECUTABLE_NAME in $TARGET_DIST_DIR." >&2
  exit 1
fi

rm -rf "$PACKAGE_DIR"
mkdir -p "$APP_DIR" "$RUNTIME_DIR"
echo "Copying Nuitka standalone directory: $STANDALONE_DIR"
cp -a "$STANDALONE_DIR/." "$APP_DIR/"

copy_dependency() {
  local source_path=$1
  local destination="$RUNTIME_DIR/$(basename "$source_path")"

  if [[ "$source_path" == "$PACKAGE_DIR"/* || -e "$destination" ]]; then
    return
  fi

  cp -L "$source_path" "$destination"
}

# Collect the dependency closure for every ELF shipped by Nuitka.
for _ in 1 2 3; do
  while IFS= read -r elf_file; do
    while IFS= read -r dependency; do
      [[ -n "$dependency" ]] && copy_dependency "$dependency"
    done < <(
      ldd "$elf_file" 2>/dev/null \
        | sed -n -E 's@^[[:space:]]*[^[:space:]]+[[:space:]]+=>[[:space:]]+(/[^[:space:]]+).*$@\1@p; s@^[[:space:]]*(/[^[:space:]]+)[[:space:]]+\(.*$@\1@p'
    )
  done < <(find "$APP_DIR" "$RUNTIME_DIR" -type f -exec file {} + | awk -F: '/ELF/{print $1}')
done

# NSS modules are loaded dynamically and therefore do not appear in ldd output.
for nss_name in libnss_files.so.2 libnss_dns.so.2 libnss_compat.so.2; do
  nss_library="$(ldconfig -p | awk -v name="$nss_name" '$1 == name && !found { print $NF; found = 1 }')"
  [[ -n "$nss_library" && -e "$nss_library" ]] && copy_dependency "$nss_library"
done

# Complete the dependency closure of the dynamically loaded NSS modules.
while IFS= read -r nss_file; do
  while IFS= read -r dependency; do
    [[ -n "$dependency" ]] && copy_dependency "$dependency"
  done < <(
    ldd "$nss_file" 2>/dev/null \
      | sed -n -E 's@^[[:space:]]*[^[:space:]]+[[:space:]]+=>[[:space:]]+(/[^[:space:]]+).*$@\1@p; s@^[[:space:]]*(/[^[:space:]]+)[[:space:]]+\(.*$@\1@p'
  )
done < <(find "$RUNTIME_DIR" -type f -name 'libnss_*.so.2')

LOADER_PATH="$(find /lib64 /usr/lib64 /lib /usr/lib -maxdepth 1 -name 'ld-linux-x86-64.so.2' -print -quit)"
if [[ -z "$LOADER_PATH" ]]; then
  echo "Cannot find the glibc dynamic loader." >&2
  exit 1
fi
# Nuitka resolves its standalone files relative to the invoked ELF loader.
# Keep that loader beside the application binary and extension modules.
cp -L "$LOADER_PATH" "$APP_DIR/ld-linux-x86-64.so.2"

cat > "$PACKAGE_DIR/pg_aiqo_report" <<'LAUNCHER'
#!/bin/sh
set -eu

APP_HOME=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
LIBRARY_PATH="$APP_HOME/runtime:$APP_HOME/app"

exec "$APP_HOME/app/ld-linux-x86-64.so.2" \
  --library-path "$LIBRARY_PATH" \
  "$APP_HOME/app/pg_aiqo_report.bin" "$@"
LAUNCHER
chmod 0755 "$PACKAGE_DIR/pg_aiqo_report"

cat > "$PACKAGE_DIR/THIRD_PARTY_NOTICES.txt" <<'NOTICES'
This distribution includes GNU C Library runtime components from the
manylinux2014 build environment. GNU libc is licensed under the GNU Lesser
General Public License, version 2.1 or later. Corresponding source and license
information are available from https://www.gnu.org/software/libc/ and the
CentOS 7 source package repositories.
NOTICES

GLIBC_LICENSE="$(find /usr/share/licenses -path '*glibc*' -name 'COPYING.LIB' -print -quit 2>/dev/null || true)"
[[ -n "$GLIBC_LICENSE" ]] && cp "$GLIBC_LICENSE" "$PACKAGE_DIR/COPYING.LIB"
rpm -q glibc > "$PACKAGE_DIR/GLIBC_VERSION.txt"

bash scripts/verify_centos6_bundle.sh "$PACKAGE_DIR"
# The app needs the bundled glibc loader on CentOS 6. Keep the verified
# standalone bundle inside a single self-extracting executable.
PAYLOAD="$TARGET_DIST_DIR/.pg_aiqo_report-centos6-payload.tar.gz"
ONEFILE="$TARGET_DIST_DIR/pg_aiqo_report-centos6"
ARCHIVE="$TARGET_DIST_DIR/pg_aiqo_report-linux-centos6-x86_64.tar.gz"
tar -czf "$PAYLOAD" -C "$TARGET_DIST_DIR" "$PACKAGE_NAME"

cat > "$ONEFILE" <<'ONEFILE_LAUNCHER'
#!/bin/sh
set -eu

work_dir=$(mktemp -d "${TMPDIR:-/tmp}/pg_aiqo_report.XXXXXXXX")
child=
cleanup() { rm -rf "$work_dir"; }
forward_signal() {
  if [ -n "$child" ]; then
    kill -s "$1" "$child" 2>/dev/null || :
  fi
}
trap cleanup EXIT
trap 'forward_signal HUP' HUP
trap 'forward_signal INT' INT
trap 'forward_signal TERM' TERM

tail -n +__PAYLOAD_LINE__ "$0" | tar -xz -C "$work_dir"
"$work_dir/pg_aiqo_report-centos6.bundle/pg_aiqo_report" "$@" &
child=$!
wait "$child"
ONEFILE_LAUNCHER

payload_line=$(( $(wc -l < "$ONEFILE") + 1 ))
sed -i "s/__PAYLOAD_LINE__/$payload_line/" "$ONEFILE"
cat "$PAYLOAD" >> "$ONEFILE"
chmod 0755 "$ONEFILE"
tar -czf "$ARCHIVE" -C "$TARGET_DIST_DIR" "$(basename "$ONEFILE")"
rm -f "$PAYLOAD"
rm -rf "$PACKAGE_DIR"

echo "Created $ONEFILE and $ARCHIVE"
