## 03 — Tags

- Todos have a `tags` field: an array of strings, defaulting to `[]`.
  - `tags` may be set on create and on PATCH. On PATCH it replaces the whole set.
  - Each tag is 1–32 characters from `a-z`, `0-9` and `-`. Anything else (or
    a non-array `tags`) → 400, and nothing is created or changed.
  - Duplicates collapse into one. Tags are always returned sorted ascending.
- `GET /todos?tag=x` returns todos that have tag `x`. If `tag` is repeated
  (`?tag=a&tag=b`), a todo must have all of the given tags. It combines with
  the other filters using AND.
- `GET /tags` returns 200 and an array of `{"tag": "...", "count": n}`, one
  entry per tag used by at least one non-deleted todo. `count` is how many
  todos have that tag. The array is sorted by tag.
