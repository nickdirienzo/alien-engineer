from harness import req, q, nonce, restart, run


def main(t):
    n = nonce()
    u = "notags_" + n
    r = req("POST", "/todos", {"title": "x"}, user=u)
    a = r.json["id"] if isinstance(r.json, dict) else None
    t.check("todos have no tags field", isinstance(r.json, dict) and "tags" not in r.json, r.raw)
    t.check("POST with tags returns 400", req("POST", "/todos", {"title": "y", "tags": ["a"]}, user=u).status == 400)
    t.check("POST with empty tags returns 400", req("POST", "/todos", {"title": "y", "tags": []}, user=u).status == 400)
    t.check("PATCH with tags returns 400", req("PATCH", "/todos/%s" % a, {"tags": ["a"]}, user=u).status == 400)
    t.check("bulk item with tags returns 400", req("POST", "/todos/bulk", [{"title": "z", "tags": ["a"]}], user=u).status == 400)
    t.check("GET /tags returns 404", req("GET", "/tags", user=u).status == 404)
    t.check("GET /todos?tag= returns 400", req("GET", q("/todos", tag="a"), user=u).status == 400)
    t.check("no listed todo has tags", all("tags" not in x for x in (req("GET", "/todos").json or [])))
    t.check("only valid todos were created", len(req("GET", "/todos", user=u).json or []) == 1)
    restart()
    r = req("GET", "/todos/%s" % a, user=u)
    t.check("still no tags after restart", isinstance(r.json, dict) and "tags" not in r.json, r.raw)


run(main)
