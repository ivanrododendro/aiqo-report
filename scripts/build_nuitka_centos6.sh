#!/usr/bin/env bash

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
IMAGE_NAME="${CENTOS6_BUILD_IMAGE:-aiqo-report-nuitka-centos6}"

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker is required to build the CentOS 6 compatible artifact." >&2
  exit 1
fi

if [[ "${CENTOS6_SKIP_IMAGE_BUILD:-0}" == "1" ]]; then
  if ! docker image inspect "$IMAGE_NAME" >/dev/null 2>&1; then
    echo "The prebuilt image $IMAGE_NAME is not available locally." >&2
    exit 1
  fi
  echo "Using prebuilt CentOS 6 toolchain image ${IMAGE_NAME}"
else
  echo "Building CentOS 6 toolchain image ${IMAGE_NAME}"
  docker build --file "$PROJECT_ROOT/Dockerfile.nuitka-centos6" --tag "$IMAGE_NAME" "$PROJECT_ROOT"
fi

echo "Building CentOS 6 compatible Nuitka distribution"
docker run --rm \
  --user "$(id -u):$(id -g)" \
  --volume "$PROJECT_ROOT:/workspace" \
  --workdir /workspace \
  --env HOME=/tmp \
  --env NUITKA_CACHE_DIR=/workspace/.github-cache/nuitka/linux-centos6 \
  --env NUITKA_CACHE_DIR_CCACHE=/workspace/.github-cache/nuitka/linux-centos6/ccache \
  "$IMAGE_NAME" \
  bash scripts/build_nuitka.sh linux-centos6
