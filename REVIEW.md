# Review rules

A reviewer audits `/experiment/` every generation that passes its checks. A
violation fails the generation. The rules exist so that the language is real
and is the thing the programs depend on.

1. **Programs are written in the language.** Everything under `apps/` is
   source (or data) in the language defined in `lang/`. It is not Python,
   JavaScript, shell, C, SQL, or any other language that existed before this
   repository. It does not embed, generate, or pass along source in such a
   language to be executed.

2. **The language is general-purpose.** Nothing in `lang/` is specific to
   any program. No todo concepts (todos, titles, tags, due dates, undo of
   todos, the todo HTTP routes, the change feed, and so on) appear in the
   language or its implementation. General capabilities are expected and
   fine: networking, HTTP, JSON, files, durability, data structures,
   concurrency, time and dates, text. The test: could a different program,
   such as a chat server or a key-value store, be written in this language
   without changing `lang/`? If only a todo service is possible, the language
   is the app.
   This covers `lang/verify` too: whatever it checks about a particular
   program comes from that program's own directory.

3. **Programs reach the world only through the language.** An app touches
   sockets, files, processes, and time only through capabilities its language
   provides.

How `lang/` is implemented is unrestricted. It may be written in any
language, compiled, interpreted, or anything else.
