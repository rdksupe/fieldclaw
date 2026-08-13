---
name: fieldclaw-site-setup
description: Set up / map a FieldClaw site — wiki folders (via /init or scaffold), GeoJSON or PDF/image site plans (Datalab/Chandra OCR), zones API, generative map widgets. Also authoritative project enumeration/resolution. Companion to /init and the fieldclaw umbrella skill.
version: 0.3.1
---

# FieldClaw Site Setup & Zone Mapping

Stand up or repair a site map. For **full from-scratch** bootstrap (folders +
mail + people + map), prefer the Supervisor slash command **`/init`**
(`init` skill). This skill is the map/zones deep-dive used by `/init` step 4
and by "import the logistics map" asks.

## Ownership of wiki folders

The FieldClaw API only ensures `kb/projects/{id}/raw/` + `wiki/index.md`.
**It does not hardcode** `zones/`, `ops/`, etc.

- New site: run `/init` or `python $HERMES_HOME/skills/fieldclaw/wiki_fs.py scaffold`
- Ad-hoc: `mkdir` the folders you need under `wiki/` and link them from `index.md`
- Ingest paths mkdir parents on write (e.g. `sources/`, `media/`) — still prefer
  an explicit scaffold so the Wiki UI nav is complete early

Suggested folders: `ops`, `zones`, `people`, `sources`, `maps`, `pos`, `rfis`,
`media`, `pageindex` (+ custom as needed).

## The key pitfall: wiki zones exist ≠ API zone registry populated

Wiki pages under `zones/` do **NOT** guarantee `GET .../zones` is populated.
**Never report "zones live" off the wiki index.** Always verify
`GET {BASE}/api/projects/{id}/zones` (label + polygon).

## Authoritative project enumeration & resolution

Asked "which project / what projects are available", resolve from the DB + API,
**not** memory, other agents' logs, or wiki stubs:

- **Sources of truth, in order:** backing SQLite `data/fieldclaw.db`
  (`SELECT id,name,inbox_email FROM projects`) and the public
  `GET {BASE}/api/projects` (the list endpoint needs **no** auth, but
  `GET /api/projects/{id}` and all per-project routes need a valid `X-API-Key`).
- Memory and cron log references routinely carry **stale project names**
  (e.g. "Human_DC1", "My Site") that no longer exist after a reset/re-seed.
  When memory/logs disagree with DB+API, report the DB+API truth and flag the
  stale reference rather than silently trusting the old name.
- Wiki index files under `kb/projects/{id}/wiki/index.md` are **not** evidence
  of registration — `/init` scaffolds these stub indexes; only a row in the
  `projects` table makes a project live. Earlier sites that are no longer in the
  DB must be explicitly re-registered before you operate on them.

## Map inputs (pick one)

| Input | How |
|-------|-----|
| `*.geojson` / logistics `*.json` | `POST .../sitemap` or `mail/pull-attachments` (auto) |
| Site-plan **PDF / PNG / JPG** with name hint (`sitemap`, `site-plan`, `zone-map`, `logistics`, …) | `POST .../sitemap/upload` multipart **or** `mail/pull-attachments` → OCR (Datalab, Chandra-class) → zones |
| No geometry in OCR | API lays out inferred labels on a **grid** (approximate); refine later with real GeoJSON |

Wilbarger demo sample: `kb/samples/sitemaps/wilbarger-rwwtf-zones.geojson`.

## Workflow

1. **Resolve project** — `GET /api/projects` (match name / inbox). Env `FIELDCLAW_PROJECT_ID` may be stale.
2. **Scaffold wiki** if folders missing — `wiki_fs.py scaffold` (or full `/init`).
3. **Check** — `GET .../zones` + `GET .../wiki/pages` + `GET .../people` (superintendent telegram bound).
4. **Locate map** — `wiki/sources` / `wiki/maps` / AgentMail attachment.
5. **Import**
   - GeoJSON: `POST .../sitemap` `{ "geojson": <FC>, "replace": true }`
   - PDF/image: `POST .../sitemap/upload` (multipart file) **or** ensure filename matches sitemap hints then `POST .../mail/pull-attachments`
6. **Verify** — `GET .../zones` labels+polygons match intent.
7. **UI** — Wiki → **Maps** (live tiles + site-plan gallery) and **PDFs & photos**. Binaries in `wiki/sources/`; sitemap-named also in `wiki/maps/`.
8. **Optional generative UI** — after reading zones / OCR notes, push widgets:

```
PUT {BASE}/api/projects/{id}/ui/widgets
{ "replace": true, "widgets": [
  {"type":"legend","items":["Headworks","Aeration","UV","Biosolids"]},
  {"type":"callout","zone":"Aeration Basins","text":"GMP2 BOP2 critical path"},
  {"type":"stat","label":"zones","value":"11"}
] }
```

Dashboard polls `GET .../ui/widgets` and renders chips/callouts above the zone map.

## People / role

- Operator is `superintendent` (not foreman).
- Foreman is a separate Telegram user / profile — do not seed until asked.

## Pitfalls

- **PDF without a sitemap-ish filename** → treated as normal wiki ingest only (no zones). Rename or use `/sitemap/upload`.
- **Location-map PDFs** (roads only) OCR poorly for process zones — prefer real GeoJSON or a true plot plan.
- **Secrets in shell:** use Python `os.environ` scripts, never inline `$FIELDCLAW_API_KEY`.
- **`execute_code` blocked under cron** — write `.py` + `terminal`.
- **Editing fieldclaw SKILL.md from the `default` profile:** `skill_manage` patch/edit/write_file fail with "Skill not found in active profile"; only `action='create'` resolves on this store. To update an existing fieldclaw skill, recreate it via `skill_manage action='create'` with the full updated SKILL.md, or edit the file on disk at `~/.hermes-fieldclaw/skills/fieldclaw/<name>/SKILL.md`.

## Verification

1. `ls wiki/` shows expected folders (created by Hermes, not assumed)
2. `GET /zones` → N features with polygons (or explicitly empty)
3. `wiki/index.md` lists folders that exist
4. `GET /ui/widgets` if you pushed generative UI
5. Superintendent `telegram_id` set on `GET /people`
