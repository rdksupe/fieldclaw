# FieldClaw wiki librarian rules

- `raw/` is immutable source truth (PDF dumps, notes). Never rewrite in place after ingest except append-only corrections logged as new files.
- `wiki/` is compiled markdown: entity pages, source pages, `index.md`.
- On every ingest: update or create pages, refresh `index.md`.
- Query path: read `index.md` first, then open linked pages. No vector database.
- Prefer construction entities: PO numbers, zones, suppliers, materials, RFIs.
