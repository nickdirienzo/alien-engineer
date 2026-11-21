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
everything so far. The prompt (`program.md`) says almost nothing about how
to build.

## What decides whether a generation is kept

1. **Checks**: black-box tests of every released requirement, run by a
   separate user with an empty home, a clean environment and no network, on a
   copy of the non-ignored files.
2. **Its own verification**: `lang/verify apps/todo` must exit 0.
3. **Review**: a model enforces `REVIEW.md` (apps are really written in the
   language; the language is general-purpose and isn't secretly the app).

Anything else is reverted, and the next maintainer is told why.

## What is measured, and shown to the next maintainer

| Pressure | Measurement |
|---|---|
| Cost of change | Dollars, tokens and turns per generation and per requirement |
| Optimization | A fixed benchmark: throughput, latency, start, restart, memory |
| Proof it works | Bugs are planted in `apps/todo`; does `lang/verify` catch them? (The official checks are scored on the same bugs.) |
| Answers on demand | A fresh model gets a planted bug plus the failing checks: can it find the line? |
| Amnesia | A fresh model must write a new small program in the language from the repo alone |
| Dependencies | The reviewer lists code not written here; its size is tracked |
| Disposable code | Share of the previous generation's lines removed, for `lang/` and `apps/` |

Two more are off by default because they change the experiment itself:
`BUDGET_USD=5` caps each maintainer run, and `PARALLEL=1` gives two
maintainers one requirement each in separate clones, then has a third merge.

## Layout

| Path | Purpose |
|------|---------|
| `program.md` | The agent's (minimal) mandate |
| `REVIEW.md` | Rules the reviewer enforces |
| `harness/requirements/NN-*/` | Hidden queue: `spec.md`, `check.py`, optional `retires` |
| `harness/evolve.py` | The loop (hidden from the agent; `evolve.sh` starts it) |
| `harness/lib/` | Check helpers and runner (visible to the agent) |
| `harness/private/`, `harness/probes/` | Benchmark and newcomer tasks (hidden) |
| `harness/reference/` | Reference app, `validate.sh` (are the checks sound?), `simulate.sh` (dry-run the loop with a fake model) |
| `report.py` | Turns `metrics.tsv` into `REPORT.md` |

## Run it

```bash
export ANTHROPIC_API_KEY=sk-...
MODELS=claude-fable-5-2 MAX_GENERATIONS=15 ./run.sh   # ./watch.sh in another terminal
```

| Env var | Default | |
|---|---|---|
| `MODELS` | `claude-fable-5-2` | Comma list rotates maintainers each generation |
| `MAX_GENERATIONS` | 60 | |
| `REQ_GAP` | 1 | Passing generations between requirements (3 = two idle ones) |
| `REVIEW_MODEL`, `PROBE_MODEL` | `claude-sonnet-5-5` | |
| `PROBE_EVERY` | 3 | Model probes every Nth kept generation; 0 turns them off |
| `MUTANTS` | 3 | Bugs planted per probe |
| `BUDGET_USD` | none | Cap per maintainer run |
| `PARALLEL` | 0 | 1 = two maintainers plus a merger per release |
| `EFFORT`, `GEN_TIMEOUT` | `max`, 3600 | |

Results land in `./results/`: `experiment/` (git history, one commit per kept
generation), `results/` (metrics, prompts, transcripts, check and probe logs)
and `REPORT.md`.

Before changing a check, run `bash harness/reference/validate.sh`. Before
changing the loop, run `bash harness/reference/simulate.sh` as root in a
throwaway container.
