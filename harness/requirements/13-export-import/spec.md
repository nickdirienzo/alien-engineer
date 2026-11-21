## 13 — Export and import

- `GET /export` returns 200 and `{"version": 1, "todos": [...]}`: every one of
  the current user's todos, as full todo objects, in creation order.
- `POST /import` with a body of that same shape **replaces** all of the
  current user's todos with exactly the given ones (same ids, every field,
  that order). It returns 200 and `{"imported": n}`.
  - Ids must be non-empty strings of at most 128 characters, unique within the
    payload. Every todo must be valid under the current rules. Otherwise → 400.
  - If any id currently belongs to a different user → 409.
  - On any error nothing changes.
  - Todos created later must never reuse an imported id.
- An import is one undoable mutation. Undo restores the previous set exactly.
  In the change feed, an import emits a `delete` for every previous todo and a
  `create` for every imported one.
