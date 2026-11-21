## 02 — Editing titles and due dates

- `PATCH /todos/:id` may include `title` (same rules as on create; invalid →
  400 and no change). Every successful PATCH returns 200 with the full,
  updated todo object.
- Todos have a `due` field: either `null` or a date string `"YYYY-MM-DD"`.
  - `due` may be set on create and on PATCH. It defaults to `null`.
    `"due": null` on PATCH clears it.
  - The date must be a real calendar date (`2024-02-29` is valid,
    `2025-02-29` is not). It must be exactly in `YYYY-MM-DD` form. Anything
    else → 400, and nothing is created or changed.
- `GET /todos?due_before=YYYY-MM-DD` returns only todos whose `due` is strictly
  before that date. Todos with no due date are excluded. An invalid date → 400.
- Filters combine with AND, e.g. `?completed=false&due_before=2027-01-01`.
- A PATCH changes only the fields it contains.
