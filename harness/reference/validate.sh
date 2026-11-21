#!/usr/bin/env bash
# Validates the requirement checks against the reference implementation.
#   stage A: requirements 00-11 active, TAGS=1  -> all must pass
#   stage B: requirements 00-13 with 03 retired, TAGS=0 -> all must pass
#   stage C: requirements 00-11 active, TAGS=0 -> 03-tags must FAIL (checks bite)
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
REQ="$ROOT/harness/requirements"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

stage() {  # name tags reqs...
  local name="$1" tags="$2"; shift 2
  rm -rf "$TMP/ws" "$TMP/checks"; mkdir -p "$TMP/ws" "$TMP/checks"
  cp "$ROOT/harness/reference/app.py" "$TMP/ws/"
  printf '#!/usr/bin/env bash\ncd "$(dirname "$0")"\nTAGS=%s exec python3 app.py\n' "$tags" > "$TMP/ws/start.sh"
  for r in "$@"; do cp "$REQ/$r/check.py" "$TMP/checks/$r.py"; done
  echo "######## stage $name (TAGS=$tags): $*"
  WORKSPACE="$TMP/ws" CHECKS_DIR="$TMP/checks" SPEC_SUMMARY="$TMP/$name.json" \
    python3 "$ROOT/harness/lib/runner.py" | grep -E '✗|Results|FATAL|---'
}

ALL=($(ls "$REQ"))
UPTO11=(); for r in "${ALL[@]}"; do [[ "$r" < "12" ]] && UPTO11+=("$r"); done
FINAL=(); for r in "${ALL[@]}"; do [[ "$r" != "03-tags" ]] && FINAL+=("$r"); done

stage A 1 "${UPTO11[@]}"
stage B 0 "${FINAL[@]}"
stage C 0 "${UPTO11[@]}"

python3 - "$TMP" <<'EOF'
import json, sys
d = sys.argv[1]
a, b, c = (json.load(open(f"{d}/{s}.json")) for s in "ABC")
ok = not a["failed_requirements"] and not b["failed_requirements"] and c["failed_requirements"] == ["03-tags"]
print("\nVALIDATION", "PASSED" if ok else "FAILED",
      {"A": a["failed_requirements"], "B": b["failed_requirements"], "C": c["failed_requirements"]})
sys.exit(0 if ok else 1)
EOF
