## 08 — Change feed

- `GET /changes?since=N` (`N` is an integer ≥ 0, default 0; invalid → 400)
  returns 200 with:
  `{"changes": [{"seq": <int>, "op": "create"|"update"|"delete", "id": "<todo id>"}, ...], "next": <int>}`
- The feed is per user. It lists, in ascending `seq` order, every change to
  the user's todos with `seq > N`. `next` is the highest `seq` returned, or
  `N` if nothing was returned. A client that repeatedly passes back `next`
  sees every change exactly once.
- Each mutation produces one entry per affected todo. A bulk create produces
  one `create` per todo; clear-completed produces one `delete` per todo. An
  undo produces entries describing what it did: undoing a create emits
  `delete`, undoing a delete emits `create`, undoing an update emits `update`.
- `seq` values strictly increase within a user's feed, are never reused, and
  survive restarts.
