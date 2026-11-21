from harness import req, q, nonce, ids, body_id, restart, run


def main(t):
    n = nonce()
    titles = ["Alpha %s one" % n, "beta %s TWO" % n, "GAMMA %s three" % n, "delta %s four" % n, "Epsilon %s five" % n]
    made = [body_id(req("POST", "/todos", {"title": s})) for s in titles]
    noise = body_id(req("POST", "/todos", {"title": "unrelated noise"}))

    r = req("GET", q("/todos", q=n.upper()))
    t.check("q is case-insensitive and returns creation order", ids(r.json) == made, ids(r.json))
    t.check("X-Total-Count present", r.headers.get("x-total-count") == "5", r.headers.get("x-total-count"))
    t.check("q excludes non-matching", noise not in ids(r.json))
    t.check("q is a substring match", ids(req("GET", q("/todos", q="ta %s tw" % n)).json) == [made[1]])
    t.check("q treats regex characters literally", ids(req("GET", q("/todos", q=n + ".*")).json) == [])

    r = req("GET", q("/todos", q=n, limit=2, offset=1))
    t.check("limit/offset page the results", ids(r.json) == made[1:3], ids(r.json))
    t.check("X-Total-Count ignores paging", r.headers.get("x-total-count") == "5", r.headers.get("x-total-count"))
    t.check("offset past end returns []", req("GET", q("/todos", q=n, offset=50)).json == [])

    req("PATCH", "/todos/%s" % made[0], {"completed": True, "title": "Alpha %s one edited" % n})
    r = req("GET", q("/todos", q=n))
    t.check("updates do not reorder", ids(r.json) == made, ids(r.json))
    r = req("GET", q("/todos", q=n, completed="false", limit=1))
    t.check("q + completed + limit combine", ids(r.json) == [made[1]] and r.headers.get("x-total-count") == "4", (ids(r.json), r.headers.get("x-total-count")))

    for label, params in [("limit=0", {"limit": 0}), ("limit=1001", {"limit": 1001}),
                          ("offset=-1", {"offset": -1}), ("limit=abc", {"limit": "abc"})]:
        t.check("400 on %s" % label, req("GET", q("/todos", **params)).status == 400)

    all_ids = ids(req("GET", "/todos").json)
    restart()
    t.check("full list order identical after restart", ids(req("GET", "/todos").json) == all_ids)
    t.check("search order identical after restart", ids(req("GET", q("/todos", q=n)).json) == made)


run(main)
