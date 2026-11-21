from harness import req, nonce, restart, run


def main(t):
    n = nonce()
    k1, k2 = "b-" + n, "a-" + n
    t.check("GET /kv on empty store returns []", req("GET", "/kv").json == [], req("GET", "/kv").raw)
    t.check("GET missing key is 404", req("GET", "/kv/" + k1).status == 404)
    t.check("PUT returns 200", req("PUT", "/kv/" + k1, raw=b"hello \xf0\x9f\xa6\x84 world").status == 200)
    r = req("GET", "/kv/" + k1)
    t.check("GET returns exact bytes", r.status == 200 and r.raw == b"hello \xf0\x9f\xa6\x84 world", r.raw)
    req("PUT", "/kv/" + k2, raw=b"{\"not\": \"parsed\"}")
    req("PUT", "/kv/" + k1, raw=b"second")
    t.check("PUT overwrites", req("GET", "/kv/" + k1).raw == b"second")
    t.check("GET /kv lists keys sorted", req("GET", "/kv").json == [k2, k1], req("GET", "/kv").raw)
    for bad in ["UPPER", "has_underscore", "x" * 65]:
        t.check("400 on key %r" % bad[:12], req("PUT", "/kv/" + bad, raw=b"v").status == 400)
    t.check("64-char key accepted", req("PUT", "/kv/" + "k" * 64, raw=b"v").status == 200)
    t.check("DELETE existing returns 200", req("DELETE", "/kv/" + k2).status == 200)
    t.check("DELETE missing returns 404", req("DELETE", "/kv/" + k2).status == 404)
    restart()
    t.check("value survives restart", req("GET", "/kv/" + k1).raw == b"second")
    t.check("delete survives restart", req("GET", "/kv/" + k2).status == 404)
    t.check("keys correct after restart", req("GET", "/kv").json == [k1, "k" * 64], req("GET", "/kv").raw)


run(main)
