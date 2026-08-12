---
name: init
description: Supervisor /init — bootstrap a FieldClaw project from scratch (wiki folders, mail, sitemap, people, dashboard). Invoke via Telegram slash /init or when asked to set up a new site.
version: 0.1.0
---

# `/init` — full project context from scratch

You are Supervisor Claw. When the user runs **`/init`** (or says “set up this
site from scratch”), run this checklist end-to-end. Do **not** invent site
facts — only scaffold structure and import what mail/files actually contain.

Companion skills: `fieldclaw` (umbrella), `fieldclaw-site-setup` (zones/map).

## Goal

A usable project with:

1. Resolved/created FieldClaw project + KB root
2. Wiki folder taxonomy created **by you** (API does not hardcode folders)
3. Mail attachments pulled / docs ingested
4. Zones live in the **API** (GeoJSON or site-plan OCR) when a map exists
5. People roles checked; pairing instructions if unbound
6. Short status report back to the superintendent on Telegram

## 0. Resolve or create project

```
GET {FIELDCLAW_BASE_URL}/api/projects
Header: X-API-Key: {FIELDCLAW_API_KEY}
```

- If env `FIELDCLAW_PROJECT_ID` 404s → re-resolve by name/inbox.
- If **no** projects: create one

```
POST {FIELDCLAW_BASE_URL}/api/projects
{ "name": "<site name from user or mail>", "provision_inbox": true }
```

Optional: pass existing `inbox_email` when the inbox already exists.

Set working KB: `$REPO/kb/projects/{id}/` (or `project.kb_relpath`).
Prefer `python $HERMES_HOME/skills/fieldclaw/scripts/resolve_project.py`.

## 1. Scaffold wiki folders (Hermes owns taxonomy)

API only creates `raw/` + `wiki/index.md`. **You** create folders:

```bash
python $HERMES_HOME/skills/fieldclaw/wiki_fs.py scaffold
```

Suggested set (add more only if the site needs them):

| Folder | Purpose |
|--------|---------|
| `ops/` | `log.md`, schedule/safety notes |
| `zones/` | one page per process area |
| `people/` | crew / contacts |
| `sources/` | PDF outlines + OCR notes |
| `maps/` | site plans / GeoJSON copies for Wiki → Maps tab |
| `pos/` | purchase orders |
| `rfis/` | RFIs |
| `media/` | field photos |
| `pageindex/` | large-PDF trees |

Write starter stubs if missing:

- `wiki/ops/log.md` — site log header
- `wiki/ops/agents.md` — Supervisor + Foreman pairing note
- `wiki/people/` pages only for **known** people (from API `GET .../people`), never invent names
- Refresh `wiki/index.md` (scaffold does this)

You may add custom folders (e.g. `contracts/`) when docs require them — mkdir + link from index.

## 2. Bind / verify people

```
GET .../api/projects/{id}/people
GET .../api/people/by-telegram/{telegram_user_id}   # if available
```

- Operator on this chat should be `superintendent`.
- If unbound: tell them to send pairing code → `POST /api/pairing/approve`
  with `bind_role: "superintendent"`.
- Do **not** seed/register a foreman until the human asks.

## 3. Pull mail + ingest

```
POST .../api/projects/{id}/mail/pull-attachments
```

Then, for anything still sitting on disk / in AgentMail:

- PDFs → `wiki_fs.py ingest` or `pageindex` (large)
- Images as proofs → `POST .../proofs`
- Filenames with `sitemap` / `site-plan` / `zone-map` / `logistics` → zone import
  (see step 4)

Project facts into logbook with `email.parsed` / `wiki.updated` as appropriate.
Never claim KB updated unless ingest succeeded.

## 4. Map the site (zones)

Follow **`fieldclaw-site-setup`**:

| Input | Action |
|-------|--------|
| `*.geojson` | `POST .../sitemap` or upload |
| Site-plan PDF/PNG with name hint | `POST .../sitemap/upload` |
| Nothing in mail | Ask superintendent for area names → `POST .../zones` (no invented A/B/C) |

**Verify** `GET .../zones` has polygons/labels before saying the map is live.
Wiki `zones/*.md` alone is not enough.

Optional generative UI:

```
PUT .../ui/widgets
{ "replace": true, "widgets": [ ... legend / callout / stat from real zones ... ] }
```

## 5. Confirm UI surfaces

- Wiki **Pages** — folders you created show in nav
- Wiki **Maps** — zone tiles + site-plan gallery (`wiki/maps/`, sitemap-named files)
- Wiki **PDFs & photos** — binaries under `wiki/sources` / `raw`

## 6. Report back (Telegram)

Short checklist to the superintendent:

```
Init complete for <project name>
• inbox: <email>
• wiki folders: …
• zones: N (or “none yet — send GeoJSON / site-plan”)
• people: super bound? foreman unbound until you say
• next: …
```

Log `notify.sent` only if Telegram delivery confirmed.

## Pitfalls

- **Do not** wait for the API to mkdir taxonomy — that is your job in `/init`.
- **Do not** invent zones, POs, or people.
- **Do not** seed foreman traffic / demo pulse unless explicitly asked.
- Cron: use HTTP + `terminal` scripts; avoid `execute_code` under cron.
- Secrets: never echo `$FIELDCLAW_API_KEY` in shell one-liners.

## Done when

1. `GET /projects/{id}` OK  
2. `ls wiki/` shows folders you created  
3. `GET /zones` matches reality (or explicitly empty + next ask)  
4. Superintendent got the summary message  
