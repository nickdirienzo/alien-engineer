## 10 — Scale and concurrency

All times are measured by the client on the same machine and include transfer.

- A single user can hold 20,000 todos. Loading them with 20 bulk requests of
  1000 must take under 10 seconds in total.
- With 20,000 todos:
  - `GET /todos` (everything) in under 1 second.
  - `GET /todos?q=...` in under 0.5 seconds.
  - A restart is ready (answering `GET /todos`) within 3 seconds of `start.sh`.
  - 1000 sequential single creates in under 3 seconds.
- 50 concurrent `POST /todos` requests from 50 clients all succeed with
  distinct ids, and every one of them shows up in the list.
