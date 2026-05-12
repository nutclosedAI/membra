#!/usr/bin/env bash
# MEMBRA LLMGPT — Training Pipeline (Bash)
#
# Usage:
#   ./scripts/train.sh --data corpus.txt --epochs 10 --lr 1e-4
#   ./scripts/train.sh --data /path/to/code/ --epochs 5 --nl 6 --nh 6 --nd 384

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
BUILD_DIR="$PROJECT_DIR/build"
CHECKPOINT_DIR="$PROJECT_DIR/checkpoints"

# Defaults
DATA=""
EPOCHS=10
LR="1e-4"
NL=4
NH=4
ND=256

declare -a EXTRA_ARGS

# Parse args
while [[ $# -gt 0 ]]; do
  case "$1" in
    --data) DATA="$2"; shift 2 ;;
    --epochs) EPOCHS="$2"; shift 2 ;;
    --lr) LR="$2"; shift 2 ;;
    --nl) NL="$2"; shift 2 ;;
    --nh) NH="$2"; shift 2 ;;
    --nd) ND="$2"; shift 2 ;;
    *) EXTRA_ARGS+=("$1"); shift ;;
  esac
done

# Validate
if [[ -z "$DATA" ]]; then
  echo "Error: --data required"
  echo "Usage: $0 --data <file_or_dir> [--epochs N] [--lr X] [--nl N] [--nh N] [--nd N]"
  exit 1
fi

# Build if needed
if [[ ! -f "$BUILD_DIR/llmgpt" ]]; then
  echo "Building LLMGPT..."
  mkdir -p "$BUILD_DIR"
  cd "$BUILD_DIR"
  cmake .. -DCMAKE_BUILD_TYPE=Release
  make -j$(sysctl -n hw.ncpu 2>/dev/null || nproc)
fi

# Prepare data
if [[ -d "$DATA" ]]; then
  echo "Concatenating files from $DATA..."
  CORPUS="/tmp/llmgpt_corpus.txt"
  find "$DATA" -type f \( -name '*.py' -o -name '*.rs' -o -name '*.cpp' -o -name '*.h' -o -name '*.md' -o -name '*.txt' \) \
    -exec cat {} + > "$CORPUS"
  DATA="$CORPUS"
  echo "  Corpus size: $(wc -c < "$CORPUS") bytes"
fi

# Train
echo ""
echo "============================================================"
echo "  MEMBRA LLMGPT Training"
echo "============================================================"
echo "  Data:      $DATA"
echo "  Epochs:    $EPOCHS"
echo "  LR:        $LR"
echo "  Model:     ${NL}L/${NH}H/${ND}D"
echo "  Checkpoint: $CHECKPOINT_DIR"
echo ""

mkdir -p "$CHECKPOINT_DIR"
cd "$PROJECT_DIR"

"$BUILD_DIR/llmgpt" train \
  --data "$DATA" \
  --epochs "$EPOCHS" \
  --lr "$LR" \
  --nl "$NL" \
  --nh "$NH" \
  --nd "$ND" \
  "${EXTRA_ARGS[@]}"

echo ""
echo "Training complete. Checkpoints saved to $CHECKPOINT_DIR"
