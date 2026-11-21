import threading
import time
from harness import req, q, nonce, ids, restart, run


def main(t):
    n = nonce()
    u = "scale_" + n
    t0 = time.time()
    ok = all(req("POST", "/todos/bulk", [{"title": "item %d-%d %s" % (b, i, "needle" if i == 7 else "hay")} for i in range(1000)],
                 user=u, timeout=30).status == 201 for b in range(20))
    dt = time.time() - t0
    t.check("20 x 1000 bulk loads in < 10s (%.2fs)" % dt, ok and dt < 10)

    t0 = time.time()
    r = req("GET", "/todos", user=u, timeout=30)
    dt = time.time() - t0
    t.check("list 20k in < 1s (%.2fs)" % dt, dt < 1 and len(r.json or []) == 20000, len(r.json or []))

    t0 = time.time()
    r = req("GET", q("/todos", q="NEEDLE"), user=u, timeout=30)
    dt = time.time() - t0
    t.check("search 20k in < 0.5s (%.2fs)" % dt, dt < 0.5 and len(r.json or []) == 20, len(r.json or []))

    try:
        dt = restart(timeout=10)
    except RuntimeError as e:
        dt = 99
        t.check("restart with 20k todos succeeds", False, str(e))
    t.check("restart with 20k todos ready in < 3s (%.2fs)" % dt, dt < 3)

    t0 = time.time()
    for i in range(1000):
        req("POST", "/todos", {"title": "seq %d" % i}, user=u)
    dt = time.time() - t0
    t.check("1000 sequential creates at 20k in < 3s (%.2fs)" % dt, dt < 3)

    results = [None] * 50

    def worker(i):
        results[i] = req("POST", "/todos", {"title": "conc %d %s" % (i, n)}, user=u, timeout=20)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(50)]
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    got = [r.json.get("id") if r and isinstance(r.json, dict) else None for r in results]
    t.check("50 concurrent creates all return 201", all(r and r.status == 201 for r in results), [r.status if r else None for r in results])
    t.check("50 concurrent creates have distinct ids", len(set(got)) == 50 and None not in got)
    listed = set(ids(req("GET", q("/todos", q="conc"), user=u).json))
    t.check("all concurrent creates are listed", set(got) <= listed, len(listed))


run(main)
