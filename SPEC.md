# Todo App Specification

This is the behavioral contract. The system under evolution MUST satisfy all
invariants below. These invariants are tested by `spec_check.sh`.

If you believe a spec invariant is blocking a meaningful improvement, write
your proposed change to `SPEC_PROPOSAL.md` and exit. A human will review.

## Interface

The system MUST expose an HTTP API on port 8080.

## Invariants

1. **Create**: `POST /todos` with JSON `{"title": "..."}` returns 201 and a
   JSON object with at least `id` (unique string) and `title`.

2. **List**: `GET /todos` returns 200 and a JSON array of all created,
   non-deleted todos.

3. **Complete**: `PATCH /todos/:id` with `{"completed": true}` returns 200.
   Completed state persists across subsequent GETs.

4. **Delete**: `DELETE /todos/:id` returns 200. Todo no longer appears in
   `GET /todos`.

5. **Filter**: `GET /todos?completed=true` returns only completed todos.
   `GET /todos?completed=false` returns only incomplete todos.

6. **Persistence**: Todos survive a system restart. After `spec_check.sh`
   stops and restarts the system, previously created todos are still present.

7. **Performance**: Creating 1000 todos and listing them completes in under
   5 seconds total.

## Non-requirements

- No specific programming language, framework, or runtime
- No specific database or storage technology
- No requirement for human-readable source code
- No requirement for conventional project structure
- No requirement for conventional file formats
