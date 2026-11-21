## 06 — Bulk create and clearing completed todos

- `POST /todos/bulk` takes a JSON array of 1–1000 objects, each shaped like a
  `POST /todos` body. It returns 201 and an array of the created todos, in
  the same order. The operation is atomic: if any item is invalid (or the
  array is empty, too long, or not an array), it returns 400 and creates
  nothing.
- `DELETE /todos?completed=true` deletes all of the current user's completed
  todos and returns 200 with `{"deleted": n}`. `DELETE /todos` without
  `completed=true` returns 400 and deletes nothing.
