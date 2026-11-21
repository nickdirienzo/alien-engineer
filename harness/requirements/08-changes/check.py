from harness import req, q, nonce, ids, restart, run


def main(t):
    n = nonce()
    u = "feed_" + n
    r = req("GET", "/changes", user=u)
    t.check("GET /changes returns 200 with changes + next",
            r.status == 200 and isinstance(r.json, dict) and r.json.get("changes") == [] and isinstance(r.json.get("next"), int), r.raw)
    cur = (r.json or {}).get("next", 0)
    seen = []

    def pull():
        nonlocal cur
        r = req("GET", q("/changes", since=cur), user=u)
        ch = (r.json or {}).get("changes", [])
        cur = (r.json or {}).get("next", cur)
        seen.extend(ch)
        return [(c.get("op"), c.get("id")) for c in ch]

    a = req("POST", "/todos", {"title": "A"}, user=u).json["id"]
    t.check("create emits create", pull() == [("create", a)])
    req("PATCH", "/todos/%s" % a, {"completed": True}, user=u)
    t.check("patch emits update", pull() == [("update", a)])
    req("DELETE", "/todos/%s" % a, user=u)
    t.check("delete emits delete", pull() == [("delete", a)])
    req("POST", "/undo", user=u)
    t.check("undoing a delete emits create", pull() == [("create", a)])
    made = ids(req("POST", "/todos/bulk", [{"title": "x"}, {"title": "y"}], user=u).json)
    t.check("bulk emits one create per todo in order", pull() == [("create", made[0]), ("create", made[1])])
    req("POST", "/undo", user=u)
    t.check("undoing bulk emits deletes", sorted(pull()) == sorted([("delete", made[0]), ("delete", made[1])]))
    req("PATCH", "/todos/%s" % a, {"completed": True}, user=u)
    pull()
    req("DELETE", q("/todos", completed="true"), user=u)
    t.check("clear-completed emits delete per todo", pull() == [("delete", a)])
    t.check("polling with next returns nothing new", pull() == [])

    other = req("GET", "/changes", user="feed_other_" + n).json or {}
    t.check("feed is per user", other.get("changes") == [], other)

    seqs = [c.get("seq") for c in seen]
    t.check("seq strictly increasing", all(isinstance(s, int) for s in seqs) and seqs == sorted(set(seqs)), seqs)
    full = [c.get("seq") for c in (req("GET", "/changes", user=u).json or {}).get("changes", [])]
    t.check("since=0 returns the whole history", full == seqs, full)

    restart()
    b = req("POST", "/todos", {"title": "B"}, user=u).json["id"]
    after = pull()
    t.check("feed continues after restart with fresh seq", after == [("create", b)] and seen[-1]["seq"] > max(seqs))
    t.check("since=-1 returns 400", req("GET", q("/changes", since=-1), user=u).status == 400)
    t.check("since=abc returns 400", req("GET", q("/changes", since="abc"), user=u).status == 400)


run(main)
