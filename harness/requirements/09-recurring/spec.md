## 09 — Recurring todos

- Todos have a `repeat` field: `null` (the default), `"daily"`, `"weekly"`, or
  `"monthly"`. It may be set on create and on PATCH. Any other value → 400.
  A todo with a non-null `repeat` must have a `due` date. Setting `repeat`
  without one, or clearing `due` on a repeating todo, → 400.
- When a repeating todo changes from incomplete to complete, the system also
  creates its next occurrence: a new todo with the same title (and other
  user-set fields), `completed: false`, the same `repeat`, and `due` moved
  forward one period from the completed todo's due date:
  - daily: +1 day; weekly: +7 days.
  - monthly: same day of the next month. If that day doesn't exist, use the
    month's last day (Jan 31 → Feb 28, or Feb 29 in leap years).
  - The new todo is the newest in creation order.
- The PATCH response is the completed todo. Completing an already-completed
  todo creates nothing.
- Undoing that PATCH reverts both changes in one step: the completion and the
  spawned todo. The change feed shows an `update` and a `create`.
