## 01 — Validation, single-todo reads, and 404s

- `GET /todos/:id` returns 200 and the todo object, or 404 if no such todo
  exists (or it was deleted).
- `PATCH /todos/:id` and `DELETE /todos/:id` on an unknown or deleted id
  return 404.
- New todos have `"completed": false`.
- Titles:
  - MUST be a string of 1–1000 characters, counted in Unicode code points
    (one emoji = one character).
  - MUST NOT be empty or consist only of whitespace.
  - Are stored and returned exactly as given: no trimming or normalization.
    Any Unicode is allowed, including emoji, CJK, RTL text, quotes,
    backslashes, newlines and tabs, whether sent as raw UTF-8 or as JSON
    `\u` escapes.
- `POST /todos` returns 400 if the body is not valid JSON, is not an object,
  or has a missing or invalid `title`. Nothing is created.
- `PATCH /todos/:id` with a `completed` value that is not a boolean returns 400,
  and the todo is unchanged.
