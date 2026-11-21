A vote counter over HTTP, listening on 127.0.0.1 on the port in the `PORT`
environment variable (8080 if unset). Bodies are JSON.

- `POST /vote` with `{"voter": "<name>", "choice": "<text>"}` records that
  voter's choice and returns 200. Both fields must be non-empty strings of at
  most 100 characters, otherwise 400. A voter who votes again replaces their
  earlier vote.
- `GET /results` returns 200 and a JSON array of `{"choice": ..., "votes": n}`
  for every choice with at least one vote, sorted by votes descending, then
  by choice ascending.
- `GET /voters/<name>` returns 200 and `{"choice": ...}`, or 404 if that
  voter has not voted.
- Votes survive the process being stopped and started again. State lives in
  files inside the program's own directory.
