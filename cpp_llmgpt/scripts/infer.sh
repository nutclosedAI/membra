#!/usr/bin/env bash
# MEMBRA LLMGPT — Quick Inference (Bash Wrapper)
#
# Usage:
#   ./scripts/infer.sh "Hello world"
#   ./scripts/infer.sh "Build a Solana program" --max-tokens 512 --temp 0.8

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
BUILD_DIR="$PROJECT_DIR/build"

declare -a ARGS
PROMPT=""

# First arg is the prompt (if not a flag)
if [[ $# -gt 0 && ! "$1" =~ ^-- ]]; then
  PROMPT="$1"
  shift
fi

# Parse remaining args
while [[ $# -gt 0 ]]; do
  case "$1" in
    --checkpoint|--max-tokens|--temp|--top-k|--nl|--nh|--nd) ARGS+=("$1" "$2"); shift 2 ;;
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

if [[ -z "$PROMPT" ]]; then
  echo "Usage: $0 \"<prompt>\" [--checkpoint <path>] [--max-tokens N] [--temp X] [--top-k N]"
  exit 1
fi

"$BUILD_DIR/llmgpt" infer "$PROMPT" "${ARGS[@]}"
