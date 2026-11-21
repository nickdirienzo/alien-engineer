## 04 — Search, ordering, and paging

- `GET /todos?q=text` returns todos whose title contains `text`. The match is
  case-insensitive (at least for ASCII letters) and is a plain substring
  match, not a pattern.
- All filters combine with AND.
- Results are always in **creation order**, oldest first. Updates do not
  change a todo's position, and the order is the same after a restart.
- `limit` (integer 1–1000) and `offset` (integer ≥ 0) page the filtered
  results. With no `limit`, all results are returned. Invalid values → 400.
- Every `GET /todos` response includes an `X-Total-Count` header: the number
  of todos matching the filters, before `limit`/`offset` are applied.
