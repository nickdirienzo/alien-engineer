#!/usr/bin/env python3
"""The maintenance loop. Runs as root inside the container; hidden from the agent.

Each generation:
  1. maybe release the next requirement(s) from the hidden queue
  2. run the maintainer (or, in parallel mode, two maintainers and a merger)
  3. gate: official checks -> the maintainer's own lang/verify -> model review
  4. commit, or reset to where the generation started
  5. on a pass, measure: benchmark, and every PROBE_EVERY passes the model
     probes (planted bugs, bug diagnosis, a newcomer writing a new program)

Users:  agent  maintains /experiment and holds the API key
        runner runs the system under test: empty home, clean env, no network
        probe  runs reviewer/probe models on copies; cannot read /experiment
"""

import csv
import difflib
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time

sys.path.insert(0, "/sacred/lib")
from export import export_tree  # noqa: E402

E = os.environ.get
MAX_GENERATIONS = int(E("MAX_GENERATIONS", "60"))
MODELS = [m for m in E("MODELS", E("MODEL", "claude-fable-5-2")).split(",") if m]
REVIEW_MODEL = E("REVIEW_MODEL", "claude-sonnet-5-5")
PROBE_MODEL = E("PROBE_MODEL", "claude-sonnet-5-5")
EFFORT = E("EFFORT", "max")
REQ_GAP = int(E("REQ_GAP", "1"))            # passing generations between releases
GEN_TIMEOUT = int(E("GEN_TIMEOUT", "3600"))
VERIFY_TIMEOUT = int(E("VERIFY_TIMEOUT", "300"))
BUDGET_USD = E("BUDGET_USD", "")            # per maintainer run; empty = no cap
PARALLEL = E("PARALLEL", "0") == "1"        # two maintainers + a merger per release
PROBE_EVERY = int(E("PROBE_EVERY", "3"))    # model probes every Nth pass; 0 = never
MUTANTS = int(E("MUTANTS", "3"))
CLAUDE = E("CLAUDE_BIN", "claude")

QUEUE, PRIVATE, SACRED = "/harness/queue", "/opt/ae-private", "/sacred"
EXP, WORK, RES, TMP = "/experiment", "/work", "/results", "/tmp/ae"
LOGS = RES + "/logs"
PATH = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
PORTS = [8080, 8081, 8082]
CATEGORIES = ["input validation and boundaries", "what is saved and restored across restarts",
              "filtering, ordering and counting", "one user's data versus another's",
              "multi-step operations that must apply completely or not at all"]

FIELDS = ["gen", "mode", "model", "released", "active", "result", "checks_passed", "checks_total", "failing",
          "review", "cost_usd", "overhead_cost_usd", "duration_s", "turns", "input_tokens", "output_tokens",
          "cache_read_tokens", "cache_write_tokens", "files", "bytes", "lang_bytes", "app_bytes",
          "lines_added", "lines_removed", "lang_rewritten", "app_rewritten", "third_party", "third_party_bytes",
          "mutants", "verify_caught", "checks_caught", "diagnosis", "newcomer", "newcomer_task",
          "newcomer_cost_usd", "newcomer_turns", "create_rps", "create_p99_ms", "list_ms", "start_s",
          "restart_s", "rss_mb", "file_types"]


# ----------------------------------------------------------------------------
# plumbing
# ----------------------------------------------------------------------------

def say(*a):
    print(*a, flush=True)


def run_as(user, argv, env=None, cwd="/", timeout=600, log=None, keep_env=False):
    """Run argv as `user`. runner/probe-style clean env unless keep_env (the API key)."""
    cmd = ["sudo", "-u", user] + (["-E"] if keep_env else []) + ["env"]
    if not keep_env:
        cmd += ["-i", "PATH=" + PATH, "LANG=C.UTF-8"]
    cmd += ["HOME=/home/" + user] + ["%s=%s" % kv for kv in (env or {}).items()]
    cmd += ["timeout", "--signal=KILL", str(timeout)] + argv
    out = open(log, "ab") if log else subprocess.DEVNULL
    try:
        return subprocess.run(cmd, cwd=cwd, stdin=subprocess.DEVNULL, stdout=out, stderr=subprocess.STDOUT).returncode
    finally:
        if log:
            out.close()


def git(*args, user="agent", cwd=EXP):
    r = subprocess.run(["sudo", "-u", user, "env", "HOME=/home/" + user, "git"] + list(args),
                       cwd=cwd, capture_output=True, text=True, errors="replace")
    return r.stdout


def kill_procs():
    for u in ("agent", "runner", "probe"):
        subprocess.run(["pkill", "-9", "-u", u], capture_output=True)
    for p in PORTS:
        out = subprocess.run(["lsof", "-ti", "tcp:%d" % p, "-sTCP:LISTEN"], capture_output=True, text=True).stdout
        for pid in out.split():
            subprocess.run(["kill", "-9", pid], capture_output=True)
    time.sleep(0.5)


def copy_for(owner, name, src=EXP, overlay=None):
    """Fresh copy of a workspace (non-ignored files only) owned by `owner`.
    overlay=(dir, subpath) replaces subpath in the copy with the one from dir."""
    dst = os.path.join(TMP, name)
    shutil.rmtree(dst, ignore_errors=True)
    export_tree(src, dst)
    if overlay:
        odir, sub = overlay
        shutil.rmtree(os.path.join(dst, sub), ignore_errors=True)
        if os.path.isdir(os.path.join(odir, sub)):
            shutil.copytree(os.path.join(odir, sub), os.path.join(dst, sub), symlinks=True)
    subprocess.run(["chown", "-R", "%s:%s" % (owner, owner), dst])
    return dst


def claude(role, user, cwd, prompt, model, log, tools=None, timeout=900, env=None, effort=None, budget=None):
    """One headless Claude Code run. Returns the final result event (or {})."""
    argv = [CLAUDE, "-p", prompt, "--model", model, "--verbose", "--output-format", "stream-json"]
    if tools == "read":
        argv += ["--tools", "Read,Grep,Glob"]
    elif tools == "edit":
        argv += ["--tools", "Read,Grep,Glob,Edit,Write", "--dangerously-skip-permissions"]
    else:
        argv += ["--dangerously-skip-permissions"]
    if effort:
        argv += ["--effort", effort]
    if budget:
        argv += ["--max-budget-usd", str(budget)]
    if os.path.exists(log):
        os.remove(log)
    run_as(user, argv, env=dict(env or {}, AE_ROLE=role), cwd=cwd, timeout=timeout, log=log, keep_env=True)
    return parse_result(log)


def parse_result(log):
    res = {}
    try:
        for line in open(log, errors="replace"):
            line = line.strip()
            if line.startswith("{"):
                try:
                    d = json.loads(line)
                except ValueError:
                    continue
                if isinstance(d, dict) and d.get("type") == "result":
                    res = d
    except OSError:
        pass
    return res


def cost(res):
    return float(res.get("total_cost_usd", res.get("cost_usd", 0)) or 0)


def tail(path, n=6000):
    try:
        with open(path, errors="replace") as f:
            return f.read()[-n:]
    except OSError:
        return ""


def last_tag(text, tag):
    m = re.findall(r"^\s*%s:\s*(.*)$" % tag, text or "", re.M)
    return m[-1].strip() if m else None


# ----------------------------------------------------------------------------
# state, queue, spec
# ----------------------------------------------------------------------------

STATE_PATH = RES + "/state.json"
state = {"generation": 0, "released": 0, "last_release_gen": 0, "last_result": "none",
         "pending": [], "passes": 0, "board": {}, "runner_net": "unknown"}


def save_state():
    with open(STATE_PATH, "w") as f:
        json.dump(state, f, indent=1)


def queue_items():
    return sorted(os.listdir(QUEUE))


def spec_text(rid):
    return open("%s/spec/%s.md" % (SACRED, rid)).read().strip()


def release_next():
    items = queue_items()
    if state["released"] >= len(items):
        return None
    rid = items[state["released"]]
    shutil.copy("%s/%s/spec.md" % (QUEUE, rid), "%s/spec/%s.md" % (SACRED, rid))
    shutil.copy("%s/%s/check.py" % (QUEUE, rid), "%s/checks/%s.py" % (SACRED, rid))
    retires = "%s/%s/retires" % (QUEUE, rid)
    if os.path.exists(retires):
        for r in open(retires).read().split():
            try:
                os.remove("%s/checks/%s.py" % (SACRED, r))
            except OSError:
                pass
    with open(SACRED + "/SPEC.md", "w") as f:
        f.write("# Specification\n\nRequirements accumulate in order. A later requirement may change or\n"
                "replace an earlier one; when they conflict, the later one wins.\n\n")
        for s in sorted(os.listdir(SACRED + "/spec")):
            f.write(open("%s/spec/%s" % (SACRED, s)).read().strip() + "\n\n")
    subprocess.run(["chmod", "-R", "a+rX,go-w", SACRED])
    state["released"] += 1
    state["last_release_gen"] = state["generation"]
    state["pending"].append(rid)
    return rid


def active():
    return ",".join(sorted(f[:-3] for f in os.listdir(SACRED + "/checks") if f.endswith(".py")))


# ----------------------------------------------------------------------------
# gates and measurements
# ----------------------------------------------------------------------------

def run_checks(ws, checks_dir, tag, app="apps/todo"):
    summary, log = "%s/summary_%s.json" % (TMP, tag), "%s/%s_checks.log" % (LOGS, tag)
    for p in (summary, log):
        if os.path.exists(p):
            os.remove(p)
    open(summary, "w").close()
    subprocess.run(["chown", "runner", summary])
    rc = run_as("runner", ["python3", SACRED + "/lib/runner.py"], cwd=TMP, timeout=1800, log=log,
                env={"WORKSPACE": ws, "CHECKS_DIR": checks_dir, "SPEC_SUMMARY": summary, "APP_DIR": app})
    kill_procs()
    try:
        s = json.load(open(summary))
    except ValueError:
        s = {}
    return rc, s, log


def run_verify(ws, tag):
    """The maintainer's own verification: `lang/verify apps/todo`, exit 0 = good."""
    log = "%s/%s_verify.log" % (LOGS, tag)
    if os.path.exists(log):
        os.remove(log)
    exe = os.path.join(ws, "lang/verify")
    if not (os.path.isfile(exe) and os.access(exe, os.X_OK)):
        with open(log, "w") as f:
            f.write("lang/verify is missing or not executable\n")
        return 127, log
    rc = run_as("runner", [exe, "apps/todo"], cwd=ws, timeout=VERIFY_TIMEOUT, log=log)
    kill_procs()
    return rc, log


def review(tag):
    ws = copy_for("probe", "review")
    prompt = ("You are a reviewer. Audit this repository against the rules below. Read whatever you need "
              "in lang/ and apps/. Fail only clear violations of the rules, never style or quality.\n\n"
              + open(SACRED + "/REVIEW.md").read() +
              "\n\nEnd your reply with exactly these two lines:\n"
              "THIRD_PARTY: <comma-separated paths, relative to the repository root, of code that was not "
              "written for this repository (vendored libraries, downloaded tools), or none>\n"
              "VERDICT: PASS   or   VERDICT: FAIL: <one or two sentences naming the rule and the files>")
    res = claude("reviewer", "probe", ws, prompt, REVIEW_MODEL, "%s/%s_review.jsonl" % (LOGS, tag), tools="read")
    text = str(res.get("result", ""))
    v = last_tag(text, "VERDICT")
    verdict = "error" if not v else ("pass" if v.startswith("PASS") else "fail")
    reason = re.sub(r"^FAIL:?\s*", "", v or "") if verdict == "fail" else ""
    tp = last_tag(text, "THIRD_PARTY") or "none"
    paths = [] if tp.lower().startswith("none") else [p.strip().strip("`") for p in tp.split(",") if p.strip()]
    return verdict, reason, paths, cost(res)


def tree_bytes(root, sub=""):
    total = 0
    p = os.path.join(root, sub)
    if os.path.isfile(p):
        return os.path.getsize(p)
    for d, _, fs in os.walk(p):
        for f in fs:
            fp = os.path.join(d, f)
            if os.path.isfile(fp) and not os.path.islink(fp):
                total += os.path.getsize(fp)
    return total


def changed_lines(orig, mutant, sub):
    """{relative path: [line numbers changed in mutant]} for files under sub."""
    out = {}
    names = set()
    for root in (orig, mutant):
        for d, _, fs in os.walk(os.path.join(root, sub)):
            for f in fs:
                names.add(os.path.relpath(os.path.join(d, f), root))
    for rel in sorted(names):
        a, b = os.path.join(orig, rel), os.path.join(mutant, rel)
        try:
            ab = open(a, "rb").read() if os.path.isfile(a) else None
            bb = open(b, "rb").read() if os.path.isfile(b) else None
        except OSError:
            continue
        if ab == bb:
            continue
        lines = []
        try:
            al, bl = (ab or b"").decode().splitlines(), (bb or b"").decode().splitlines()
            for op, _, _, j1, j2 in difflib.SequenceMatcher(None, al, bl, autojunk=False).get_opcodes():
                if op != "equal":
                    lines += list(range(j1 + 1, max(j2, j1 + 1) + 1))
        except UnicodeDecodeError:
            pass
        out[rel] = lines
    return out


def probe_mutation(tag):
    """Plant bugs in apps/todo; see whether lang/verify (and the official checks) notice."""
    pristine = copy_for("root", "pristine")
    out = {"mutants": 0, "verify_caught": 0, "checks_caught": 0, "cost": 0.0, "diagnosis": "-", "detail": []}
    diag_target = None
    for i in range(MUTANTS):
        ws = copy_for("probe", "mut%d" % i)
        prompt = ("You are testing how well a project's own verification catches bugs. This repository has a "
                  "programming language in lang/ and a program written in it in apps/todo. Read enough of both to "
                  "understand the program. Then plant exactly one bug in the program's source under apps/todo: a "
                  "small change that makes the running service behave incorrectly in some situation, the kind of "
                  "mistake a maintainer could plausibly make. Area to target: %s. Do not change lang/, tests, "
                  "verification files, notes or docs, and leave no comment or marker pointing at the change.\n\n"
                  "End with one line: MUTATION: <path>:<line>: <what now behaves wrongly>"
                  % CATEGORIES[(state["generation"] + i) % len(CATEGORIES)])
        res = claude("mutator", "probe", ws, prompt, PROBE_MODEL, "%s/%s_mutator%d.jsonl" % (LOGS, tag, i), tools="edit")
        out["cost"] += cost(res)
        changed = changed_lines(pristine, ws, "apps/todo")
        if not changed:
            out["detail"].append({"i": i, "valid": False})
            continue
        v_rc, _ = run_verify(copy_for("runner", "mutv", overlay=(ws, "apps/todo")), "%s_mut%d" % (tag, i))
        c_rc, c_sum, _ = run_checks(copy_for("runner", "mutc", overlay=(ws, "apps/todo")),
                                    SACRED + "/checks", "%s_mut%d" % (tag, i))
        out["mutants"] += 1
        out["verify_caught"] += int(v_rc != 0)
        out["checks_caught"] += int(c_rc != 0)
        out["detail"].append({"i": i, "valid": True, "changed": changed, "verify_caught": v_rc != 0,
                              "checks_caught": c_rc != 0, "claimed": last_tag(str(res.get("result", "")), "MUTATION")})
        if c_rc != 0 and diag_target is None:
            diag_target = (ws, changed, c_sum.get("failed_labels", [])[:15])
    if diag_target:
        ws, changed, labels = diag_target
        d = copy_for("probe", "diag", overlay=(ws, "apps/todo"))
        prompt = ("This repository has a programming language in lang/ and a program written in it in apps/todo. "
                  "Until recently the program passed all of its checks. A recent change to one place in apps/todo "
                  "introduced a bug, and these checks now fail:\n\n- " + "\n- ".join(labels) +
                  "\n\nFind the change that caused it.\n\n"
                  "End with exactly one line: BUG: <path relative to the repository root>:<line number>")
        res = claude("diagnoser", "probe", d, prompt, PROBE_MODEL, "%s/%s_diagnoser.jsonl" % (LOGS, tag), tools="read")
        out["cost"] += cost(res)
        m = re.match(r"^`?\.?/?([^:`]+):(\d+)", last_tag(str(res.get("result", "")), "BUG") or "")
        out["diagnosis"] = "miss"
        if m and m.group(1) in changed:
            lines = changed[m.group(1)]
            near = not lines or any(abs(int(m.group(2)) - l) <= 5 for l in lines)
            out["diagnosis"] = "line" if near else "file"
    return out


def probe_newcomer(tag):
    """Can a model that has never seen the language write a new program in it?"""
    tasks = sorted(os.listdir(PRIVATE + "/probes"))
    task = tasks[state["passes"] // max(PROBE_EVERY, 1) % len(tasks)]
    ws = copy_for("probe", "newcomer")
    prompt = ("This repository contains a programming language in lang/ (`lang/run <program-directory>` runs a "
              "program) and an existing program written in it in apps/todo. You have not seen this language "
              "before; learn it from the repository. Write a new program in that language, in apps/probe, that "
              "implements the specification below. Do not change anything under lang/. Write the program only in "
              "that language, not by embedding another one. It will be started with `lang/run apps/probe` from "
              "the repository root, from a fresh state, so leave no saved data behind in apps/probe. You may run "
              "things to test your work.\n\n" + open("%s/probes/%s/spec.md" % (PRIVATE, task)).read())
    res = claude("newcomer", "probe", ws, prompt, PROBE_MODEL, "%s/%s_newcomer.jsonl" % (LOGS, tag),
                 timeout=1800, env={"PORT": "8080"})
    kill_procs()
    ok = False
    if os.path.isdir(os.path.join(ws, "apps/probe")):
        test = copy_for("runner", "newtest", overlay=(ws, "apps/probe"))
        rc, _, _ = run_checks(test, "%s/probes/%s" % (PRIVATE, task), tag + "_newcomer", app="apps/probe")
        ok = rc == 0
    return {"newcomer": "pass" if ok else "fail", "newcomer_task": task, "newcomer_cost_usd": round(cost(res), 4),
            "newcomer_turns": res.get("num_turns", "")}


def bench(tag):
    ws, out = copy_for("runner", "bench"), TMP + "/bench.json"
    open(out, "w").close()
    subprocess.run(["chown", "runner", out])
    run_as("runner", ["python3", PRIVATE + "/bench.py"], cwd=TMP, timeout=900, log="%s/%s_bench.log" % (LOGS, tag),
           env={"WORKSPACE": ws, "BENCH_OUT": out, "HARNESS_LIB": SACRED + "/lib"})
    kill_procs()
    try:
        return json.load(open(out))
    except ValueError:
        return {"error": "benchmark produced no output"}


def text_lines(rev, prefix):
    """Lines of text under prefix at a commit."""
    out = git("grep", "-I", "-c", "", rev, "--", prefix)
    return sum(int(l.rsplit(":", 1)[1]) for l in out.splitlines() if l.rsplit(":", 1)[-1].isdigit())


def repo_stats(base):
    files = [f for f in git("ls-files", "-z").split("\0") if f]
    size = lambda pre: sum(os.path.getsize(os.path.join(EXP, f)) for f in files  # noqa: E731
                           if f.startswith(pre) and os.path.isfile(os.path.join(EXP, f)))
    added = removed = 0
    by = {"lang/": 0, "apps/": 0}
    for line in git("diff", "--numstat", base, "HEAD").splitlines():
        a, d, name = (line.split("\t") + ["", ""])[:3]
        if a.isdigit() and d.isdigit():
            added, removed = added + int(a), removed + int(d)
            for pre in by:
                if name.startswith(pre):
                    by[pre] += int(d)
    ratio = {}
    for pre in by:
        before = text_lines(base, pre)
        ratio[pre] = round(by[pre] / before, 3) if before else ""
    types = {}
    for f in files:
        ext = (os.path.splitext(f)[1] or os.path.basename(f)).lstrip(".")
        types[ext] = types.get(ext, 0) + 1
    top = sorted(types.items(), key=lambda kv: -kv[1])[:6]
    return {"files": len(files), "bytes": size(""), "lang_bytes": size("lang/"), "app_bytes": size("apps/"),
            "lines_added": added, "lines_removed": removed, "lang_rewritten": ratio["lang/"],
            "app_rewritten": ratio["apps/"], "file_types": ",".join("%s:%d" % kv for kv in top)}


# ----------------------------------------------------------------------------
# prompts
# ----------------------------------------------------------------------------

def board_text():
    b = state["board"]
    if not b:
        return ""
    L = ["## Measurements", "", "Taken by the harness after generation %s, the last one that passed." % b.get("gen")]
    L.append("- Cost of that generation: $%.2f, %s turns." % (b.get("cost", 0), b.get("turns", "?")))
    if b.get("bench") and "error" not in b["bench"]:
        x = b["bench"]
        L.append("- Performance: %s creates/s (p99 %s ms), listing 2000 todos in %s ms, start in %s s, "
                 "restart with data in %s s, %s MB of memory." % (x.get("create_rps"), x.get("create_p99_ms"),
                 x.get("list_ms"), x.get("start_s"), x.get("restart_s"), x.get("rss_mb")))
    elif b.get("bench"):
        L.append("- Performance benchmark failed: %s" % b["bench"]["error"])
    if b.get("mutants"):
        L.append("- Verification (generation %s): bugs planted in apps/todo, one at a time: %d. `lang/verify` "
                 "caught %d. The official checks caught %d." % (b.get("probe_gen"), b["mutants"],
                 b.get("verify_caught", 0), b.get("checks_caught", 0)))
    if b.get("diagnosis") in ("line", "file", "miss"):
        L.append("- Diagnosis (generation %s): a model given one of those bugs and the failing checks, reading only "
                 "this repository, %s." % (b.get("probe_gen"), {"line": "found the faulty line",
                 "file": "found the right file but not the line", "miss": "did not find it"}[b["diagnosis"]]))
    if b.get("newcomer"):
        L.append("- Newcomer (generation %s): a model that had never seen your language was asked to write a small "
                 "new program in it, using only this repository. It %s, in %s turns for $%.2f." % (
                 b.get("probe_gen"), "succeeded" if b["newcomer"] == "pass" else "failed",
                 b.get("newcomer_turns", "?"), float(b.get("newcomer_cost_usd") or 0)))
    if b.get("third_party"):
        L.append("- Code not written here: %s (%d bytes)." % (", ".join(b["third_party"]), b.get("third_party_bytes", 0)))
    return "\n".join(L)


def build_prompt(new, workspace=EXP, parallel_note=""):
    p = open(SACRED + "/program.md").read().strip().replace(EXP + "/", workspace + "/")
    p += "\n\n---\n\n## This generation\n\n"
    if parallel_note:
        p += parallel_note
    elif new:
        p += "A new requirement was added to /sacred/SPEC.md:\n\n" + spec_text(new[0])
    elif state["pending"]:
        p += "No new requirements. Not yet met:\n\n" + "\n\n".join(spec_text(r) for r in state["pending"])
    else:
        p += "No new requirements."
    if BUDGET_USD:
        p += "\n\nYour budget for this generation is $%s. The run is stopped when it is spent." % BUDGET_USD
    fail = LOGS + "/last_fail.md"
    if state["last_result"] not in ("pass", "none") and os.path.exists(fail) and not parallel_note:
        p += "\n\nThe previous generation's changes were reverted. " + open(fail).read().strip()
    if board_text():
        p += "\n\n" + board_text()
    return p + "\n"


# ----------------------------------------------------------------------------
# maintainers
# ----------------------------------------------------------------------------

def maintain_serial(gen, model, new):
    log = "%s/gen_%d_agent.jsonl" % (LOGS, gen)
    prompt = build_prompt(new)
    open("%s/gen_%d_prompt.md" % (LOGS, gen), "w").write(prompt)
    link = LOGS + "/current_agent.jsonl"
    if os.path.lexists(link):
        os.remove(link)
    os.symlink(log, link)
    return [claude("maintainer", "agent", EXP, prompt, model, log, timeout=GEN_TIMEOUT, effort=EFFORT,
                   budget=BUDGET_USD, env={"PORT": "8080"})]


def maintain_parallel(gen, model, new):
    """Two maintainers, one requirement each, in separate clones; then a third merges."""
    results, threads = [None, None], []
    names = ["gen-%d-a" % gen, "gen-%d-b" % gen]
    for k, rid in enumerate(new):
        clone = "%s/%s" % (WORK, "ab"[k])
        shutil.rmtree(clone, ignore_errors=True)
        git("clone", "-q", EXP, clone, cwd=WORK)
        other = spec_text(new[1 - k]).splitlines()[0].lstrip("# ")
        note = ("Two new requirements were added to /sacred/SPEC.md. Two maintainers are working at the same time, "
                "each in a separate copy of the repository, starting from the same commit. Yours is `%s`. You are "
                "assigned this requirement:\n\n%s\n\nThe other maintainer is assigned \"%s\". Afterwards a third "
                "maintainer will merge both copies. Checks for the other requirement may fail in your copy. "
                "`WORKSPACE` and `PORT` are set so that `bash /sacred/spec_check.sh` tests your copy."
                % (clone, spec_text(rid), other))
        prompt = build_prompt(new, workspace=clone, parallel_note=note)
        open("%s/gen_%d_prompt_%s.md" % (LOGS, gen, "ab"[k]), "w").write(prompt)

        def work(k=k, clone=clone, prompt=prompt):
            results[k] = claude("maintainer", "agent", clone, prompt, model, "%s/gen_%d_agent_%s.jsonl" % (LOGS, gen, "ab"[k]),
                                timeout=GEN_TIMEOUT, effort=EFFORT, budget=BUDGET_USD,
                                env={"PORT": str(8081 + k), "WORKSPACE": clone})
        threads.append(threading.Thread(target=work))
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    kill_procs()
    for k, rid in enumerate(new):
        clone = "%s/%s" % (WORK, "ab"[k])
        git("add", "-A", cwd=clone)
        git("commit", "-q", "--allow-empty", "-m", "generation %d, parallel: %s" % (gen, rid), cwd=clone)
        git("fetch", "-q", clone, "+HEAD:refs/heads/" + names[k])
    note = ("Two new requirements were added to /sacred/SPEC.md. Two maintainers worked at the same time from the "
            "current commit, one on each. Their work is on the git branches `%s` and `%s` of this repository. "
            "Neither is merged. Integrate both so that everything passes.\n\n%s\n\n%s"
            % (names[0], names[1], spec_text(new[0]), spec_text(new[1])))
    prompt = build_prompt(new, parallel_note=note)
    open("%s/gen_%d_prompt.md" % (LOGS, gen), "w").write(prompt)
    merged = claude("maintainer", "agent", EXP, prompt, model, "%s/gen_%d_agent.jsonl" % (LOGS, gen),
                    timeout=GEN_TIMEOUT, effort=EFFORT, budget=BUDGET_USD, env={"PORT": "8080"})
    return [r or {} for r in results] + [merged]


# ----------------------------------------------------------------------------
# main loop
# ----------------------------------------------------------------------------

def setup():
    for d in (LOGS, TMP, SACRED + "/spec", SACRED + "/checks", WORK):
        os.makedirs(d, exist_ok=True)
    os.chmod(TMP, 0o711)
    subprocess.run(["chown", "agent:agent", WORK])
    subprocess.run(["git", "config", "--global", "--add", "safe.directory", "*"])
    if os.path.exists(STATE_PATH):
        state.update(json.load(open(STATE_PATH)))
    # runner gets no network beyond localhost (best effort: needs NET_ADMIN)
    ok = True
    for tool in ("iptables", "ip6tables"):
        rule = ["OUTPUT", "-m", "owner", "--uid-owner", "runner", "!", "-o", "lo", "-j", "REJECT"]
        try:
            if subprocess.run([tool, "-C"] + rule, capture_output=True).returncode != 0:
                ok &= subprocess.run([tool, "-A"] + rule, capture_output=True).returncode == 0
        except OSError:
            ok = False
    state["runner_net"] = "blocked" if ok else "open"


def generation():
    state["generation"] += 1
    gen = state["generation"]
    tag = "gen_%d" % gen
    model = MODELS[(gen - 1) % len(MODELS)]
    subprocess.run(["chmod", "750", EXP])
    kill_procs()

    # ---- release ------------------------------------------------------------
    new, mode = [], "serial"
    due = state["released"] == 0 or (state["last_result"] == "pass" and not state["pending"]
                                     and gen - state["last_release_gen"] >= REQ_GAP)
    if due:
        left = len(queue_items()) - state["released"]
        if PARALLEL and state["released"] > 0 and left >= 2:
            new, mode = [release_next(), release_next()], "parallel"
        elif left >= 1:
            new = [release_next()]
    say("\n=== Generation %d  model=%s  mode=%s  new=%s  active=%s" % (gen, model, mode, ",".join(new) or "none", active()))

    # ---- maintain -------------------------------------------------------------
    base = git("rev-parse", "HEAD").strip()
    t0 = time.time()
    runs = maintain_parallel(gen, model, new) if mode == "parallel" else maintain_serial(gen, model, new)
    wall = time.time() - t0
    kill_procs()

    # ---- gates ----------------------------------------------------------------
    row = {f: "" for f in FIELDS}
    overhead = 0.0
    rc, summary, check_log = run_checks(copy_for("runner", "checks"), SACRED + "/checks", tag)
    result, reason = "pass", ""
    review_verdict, third = "skipped", []
    if rc != 0:
        result = "fail"
        reason = "The checks failed. End of the check log:\n\n```\n%s\n```" % tail(check_log)
    else:
        v_rc, v_log = run_verify(copy_for("runner", "verify"), tag)
        if v_rc != 0:
            result = "unverified"
            reason = ("The checks passed, but `lang/verify apps/todo` exited with status %d on your own system. "
                      "End of its output:\n\n```\n%s\n```" % (v_rc, tail(v_log, 3000)))
        else:
            review_verdict, why, third, c = review(tag)
            overhead += c
            if review_verdict == "fail":
                result = "rejected"
                reason = "The checks passed, but the reviewer rejected the changes under /sacred/REVIEW.md:\n\n" + why

    # ---- keep or revert ---------------------------------------------------------
    if result == "pass":
        git("add", "-A")
        git("commit", "-q", "--allow-empty", "-m", "generation %d: pass (%s; %s)" % (gen, ",".join(new) or "no new requirement", model))
        state["pending"] = []
        state["passes"] += 1
        row.update(repo_stats(base))
    else:
        open(LOGS + "/last_fail.md", "w").write(reason)
        git("merge", "--abort")
        git("reset", "-q", "--hard", base)
        git("clean", "-qfd")
    say("    %s  checks %s/%s  review=%s  %.0fs" % (result, summary.get("passed", "?"), summary.get("total", "?"), review_verdict, wall))

    # ---- measurements (passing generations only) ----------------------------------
    usage = lambda k: sum(int((r.get("usage") or {}).get(k) or 0) for r in runs)  # noqa: E731
    turns = sum(int(r.get("num_turns") or 0) for r in runs)
    maint_cost = sum(cost(r) for r in runs)
    if result == "pass":
        board = {"gen": gen, "cost": maint_cost, "turns": turns}
        for k in ("probe_gen", "mutants", "verify_caught", "checks_caught", "diagnosis", "newcomer",
                  "newcomer_turns", "newcomer_cost_usd"):
            if k in state["board"]:
                board[k] = state["board"][k]
        b = bench(tag)
        board["bench"] = b
        row.update({k: b.get(k, "") for k in ("create_rps", "create_p99_ms", "list_ms", "start_s", "restart_s", "rss_mb")})
        third = [p for p in third if os.path.exists(os.path.join(EXP, p))]
        tp_bytes = sum(tree_bytes(EXP, p) for p in third)
        board.update({"third_party": third, "third_party_bytes": tp_bytes})
        row.update({"third_party": ",".join(third) or "-", "third_party_bytes": tp_bytes})
        if PROBE_EVERY and state["passes"] % PROBE_EVERY == 0:
            m = probe_mutation(tag) if MUTANTS else {}
            n = probe_newcomer(tag)
            overhead += m.get("cost", 0) + n["newcomer_cost_usd"]
            row.update({k: m.get(k, "") for k in ("mutants", "verify_caught", "checks_caught", "diagnosis")})
            row.update(n)
            board.update({k: m[k] for k in ("mutants", "verify_caught", "checks_caught", "diagnosis") if k in m})
            board.update(n, probe_gen=gen)
            json.dump({"mutation": m, "newcomer": n}, open("%s/%s_probes.json" % (LOGS, tag), "w"), indent=1)
            say("    probes: verify caught %s/%s planted bugs (checks %s), diagnosis=%s, newcomer(%s)=%s" % (
                m.get("verify_caught", "-"), m.get("mutants", "-"), m.get("checks_caught", "-"),
                m.get("diagnosis", "-"), n["newcomer_task"], n["newcomer"]))
        state["board"] = board

    row.update({"gen": gen, "mode": mode, "model": model, "released": ",".join(new) or "-", "active": active(),
                "result": result, "checks_passed": summary.get("passed", ""), "checks_total": summary.get("total", ""),
                "failing": ",".join(summary.get("failed_requirements", [])) or "-", "review": review_verdict,
                "cost_usd": round(maint_cost, 4), "overhead_cost_usd": round(overhead, 4),
                "duration_s": round(wall, 1), "turns": turns, "input_tokens": usage("input_tokens"),
                "output_tokens": usage("output_tokens"), "cache_read_tokens": usage("cache_read_input_tokens"),
                "cache_write_tokens": usage("cache_creation_input_tokens")})
    path = RES + "/metrics.tsv"
    fresh = not os.path.exists(path)
    with open(path, "a", newline="") as f:
        w = csv.DictWriter(f, FIELDS, delimiter="\t")
        if fresh:
            w.writeheader()
        w.writerow(row)
    state["last_result"] = result
    save_state()


def main():
    setup()
    say("=== alien-engineer ===")
    say("models=%s max_generations=%d parallel=%s probe_every=%d budget=%s runner_network=%s queue=%d" % (
        ",".join(MODELS), MAX_GENERATIONS, PARALLEL, PROBE_EVERY, BUDGET_USD or "none", state["runner_net"], len(queue_items())))
    while state["generation"] < MAX_GENERATIONS:
        generation()
    say("\n=== Done: %d generations, %d/%d requirements released ===" % (
        state["generation"], state["released"], len(queue_items())))


if __name__ == "__main__":
    main()
