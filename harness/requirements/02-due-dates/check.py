from harness import req, q, nonce, ids, body_id, restart, run


def main(t):
    n = nonce()
    r = req("POST", "/todos", {"title": "plain " + n})
    plain = body_id(r)
    t.check("new todo has due=null", isinstance(r.json, dict) and "due" in r.json and r.json["due"] is None, r.raw)

    r = req("POST", "/todos", {"title": "leap " + n, "due": "2024-02-29"})
    leap = body_id(r)
    t.check("create with valid leap-day due returns 201", r.status == 201 and (r.json or {}).get("due") == "2024-02-29", r.raw)
    late = body_id(req("POST", "/todos", {"title": "late " + n, "due": "2031-06-15"}))

    for bad in ["2025-02-29", "2024-13-01", "2024-1-05", "20240105", "tomorrow", 20240105, "2024-02-30", ""]:
        r = req("POST", "/todos", {"title": "bad " + n, "due": bad})
        t.check("400 on due=%r" % (bad,), r.status == 400, r.status)
    t.check("no todos created by bad dues",
            not any((x.get("title") == "bad " + n) for x in (req("GET", "/todos").json or [])))

    r = req("PATCH", "/todos/%s" % plain, {"title": "renamed " + n})
    t.check("PATCH title returns 200 with updated todo",
            r.status == 200 and isinstance(r.json, dict) and r.json.get("title") == "renamed " + n and r.json.get("id") == plain, r.raw)
    t.check("PATCH title leaves due untouched", (r.json or {}).get("due") is None)
    r = req("PATCH", "/todos/%s" % plain, {"title": "   "})
    t.check("PATCH whitespace title returns 400", r.status == 400, r.status)
    t.check("title unchanged after bad PATCH", (req("GET", "/todos/%s" % plain).json or {}).get("title") == "renamed " + n)

    r = req("PATCH", "/todos/%s" % plain, {"due": "2026-12-25"})
    t.check("PATCH due returns updated todo", (r.json or {}).get("due") == "2026-12-25" and (r.json or {}).get("title") == "renamed " + n, r.raw)
    r = req("PATCH", "/todos/%s" % plain, {"due": "2026-02-31"})
    t.check("PATCH invalid due returns 400", r.status == 400, r.status)
    t.check("due unchanged after bad PATCH", (req("GET", "/todos/%s" % plain).json or {}).get("due") == "2026-12-25")

    r = req("GET", q("/todos", due_before="2027-01-01"))
    got = ids(r.json)
    t.check("due_before returns 200", r.status == 200, r.status)
    t.check("due_before includes earlier dues", plain in got and leap in got, got)
    t.check("due_before excludes later dues", late not in got)
    t.check("due_before only returns todos with due < date",
            all(x.get("due") is not None and x["due"] < "2027-01-01" for x in (r.json or [])))
    t.check("due_before is strict", plain not in ids(req("GET", q("/todos", due_before="2026-12-25")).json))
    t.check("due_before invalid date returns 400", req("GET", q("/todos", due_before="2026-13-01")).status == 400)

    req("PATCH", "/todos/%s" % leap, {"completed": True})
    both = ids(req("GET", q("/todos", completed="false", due_before="2027-01-01")).json)
    t.check("filters combine with AND", plain in both and leap not in both, both)

    r = req("PATCH", "/todos/%s" % plain, {"due": None})
    t.check("PATCH due=null clears it", r.status == 200 and isinstance(r.json, dict) and r.json.get("due") is None, r.raw)

    restart()
    t.check("due persists across restart", (req("GET", "/todos/%s" % leap).json or {}).get("due") == "2024-02-29")
    t.check("cleared due persists across restart", (req("GET", "/todos/%s" % plain).json or {}).get("due", "x") is None)


run(main)
