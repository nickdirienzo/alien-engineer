import json
from harness import req, nonce, ids, body_id, restart, run

WEIRD = "\U0001F984 ünïcödé 中文 עברית \"q\" \\back\\ new\nline\ttab  "


def main(t):
    n = nonce()
    count = lambda: len(req("GET", "/todos").json or [])  # noqa: E731
    base = count()

    for label, raw in [("missing title", "{}"), ("empty title", '{"title": ""}'),
                       ("whitespace title", '{"title": "  \\t\\n "}'), ("numeric title", '{"title": 5}'),
                       ("null title", '{"title": null}'), ("array body", '["x"]'),
                       ("invalid JSON", '{"title": "x"'), ("empty body", "")]:
        r = req("POST", "/todos", raw=raw)
        t.check("400 on %s" % label, r.status == 400, r.status)
    t.check("nothing created by invalid posts", count() == base)

    r = req("POST", "/todos", {"title": WEIRD + n})
    a = body_id(r)
    t.check("unicode title (escaped JSON) returns 201", r.status == 201, r.status)
    t.check("unicode title echoed exactly", isinstance(r.json, dict) and r.json.get("title") == WEIRD + n, r.raw)
    r = req("POST", "/todos", raw=json.dumps({"title": WEIRD + n}, ensure_ascii=False).encode("utf-8"))
    b = body_id(r)
    t.check("unicode title (raw UTF-8) echoed exactly", isinstance(r.json, dict) and r.json.get("title") == WEIRD + n, r.raw)

    r = req("GET", "/todos/%s" % a)
    t.check("GET /todos/:id returns 200 + todo", r.status == 200 and isinstance(r.json, dict) and r.json.get("id") == a, r.raw)
    t.check("GET /todos/:id has exact title", isinstance(r.json, dict) and r.json.get("title") == WEIRD + n)
    t.check("GET /todos/:id has completed=false", isinstance(r.json, dict) and r.json.get("completed") is False)

    emoji1000 = "\U0001F600" * 1000
    r = req("POST", "/todos", {"title": emoji1000})
    t.check("1000-code-point emoji title accepted", r.status == 201 and (r.json or {}).get("title") == emoji1000, r.status)
    long_id = body_id(r)
    r = req("POST", "/todos", {"title": "x" * 1001})
    t.check("1001-character title rejected with 400", r.status == 400, r.status)

    r = req("PATCH", "/todos/%s" % a, {"completed": "yes"})
    t.check("PATCH non-boolean completed returns 400", r.status == 400, r.status)
    t.check("todo unchanged after bad PATCH", (req("GET", "/todos/%s" % a).json or {}).get("completed") is False)

    ghost = "does-not-exist-" + n
    t.check("GET unknown id returns 404", req("GET", "/todos/" + ghost).status == 404)
    t.check("PATCH unknown id returns 404", req("PATCH", "/todos/" + ghost, {"completed": True}).status == 404)
    t.check("DELETE unknown id returns 404", req("DELETE", "/todos/" + ghost).status == 404)
    req("DELETE", "/todos/%s" % b)
    t.check("GET deleted id returns 404", req("GET", "/todos/%s" % b).status == 404)
    t.check("DELETE deleted id returns 404", req("DELETE", "/todos/%s" % b).status == 404)

    restart()
    r = req("GET", "/todos/%s" % a)
    t.check("unicode title exact after restart", isinstance(r.json, dict) and r.json.get("title") == WEIRD + n, r.raw)
    t.check("long emoji title exact after restart", (req("GET", "/todos/%s" % long_id).json or {}).get("title") == emoji1000)
    t.check("deleted todo still gone after restart", b not in ids(req("GET", "/todos").json))


run(main)
