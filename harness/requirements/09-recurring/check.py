from harness import req, q, nonce, ids, restart, run


def main(t):
    n = nonce()
    u = "rec_" + n

    def spawn(repeat, due):
        a = req("POST", "/todos", {"title": "%s %s" % (repeat, due), "repeat": repeat, "due": due}, user=u).json["id"]
        before = ids(req("GET", "/todos", user=u).json)
        r = req("PATCH", "/todos/%s" % a, {"completed": True}, user=u)
        after = req("GET", "/todos", user=u).json or []
        new = [x for x in after if str(x.get("id")) not in before]
        return a, r, new, after

    r = req("POST", "/todos", {"title": "x", "repeat": "daily"}, user=u)
    t.check("repeat without due returns 400", r.status == 400, r.status)
    t.check("invalid repeat returns 400", req("POST", "/todos", {"title": "x", "repeat": "hourly", "due": "2027-01-01"}, user=u).status == 400)
    r = req("POST", "/todos", {"title": "plain"}, user=u)
    t.check("repeat defaults to null", isinstance(r.json, dict) and "repeat" in r.json and r.json["repeat"] is None, r.raw)

    for repeat, due, expect in [("daily", "2026-12-31", "2027-01-01"), ("weekly", "2026-12-28", "2027-01-04"),
                                ("monthly", "2027-01-31", "2027-02-28"), ("monthly", "2028-01-31", "2028-02-29"),
                                ("monthly", "2027-12-15", "2028-01-15")]:
        a, r, new, after = spawn(repeat, due)
        t.check("PATCH returns the completed todo (%s)" % repeat,
                r.status == 200 and (r.json or {}).get("id") == a and (r.json or {}).get("completed") is True, r.raw)
        ok = (len(new) == 1 and new[0].get("due") == expect and new[0].get("repeat") == repeat
              and new[0].get("completed") is False and new[0].get("title") == "%s %s" % (repeat, due)
              and str(after[-1].get("id")) == str(new[0].get("id")))
        t.check("%s from %s spawns next occurrence due %s" % (repeat, due, expect), ok, new)

    a, _, new, _ = spawn("daily", "2027-05-05")
    before = ids(req("GET", "/todos", user=u).json)
    req("PATCH", "/todos/%s" % a, {"completed": True}, user=u)
    t.check("completing an already-completed todo spawns nothing", ids(req("GET", "/todos", user=u).json) == before)

    feed_from = req("GET", "/changes", user=u).json["next"]
    b = req("POST", "/todos", {"title": "undo me", "repeat": "weekly", "due": "2027-06-01"}, user=u).json["id"]
    snap = req("GET", "/todos", user=u).json
    feed_mid = req("GET", "/changes", user=u).json["next"]
    req("PATCH", "/todos/%s" % b, {"completed": True}, user=u)
    ops = sorted(c["op"] for c in req("GET", q("/changes", since=feed_mid), user=u).json["changes"])
    t.check("feed shows update + create for a recurrence", ops == ["create", "update"], ops)
    req("POST", "/undo", user=u)
    t.check("undo reverts completion and spawn in one step", req("GET", "/todos", user=u).json == snap)
    del feed_from

    t.check("clearing due on repeating todo returns 400", req("PATCH", "/todos/%s" % b, {"due": None}, user=u).status == 400)
    t.check("repeat can be turned off", (req("PATCH", "/todos/%s" % b, {"repeat": None}, user=u).json or {}).get("repeat", "x") is None)
    restart()
    t.check("repeat persists across restart", (req("GET", "/todos/%s" % a, user=u).json or {}).get("repeat") == "daily")


run(main)
