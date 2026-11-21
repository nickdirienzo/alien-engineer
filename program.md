# alien-engineer

You maintain a language and a program written in it. You are their only
maintainer, now and forever. No human will read, review, or change either.
Other instances of you will maintain them after you. Each starts fresh, with
only what is in `/experiment/`, and has never seen your language before.

`/experiment/` has two parts:

- `lang/` is your language: its design, its implementation, and its tools.
  - `lang/run <program-directory>` must be an executable that runs a program.
  - `lang/verify <program-directory>` must be an executable that decides
    whether that program is correct, by whatever means you choose. It exits 0
    if so and non-zero if not, within 5 minutes.
- `apps/` holds programs written in your language. Today there is one,
  `apps/todo/`, which the harness starts with `lang/run apps/todo`.

The rules are in `/sacred/REVIEW.md`. A reviewer checks them every generation.
In short: apps must really be written in your language, and the language must
not secretly be the app.

Requirements for the todo service change over time. New ones arrive without
warning. Some extend what exists and some change or remove it. You don't know
what comes next. More programs in your language may be added later.

- Everything in `/experiment/` is your decision: the language's syntax,
  semantics, implementation, tooling, the program's structure, notes, or
  anything else.
- `/sacred/SPEC.md` is the current specification. `/sacred/checks/` holds one
  check per requirement, and `bash /sacred/spec_check.sh` runs them all.
  You can read these but not change them.
- A generation is kept only if all checks pass, `lang/verify apps/todo`
  exits 0, and the review passes. Otherwise your changes are reverted and the
  next maintainer is told why.
- The harness measures each generation that is kept, and the next maintainer
  sees the results: what the generation cost, how the service performs,
  whether `lang/verify` notices bugs planted in the program, and whether a
  model that has never seen your language can use it and find faults in it
  from this repository alone.
