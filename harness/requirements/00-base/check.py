import time
from harness import req, q, nonce, find, ids, body_id, restart, run


def main(t):
    n = nonce()
    r = req("POST", "/todos", {"title": "buy milk " + n})
    t.check("POST /todos returns 201", r.status == 201, r.status)
    a = body_id(r)
    t.check("response has a string id", isinstance(a, str) and a, r.raw)
    t.check("response has the title", isinstance(r.json, dict) and r.json.get("title") == "buy milk " + n, r.raw)
    t.check("response has completed=false", isinstance(r.json, dict) and r.json.get("completed") is False, r.raw)

    b = body_id(req("POST", "/todos", {"title": "walk dog " + n}))
    t.check("ids are unique", a != b)

    r = req("GET", "/todos")
    t.check("GET /todos returns 200 and an array", r.status == 200 and isinstance(r.json, list), r.raw)
    t.check("list contains created todos", a in ids(r.json) and b in ids(r.json))

    r = req("PATCH", "/todos/" + a, {"completed": True})
    t.check("PATCH completed returns 200", r.status == 200, r.status)
    t.check("completed state visible in list", (find(req("GET", "/todos").json, a) or {}).get("completed") is True)

    r = req("DELETE", "/todos/" + b)
    t.check("DELETE returns 200", r.status == 200, r.status)
    t.check("deleted todo not in list", b not in ids(req("GET", "/todos").json))

    c = body_id(req("POST", "/todos", {"title": "incomplete " + n}))
    done = req("GET", q("/todos", completed="true")).json
    t.check("completed=true returns only completed",
            isinstance(done, list) and all(x.get("completed") is True for x in done) and a in ids(done), done)
    todo = req("GET", q("/todos", completed="false")).json
    t.check("completed=false returns only incomplete",
            isinstance(todo, list) and all(x.get("completed") is False for x in todo)
            and c in ids(todo) and a not in ids(todo), todo)

    before = sorted(ids(req("GET", "/todos").json))
    restart()
    after = req("GET", "/todos").json
    t.check("todos survive restart", sorted(ids(after)) == before and len(before) > 0)
    t.check("completed state survives restart", (find(after, a) or {}).get("completed") is True)

    t0 = time.time()
    for i in range(1000):
        req("POST", "/todos", {"title": "perf %d %s" % (i, n)})
    r = req("GET", "/todos")
    dt = time.time() - t0
    t.check("1000 creates + list in < 5s (%.2fs)" % dt, dt < 5 and r.status == 200)


run(main)
