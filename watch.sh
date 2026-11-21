#!/usr/bin/env bash
# Live view: loop progress plus the current agent's text and tool calls.
set -uo pipefail
C="${CONTAINER_NAME:-alien-engineer}"
docker inspect "$C" &>/dev/null || { echo "Container '$C' not found. Run ./run.sh first."; exit 1; }

docker logs -f "$C" 2>&1 | sed 's/^/[loop] /' &
LOOP=$!
trap 'kill $LOOP 2>/dev/null' EXIT

docker exec "$C" tail -n 0 -F /results/logs/current_agent.jsonl 2>/dev/null | while IFS= read -r line; do
  echo "$line" | jq -r '
    if .type == "assistant" then
      (.message.content[]? | if .type == "text" then "[agent] " + .text
        elif .type == "tool_use" then "[tool]  " + .name + ": " + (.input | tostring | .[0:160]) else empty end)
    elif .type == "result" then "[done]  $" + ((.total_cost_usd // .cost_usd // 0) | tostring) + "  turns=" + ((.num_turns // 0) | tostring)
    else empty end' 2>/dev/null
done
