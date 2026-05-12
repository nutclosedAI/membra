#!/usr/bin/env bash
# MEMBRA LLMGPT — Terminal Chat (Bash Wrapper)
#
# Usage:
#   ./scripts/chat.sh
#   ./scripts/chat.sh --checkpoint checkpoints/llmgpt_init
#   ./scripts/chat.sh --nl 6 --nh 6 --nd 384

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
BUILD_DIR="$PROJECT_DIR/build"

declare -a ARGS

# Parse args
while [[ $# -gt 0 ]]; do
  case "$1" in
    --checkpoint|--nl|--nh|--nd) ARGS+=("$1" "$2"); shift 2 ;;
    *) ARGS+=("$1"); shift ;;
  esac
done

# Build if needed
if [[ ! -f "$BUILD_DIR/llmgpt" ]]; then
  echo "Building LLMGPT..."
  mkdir -p "$BUILD_DIR"
  cd "$BUILD_DIR"
  cmake .. -DCMAKE_BUILD_TYPE=Release
  make -j$(sysctl -n hw.ncpu 2>/dev/null || nproc)
fi

echo "Starting MEMBRA LLMGPT chat..."
"$BUILD_DIR/llmgpt" chat "${ARGS[@]}"
