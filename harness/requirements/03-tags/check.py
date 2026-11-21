from harness import req, q, nonce, ids, body_id, restart, run


def tagcounts(prefix):
    r = req("GET", "/tags")
    if not isinstance(r.json, list):
        return None
    return {x.get("tag"): x.get("count") for x in r.json if isinstance(x, dict) and str(x.get("tag", "")).startswith(prefix)}


def main(t):
    n = nonce()
    A, B = "a-" + n, "b-" + n
    r = req("POST", "/todos", {"title": "plain " + n})
    t.check("new todo has tags=[]", isinstance(r.json, dict) and r.json.get("tags") == [], r.raw)

    r = req("POST", "/todos", {"title": "one " + n, "tags": [B, A, B]})
    one = body_id(r)
    t.check("tags deduplicated and sorted", (r.json or {}).get("tags") == [A, B], r.raw)
    two = body_id(req("POST", "/todos", {"title": "two " + n, "tags": [A]}))
    three = body_id(req("POST", "/todos", {"title": "three " + n, "tags": [B]}))

    for bad in [["Upper"], ["has space"], ["x" * 33], [""], [5], "a-tag", ["ok", "b@d"]]:
        r = req("POST", "/todos", {"title": "bad " + n, "tags": bad})
        t.check("400 on tags=%r" % (bad,), r.status == 400, r.status)
    t.check("longest valid tag accepted", req("POST", "/todos", {"title": "long " + n, "tags": ["z" * 32]}).status == 201)

    got = ids(req("GET", q("/todos", tag=A)).json)
    t.check("?tag filters", one in got and two in got and three not in got, got)
    got = ids(req("GET", q("/todos", ("tag", A), ("tag", B))).json)
    t.check("repeated ?tag requires all tags", got == [one], got)
    req("PATCH", "/todos/%s" % two, {"completed": True})
    got = ids(req("GET", q("/todos", tag=A, completed="true")).json)
    t.check("?tag combines with completed", got == [two], got)

    r = req("GET", "/tags")
    t.check("GET /tags returns 200 + array", r.status == 200 and isinstance(r.json, list), r.raw)
    tags = [x.get("tag") for x in r.json or [] if isinstance(x, dict)]
    t.check("GET /tags sorted by tag", tags == sorted(tags), tags)
    t.check("GET /tags counts", tagcounts(n[:0] + "a-" + n) == {A: 2} and tagcounts("b-" + n) == {B: 2})

    r = req("PATCH", "/todos/%s" % one, {"tags": [B]})
    t.check("PATCH replaces tag set", (r.json or {}).get("tags") == [B], r.raw)
    r = req("PATCH", "/todos/%s" % one, {"tags": ["NOPE"]})
    t.check("PATCH invalid tags returns 400", r.status == 400, r.status)
    t.check("tags unchanged after bad PATCH", (req("GET", "/todos/%s" % one).json or {}).get("tags") == [B])
    t.check("counts follow PATCH", tagcounts("a-" + n) == {A: 1} and tagcounts("b-" + n) == {B: 2})

    req("DELETE", "/todos/%s" % two)
    t.check("tag with zero todos disappears from /tags", tagcounts("a-" + n) == {})

    restart()
    t.check("tags persist across restart", (req("GET", "/todos/%s" % three).json or {}).get("tags") == [B])
    t.check("/tags correct after restart", tagcounts("b-" + n) == {B: 2})


run(main)
