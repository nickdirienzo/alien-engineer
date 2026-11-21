"""Shared helpers for requirement checks.

Each check script is run as its own process by runner.py with:
  RUN_DIR      fresh copy of the workspace the system runs from
  RESULTS      JSONL file that check results are appended to
  CHECK_NAME   requirement id (e.g. 03-tags)
"""

import http.client
import json
import os
import signal
import socket
import subprocess
import sys
import time
import urllib.parse
import uuid
from collections import namedtuple

HOST = "127.0.0.1"
PORT = int(os.environ.get("PORT", "8080"))
RUN_DIR = os.environ.get("RUN_DIR", "")
PGID_FILE = RUN_DIR + ".pgid"
ENTRY = os.environ.get("APP_ENTRY", "lang/run")   # the agent's toolchain
APP = os.environ.get("APP_DIR", "apps/todo")      # the program it runs
LOG_FILE = RUN_DIR + ".log"

Resp = namedtuple("Resp", "status json headers raw")


# --------------------------------------------------------------------------
# HTTP
# --------------------------------------------------------------------------

def req(method, path, body=None, user=None, raw=None, headers=None, timeout=10):
    """One request on a fresh connection. status 0 means connection failure."""
    h = {}
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        h["Content-Type"] = "application/json"
    if raw is not None:
        data = raw if isinstance(raw, bytes) else raw.encode()
        h["Content-Type"] = "application/json"
    if user is not None:
        h["X-User"] = user
    h.update(headers or {})
    conn = http.client.HTTPConnection(HOST, PORT, timeout=timeout)
    try:
        conn.request(method, path, body=data, headers=h)
        r = conn.getresponse()
        b = r.read()
        status = r.status
        hdrs = {k.lower(): v for k, v in r.getheaders()}
    except Exception as e:  # noqa: BLE001
        return Resp(0, None, {}, str(e).encode())
    finally:
        conn.close()
    try:
        j = json.loads(b) if b else None
    except ValueError:
        j = None
    return Resp(status, j, hdrs, b)


def q(path, *pairs, **params):
    """Build a path with a query string. pairs allows repeated keys."""
    items = list(pairs) + list(params.items())
    return path + ("?" + urllib.parse.urlencode(items) if items else "")


def nonce():
    return uuid.uuid4().hex[:10]


def find(todos, tid):
    if not isinstance(todos, list):
        return None
    for t in todos:
        if isinstance(t, dict) and str(t.get("id")) == str(tid):
            return t
    return None


def ids(todos):
    if not isinstance(todos, list):
        return []
    return [str(t.get("id")) for t in todos if isinstance(t, dict)]


def body_id(r):
    return r.json.get("id") if isinstance(r.json, dict) else None


# --------------------------------------------------------------------------
# Process control
# --------------------------------------------------------------------------

def _port_open():
    s = socket.socket()
    s.settimeout(0.2)
    try:
        s.connect((HOST, PORT))
        return True
    except OSError:
        return False
    finally:
        s.close()


def hard_kill():
    """SIGKILL the system: its process group, then anything on the port."""
    try:
        with open(PGID_FILE) as f:
            os.killpg(int(f.read().strip()), signal.SIGKILL)
    except (OSError, ValueError):
        pass
    try:
        out = subprocess.run(["lsof", "-ti", "tcp:%d" % PORT, "-sTCP:LISTEN"], capture_output=True, text=True).stdout
        for pid in out.split():
            try:
                os.kill(int(pid), signal.SIGKILL)
            except (OSError, ValueError):
                pass
    except OSError:
        pass
    deadline = time.time() + 5
    while _port_open() and time.time() < deadline:
        time.sleep(0.05)


def stop():
    """Graceful stop: SIGTERM the process group, wait up to 5s, then SIGKILL."""
    try:
        with open(PGID_FILE) as f:
            os.killpg(int(f.read().strip()), signal.SIGTERM)
        deadline = time.time() + 5
        while _port_open() and time.time() < deadline:
            time.sleep(0.05)
    except (OSError, ValueError):
        pass
    hard_kill()


def start(timeout=10):
    """Run `lang/run apps/todo` and wait until GET /todos answers. Returns seconds taken."""
    t0 = time.time()
    log = open(LOG_FILE, "ab")
    p = subprocess.Popen([os.path.join(RUN_DIR, ENTRY), APP], cwd=RUN_DIR, env=dict(os.environ, PORT=str(PORT)), stdin=subprocess.DEVNULL,
                         stdout=log, stderr=log, start_new_session=True)
    with open(PGID_FILE, "w") as f:
        f.write(str(p.pid))
    while time.time() - t0 < timeout:
        if req("GET", "/todos", timeout=2).status:
            return time.time() - t0
        time.sleep(0.05)
    raise RuntimeError("system did not answer GET /todos within %ss of `%s %s`" % (timeout, ENTRY, APP))


def group_rss_mb():
    """Resident memory of the system's process group, in MB."""
    try:
        with open(PGID_FILE) as f:
            pgid = f.read().strip()
        out = subprocess.run(["ps", "-eo", "pgid=,rss="], capture_output=True, text=True).stdout
        return round(sum(int(l.split()[1]) for l in out.splitlines() if l.split() and l.split()[0] == pgid) / 1024, 1)
    except (OSError, ValueError, IndexError):
        return None


def restart(graceful=True, timeout=10):
    stop() if graceful else hard_kill()
    return start(timeout=timeout)


def ensure_running():
    if not req("GET", "/todos", timeout=2).status:
        start()


# --------------------------------------------------------------------------
# Result recording
# --------------------------------------------------------------------------

class Checker:
    def __init__(self):
        self.name = os.environ.get("CHECK_NAME", os.path.basename(sys.argv[0]))
        self.results_path = os.environ.get("RESULTS")

    def check(self, label, cond, detail=None):
        ok = bool(cond)
        line = ("  ✓ " if ok else "  ✗ ") + label
        if not ok and detail is not None:
            d = detail if isinstance(detail, str) else repr(detail)
            line += "   [got: %s]" % d[:300]
        print(line, flush=True)
        if self.results_path:
            with open(self.results_path, "a") as f:
                f.write(json.dumps({"check": self.name, "label": label, "ok": ok}) + "\n")
        return ok


def run(main):
    """Entry point for check scripts. An exception counts as one failed check."""
    t = Checker()
    try:
        main(t)
    except Exception as e:  # noqa: BLE001
        t.check("check script ran to completion", False, "%s: %s" % (type(e).__name__, e))
    if t.results_path:
        with open(t.results_path, "a") as f:
            f.write(json.dumps({"check": t.name, "done": True}) + "\n")
