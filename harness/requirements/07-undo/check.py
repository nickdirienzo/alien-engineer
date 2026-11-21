from harness import req, q, nonce, ids, restart, run


def snapshot(u):
    return req("GET", "/todos", user=u).json


def main(t):
    n = nonce()
    u, u2 = "undo_" + n, "undo2_" + n
    t.check("undo with no history returns 409", req("POST", "/undo", user=u).status == 409)

    a = req("POST", "/todos", {"title": "A", "due": "2027-01-01"}, user=u).json["id"]
    b = req("POST", "/todos", {"title": "B"}, user=u).json["id"]
    s_ab = snapshot(u)
    req("PATCH", "/todos/%s" % a, {"completed": True, "title": "A2", "due": None}, user=u)
    s_patched = snapshot(u)
    req("DELETE", "/todos/%s" % b, user=u)

    t.check("other user's undo does not touch this user", req("POST", "/undo", user=u2).status == 409)
    r = req("POST", "/undo", user=u)
    t.check("undo returns 200", r.status == 200, r.status)
    t.check("undo delete restores todo with same id, fields and position", snapshot(u) == s_patched, snapshot(u))
    req("POST", "/undo", user=u)
    t.check("undo patch restores every field", snapshot(u) == s_ab, snapshot(u))
    req("POST", "/undo", user=u)
    t.check("undo create removes the todo", ids(snapshot(u)) == [a])
    req("POST", "/undo", user=u)
    t.check("undo first create leaves nothing", snapshot(u) == [])
    t.check("history exhausted returns 409", req("POST", "/undo", user=u).status == 409)

    made = ids(req("POST", "/todos/bulk", [{"title": "x%d" % i} for i in range(4)], user=u).json)
    req("PATCH", "/todos/%s" % made[1], {"completed": True}, user=u)
    req("PATCH", "/todos/%s" % made[3], {"completed": True}, user=u)
    before_clear = snapshot(u)
    req("DELETE", q("/todos", completed="true"), user=u)
    req("POST", "/undo", user=u)
    t.check("clear-completed undoes as one step, positions restored", snapshot(u) == before_clear, snapshot(u))
    req("POST", "/undo", user=u)
    req("POST", "/undo", user=u)
    req("POST", "/undo", user=u)
    t.check("bulk create undoes as one step", snapshot(u) == [], snapshot(u))

    c = req("POST", "/todos", {"title": "C"}, user=u).json["id"]
    d = req("POST", "/todos", {"title": "D"}, user=u).json["id"]
    restart()
    req("POST", "/undo", user=u)
    t.check("undo history survives restart", ids(snapshot(u)) == [c], ids(snapshot(u)))

    for i in range(105):
        req("POST", "/todos", {"title": "h%d" % i}, user=u2)
    ok = all(req("POST", "/undo", user=u2).status == 200 for _ in range(100))
    t.check("at least 100 steps of history", ok and len(snapshot(u2)) == 5)
    del d


run(main)
