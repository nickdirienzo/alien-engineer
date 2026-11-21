from harness import req, q, nonce, ids, restart, run


def main(t):
    n = nonce()
    u, other = "bulk_" + n, "bulk2_" + n
    keep = req("POST", "/todos", {"title": "other user's done todo"}, user=other).json["id"]
    req("PATCH", "/todos/%s" % keep, {"completed": True}, user=other)

    r = req("POST", "/todos/bulk", [{"title": "b1"}, {"title": "b2", "due": "2027-03-01"}, {"title": "b3"}], user=u)
    made = ids(r.json)
    t.check("bulk returns 201", r.status == 201, r.status)
    t.check("bulk returns todos in order", [x.get("title") for x in r.json or []] == ["b1", "b2", "b3"], r.raw)
    t.check("bulk items get full fields", isinstance(r.json, list) and len(r.json) == 3 and r.json[1].get("due") == "2027-03-01"
            and all(x.get("completed") is False for x in r.json), r.raw)
    t.check("bulk todos listed in creation order", ids(req("GET", "/todos", user=u).json) == made)

    for label, body in [("one invalid item", [{"title": "ok"}, {"title": ""}]), ("empty array", []),
                        ("non-array", {"title": "x"}), ("1001 items", [{"title": "t"}] * 1001)]:
        t.check("400 on %s" % label, req("POST", "/todos/bulk", body, user=u).status == 400)
    t.check("failed bulk creates nothing", len(req("GET", "/todos", user=u).json or []) == 3)

    r = req("POST", "/todos/bulk", [{"title": "m%d" % i} for i in range(1000)], user=u)
    t.check("1000-item bulk accepted", r.status == 201 and len(r.json or []) == 1000, r.status)

    req("PATCH", "/todos/%s" % made[0], {"completed": True}, user=u)
    req("PATCH", "/todos/%s" % made[2], {"completed": True}, user=u)
    t.check("DELETE /todos without filter returns 400", req("DELETE", "/todos", user=u).status == 400)
    t.check("DELETE /todos?completed=false returns 400", req("DELETE", q("/todos", completed="false"), user=u).status == 400)
    r = req("DELETE", q("/todos", completed="true"), user=u)
    t.check("clear completed returns {deleted: 2}", r.status == 200 and r.json == {"deleted": 2}, r.raw)
    left = ids(req("GET", "/todos", user=u).json)
    t.check("only incomplete todos remain", made[1] in left and made[0] not in left and made[2] not in left and len(left) == 1001)
    t.check("other users' completed todos untouched", req("GET", "/todos/%s" % keep, user=other).status == 200)

    restart()
    t.check("bulk + clear persist across restart", len(req("GET", "/todos", user=u).json or []) == 1001)


run(main)
