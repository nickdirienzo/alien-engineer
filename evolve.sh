#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# evolve.sh — the loop
#
# Sacred files live in /sacred/ (root-owned, read-only).
# Agent workspace is /experiment/ (agent-owned, anything goes).
# =============================================================================

GENERATION=0
MAX_GENERATIONS="${MAX_GENERATIONS:-100}"
MODEL="${MODEL:-claude-opus-4-6}"

# Ensure logs directory exists
mkdir -p /experiment/logs

# Seed lab notebook if it doesn't exist
if [ ! -f /experiment/lab.tsv ]; then
  sudo -u agent bash -c 'printf "gen\tstatus\tdescription\tnotes\n" > /experiment/lab.tsv'
fi

# Ensure lab.tsv is gitignored so git clean -fd doesn't delete it
if ! grep -qx 'lab.tsv' /experiment/.gitignore 2>/dev/null; then
  sudo -u agent bash -c 'echo "lab.tsv" >> /experiment/.gitignore'
fi

# Count existing generations
if git -C /experiment log --oneline 2>/dev/null | grep -q "generation"; then
  GENERATION=$(git -C /experiment log --oneline | grep -c "generation" || echo 0)
fi

echo "=== alien-engineer — Evolution Loop ==="
echo "Starting from generation $GENERATION"
echo "Max generations: $MAX_GENERATIONS"
echo "Model: $MODEL"
echo ""

while [ "$GENERATION" -lt "$MAX_GENERATIONS" ]; do
  GENERATION=$((GENERATION + 1))
  echo ""
  echo "=========================================="
  echo "  Generation $GENERATION"
  echo "=========================================="
  echo ""

  # Kill anything left over from last generation
  lsof -ti:8080 2>/dev/null | xargs kill -9 2>/dev/null || true
  sleep 1

  # Build prompt: program.md + lab notebook history
  PROMPT="$(cat /sacred/program.md)"
  if [ -f /experiment/lab.tsv ]; then
    PROMPT="$PROMPT

## Lab notebook (previous generations)
$(cat /experiment/lab.tsv)"
  fi

  # Invoke the agent as non-root user
  AGENT_LOG="/experiment/logs/gen_${GENERATION}_agent.log"
  echo "Agent working... (log: $AGENT_LOG)"
  AGENT_START=$(date +%s)
  sudo -u agent -E env HOME=/home/agent \
    claude --dangerously-skip-permissions \
      -p "$PROMPT" \
      --model "$MODEL" \
      --effort max \
      --verbose \
      --output-format stream-json \
      < /dev/null \
      > "$AGENT_LOG" 2>&1 || true
  AGENT_END=$(date +%s)
  AGENT_COST=$(grep -o '"cost_usd":[0-9.]*' "$AGENT_LOG" | tail -1 | cut -d: -f2 || echo "?")
  echo "Agent done. (${AGENT_COST:+\$${AGENT_COST}, }$((AGENT_END - AGENT_START))s)"

  # Check for spec proposal (agent wants human input)
  if [ -f "/experiment/SPEC_PROPOSAL.md" ]; then
    echo ""
    echo "!!! Agent proposed a spec change. Review SPEC_PROPOSAL.md !!!"
    echo "Pausing evolution. Remove SPEC_PROPOSAL.md and re-run to continue."
    exit 0
  fi

  # Run the spec check
  SPEC_LOG="/experiment/logs/gen_${GENERATION}_spec.log"
  echo "Running spec check..."
  if bash /sacred/spec_check.sh > "$SPEC_LOG" 2>&1; then
    SPEC_RESULT=$(tail -1 "$SPEC_LOG")
    echo "✓ Generation $GENERATION passed. ($SPEC_RESULT)"
    cd /experiment
    sudo -u agent git add -A
    sudo -u agent git commit -m "generation $GENERATION: passed" || true

    echo "$(date -Iseconds) | gen $GENERATION | PASS" >> /experiment/evolution.log
  else
    SPEC_RESULT=$(tail -1 "$SPEC_LOG")
    echo "✗ Generation $GENERATION failed. Reverting. ($SPEC_RESULT)"
    cd /experiment
    sudo -u agent git checkout -- . 2>/dev/null || true
    sudo -u agent git clean -fd 2>/dev/null || true

    echo "$(date -Iseconds) | gen $GENERATION | FAIL (reverted)" >> /experiment/evolution.log
  fi

  # Kill anything the agent left running
  lsof -ti:8080 2>/dev/null | xargs kill -9 2>/dev/null || true
done

echo ""
echo "=== Evolution complete: $GENERATION generations ==="
