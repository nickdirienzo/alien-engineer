A key-value store over HTTP, listening on 127.0.0.1 on the port in the `PORT`
environment variable (8080 if unset).

- `PUT /kv/<key>` with any request body stores the body's bytes under `<key>`
  and returns 200. Keys are 1-64 characters from `a-z 0-9 -`. Any other key
  returns 400.
- `GET /kv/<key>` returns 200 and exactly the stored bytes, or 404 if the key
  is not set.
- `DELETE /kv/<key>` returns 200 if the key existed, 404 otherwise.
- `GET /kv` returns 200 and a JSON array of all keys, sorted ascending.
- Stored values survive the process being stopped and started again. State
  lives in files inside the program's own directory.
