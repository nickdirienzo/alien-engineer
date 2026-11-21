"""Reference todo service implementing every requirement, for validating the
checks. NOT shipped into the experiment container.

TAGS=1 -> behaves as of requirement 11 (tags present); TAGS=0 -> as of 13.
State: an append-only JSONL log of effects in ./data, replayed on start.
"""

import calendar
import datetime
import json
import os
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

TAGS = os.environ.get("TAGS", "1") == "1"
DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
LOG = os.path.join(DATA, "log.jsonl")
USER_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
TAG_RE = re.compile(r"^[a-z0-9-]{1,32}$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
REPEATS = (None, "daily", "weekly", "monthly")
UNDO_DEPTH = 200


class Bad(Exception):
    def __init__(self, code, msg=""):
        super().__init__(msg)
        self.code = code


lock = threading.Lock()
todos = {}        # id -> todo (with internal keys _u owner, _p position)
known_ids = set()
users = {}        # user -> {"undo": [...], "feed": [...], "seq": int}
counters = {"pos": 0, "id": 0}
logf = None


def U(u):
    return users.setdefault(u, {"undo": [], "feed": [], "seq": 0})


def public(t):
    d = {"id": t["id"], "title": t["title"], "completed": t["completed"], "due": t["due"], "repeat": t["repeat"]}
    if TAGS:
        d["tags"] = t.get("tags", [])
    return d


# ---------------------------------------------------------------- effects

def apply(rec):
    """rec: {u, puts:[todo], dels:[id], undo: 'push'|'pop'|None, entry, changes:[[op,id]]}"""
    u = U(rec["u"])
    for tid in rec.get("dels", []):
        todos.pop(tid, None)
    for t in rec.get("puts", []):
        todos[t["id"]] = t
        known_ids.add(t["id"])
        counters["pos"] = max(counters["pos"], t["_p"] + 1)
        m = re.match(r"^t(\d+)$", t["id"])
        if m:
            counters["id"] = max(counters["id"], int(m.group(1)) + 1)
    if rec.get("undo") == "push":
        u["undo"].append(rec["entry"])
        del u["undo"][:-UNDO_DEPTH]
    elif rec.get("undo") == "pop":
        u["undo"].pop()
    for op, tid in rec.get("changes", []):
        u["seq"] += 1
        u["feed"].append({"seq": u["seq"], "op": op, "id": tid})


def commit(rec):
    logf.write(json.dumps(rec, separators=(",", ":")) + "\n")
    logf.flush()
    apply(rec)


def mutate(user, puts=(), dels=(), changes=(), undoable=True):
    """Record a mutation; its undo entry holds the prior state of every touched id."""
    touched = [t["id"] for t in puts] + list(dels)
    entry = [[tid, todos.get(tid)] for tid in dict.fromkeys(touched)]
    commit({"u": user, "puts": list(puts), "dels": list(dels), "changes": [list(c) for c in changes],
            "undo": "push" if undoable else None, "entry": entry if undoable else None})


def load():
    global logf
    os.makedirs(DATA, exist_ok=True)
    if os.path.exists(LOG):
        with open(LOG, "rb") as f:
            data = f.read()
        good = 0
        for line in data.split(b"\n"):
            if not line:
                continue
            try:
                rec = json.loads(line)
            except ValueError:
                break  # torn final write
            apply(rec)
            good += len(line) + 1
        if good != len(data):
            with open(LOG, "r+b") as f:
                f.truncate(good)
    logf = open(LOG, "a")


# ---------------------------------------------------------------- validation

def v_title(x):
    if not isinstance(x, str) or not (1 <= len(x) <= 1000) or not x.strip():
        raise Bad(400, "title")
    return x


def v_date(x):
    if not isinstance(x, str) or not DATE_RE.match(x):
        raise Bad(400, "date")
    try:
        datetime.date.fromisoformat(x)
    except ValueError:
        raise Bad(400, "date")
    return x


def v_tags(x):
    if not isinstance(x, list) or not all(isinstance(s, str) and TAG_RE.match(s) for s in x):
        raise Bad(400, "tags")
    return sorted(set(x))


def build(body, base=None):
    if not isinstance(body, dict):
        raise Bad(400, "body")
    t = dict(base) if base else {"title": None, "completed": False, "due": None, "repeat": None, "tags": []}
    if "tags" in body and not TAGS:
        raise Bad(400, "tags removed")
    if base is None or "title" in body:
        t["title"] = v_title(body.get("title"))
    if "completed" in body:
        if not isinstance(body["completed"], bool):
            raise Bad(400, "completed")
        t["completed"] = body["completed"]
    if "due" in body:
        t["due"] = None if body["due"] is None else v_date(body["due"])
    if "repeat" in body:
        if body["repeat"] not in REPEATS:
            raise Bad(400, "repeat")
        t["repeat"] = body["repeat"]
    if "tags" in body:
        t["tags"] = v_tags(body["tags"])
    if t["repeat"] is not None and t["due"] is None:
        raise Bad(400, "repeat needs due")
    return t


def new_id():
    while True:
        tid = "t%d" % counters["id"]
        counters["id"] += 1
        if tid not in known_ids:
            return tid


def fresh(user, fields):
    t = dict(fields, id=new_id(), _u=user, _p=counters["pos"])
    counters["pos"] += 1
    return t


def next_due(due, repeat):
    d = datetime.date.fromisoformat(due)
    if repeat == "daily":
        return (d + datetime.timedelta(days=1)).isoformat()
    if repeat == "weekly":
        return (d + datetime.timedelta(days=7)).isoformat()
    y, m = (d.year + 1, 1) if d.month == 12 else (d.year, d.month + 1)
    return datetime.date(y, m, min(d.day, calendar.monthrange(y, m)[1])).isoformat()


def own(user, tid):
    t = todos.get(tid)
    if not t or t["_u"] != user:
        raise Bad(404)
    return t


def user_todos(user):
    return sorted((t for t in todos.values() if t["_u"] == user), key=lambda t: t["_p"])


def int_param(qs, key, lo, hi, default):
    if key not in qs:
        return default
    try:
        v = int(qs[key][0])
    except ValueError:
        raise Bad(400)
    if v < lo or (hi is not None and v > hi):
        raise Bad(400)
    return v


# ---------------------------------------------------------------- routes

def handle(method, path, qs, user, body):
    parts = [p for p in path.split("/") if p]
    if parts == ["todos"] and method == "GET":
        items = user_todos(user)
        if "completed" in qs:
            c = qs["completed"][0]
            if c not in ("true", "false"):
                raise Bad(400)
            items = [t for t in items if t["completed"] == (c == "true")]
        if "due_before" in qs:
            d = v_date(qs["due_before"][0])
            items = [t for t in items if t["due"] is not None and t["due"] < d]
        if "tag" in qs:
            if not TAGS:
                raise Bad(400)
            items = [t for t in items if all(g in t["tags"] for g in qs["tag"])]
        if "q" in qs:
            needle = qs["q"][0].lower()
            items = [t for t in items if needle in t["title"].lower()]
        total = len(items)
        off = int_param(qs, "offset", 0, None, 0)
        lim = int_param(qs, "limit", 1, 1000, None)
        items = items[off:off + lim] if lim is not None else items[off:]
        return 200, [public(t) for t in items], {"X-Total-Count": str(total)}
    if parts == ["todos"] and method == "POST":
        t = fresh(user, build(body))
        mutate(user, puts=[t], changes=[("create", t["id"])])
        return 201, public(t), {}
    if parts == ["todos", "bulk"] and method == "POST":
        if not isinstance(body, list) or not 1 <= len(body) <= 1000:
            raise Bad(400)
        fields = [build(b) for b in body]
        made = [fresh(user, f) for f in fields]
        mutate(user, puts=made, changes=[("create", t["id"]) for t in made])
        return 201, [public(t) for t in made], {}
    if parts == ["todos"] and method == "DELETE":
        if qs.get("completed") != ["true"]:
            raise Bad(400)
        gone = [t["id"] for t in user_todos(user) if t["completed"]]
        mutate(user, dels=gone, changes=[("delete", i) for i in gone])
        return 200, {"deleted": len(gone)}, {}
    if len(parts) == 2 and parts[0] == "todos":
        t = own(user, parts[1])
        if method == "GET":
            return 200, public(t), {}
        if method == "DELETE":
            mutate(user, dels=[t["id"]], changes=[("delete", t["id"])])
            return 200, public(t), {}
        if method == "PATCH":
            nt = build(body, t)
            puts, changes = [nt], [("update", t["id"])]
            if nt["repeat"] and nt["completed"] and not t["completed"]:
                nxt = fresh(user, {"title": nt["title"], "completed": False, "repeat": nt["repeat"],
                                   "due": next_due(nt["due"], nt["repeat"]), "tags": nt.get("tags", [])})
                puts.append(nxt)
                changes.append(("create", nxt["id"]))
            mutate(user, puts=puts, changes=changes)
            return 200, public(nt), {}
    if parts == ["tags"] and method == "GET":
        if not TAGS:
            raise Bad(404)
        counts = {}
        for t in user_todos(user):
            for g in t["tags"]:
                counts[g] = counts.get(g, 0) + 1
        return 200, [{"tag": g, "count": c} for g, c in sorted(counts.items())], {}
    if parts == ["undo"] and method == "POST":
        u = U(user)
        if not u["undo"]:
            raise Bad(409)
        puts, dels, changes = [], [], []
        for tid, before in u["undo"][-1]:
            if before is None:
                if tid in todos:
                    dels.append(tid)
                    changes.append(("delete", tid))
            else:
                changes.append(("update" if tid in todos else "create", tid))
                puts.append(before)
        commit({"u": user, "puts": puts, "dels": dels, "changes": [list(c) for c in changes], "undo": "pop"})
        return 200, {"ok": True}, {}
    if parts == ["changes"] and method == "GET":
        since = int_param(qs, "since", 0, None, 0)
        ch = [c for c in U(user)["feed"] if c["seq"] > since]
        return 200, {"changes": ch, "next": ch[-1]["seq"] if ch else since}, {}
    if parts == ["export"] and method == "GET":
        return 200, {"version": 1, "todos": [public(t) for t in user_todos(user)]}, {}
    if parts == ["import"] and method == "POST":
        if not isinstance(body, dict) or body.get("version") != 1 or not isinstance(body.get("todos"), list):
            raise Bad(400)
        seen, made = set(), []
        for item in body["todos"]:
            if not isinstance(item, dict):
                raise Bad(400)
            tid = item.get("id")
            if not isinstance(tid, str) or not 1 <= len(tid) <= 128 or tid in seen:
                raise Bad(400)
            seen.add(tid)
            made.append((tid, build({k: v for k, v in item.items() if k != "id"})))
        for tid, _ in made:
            if tid in todos and todos[tid]["_u"] != user:
                raise Bad(409)
        old = [t["id"] for t in user_todos(user)]
        puts = []
        for tid, f in made:
            puts.append(dict(f, id=tid, _u=user, _p=counters["pos"]))
            counters["pos"] += 1
        mutate(user, puts=puts, dels=[i for i in old if i not in seen],
               changes=[("delete", i) for i in old] + [("create", t["id"]) for t in puts])
        return 200, {"imported": len(puts)}, {}
    raise Bad(404)


class H(BaseHTTPRequestHandler):
    def _go(self):
        url = urlparse(self.path)
        qs = parse_qs(url.query, keep_blank_values=True)
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n) if n else b""
        try:
            user = self.headers.get("X-User", "default")
            if not USER_RE.match(user):
                raise Bad(400)
            body = None
            if self.command in ("POST", "PATCH") and not url.path.rstrip("/").endswith("undo"):
                try:
                    body = json.loads(raw)
                except ValueError:
                    raise Bad(400)
            with lock:
                code, out, hdrs = handle(self.command, url.path, qs, user, body)
        except Bad as e:
            code, out, hdrs = e.code, {"error": str(e) or "error"}, {}
        data = json.dumps(out, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        for k, v in hdrs.items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    do_GET = do_POST = do_PATCH = do_DELETE = _go

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    load()
    ThreadingHTTPServer.daemon_threads = True
    ThreadingHTTPServer.request_queue_size = 128
    ThreadingHTTPServer(("127.0.0.1", 8080), H).serve_forever()
