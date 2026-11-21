"""Summarize a run: python3 report.py results/results/metrics.tsv > REPORT.md

The headline question: does the cost of absorbing each new requirement go
up, down, or sideways as the system evolves, and what does the system turn
into along the way?
"""

import csv
import signal
import sys
from collections import OrderedDict, defaultdict

signal.signal(signal.SIGPIPE, signal.SIG_DFL)


def num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def table(headers, rows):
    print("| " + " | ".join(headers) + " |")
    print("|" + "---|" * len(headers))
    for r in rows:
        print("| " + " | ".join("" if c is None else str(c) for c in r) + " |")


rows = list(csv.DictReader(open(sys.argv[1]), delimiter="\t"))
if not rows:
    print("No generations recorded.")
    sys.exit()

# requirement (or parallel pair) -> generations from release until the first pass
reqs = OrderedDict()
current = None
for r in rows:
    if r["released"] != "-":
        current = r["released"]
        reqs[current] = {"released": r["gen"], "mode": r["mode"], "gens": 0, "cost": 0.0, "out": 0.0,
                         "done": False, "broke": set(), "bounced": []}
    if current is None or reqs[current]["done"]:
        continue
    q = reqs[current]
    q["gens"] += 1
    q["cost"] += num(r["cost_usd"])
    q["out"] += num(r["output_tokens"])
    if r["result"] == "pass":
        q["done"] = True
    else:
        q["bounced"].append(r["result"])
        q["broke"] |= {f for f in r["failing"].split(",") if f != "-" and f not in current.split(",")}

count = lambda res: sum(r["result"] == res for r in rows)  # noqa: E731
maint, over = sum(num(r["cost_usd"]) for r in rows), sum(num(r["overhead_cost_usd"]) for r in rows)
print("# alien-engineer run report\n")
print("%d generations, %d requirements released. %d passed, %d failed checks, %d failed their own verification, "
      "%d rejected by review. Maintainers cost $%.2f; review and probes cost $%.2f.\n"
      % (len(rows), sum(len(k.split(",")) for k in reqs), count("pass"), count("fail"), count("unverified"),
         count("rejected"), maint, over))

print("## Cost to absorb each requirement\n")
table(["requirement", "mode", "released at gen", "gens to pass", "cost $", "output tokens", "reverted for",
       "older requirements broken on the way"],
      [[k, q["mode"], q["released"], q["gens"] if q["done"] else "%d (not yet)" % q["gens"], "%.2f" % q["cost"],
        int(q["out"]), ", ".join(q["bounced"]) or "-", ", ".join(sorted(q["broke"])) or "-"] for k, q in reqs.items()])

print("\n## Every generation\n")
table(["gen", "mode", "model", "new", "result", "failing", "review", "cost $", "turns", "out tokens"],
      [[r["gen"], r["mode"], r["model"], r["released"], r["result"], r["failing"], r["review"],
        "%.2f" % num(r["cost_usd"]), r["turns"], r["output_tokens"]] for r in rows])

kept = [r for r in rows if r["result"] == "pass"]
print("\n## Shape of the system (kept generations)\n")
print("`rewritten` is the share of the previous generation's lines that were removed: near 0 is patching, "
      "near 1 is starting over.\n")
table(["gen", "lang bytes", "app bytes", "lines +", "lines -", "lang rewritten", "app rewritten",
       "code not written here", "its bytes", "file types"],
      [[r["gen"], r["lang_bytes"], r["app_bytes"], r["lines_added"], r["lines_removed"], r["lang_rewritten"],
        r["app_rewritten"], r["third_party"], r["third_party_bytes"], r["file_types"]] for r in kept])

print("\n## Performance (kept generations, fixed benchmark)\n")
table(["gen", "creates/s", "create p99 ms", "list 2000 ms", "start s", "restart s", "memory MB"],
      [[r["gen"], r["create_rps"], r["create_p99_ms"], r["list_ms"], r["start_s"], r["restart_s"], r["rss_mb"]]
       for r in kept])

probed = [r for r in kept if r["newcomer"]]
if probed:
    print("\n## Probes\n")
    print("Planted bugs: how many `lang/verify` caught, and how many the official checks caught. Diagnosis: whether "
          "a fresh model found a planted bug from the repo alone. Newcomer: whether a fresh model could write a "
          "new program in the language.\n")
    table(["gen", "bugs planted", "lang/verify caught", "checks caught", "diagnosis", "newcomer task", "newcomer",
           "newcomer $", "newcomer turns"],
          [[r["gen"], r["mutants"], r["verify_caught"], r["checks_caught"], r["diagnosis"], r["newcomer_task"],
            r["newcomer"], r["newcomer_cost_usd"], r["newcomer_turns"]] for r in probed])

by_model = defaultdict(lambda: [0, 0, 0.0])
for r in rows:
    m = by_model[r["model"]]
    m[0] += 1
    m[1] += r["result"] == "pass"
    m[2] += num(r["cost_usd"])
if len(by_model) > 1:
    print("\n## By maintainer\n")
    table(["model", "generations", "kept", "cost $"], [[k, g, p, "%.2f" % c] for k, (g, p, c) in by_model.items()])
