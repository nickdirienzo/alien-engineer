"""Runs every active check against a fresh copy of the workspace.

Usage: python3 runner.py            (env: WORKSPACE, CHECKS_DIR, SPEC_SUMMARY)
Exit code 0 only if every check passed.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from collections import OrderedDict

LIB = os.path.dirname(os.path.abspath(__file__))
WORKSPACE = os.environ.get("WORKSPACE", "/experiment")
CHECKS_DIR = os.environ.get("CHECKS_DIR", "/sacred/checks")
SUMMARY = os.environ.get("SPEC_SUMMARY")
CHECK_TIMEOUT = int(os.environ.get("CHECK_TIMEOUT", "600"))


def main():
    tmp = tempfile.mkdtemp(prefix="todo-run-")
    run_dir = os.path.join(tmp, "app")
    results = os.path.join(tmp, "results.jsonl")
    os.environ["RUN_DIR"] = run_dir
    os.environ["RESULTS"] = results
    os.environ["PYTHONPATH"] = LIB
    sys.path.insert(0, LIB)
    import harness  # noqa: E402  (reads RUN_DIR at import)

    fatal = None
    from export import export_tree  # noqa: E402
    export_tree(WORKSPACE, run_dir)
    checks = sorted(f for f in os.listdir(CHECKS_DIR) if f.endswith(".py"))

    print("=== Spec check (%d requirements active) ===" % len(checks), flush=True)
    harness.hard_kill()
    entry = os.path.join(run_dir, harness.ENTRY)
    if not (os.path.isfile(entry) and os.access(entry, os.X_OK)):
        fatal = "%s is missing or not executable" % harness.ENTRY
    elif not os.path.isdir(os.path.join(run_dir, harness.APP)):
        fatal = "%s/ does not exist" % harness.APP
    else:
        try:
            harness.start()
        except (RuntimeError, OSError) as e:
            fatal = str(e)

    if not fatal:
        for c in checks:
            name = c[:-3]
            print("\n--- %s ---" % name, flush=True)
            try:
                harness.ensure_running()
            except RuntimeError as e:
                print("  (could not restart system: %s)" % e, flush=True)
            env = dict(os.environ, CHECK_NAME=name)
            try:
                subprocess.run([sys.executable, os.path.join(CHECKS_DIR, c)],
                               env=env, timeout=CHECK_TIMEOUT)
            except subprocess.TimeoutExpired:
                with open(results, "a") as f:
                    f.write(json.dumps({"check": name, "label": "finished within %ss" % CHECK_TIMEOUT, "ok": False}) + "\n")
                print("  ✗ timed out after %ss" % CHECK_TIMEOUT, flush=True)
        harness.stop()

    rows = []
    if os.path.exists(results):
        with open(results) as f:
            rows = [json.loads(l) for l in f if l.strip()]
    finished = {r["check"] for r in rows if r.get("done")}
    rows = [r for r in rows if not r.get("done")]
    for c in checks:  # a check that died without reporting completion fails
        if c[:-3] not in finished and not fatal:
            rows.append({"check": c[:-3], "label": "check script exited cleanly", "ok": False})
            print("  \u2717 %s: check script died before finishing" % c[:-3])
    per = OrderedDict((c[:-3], {"passed": 0, "total": 0}) for c in checks)
    for r in rows:
        p = per.setdefault(r["check"], {"passed": 0, "total": 0})
        p["total"] += 1
        p["passed"] += int(r["ok"])
    for name, p in per.items():
        if p["total"] == 0:  # a check that recorded nothing counts as failed
            p["total"] = 1
    failed = [n for n, p in per.items() if p["passed"] < p["total"]]
    passed = sum(p["passed"] for p in per.values())
    total = sum(p["total"] for p in per.values())
    if fatal:
        failed, passed, total = list(per), 0, max(total, 1)
        print("\nFATAL: %s" % fatal)
        if os.path.exists(harness.LOG_FILE):
            with open(harness.LOG_FILE, errors="replace") as f:
                tail = f.read()[-2000:]
            if tail.strip():
                print("--- system output (tail) ---\n" + tail)

    summary = {"passed": passed, "total": total, "failed_requirements": failed,
               "fatal": fatal, "per_requirement": per,
               "failed_labels": [r["check"] + ": " + r["label"] for r in rows if not r["ok"]]}
    if SUMMARY:
        with open(SUMMARY, "w") as f:
            json.dump(summary, f)
    shutil.rmtree(tmp, ignore_errors=True)
    for ext in (".pgid", ".log"):
        try:
            os.remove(run_dir + ext)
        except OSError:
            pass
    print("\n=== Results: %d/%d passed%s ===" % (passed, total,
          "" if not failed else "; failing: " + ", ".join(failed)))
    sys.exit(0 if not failed and not fatal else 1)


if __name__ == "__main__":
    main()
