from harness import req, q, nonce, ids, restart, run


def todos(u):
    return req("GET", "/todos", user=u).json


def main(t):
    n = nonce()
    u, v = "exp_" + n, "imp_" + n
    req("POST", "/todos", {"title": "one", "due": "2027-02-01", "repeat": "monthly"}, user=u)
    two = req("POST", "/todos", {"title": "two \U0001F984"}, user=u).json["id"]
    req("POST", "/todos", {"title": "three"}, user=u)
    req("PATCH", "/todos/%s" % two, {"completed": True}, user=u)

    r = req("GET", "/export", user=u)
    exp = r.json
    t.check("export returns version 1 + todos", r.status == 200 and isinstance(exp, dict) and exp.get("version") == 1, r.raw)
    t.check("export equals list in order", isinstance(exp, dict) and exp.get("todos") == todos(u))

    req("DELETE", "/todos/%s" % two, user=u)
    req("POST", "/todos", {"title": "four"}, user=u)
    mutated = todos(u)
    feed_at = req("GET", "/changes", user=u).json["next"]
    r = req("POST", "/import", exp, user=u)
    t.check("import returns {imported: 3}", r.status == 200 and r.json == {"imported": 3}, r.raw)
    t.check("import replaces todos exactly", todos(u) == exp["todos"], todos(u))
    ops = [(c["op"]) for c in req("GET", q("/changes", since=feed_at), user=u).json["changes"]]
    t.check("import emits deletes for old + creates for new", sorted(ops) == ["create"] * 3 + ["delete"] * 3, ops)

    req("POST", "/undo", user=u)
    t.check("undo import restores previous set", todos(u) == mutated, todos(u))
    req("POST", "/import", exp, user=u)

    t.check("importing another user's ids returns 409", req("POST", "/import", exp, user=v).status == 409)
    t.check("409 import changes nothing", todos(v) == [])

    fresh = {"version": 1, "todos": [{"id": "imp-%s-%d" % (n, i), "title": "f%d" % i, "completed": False,
                                      "due": None, "repeat": None} for i in range(3)]}
    r = req("POST", "/import", fresh, user=v)
    t.check("import with new ids accepted", r.status == 200 and ids(todos(v)) == ["imp-%s-%d" % (n, i) for i in range(3)], r.raw)
    new = req("POST", "/todos", {"title": "after import"}, user=v).json["id"]
    t.check("new ids never collide with imported ids", new not in ids(fresh["todos"]))

    before = todos(v)
    for label, body in [("duplicate ids", {"version": 1, "todos": [fresh["todos"][0], fresh["todos"][0]]}),
                        ("invalid todo", {"version": 1, "todos": [{"id": "x-" + n, "title": "", "completed": False, "due": None, "repeat": None}]}),
                        ("long id", {"version": 1, "todos": [dict(fresh["todos"][0], id="i" * 129)]}),
                        ("not an object", [1, 2])]:
        t.check("400 on %s" % label, req("POST", "/import", body, user=v).status == 400)
    t.check("failed imports change nothing", todos(v) == before)

    restart()
    t.check("import persists across restart", todos(u) == exp["todos"])


run(main)
