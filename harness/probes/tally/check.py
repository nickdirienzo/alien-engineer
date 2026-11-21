from harness import req, restart, run


def vote(voter, choice):
    return req("POST", "/vote", {"voter": voter, "choice": choice})


def main(t):
    t.check("results start empty", req("GET", "/results").json == [], req("GET", "/results").raw)
    t.check("unknown voter is 404", req("GET", "/voters/ann").status == 404)
    t.check("vote returns 200", vote("ann", "tea").status == 200)
    vote("bob", "coffee")
    vote("cy", "coffee")
    vote("di", "tea")
    vote("ed", "water")
    want = [{"choice": "coffee", "votes": 2}, {"choice": "tea", "votes": 2}, {"choice": "water", "votes": 1}]
    t.check("results sorted by votes desc then choice", req("GET", "/results").json == want, req("GET", "/results").raw)
    vote("ed", "tea")
    want = [{"choice": "tea", "votes": 3}, {"choice": "coffee", "votes": 2}]
    t.check("revote replaces earlier vote", req("GET", "/results").json == want, req("GET", "/results").raw)
    t.check("voter lookup", req("GET", "/voters/ed").json == {"choice": "tea"})
    for label, body in [("missing choice", {"voter": "x"}), ("empty voter", {"voter": "", "choice": "a"}),
                        ("long choice", {"voter": "x", "choice": "c" * 101}), ("non-string", {"voter": "x", "choice": 5})]:
        t.check("400 on %s" % label, req("POST", "/vote", body).status == 400)
    t.check("400 on invalid JSON", req("POST", "/vote", raw="{nope").status == 400)
    t.check("invalid votes not counted", req("GET", "/results").json == want)
    restart()
    t.check("results survive restart", req("GET", "/results").json == want, req("GET", "/results").raw)
    t.check("voter lookup survives restart", req("GET", "/voters/bob").json == {"choice": "coffee"})


run(main)
