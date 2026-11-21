## 11 — Crash safety

- Any mutation that has received a 2xx response must survive the system being
  SIGKILLed immediately afterward, with no `stop.sh` and no graceful shutdown.
  This covers todos, undo history, and the change feed.
- After a crash the system must restart normally and be consistent. A
  mutation that was in flight but never acknowledged may be applied or not,
  but never half-applied: a bulk create is all or nothing.
