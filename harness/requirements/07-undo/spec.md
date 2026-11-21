## 07 — Undo

- `POST /undo` reverts the current user's most recent mutation that has not
  already been undone, and returns 200. Calling it again keeps going further
  back. When nothing is left to undo it returns 409.
- A mutation is any successful create, PATCH, DELETE, bulk create, or clear of
  completed todos (and any mutating endpoint added later). Bulk create and
  clear-completed each undo as a single step.
- Undoing restores exactly the previous state of the affected todos: same
  ids, every field, and the original position in creation order. Undoing a
  create removes the todo.
- There is no redo. Undo history is per user, survives restarts, and keeps at
  least the last 100 mutations per user.
