## 12 — Remove tags

Tags turned out to be unused. They are removed. **This replaces requirement 03.**

- Todo objects no longer have a `tags` field, including todos that had tags
  before.
- A `POST /todos`, `PATCH`, or bulk item containing a `tags` field → 400.
- `GET /tags` → 404.
- `GET /todos?tag=...` → 400.
- Nothing else changes.
