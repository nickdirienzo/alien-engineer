## 00 — Base todo service

### Environment contract

- The workspace root MUST contain `start.sh`. The harness runs `bash start.sh`
  from a **fresh copy of the workspace** (without `.git`) and waits for the
  system to answer HTTP on port 8080 (127.0.0.1), for at most 10 seconds.
- All persistent state MUST live inside that copied directory. Each check run
  starts from the workspace as committed, so state from earlier runs is gone.
- To stop the system the harness runs `bash stop.sh` if it exists, then
  SIGKILLs the process group started by `start.sh` and anything still
  listening on port 8080.

### API

All request and response bodies are JSON.

1. **Create**: `POST /todos` with `{"title": "..."}` returns 201 and a JSON
   object with at least `id` (a unique string), `title`, and `completed`.
2. **List**: `GET /todos` returns 200 and a JSON array of all non-deleted todos.
3. **Complete**: `PATCH /todos/:id` with `{"completed": true}` returns 200.
   The completed state is reflected in subsequent GETs.
4. **Delete**: `DELETE /todos/:id` returns 200. The todo no longer appears in
   `GET /todos`.
5. **Filter**: `GET /todos?completed=true` returns only completed todos;
   `GET /todos?completed=false` returns only incomplete todos.
6. **Persistence**: todos survive a stop and restart.
7. **Performance**: 1000 sequential creates followed by a list complete in
   under 5 seconds.
