import threading
import time
from harness import req, nonce, ids, hard_kill, start, run


def crash():
    hard_kill()
    start()


def main(t):
    n = nonce()
    u = "crash_" + n

    a = req("POST", "/todos", {"title": "A"}, user=u).json["id"]
    crash()
    t.check("create survives SIGKILL", ids(req("GET", "/todos", user=u).json) == [a])

    req("PATCH", "/todos/%s" % a, {"completed": True, "title": "A2"}, user=u)
    crash()
    r = req("GET", "/todos/%s" % a, user=u).json or {}
    t.check("update survives SIGKILL", r.get("completed") is True and r.get("title") == "A2", r)

    b = req("POST", "/todos", {"title": "B"}, user=u).json["id"]
    req("DELETE", "/todos/%s" % b, user=u)
    crash()
    t.check("delete survives SIGKILL", ids(req("GET", "/todos", user=u).json) == [a])
    req("POST", "/undo", user=u)
    t.check("undo history survives SIGKILL", ids(req("GET", "/todos", user=u).json) == [a, b])
    crash()
    t.check("undo result survives SIGKILL", ids(req("GET", "/todos", user=u).json) == [a, b])
    feed = [(c.get("op"), c.get("id")) for c in (req("GET", "/changes", user=u).json or {}).get("changes", [])]
    t.check("change feed survives SIGKILL",
            feed == [("create", a), ("update", a), ("create", b), ("delete", b), ("create", b)], feed)

    acked, stop = [], False

    def writer():
        i = 0
        while not stop:
            if i % 5 == 0:
                r = req("POST", "/todos/bulk", [{"title": "bulk%d-%d" % (i, k)} for k in range(50)], user=u, timeout=2)
                if r.status == 201:
                    acked.extend(ids(r.json))
            else:
                r = req("POST", "/todos", {"title": "burst %d" % i}, user=u, timeout=2)
                if r.status == 201:
                    acked.append(r.json["id"])
            i += 1

    th = threading.Thread(target=writer)
    th.start()
    time.sleep(0.7)
    hard_kill()
    stop = True
    th.join()
    try:
        start()
        restarted = True
    except RuntimeError:
        restarted = False
    t.check("system restarts after mid-write SIGKILL", restarted)
    todos = req("GET", "/todos", user=u).json or []
    present = set(ids(todos))
    t.check("every acknowledged write survived (%d acked)" % len(acked), len(acked) > 0 and set(acked) <= present,
            len(set(acked) - present))
    groups = {}
    for x in todos:
        title = str(x.get("title", ""))
        if title.startswith("bulk"):
            groups.setdefault(title.split("-")[0], 0)
            groups[title.split("-")[0]] += 1
    t.check("no half-applied bulk creates", all(c == 50 for c in groups.values()), groups)
    t.check("system still works after crash recovery", req("POST", "/todos", {"title": "after"}, user=u).status == 201)


run(main)
