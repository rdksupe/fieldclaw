---
name: fieldclaw-sitemap-import-no-inbox
description: FieldClaw cron fallback for importing an inbound *.geojson site-logistics/zone map when the target project has NO mapped inbox_email — mail/pull-attachments returns 400, so fall back to fetching the attachment from AgentMail REST (signed download_url) and POST /sitemap. Class-level companion to fieldclaw-geojson-sitemap-import.
version: 0.1.0
---

# FieldClaw sitemap import — project with no inbox_email (manual fallback)

`POST /api/projects/{pid}/mail/pull-attachments` is the normal one-call route to
import an inbound `*.geojson` site-logistics map into zones (see
`fieldclaw-geojson-sitemap-import`). That route is **not always available**: when
the resolved project has `inbox_email: null` (no mapped inbox), it returns
`400 {"detail":"project has no inbox_email"}` and cannot locate the attachment.

This skill is the manual fallback so a zone-map import still completes rather than
dead-ending on the 400. Verified 2026-08-12 (Smoke Site, single project, no mapped
inbox; thread `f8e8ede9…`, attachment `human-dc1-site-logistics.geojson`).

## When to use

- An inbound mail carries a `*.geojson` `application/geo+json` FeatureCollection
  (site logistics / zone map).
- You've resolved the project and `GET /api/projects` shows `inbox_email: null` for it.
- You called `mail/pull-attachments` and it 400'd with `project has no inbox_email`.

## Manual import steps

1. **Download the attachment from AgentMail REST** (works with Bearer API-key auth;
   MCP may be down):
   - `GET https://api.agentmail.to/v0/inboxes/{inbox_id}/threads/{thread_id}/attachments/{attachment_id}`
     → returns metadata with a **signed, expiring `download_url`** (mind `expires_at`,
     ~4h; refetch for a fresh URL if expired).
   - `GET <download_url>` (public CDN, no auth) → raw bytes. Note this path IS the
     correct one — the skill `fieldclaw-geojson-sitemap-import`'s older pitfall
     about `/inboxes/{inbox}/attachments/{id}` 404ing refers to the path WITHOUT the
     `threads/{tid}` segment; include it.
2. **POST the map**: `POST /api/projects/{pid}/sitemap` with JSON body
   `{"geojson": {<parsed FeatureCollection>}, "replace": true}` (`X-API-Key` header).
   Response `zones[]` is authoritative; `replaced` = how many were created.
3. **POST `email.inbound` + `email.parsed`** events (payload: thread_id, from,
   subject, received_at, message_count / po_ids, eta, zones, intent, has_delay).
   For a sitemap there's usually no PO/ETA → no `schedule.flagged` unless a real
   delay keyword appears.
4. **POST `wiki.updated`** — the import wrote wiki zone pages, so log it (fieldclaw
   skill honesty rule: only claim wiki updated if this succeeds).
5. **Verify before reporting**: `GET /api/projects/{pid}/zones` (expect N zones) and
   `GET /api/projects/{pid}/wiki/pages` (expect `index.md`, `ops/log.md`, and
   `zones/<slug>.md` per zone). Only then say the zone map is live.

## Order matters

Log `email.inbound` + `email.parsed` BEFORE or alongside the import so the thread is
marked handled, but never claim the wiki/zones updated from the events alone — the
import step (sitemap POST) and its verify are what prove the KB changed.

## Pitfall: don't stop at the 400 and notify "cannot import"

The `pull-attachments` 400 is a routing limitation (no inbox), not a fatal error.
The attachment is still in AgentMail; fetch-and-POST gets the map in. Only report a
failure after the manual fallback also fails.

## See also / overlap

Overlaps `fieldclaw-geojson-sitemap-import` (preferred route + its response shape).
That skill covers projects WITH a mapped inbox; this one covers the no-inbox case.
The curator should consider folding both under one umbrella with a "mapped inbox vs
no mapped inbox" branch. Related: `multi-project-inbox-polling` (routing),
`agentmail-rest-polling` (REST shapes, GET-only limits).
