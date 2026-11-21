from harness import req, q, nonce, ids, body_id, restart, run


def main(t):
    n = nonce()
    ua, ub = "ua_" + n, "ub-" + n
    a1 = body_id(req("POST", "/todos", {"title": "same " + n}, user=ua))
    a2 = body_id(req("POST", "/todos", {"title": "a only " + n}, user=ua))
    b1 = body_id(req("POST", "/todos", {"title": "same " + n}, user=ub))
    t.check("ids unique across users", len({a1, a2, b1}) == 3 and None not in (a1, a2, b1))

    r = req("GET", "/todos", user=ua)
    t.check("user A sees exactly their todos", ids(r.json) == [a1, a2], ids(r.json))
    t.check("X-Total-Count is per user", r.headers.get("x-total-count") == "2", r.headers.get("x-total-count"))
    t.check("user B sees exactly their todos", ids(req("GET", "/todos", user=ub).json) == [b1])
    t.check("search is per user", ids(req("GET", q("/todos", q="same " + n), user=ua).json) == [a1])
    t.check("default user does not see named users' todos",
            not set(ids(req("GET", q("/todos", q=n)).json)) & {a1, a2, b1})

    t.check("GET other user's todo is 404", req("GET", "/todos/%s" % a1, user=ub).status == 404)
    t.check("PATCH other user's todo is 404", req("PATCH", "/todos/%s" % a1, {"completed": True}, user=ub).status == 404)
    t.check("DELETE other user's todo is 404", req("DELETE", "/todos/%s" % a2, user=ub).status == 404)
    r = req("GET", "/todos/%s" % a1, user=ua)
    t.check("other user's PATCH did not apply", (r.json or {}).get("completed") is False, r.raw)
    t.check("other user's DELETE did not apply", req("GET", "/todos/%s" % a2, user=ua).status == 200)
    t.check("no-header request cannot reach named user's todo", req("GET", "/todos/%s" % a1).status == 404)

    for bad in ["has space", "x" * 65, "b@d", "é"]:
        r = req("GET", "/todos", headers={"X-User": bad.encode("utf-8").decode("latin-1")})
        t.check("400 on X-User=%r" % bad, r.status == 400, r.status)
    t.check("64-char user accepted", req("GET", "/todos", user="u" * 64).status == 200)

    restart()
    t.check("isolation persists across restart",
            ids(req("GET", "/todos", user=ua).json) == [a1, a2] and ids(req("GET", "/todos", user=ub).json) == [b1])


run(main)
