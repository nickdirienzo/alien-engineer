"""Summarize a run: python3 report.py results/results/metrics.tsv > REPORT.md

The headline question: does the cost of absorbing each new requirement go
up, down, or sideways as the system evolves, and what does the system turn
into along the way?
"""

import csv
import signal
import sys

signal.signal(signal.SIGPIPE, signal.SIG_DFL)
from collections import OrderedDict, defaultdict


def num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


rows = list(csv.DictReader(open(sys.argv[1]), delimiter="\t"))
if not rows:
    print("No generations recorded.")
    sys.exit()

# requirement -> generations spent from release until first pass
reqs = OrderedDict()
current = None
for r in rows:
    if r["released"] != "-":
        current = r["released"]
        reqs[current] = {"released": int(r["gen"]), "gens": 0, "cost": 0.0, "out_tokens": 0.0,
                         "satisfied": None, "regressions": set()}
    if current is None:
        continue
    q = reqs[current]
    if q["satisfied"] is None:
        q["gens"] += 1
        q["cost"] += num(r["cost_usd"])
        q["out_tokens"] += num(r["output_tokens"])
        if r["result"] == "pass":
            q["satisfied"] = int(r["gen"])
        else:
            q["regressions"] |= {f for f in r["failing"].split(",") if f not in ("-", current)}

print("# alien-engineer run report\n")
total = sum(num(r["cost_usd"]) for r in rows)
print("%d generations, %d requirements released, %d passing generations, $%.2f total.\n"
      % (len(rows), len(reqs), sum(r["result"] == "pass" for r in rows), total))

print("## Cost to absorb each requirement\n")
print("| requirement | released gen | gens to pass | cost $ | output tokens | broke older requirements along the way |")
print("|---|---|---|---|---|---|")
for name, q in reqs.items():
    print("| %s | %d | %s | %.2f | %d | %s |" % (
        name, q["released"], q["gens"] if q["satisfied"] else "%d (not yet)" % q["gens"],
        q["cost"], q["out_tokens"], ", ".join(sorted(q["regressions"])) or "-"))

print("\n## Every generation\n")
print("| gen | model | new req | result | failing | cost $ | turns | out tokens | files | bytes | lines changed | file types |")
print("|---|---|---|---|---|---|---|---|---|---|---|---|")
for r in rows:
    print("| %s | %s | %s | %s | %s | %.2f | %s | %s | %s | %s | %s | %s |" % (
        r["gen"], r["model"], r["released"], r["result"], r["failing"], num(r["cost_usd"]), r["turns"],
        r["output_tokens"], r["files"], r["bytes"], r["lines_changed"], r["file_types"]))

by_model = defaultdict(lambda: [0, 0, 0.0])
for r in rows:
    m = by_model[r["model"]]
    m[0] += 1
    m[1] += r["result"] == "pass"
    m[2] += num(r["cost_usd"])
if len(by_model) > 1:
    print("\n## By maintainer\n")
    print("| model | generations | passed | cost $ |")
    print("|---|---|---|---|")
    for k, (g, p, c) in by_model.items():
        print("| %s | %d | %d | %.2f |" % (k, g, p, c))
