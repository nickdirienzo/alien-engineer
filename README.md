# alien-engineer

An experiment in letting an AI agent evolve a todo app unconstrained by human
coding conventions. Inspired by Geoffrey Challen's [Move 37 Coding](https://www.geoffreychallen.com/essays/2026-03-01-move-37-coding)
and [Karpathy's autoresearch](https://github.com/karpathy/autoresearch).

## The question

What does software look like when an AI is its only maintainer, forever,
the requirements keep changing, and it has to build in a language of its
own design?

An agent maintains two things across many generations: `lang/`, a language
it designs and implements, and `apps/todo/`, a todo service written in that
language. Each generation is a fresh agent run with nothing but the repo, so
every maintainer has to learn the language from whatever its predecessors
left. Requirements arrive from a hidden queue (validation, due dates, tags,
search, users, bulk, undo, a change feed, recurrence, scale, crash safety,
*removing* tags, export/import), each released once the system passes
everything so far.

Two gates decide whether a generation is kept: the black-box checks, and a
model reviewer that enforces `REVIEW.md` (apps are really written in the
language; the language is general-purpose and isn't secretly the app). The
prompt (`program.md`) says almost nothing about how to build.

## Layout

| Path | Purpose |
|------|---------|
| `program.md` | The agent's (minimal) mandate |
| `REVIEW.md` | Rules the reviewer enforces each generation |
| `harness/requirements/NN-*/` | Hidden queue: `spec.md`, `check.py`, optional `retires` |
| `harness/lib/` | Check helpers + runner (runs each check on a fresh copy of the workspace) |
| `harness/reference/` | Reference implementation + `validate.sh` to prove the checks are sound (not shipped to the agent) |
| `evolve.sh` | The loop: release, prompt, run agent, check, review, commit or revert, record metrics |
| `report.py` | Turns `metrics.tsv` into `REPORT.md` |

## Run it

```bash
export ANTHROPIC_API_KEY=sk-...
MODELS=claude-fable-5-2 MAX_GENERATIONS=60 ./run.sh   # ./watch.sh in another terminal
```

`MODELS=claude-fable-5-2,claude-opus-5-5` rotates maintainers each
generation. `REVIEW_MODEL` sets the reviewer (default `claude-sonnet-5-5`). `REQ_GAP=3` leaves two quiet generations between requirements, to
see what the agent does with no task. Results land in `./results/`:
`experiment/` (git history, one commit per generation), `results/` (metrics,
prompts, agent transcripts, check logs) and `REPORT.md`.

Before changing any check, run `bash harness/reference/validate.sh`.

## What to look for

- Cost per requirement over time: does the system get cheaper or more
  expensive to change?
- What the language becomes: syntax, semantics, what it optimizes for, how it changes.
- How `lang/` and `apps/` grow relative to each other (`lang_bytes` vs `app_bytes`).
- How often the reviewer rejects, and what the agent tried.
- What the agent leaves for its successors (notes, formats, tooling).
- Regressions: which changes break older behavior.
- Whether systems built by one model are maintainable by another.
