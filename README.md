# alien-engineer

An experiment in letting an AI agent evolve a todo app unconstrained by human
coding conventions. Inspired by Geoffrey Challen's [Move 37 Coding](https://www.geoffreychallen.com/essays/2026-03-01-move-37-coding)
and [Karpathy's autoresearch](https://github.com/karpathy/autoresearch).

## The idea

Give an AI agent a behavioral spec for a todo app, then let it evolve the
implementation across many generations. The agent owns everything — language,
runtime, storage, structure — except the spec. The evolutionary pressure is
toward simplicity and token efficiency, not human readability.

The git history is the research artifact.

## Sacred files (agent cannot modify)

| File | Purpose |
|------|---------|
| `SPEC.md` | Behavioral contract — what the system must do |
| `spec_check.sh` | Black-box test harness — verifies the spec |
| `evolve.sh` | The evolution loop |
| `program.md` | The agent's mandate |

Everything else is the agent's to create, destroy, or reinvent.

## Run it

```bash
export ANTHROPIC_API_KEY=sk-...
./run.sh
```

Watch it:
```bash
docker logs -f alien-engineer
```

Extract results when done:
```bash
docker cp alien-engineer:/experiment ./results
cd results && git log --oneline  # the evolutionary history
```

## Configuration

| Env var | Default | Description |
|---------|---------|-------------|
| `MAX_GENERATIONS` | 100 | Stop after N generations |
| `MODEL` | claude-opus-4-6 | Model to use |

## What to look for

- Does the representation drift from conventional code?
- Does token cost per generation decrease over time?
- Does the agent invent new abstractions or formats?
- At what generation does a human stop being able to read the implementation?
