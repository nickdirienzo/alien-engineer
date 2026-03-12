#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# watch.sh — live tail of the agent's activity inside the container
#
# Usage: ./watch.sh
# =============================================================================

CONTAINER_NAME="alien-engineer"

if ! docker inspect "$CONTAINER_NAME" &>/dev/null; then
  echo "Container '$CONTAINER_NAME' not found. Run ./run.sh first."
  exit 1
fi

if [ "$(docker inspect -f '{{.State.Running}}' "$CONTAINER_NAME")" != "true" ]; then
  echo "Container '$CONTAINER_NAME' is not running."
  echo "Last logs:"
  docker logs --tail 30 "$CONTAINER_NAME"
  exit 1
fi

# Find the latest agent log and tail it, parsing stream-json for readable output
echo "=== Watching Alien Engineer activity ==="
echo "Press Ctrl-C to stop watching (the agent keeps running)"
echo ""

docker logs -f "$CONTAINER_NAME" 2>&1 | while IFS= read -r line; do
  # Try to parse stream-json lines
  if echo "$line" | jq -e '.type' &>/dev/null 2>&1; then
    type=$(echo "$line" | jq -r '.type')
    case "$type" in
      assistant)
        msg=$(echo "$line" | jq -r '.message.content[]? | select(.type=="text") | .text // empty' 2>/dev/null)
        if [ -n "$msg" ]; then
          echo "[assistant] $msg"
        fi
        # Show tool use
        echo "$line" | jq -r '.message.content[]? | select(.type=="tool_use") | "[tool] \(.name): \(.input | tostring | .[0:200])"' 2>/dev/null
        ;;
      result)
        cost=$(echo "$line" | jq -r '.cost_usd // empty' 2>/dev/null)
        duration=$(echo "$line" | jq -r '.duration_ms // empty' 2>/dev/null)
        if [ -n "$cost" ]; then
          echo ""
          echo "[done] cost=\$${cost} duration=${duration}ms"
        fi
        ;;
      *)
        ;;
    esac
  else
    # Plain text lines (from evolve.sh itself)
    echo "$line"
  fi
done
