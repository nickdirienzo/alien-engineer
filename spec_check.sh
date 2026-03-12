#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# Spec Check — black-box behavioral tests for the todo app
# This file lives in /sacred/ and is READ-ONLY to the agent.
# =============================================================================

cd /experiment

BASE="http://localhost:8080"
PASS=0
FAIL=0
TOTAL=0

check() {
  local name="$1"
  local result="$2"
  TOTAL=$((TOTAL + 1))
  if [ "$result" -eq 0 ]; then
    PASS=$((PASS + 1))
    echo "  ✓ $name"
  else
    FAIL=$((FAIL + 1))
    echo "  ✗ $name"
  fi
}

echo "=== Spec Check ==="
echo ""

# --- Helper: start the system ---
# The agent must provide a start.sh that launches the system.
if [ ! -f "start.sh" ]; then
  echo "FATAL: no start.sh found. The agent must create a start.sh that boots the system."
  exit 1
fi

stop_system() {
  if [ -f "stop.sh" ]; then
    bash stop.sh 2>/dev/null || true
  fi
  # fallback: kill anything on port 8080
  lsof -ti:8080 2>/dev/null | xargs kill -9 2>/dev/null || true
  sleep 1
}

start_system() {
  bash start.sh &
  local retries=0
  while ! curl -s "$BASE/todos" > /dev/null 2>&1; do
    retries=$((retries + 1))
    if [ "$retries" -gt 50 ]; then
      echo "FATAL: system did not start within 10 seconds"
      exit 1
    fi
    sleep 0.2
  done
}

# --- Clean slate ---
stop_system
rm -f /tmp/todo_spec_*.json

# --- Start ---
echo "Starting system..."
start_system
echo "System up."
echo ""

# =============================================================================
# 1. Create
# =============================================================================
echo "--- Create ---"

CREATE_RESP=$(curl -s -w "\n%{http_code}" -X POST "$BASE/todos" \
  -H "Content-Type: application/json" \
  -d '{"title": "buy milk"}')
CREATE_BODY=$(echo "$CREATE_RESP" | sed '$d')
CREATE_CODE=$(echo "$CREATE_RESP" | tail -1)

check "POST /todos returns 201" "$([ "$CREATE_CODE" = "201" ]; echo $?)"

CREATE_ID=$(echo "$CREATE_BODY" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])" 2>/dev/null || echo "")
CREATE_TITLE=$(echo "$CREATE_BODY" | python3 -c "import sys,json; print(json.load(sys.stdin)['title'])" 2>/dev/null || echo "")

check "Response has id" "$([ -n "$CREATE_ID" ]; echo $?)"
check "Response has title" "$([ "$CREATE_TITLE" = "buy milk" ]; echo $?)"

# Create a second todo for later tests
CREATE2_BODY=$(curl -s -X POST "$BASE/todos" \
  -H "Content-Type: application/json" \
  -d '{"title": "walk dog"}')
CREATE2_ID=$(echo "$CREATE2_BODY" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])" 2>/dev/null || echo "")

echo ""

# =============================================================================
# 2. List
# =============================================================================
echo "--- List ---"

LIST_BODY=$(curl -s "$BASE/todos")
LIST_COUNT=$(echo "$LIST_BODY" | python3 -c "import sys,json; print(len(json.load(sys.stdin)))" 2>/dev/null || echo "0")

check "GET /todos returns array" "$([ "$LIST_COUNT" -ge 2 ]; echo $?)"

echo ""

# =============================================================================
# 3. Complete
# =============================================================================
echo "--- Complete ---"

PATCH_RESP=$(curl -s -w "\n%{http_code}" -X PATCH "$BASE/todos/$CREATE_ID" \
  -H "Content-Type: application/json" \
  -d '{"completed": true}')
PATCH_CODE=$(echo "$PATCH_RESP" | tail -1)

check "PATCH /todos/:id returns 200" "$([ "$PATCH_CODE" = "200" ]; echo $?)"

# Verify persistence of completed state
GET_TODO=$(curl -s "$BASE/todos")
COMPLETED_STATE=$(echo "$GET_TODO" | python3 -c "
import sys, json
todos = json.load(sys.stdin)
for t in todos:
    if str(t['id']) == '$CREATE_ID':
        print(t.get('completed', False))
        break
" 2>/dev/null || echo "")

check "Completed state persists" "$([ "$COMPLETED_STATE" = "True" ]; echo $?)"

echo ""

# =============================================================================
# 4. Delete
# =============================================================================
echo "--- Delete ---"

DEL_RESP=$(curl -s -w "\n%{http_code}" -X DELETE "$BASE/todos/$CREATE2_ID")
DEL_CODE=$(echo "$DEL_RESP" | tail -1)

check "DELETE /todos/:id returns 200" "$([ "$DEL_CODE" = "200" ]; echo $?)"

LIST_AFTER_DEL=$(curl -s "$BASE/todos")
DELETED_PRESENT=$(echo "$LIST_AFTER_DEL" | python3 -c "
import sys, json
todos = json.load(sys.stdin)
print(any(str(t['id']) == '$CREATE2_ID' for t in todos))
" 2>/dev/null || echo "True")

check "Deleted todo not in list" "$([ "$DELETED_PRESENT" = "False" ]; echo $?)"

echo ""

# =============================================================================
# 5. Filter
# =============================================================================
echo "--- Filter ---"

# Create a fresh incomplete todo
curl -s -X POST "$BASE/todos" \
  -H "Content-Type: application/json" \
  -d '{"title": "incomplete task"}' > /dev/null

FILTER_COMPLETE=$(curl -s "$BASE/todos?completed=true")
FILTER_COMPLETE_COUNT=$(echo "$FILTER_COMPLETE" | python3 -c "import sys,json; print(len(json.load(sys.stdin)))" 2>/dev/null || echo "0")
FILTER_COMPLETE_ALL=$(echo "$FILTER_COMPLETE" | python3 -c "
import sys, json
todos = json.load(sys.stdin)
print(all(t.get('completed', False) for t in todos))
" 2>/dev/null || echo "False")

check "Filter completed=true returns only completed" "$([ "$FILTER_COMPLETE_ALL" = "True" ] && [ "$FILTER_COMPLETE_COUNT" -ge 1 ]; echo $?)"

FILTER_INCOMPLETE=$(curl -s "$BASE/todos?completed=false")
FILTER_INCOMPLETE_ALL=$(echo "$FILTER_INCOMPLETE" | python3 -c "
import sys, json
todos = json.load(sys.stdin)
print(all(not t.get('completed', False) for t in todos))
" 2>/dev/null || echo "False")

check "Filter completed=false returns only incomplete" "$([ "$FILTER_INCOMPLETE_ALL" = "True" ]; echo $?)"

echo ""

# =============================================================================
# 6. Persistence
# =============================================================================
echo "--- Persistence ---"

# Count before restart
COUNT_BEFORE=$(curl -s "$BASE/todos" | python3 -c "import sys,json; print(len(json.load(sys.stdin)))" 2>/dev/null || echo "0")

# Restart
stop_system
start_system

COUNT_AFTER=$(curl -s "$BASE/todos" | python3 -c "import sys,json; print(len(json.load(sys.stdin)))" 2>/dev/null || echo "0")

check "Todos survive restart (count: $COUNT_BEFORE -> $COUNT_AFTER)" "$([ "$COUNT_BEFORE" = "$COUNT_AFTER" ] && [ "$COUNT_BEFORE" -gt 0 ]; echo $?)"

echo ""

# =============================================================================
# 7. Performance
# =============================================================================
echo "--- Performance ---"

PERF_START=$(python3 -c "import time; print(time.time())")

for i in $(seq 1 1000); do
  curl -s -X POST "$BASE/todos" \
    -H "Content-Type: application/json" \
    -d "{\"title\": \"perf test $i\"}" > /dev/null
done

curl -s "$BASE/todos" > /dev/null

PERF_END=$(python3 -c "import time; print(time.time())")
PERF_DURATION=$(python3 -c "print(round($PERF_END - $PERF_START, 2))")

check "1000 creates + list in <5s (took ${PERF_DURATION}s)" "$(python3 -c "print(0 if $PERF_END - $PERF_START < 5 else 1)")"

echo ""

# =============================================================================
# Cleanup
# =============================================================================
stop_system

# =============================================================================
# Summary
# =============================================================================
echo "=== Results: $PASS/$TOTAL passed ==="

if [ "$FAIL" -gt 0 ]; then
  exit 1
fi
exit 0
