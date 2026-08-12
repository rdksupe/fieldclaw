# FieldClaw HTTP — logbook + projects

```
# Auth
#   X-API-Key: FIELDCLAW_API_KEY (single shared key)
#   X-Actor-Telegram: optional person.telegram_id for role checks
#     (superintendent for sitemap/zones/super-reply/pairing; crew for events/proofs)

GET  {FIELDCLAW_BASE_URL}/api/projects
POST {FIELDCLAW_BASE_URL}/api/projects
  Body: { "name", "inbox_username?", "provision_inbox?", "inbox_email?" }

GET  /api/projects/{id}
GET  /api/projects/{id}/zones|events|tasks|people|super-queue|daily-log
POST /api/projects/{id}/events
PATCH /api/projects/{id}/people/{person_id}   { "telegram_id" }
POST /api/projects/{id}/admin/register        { "name", "email?", "telegram_id?" }
POST /api/projects/{id}/foreman/register      { "name", "email?" }

GET  /api/pairing
POST /api/pairing/approve
  Body: { "code", "platform":"telegram", "project_id", "bind_role":"foreman"|"superintendent", "person_name?" }

GET  /api/projects/{id}/wiki/index
GET  /api/projects/{id}/wiki/pages
GET  /api/projects/{id}/wiki/assets             # PDFs / images / GeoJSON for Wiki Maps + Docs tabs
# Wiki folders: created by Supervisor /init (`wiki_fs.py scaffold`) — API discovers them
GET  /api/projects/{id}/wiki/page?path=index.md
# Prefer filesystem tools on kb/projects/{id}/wiki/
POST /api/projects/{id}/wiki/lookup             # legacy; avoid — use rg/cat on wiki/
POST /api/projects/{id}/mail/pull-attachments   # AgentMail → wiki; *.geojson OR site-plan PDF/PNG → zones
POST /api/projects/{id}/sitemap                 # JSON body {geojson, replace?} → zones + wiki/zones
POST /api/projects/{id}/sitemap/upload          # multipart .geojson OR PDF/image site plan (Datalab/Chandra)
GET  /api/projects/{id}/ui/widgets              # generative map chips / callouts / stats
PUT  /api/projects/{id}/ui/widgets              # { widgets:[...], replace? }
POST /api/projects/{id}/events                  # progress.reported | shortage.raised | … → wiki/ops/log
POST /api/projects/{id}/proofs                  # multipart → wiki/media
POST /api/projects/{id}/wiki/ingest
GET  /api/projects/{id}/wiki/file/{path}        # binary under wiki/ (pdf, png, geojson)
GET  /api/projects/{id}/raw/file/{path}         # binary under raw/
```

Header: `X-API-Key: {FIELDCLAW_API_KEY}` (+ optional `X-Actor-Telegram`)

Resolve project (never trust stale env alone):

```bash
python apps/hermes-skill/fieldclaw/scripts/resolve_project.py
```
