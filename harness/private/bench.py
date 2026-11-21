"""Fixed performance benchmark. Uses only the base API (requirement 00), so
the numbers are comparable across every generation. Hidden from the agent.

env: WORKSPACE (copy to run from), BENCH_OUT (json path), PORT
"""

import json
import os
import shutil
import statistics
import sys
import tempfile
import time

N = int(os.environ.get("BENCH_N", "2000"))


def main():
    tmp = tempfile.mkdtemp(prefix="todo-bench-")
    run_dir = os.path.join(tmp, "app")
    os.environ["RUN_DIR"] = run_dir
    sys.path.insert(0, os.environ.get("HARNESS_LIB", "/sacred/lib"))
    import harness
    from export import export_tree
    export_tree(os.environ["WORKSPACE"], run_dir)

    out = {}
    try:
        harness.hard_kill()
        out["start_s"] = round(harness.start(), 3)
        lat = []
        t0 = time.time()
        for i in range(N):
            t1 = time.time()
            r = harness.req("POST", "/todos", {"title": "bench item %d" % i})
            lat.append(time.time() - t1)
            if r.status != 201:
                raise RuntimeError("create returned %s" % r.status)
        out["create_rps"] = round(N / (time.time() - t0))
        lat.sort()
        out["create_p50_ms"] = round(lat[len(lat) // 2] * 1000, 2)
        out["create_p99_ms"] = round(lat[int(len(lat) * 0.99)] * 1000, 2)
        times = []
        for _ in range(5):
            t1 = time.time()
            r = harness.req("GET", "/todos")
            times.append(time.time() - t1)
            if r.status != 200 or len(r.json or []) != N:
                raise RuntimeError("list returned %s with %s items" % (r.status, len(r.json or [])))
        out["list_ms"] = round(statistics.median(times) * 1000, 2)
        out["rss_mb"] = harness.group_rss_mb()
        out["restart_s"] = round(harness.restart(), 3)
    except Exception as e:  # noqa: BLE001
        out["error"] = "%s: %s" % (type(e).__name__, e)
    finally:
        harness.stop()
        shutil.rmtree(tmp, ignore_errors=True)
        for ext in (".pgid", ".log"):
            try:
                os.remove(run_dir + ext)
            except OSError:
                pass
    with open(os.environ["BENCH_OUT"], "w") as f:
        json.dump(out, f)


if __name__ == "__main__":
    main()
