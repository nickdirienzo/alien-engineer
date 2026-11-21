## 05 — Users

- Every request may carry an `X-User` header naming a user: 1–64 characters
  from `A-Z a-z 0-9 _ -`. An invalid value → 400. If the header is missing,
  the request acts as user `default`, so existing clients keep working.
- Each user sees only their own todos, everywhere: lists, filters,
  `X-Total-Count`, `GET /todos/:id`, `/tags`, and anything added later.
- A `GET`, `PATCH` or `DELETE` on another user's todo returns 404 and must
  not change it.
- Todo ids stay unique across all users.
