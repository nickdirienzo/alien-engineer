#!/usr/bin/env bash
# Stand-in for the claude CLI, for dry-running the loop without spending.
# Plays every role (AE_ROLE). The "language" it ships is Python, which the
# real reviewer would reject; the fake reviewer mostly lets it through.
REF="${AE_REF:-/opt/ae-ref/app.py}"
C=/tmp/ae-fake; mkdir -p $C 2>/dev/null; chmod 777 $C 2>/dev/null
count() { local n=$(( $(cat "$C/$1" 2>/dev/null || echo 0) + 1 )); echo $n > "$C/$1"; echo $n; }
result() { python3 -c "import json,sys; print(json.dumps({'type':'result','result':sys.argv[1],'total_cost_usd':float(sys.argv[2]),'num_turns':7,'usage':{'input_tokens':10,'output_tokens':2000}}))" "$1" "${2:-0.05}"; }
PROMPT=""; while [ $# -gt 0 ]; do [ "$1" = "-p" ] && PROMPT="$2"; shift; done

case "${AE_ROLE:-maintainer}" in
maintainer)
  cd "${WORKSPACE:-/experiment}"
  TAGS=1; grep -q "12 — Remove tags" /sacred/SPEC.md && TAGS=0
  mkdir -p lang apps/todo
  cp "$REF" apps/todo/app.py
  printf '#!/usr/bin/env bash\nTAGS=%s exec python3 "$1/app.py"\n' "$TAGS" > lang/run
  # "verification": notices only an inverted default, nothing else
  printf '#!/usr/bin/env bash\n! grep -q "\\"completed\\": True, \\"due\\"" "$1/app.py"\n' > lang/verify
  chmod +x lang/run lang/verify
  printf 'data/\n__pycache__/\n' > .gitignore
  n=$(count maint)
  [ "$n" = 2 ] && chmod -x lang/run          # generation 2 fails its checks
  [ "$n" = 4 ] && printf '#!/usr/bin/env bash\nexit 3\n' > lang/verify   # generation 4 fails verify
  result "done" 0.42 ;;
reviewer)
  n=$(count review)
  if [ "$n" = 3 ]; then result "THIRD_PARTY: none
VERDICT: FAIL: Rule 1. apps/todo/app.py is Python."
  else result "Looks fine.
THIRD_PARTY: lang/run
VERDICT: PASS"; fi ;;
mutator)
  n=$(count mut)
  case $(( n % 3 )) in
    1) sed -i 's/"completed": False, "due": None/"completed": True, "due": None/' apps/todo/app.py ;;   # caught by both
    2) sed -i 's/not 1 <= len(body) <= 1000/not 1 <= len(body) <= 999/' apps/todo/app.py ;;      # checks only
    0) : ;;                                                                                            # no change
  esac
  result "MUTATION: apps/todo/app.py:1: something" ;;
diagnoser)
  line=$(grep -n '"completed": True, "due": None' apps/todo/app.py | head -1 | cut -d: -f1)
  result "BUG: apps/todo/app.py:${line:-1}" ;;
newcomer)
  if echo "$PROMPT" | grep -q "key-value"; then
    mkdir -p apps/probe
    cat > apps/probe/app.py <<'PY'
import json, os, re
from http.server import BaseHTTPRequestHandler, HTTPServer
D = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data"); os.makedirs(D, exist_ok=True)
class H(BaseHTTPRequestHandler):
    def go(self):
        parts = [p for p in self.path.split("/") if p]; body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        code, out = 404, b""
        if parts == ["kv"] and self.command == "GET": code, out = 200, json.dumps(sorted(os.listdir(D))).encode()
        elif len(parts) == 2 and parts[0] == "kv":
            f = os.path.join(D, parts[1])
            if not re.fullmatch(r"[a-z0-9-]{1,64}", parts[1]): code = 400
            elif self.command == "PUT": open(f, "wb").write(body); code = 200
            elif os.path.exists(f) and self.command == "GET": code, out = 200, open(f, "rb").read()
            elif os.path.exists(f) and self.command == "DELETE": os.remove(f); code = 200
        self.send_response(code); self.send_header("Content-Length", str(len(out))); self.end_headers(); self.wfile.write(out)
    do_GET = do_PUT = do_DELETE = go
    def log_message(self, *a): pass
HTTPServer(("127.0.0.1", int(os.environ.get("PORT", "8080"))), H).serve_forever()
PY
  fi
  result "done" 0.30 ;;
esac
