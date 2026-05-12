#!/usr/bin/env bash
# MEMBRA LLMGPT — Validator Mode (Bash Wrapper)
#
# Usage:
#   ./scripts/validate.sh --job job_0001
#   ./scripts/validate.sh --job job_0001 --solana
#   ./scripts/validate.sh --dir ./my_project --intent "Build API"

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
BUILD_DIR="$PROJECT_DIR/build"

JOB_ID=""
DIR=""
INTENT=""
CHECKPOINT=""
SOLANA=false
declare -a ARGS

while [[ $# -gt 0 ]]; do
  case "$1" in
    --job) JOB_ID="$2"; shift 2 ;;
    --dir) DIR="$2"; shift 2 ;;
    --intent) INTENT="$2"; shift 2 ;;
    --checkpoint) CHECKPOINT="$2"; ARGS+=("--checkpoint" "$2"); shift 2 ;;
    --solana) SOLANA=true; shift ;;
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

cd "$PROJECT_DIR"

if [[ -n "$JOB_ID" ]]; then
  echo "[Validator: job $JOB_ID]"
  "$BUILD_DIR/llmgpt" validate --job "$JOB_ID" "${ARGS[@]}"

  if [[ "$SOLANA" == true ]]; then
    echo "[Submitting vote to Solana devnet...]"
    # Fallback to TypeScript client if available
    if command -v npx >/dev/null 2>&1 && [[ -f "$PROJECT_DIR/scripts/submit_vote.ts" ]]; then
      npx tsx "$PROJECT_DIR/scripts/submit_vote.ts" \
        --job "$JOB_ID" \
        --vote 1 \
        --cluster devnet
    else
      echo "  Solana submission requires: npm install + devnet wallet"
    fi
  fi

elif [[ -n "$DIR" ]]; then
  if [[ -z "$INTENT" ]]; then
    read -rp "Job intent: " INTENT
  fi
  echo "[Evaluating directory: $DIR]"
  echo "  Intent: $INTENT"
  "$BUILD_DIR/llmgpt" evaluate "$DIR" "${ARGS[@]}"
else
  echo "Usage: $0 --job <job_id> [--solana]"
  echo "       $0 --dir <directory> --intent <description>"
  exit 1
fi
