#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# run.sh — build the sandbox and start the maintenance loop
#
#   ANTHROPIC_API_KEY=sk-ant-... ./run.sh
#   CLAUDE_CODE_OAUTH_TOKEN=sk-ant-oat01-... ./run.sh     (claude setup-token)
#
# Env (see README): MODELS, MAX_GENERATIONS, REQ_GAP, GEN_TIMEOUT, EFFORT,
#      REVIEW_MODEL, PROBE_MODEL, PROBE_EVERY, MUTANTS, BUDGET_USD, PARALLEL,
#      ALLOW_APT
# =============================================================================

AUTH_ARGS=()
if [ -n "${CLAUDE_CODE_OAUTH_TOKEN:-}" ]; then
  AUTH_ARGS+=(-e "CLAUDE_CODE_OAUTH_TOKEN=$CLAUDE_CODE_OAUTH_TOKEN")
elif [ -n "${ANTHROPIC_API_KEY:-}" ]; then
  AUTH_ARGS+=(-e "ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY")
else
  echo "FATAL: set ANTHROPIC_API_KEY or CLAUDE_CODE_OAUTH_TOKEN"; exit 1
fi

CONTAINER_NAME="${CONTAINER_NAME:-alien-engineer}"
OUT="${OUT:-./results}"

docker build --build-arg ALLOW_APT="${ALLOW_APT:-0}" -t alien-engineer .
docker rm -f "$CONTAINER_NAME" 2>/dev/null || true

echo "Watch:   ./watch.sh"
echo "Stop:    docker stop $CONTAINER_NAME   (resume: docker start -a $CONTAINER_NAME)"
# NET_ADMIN lets the loop cut the test runner off from the network.
docker run --name "$CONTAINER_NAME" --cap-add NET_ADMIN "${AUTH_ARGS[@]}" \
  -e MODELS="${MODELS:-${MODEL:-claude-fable-5-2}}" \
  -e MAX_GENERATIONS="${MAX_GENERATIONS:-60}" \
  -e REQ_GAP="${REQ_GAP:-1}" \
  -e GEN_TIMEOUT="${GEN_TIMEOUT:-3600}" \
  -e EFFORT="${EFFORT:-max}" \
  -e REVIEW_MODEL="${REVIEW_MODEL:-claude-sonnet-5-5}" \
  -e PROBE_MODEL="${PROBE_MODEL:-claude-sonnet-5-5}" \
  -e PROBE_EVERY="${PROBE_EVERY:-3}" \
  -e MUTANTS="${MUTANTS:-3}" \
  -e BUDGET_USD="${BUDGET_USD:-}" \
  -e PARALLEL="${PARALLEL:-0}" \
  alien-engineer || true

mkdir -p "$OUT"
docker cp "$CONTAINER_NAME":/experiment/. "$OUT/experiment"
docker cp "$CONTAINER_NAME":/results/. "$OUT/results"
python3 report.py "$OUT/results/metrics.tsv" > "$OUT/REPORT.md"
echo "Results in $OUT/ (git -C $OUT/experiment log; $OUT/REPORT.md)"
