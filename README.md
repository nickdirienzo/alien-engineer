# alien-engineer

An experiment in letting an AI agent evolve a todo app unconstrained by human
coding conventions. Inspired by Geoffrey Challen's [Move 37 Coding](https://www.geoffreychallen.com/essays/2026-03-01-move-37-coding)
and [Karpathy's autoresearch](https://github.com/karpathy/autoresearch).

## The question

What does software look like when an AI is its only maintainer, forever,
and the requirements keep changing?

An agent maintains a todo service across many generations. Each one is a
fresh agent run with nothing but the repo. Requirements arrive from a hidden
queue (validation, due dates, tags, search, users, bulk, undo, a change
feed, recurrence, scale, crash safety, *removing* tags, export/import), and
each new one is released once the system passes everything so far. The
prompt (`program.md`) says almost nothing about how to build. Whatever
structure emerges is selected by one thing: the cost of the next change.

## Layout

| Path | Purpose |
|------|---------|
| `program.md` | The agent's (minimal) mandate |
| `harness/requirements/NN-*/` | Hidden queue: `spec.md`, `check.py`, optional `retires` |
| `harness/lib/` | Check helpers + runner (runs each check on a fresh copy of the workspace) |
| `harness/reference/` | Reference implementation + `validate.sh` to prove the checks are sound (not shipped to the agent) |
| `evolve.sh` | The loop: release, prompt, run agent, check, commit or revert, record metrics |
| `report.py` | Turns `metrics.tsv` into `REPORT.md` |

## Run it

```bash
export ANTHROPIC_API_KEY=sk-...
MODELS=claude-fable-5-2 MAX_GENERATIONS=60 ./run.sh   # ./watch.sh in another terminal
```

`MODELS=claude-fable-5-2,claude-opus-5-5` rotates maintainers each
generation. `REQ_GAP=3` leaves two quiet generations between requirements, to
see what the agent does with no task. Results land in `./results/`:
`experiment/` (git history, one commit per generation), `results/` (metrics,
prompts, agent transcripts, check logs) and `REPORT.md`.

Before changing any check, run `bash harness/reference/validate.sh`.

## What to look for

- Cost per requirement over time: does the system get cheaper or more
  expensive to change?
- What the representation becomes, and when it diverges from conventional code.
- What the agent leaves for its successors (notes, formats, tooling).
- Regressions: which changes break older behavior.
- Whether systems built by one model are maintainable by another.
