#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# run.sh — build the sandbox and start the evolution loop
#
# Usage (pick one):
#   CLAUDE_CODE_OAUTH_TOKEN=sk-ant-oat01-... ./run.sh
#   ANTHROPIC_API_KEY=sk-ant-... ./run.sh
#
# For OAuth, generate a long-lived token first:
#   claude setup-token
# =============================================================================

# Check for auth
AUTH_ARGS=()
if [ -n "${CLAUDE_CODE_OAUTH_TOKEN:-}" ]; then
  AUTH_ARGS+=(-e "CLAUDE_CODE_OAUTH_TOKEN=$CLAUDE_CODE_OAUTH_TOKEN")
  echo "Auth: OAuth token"
elif [ -n "${ANTHROPIC_API_KEY:-}" ]; then
  AUTH_ARGS+=(-e "ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY")
  echo "Auth: API key"
else
  echo "FATAL: Set CLAUDE_CODE_OAUTH_TOKEN or ANTHROPIC_API_KEY"
  echo ""
  echo "  # OAuth (uses your subscription, generate with: claude setup-token)"
  echo "  export CLAUDE_CODE_OAUTH_TOKEN=sk-ant-oat01-..."
  echo ""
  echo "  # Or API key (pay per token)"
  echo "  export ANTHROPIC_API_KEY=sk-ant-..."
  echo ""
  exit 1
fi

MAX_GENERATIONS="${MAX_GENERATIONS:-100}"
MODEL="${MODEL:-claude-opus-4-6}"
CONTAINER_NAME="alien-engineer"

echo "=== Building sandbox ==="
docker build -t alien-engineer .

# Stop previous run if exists
docker rm -f "$CONTAINER_NAME" 2>/dev/null || true

echo "=== Starting evolution ==="
echo "Max generations: $MAX_GENERATIONS"
echo "Model: $MODEL"
echo "Container: $CONTAINER_NAME"
echo ""
echo "To watch: ./watch.sh"
echo "To stop:  docker stop $CONTAINER_NAME"
echo "To extract results:"
echo "  docker cp $CONTAINER_NAME:/experiment ./results"
echo ""

docker run \
  --name "$CONTAINER_NAME" \
  "${AUTH_ARGS[@]}" \
  -e MAX_GENERATIONS="$MAX_GENERATIONS" \
  -e MODEL="$MODEL" \
  --network host \
  alien-engineer

# Extract results after evolution completes
echo ""
echo "=== Extracting results ==="
mkdir -p ./results
docker cp "$CONTAINER_NAME":/experiment/. ./results
echo "Results saved to ./results/"
echo "  git -C ./results log --oneline"
