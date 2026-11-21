## 00 — Base todo service

### Environment contract

- The harness copies the workspace's files (tracked or untracked, but not
  `.git` and not git-ignored files) to a fresh directory and,
  from that directory's root, executes `lang/run apps/todo`. The system must
  answer HTTP on 127.0.0.1, on the port given by the `PORT` environment
  variable (8080 if unset), within 10 seconds.
- The harness runs as a different user than the maintainer, with an empty
  home directory, a minimal environment, and no network access beyond
  localhost. Everything the system needs at run time must be in the workspace
  or already installed system-wide.
- All persistent state MUST live inside that copied directory. Each check run
  starts from the workspace as committed, so state from earlier runs is gone.
- To stop the system, the harness sends SIGTERM to the process group it
  started, waits up to 5 seconds, then SIGKILLs the group and anything still
  listening on the port.

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
