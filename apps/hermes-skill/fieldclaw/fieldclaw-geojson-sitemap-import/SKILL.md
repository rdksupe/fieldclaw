---
name: fieldclaw-geojson-sitemap-import
description: FieldClaw — import an inbound *.geojson site-logistics/zone map into zones via mail/pull-attachments, verify zones + wiki, and post email.* + wiki.updated events. For processing inbound site logistics map emails under cron.
version: 0.1.0
---

# FieldClaw GeoJSON / sitemap import (inbound site logistics map)

A frequent inbound is a `*.geojson` "site logistics / zone map" attachment
(e.g. sender says "import the Phase-1 zone map and confirm on dashboard").
This is a full pipeline: route the email to its project, log it, feed the
attachment through FieldClaw, verify zones, and report.

## When to use

- An inbound mail on a mapped FieldClaw inbox carries a `*.geojson` attachment
  whose subject/body says it is a site logistics / zone map.
- **Or** a PDF/PNG/JPG whose **filename** includes `sitemap` / `site-plan` /
  `zone-map` / `logistics` (OCR via Datalab/Chandra → zones). See
  `fieldclaw-site-setup`.
- The GeoJSON content_type is `application/geo+json` and it is a FeatureCollection.

## Steps

1. **Resolve project + route by inbox**: `GET /api/projects` → map `inbox_email`
   → `id`. Only poll the mapped inboxes. (Env `FIELDCLAW_PROJECT_ID` may be stale.)
2. **Fetch thread** (REST fallback when AgentMail MCP is down):
   `GET https://api.agentmail.to/v0/inboxes/{inbox}/threads/{thread_id}` with
   `Authorization: Bearer {AGENTMAIL_API_KEY}` → subject, body, attachments[].
3. **POST `email.inbound`** to `POST /api/projects/{pid}/events`:
   payload `thread_id, from, subject, received_at, message_count, attachments[]`.
4. **POST `email.parsed`**: payload `thread_id, from, subject, po_ids:[], eta:null,
   zones:[], intent, has_delay:false`. For a sitemap there is usually no PO/ETA —
   no `schedule.flagged` unless a delay keyword actually appears.
5. **Import the map**: `POST /api/projects/{pid}/mail/pull-attachments` (JSON, no
   body). This fetches the attachment AND auto-imports `*.geojson` → zones in one call.
   Do NOT hand-parse or fetch the geojson yourself; the route builds the zones.
6. **Post `wiki.updated`**: the import changed the wiki, so log the event per the
   `fieldclaw` skill even though the route wrote the files.
7. **Verify before reporting**: `GET /api/projects/{pid}/zones` + inspect
   `wiki/index.md` and `wiki/zones/`. Only claim "zone map is live" after both confirm.

## mail/pull-attachments response shape

```json
{"saved":[{"message_id":"<...>","filename":"<file>.geojson","bytes":N}],
 "ingested":[],
 "sitemaps":[{"replaced":6,"zones":[{"label":"Zone A — Structure","polygon":[[...]]}, ...],
              "count":6,"source":"<file>.geojson"}]}
```

- `sitemaps[].zones` = the authoritative zone set the map produced.
- `replaced` = number of zones created/replaced.
- The route writes `raw/<file>.geojson`, `wiki/zones/<slug>.md` for each zone, and
  refreshes the `index.md` "Site map (imported)" section automatically.

## Pitfalls

| Pitfall | Fix |
|---------|-----|
| Hand-fetching the geojson instead of using the route | Don't. `mail/pull-attachments` parses it into zones for you. |
| Claiming the zone map is live off the POST response alone | Cross-check `GET /zones` + `wiki/index.md` first. |
| Forgetting `wiki.updated` after the import | The import changes the wiki; log the event (echo zone labels + thread_id). |
| Trying to retrieve the attachment at `/inboxes/{inbox}/attachments/{id}` | 404 — that path does not exist. Use the FieldClaw pull route, not a manual AgentMail fetch. |
| Calling MCP list_inboxes and getting `AttributeError: 'CallToolResult' object has no attribute 'isError'` | MCP down; fall back to REST `GET /v0/inboxes`. |

## See also

- `multi-project-inbox-polling` — label filtering, dedup, inbox→project routing
- `fieldclaw-mail-poll` — consolidated single-Python-script cron pattern
- `agentmail-rest-polling` — REST response shapes, GET-only limits
