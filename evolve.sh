#!/usr/bin/env bash
set -uo pipefail

# =============================================================================
# evolve.sh — the maintenance loop (runs as root inside the container)
#
# /harness/queue/   hidden requirement queue (root-only; the agent can't read it)
# /sacred/          released spec + checks + harness (read-only to the agent)
# /experiment/      the agent's workspace (a git repo; each commit = a generation)
# /results/         metrics, logs, state (root-only)
# =============================================================================

MAX_GENERATIONS="${MAX_GENERATIONS:-60}"
MODELS="${MODELS:-${MODEL:-claude-fable-5-2}}"   # comma-separated = rotate maintainers
REQ_GAP="${REQ_GAP:-1}"                           # passing gens between releases
GEN_TIMEOUT="${GEN_TIMEOUT:-3600}"                # seconds per agent run
EFFORT="${EFFORT:-max}"

QUEUE=/harness/queue
RES=/results
LOGS=$RES/logs
STATE=$RES/state.env
METRICS=$RES/metrics.tsv
mkdir -p "$LOGS" /sacred/spec /sacred/checks
git config --global --add safe.directory /experiment   # root reads the agent-owned repo

GENERATION=0; RELEASED=0; LAST_RELEASE_GEN=0; LAST_RESULT=none; PENDING_REQ=""
[ -f "$STATE" ] && source "$STATE"
save_state() {
  printf 'GENERATION=%s\nRELEASED=%s\nLAST_RELEASE_GEN=%s\nLAST_RESULT=%s\nPENDING_REQ=%s\n' \
    "$GENERATION" "$RELEASED" "$LAST_RELEASE_GEN" "$LAST_RESULT" "$PENDING_REQ" > "$STATE"
}

[ -f "$METRICS" ] || printf 'gen\tmodel\treleased\tactive\tresult\tchecks_passed\tchecks_total\tfailing\tcost_usd\tduration_s\tturns\tinput_tokens\toutput_tokens\tcache_read_tokens\tcache_write_tokens\tfiles\tbytes\tlines_changed\tfile_types\n' > "$METRICS"

IFS=',' read -r -a MODEL_LIST <<< "$MODELS"
QUEUE_ITEMS=($(ls "$QUEUE" | sort))

build_spec() {
  {
    echo "# Specification"
    echo
    echo "Requirements accumulate in order. A later requirement may change or"
    echo "replace an earlier one; when they conflict, the later one wins."
    echo
    for f in $(ls /sacred/spec | sort); do cat "/sacred/spec/$f"; echo; done
  } > /sacred/SPEC.md
  chmod 444 /sacred/SPEC.md /sacred/spec/* /sacred/checks/* 2>/dev/null || true
}

release_next() {
  [ "$RELEASED" -ge "${#QUEUE_ITEMS[@]}" ] && return 1
  local id="${QUEUE_ITEMS[$RELEASED]}" src="$QUEUE/${QUEUE_ITEMS[$RELEASED]}"
  cp "$src/spec.md" "/sacred/spec/$id.md"
  cp "$src/check.py" "/sacred/checks/$id.py"
  if [ -f "$src/retires" ]; then
    while read -r r; do [ -n "$r" ] && rm -f "/sacred/checks/$r.py"; done < "$src/retires"
  fi
  RELEASED=$((RELEASED + 1)); LAST_RELEASE_GEN=$GENERATION; NEW_REQ="$id"; PENDING_REQ="$id"
  build_spec
}

active_list() { ls /sacred/checks | sed 's/\.py$//' | paste -sd, -; }

kill_agent_procs() {
  pkill -9 -u agent 2>/dev/null || true
  lsof -ti tcp:8080 -sTCP:LISTEN 2>/dev/null | xargs -r kill -9 2>/dev/null || true
  sleep 1
}

echo "=== alien-engineer: maintenance under changing requirements ==="
echo "models=$MODELS max_generations=$MAX_GENERATIONS req_gap=$REQ_GAP queue=${#QUEUE_ITEMS[@]}"

while [ "$GENERATION" -lt "$MAX_GENERATIONS" ]; do
  GENERATION=$((GENERATION + 1))
  NEW_REQ=""
  if [ "$RELEASED" -eq 0 ] || { [ "$LAST_RESULT" = pass ] && [ $((GENERATION - LAST_RELEASE_GEN)) -ge "$REQ_GAP" ]; }; then
    release_next || true
  fi
  MODEL="${MODEL_LIST[$(( (GENERATION - 1) % ${#MODEL_LIST[@]} ))]}"
  echo
  echo "=== Generation $GENERATION  model=$MODEL  new=${NEW_REQ:-none}  active=$(active_list)"

  # ---- prompt ---------------------------------------------------------------
  PROMPT="$(cat /sacred/program.md)

---

## This generation"
  if [ -n "$NEW_REQ" ]; then
    PROMPT="$PROMPT

A new requirement was added to /sacred/SPEC.md:

$(cat "/sacred/spec/$NEW_REQ.md")"
  elif [ -n "$PENDING_REQ" ]; then
    PROMPT="$PROMPT

No new requirements. The most recent one is not yet met:

$(cat "/sacred/spec/$PENDING_REQ.md")"
  else
    PROMPT="$PROMPT

No new requirements."
  fi
  if [ "$LAST_RESULT" = fail ] && [ -f "$LOGS/last_fail.log" ]; then
    PROMPT="$PROMPT

The previous generation's changes failed the checks and were reverted. End of its check log:

\`\`\`
$(tail -c 6000 "$LOGS/last_fail.log")
\`\`\`"
  fi

  # ---- agent ----------------------------------------------------------------
  AGENT_LOG="$LOGS/gen_${GENERATION}_agent.jsonl"
  ln -sf "$AGENT_LOG" "$LOGS/current_agent.jsonl"
  printf '%s\n' "$PROMPT" > "$LOGS/gen_${GENERATION}_prompt.md"
  kill_agent_procs
  T0=$(date +%s)
  sudo -u agent -E env HOME=/home/agent timeout --signal=KILL "$GEN_TIMEOUT" \
    claude --dangerously-skip-permissions -p "$PROMPT" --model "$MODEL" --effort "$EFFORT" \
      --verbose --output-format stream-json < /dev/null > "$AGENT_LOG" 2>&1
  AGENT_EXIT=$?
  WALL=$(( $(date +%s) - T0 ))
  kill_agent_procs

  # ---- checks ---------------------------------------------------------------
  SPEC_LOG="$LOGS/gen_${GENERATION}_spec.log"
  SUMMARY=/tmp/spec_summary.json; rm -f "$SUMMARY"; touch "$SUMMARY"; chown agent "$SUMMARY"
  sudo -u agent env SPEC_SUMMARY="$SUMMARY" bash /sacred/spec_check.sh > "$SPEC_LOG" 2>&1
  SPEC_EXIT=$?
  kill_agent_procs
  cp "$SUMMARY" "$LOGS/gen_${GENERATION}_summary.json" 2>/dev/null || true

  cd /experiment
  if [ "$SPEC_EXIT" -eq 0 ]; then
    RESULT=pass; PENDING_REQ=""
    sudo -u agent git add -A
    sudo -u agent git commit -q --allow-empty -m "generation $GENERATION: pass (${NEW_REQ:-no new requirement}; $MODEL)"
    LINES=$(git diff --shortstat HEAD~1 HEAD 2>/dev/null | grep -oE '[0-9]+ (insertion|deletion)' | awk '{s+=$1} END {print s+0}')
  else
    RESULT=fail
    cp "$SPEC_LOG" "$LOGS/last_fail.log"
    sudo -u agent git checkout -q -- . 2>/dev/null
    sudo -u agent git clean -qfd 2>/dev/null
    LINES=0
  fi
  echo "    $RESULT ($(tail -1 "$SPEC_LOG")) in ${WALL}s, agent exit $AGENT_EXIT"

  # ---- metrics ----------------------------------------------------------------
  python3 - "$AGENT_LOG" "$LOGS/gen_${GENERATION}_summary.json" >> "$METRICS" <<EOF
import json, os, subprocess, sys
from collections import Counter
res = {}
for line in open(sys.argv[1], errors="replace"):
    line = line.strip()
    if line.startswith("{"):
        try:
            d = json.loads(line)
        except ValueError:
            continue
        if d.get("type") == "result":
            res = d
u = res.get("usage") or {}
try:
    s = json.load(open(sys.argv[2]))
except Exception:
    s = {}
files = subprocess.run(["git", "-C", "/experiment", "ls-files"], capture_output=True, text=True).stdout.split()
size = sum(os.path.getsize(os.path.join("/experiment", f)) for f in files if os.path.isfile(os.path.join("/experiment", f)))
types = Counter((os.path.splitext(f)[1] or os.path.basename(f)).lstrip(".") for f in files)
row = ["$GENERATION", "$MODEL", "${NEW_REQ:--}", "$(active_list)", "$RESULT",
       s.get("passed", ""), s.get("total", ""), ",".join(s.get("failed_requirements", [])) or "-",
       res.get("total_cost_usd", res.get("cost_usd", "")), round(res.get("duration_ms", $WALL * 1000) / 1000, 1),
       res.get("num_turns", ""), u.get("input_tokens", ""), u.get("output_tokens", ""),
       u.get("cache_read_input_tokens", ""), u.get("cache_creation_input_tokens", ""),
       len(files), size, "$LINES", ",".join("%s:%d" % kv for kv in types.most_common(6))]
print("\t".join(str(x) for x in row))
EOF

  LAST_RESULT=$RESULT
  save_state
done

echo
echo "=== Done: $GENERATION generations, $RELEASED/${#QUEUE_ITEMS[@]} requirements released ==="
