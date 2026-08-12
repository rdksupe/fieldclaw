# FieldClaw

**Ground truth in. Decisions out.**

FieldClaw is a construction execution brain built on top of [Hermes](https://github.com/NousResearch/hermes-agent): a project logbook API, a folder-organized site wiki, Telegram capture for foremen and superintendents, and AgentMail for supplier and AE traffic. The product thesis is simple. Field knowledge dies in heads and chat threads; office knowledge dies in inboxes; the superintendent sits between both worlds and still waits for truth. FieldClaw closes that loop so a status report, shortage, or delayed PO becomes structured state, wiki context, and a decision path back to the crew.

Pitch deck: [`deck/FieldClaw_Pitch_Deck.pdf`](deck/FieldClaw_Pitch_Deck.pdf)

---

## Architecture

Editable source: [`docs/diagrams/fieldclaw-architecture.excalidraw`](docs/diagrams/fieldclaw-architecture.excalidraw) · Mermaid source: [`docs/diagrams/fieldclaw-architecture.mmd`](docs/diagrams/fieldclaw-architecture.mmd)

![FieldClaw technical architecture](docs/diagrams/fieldclaw-architecture.png)

The diagram shows three planes working together. On the left, field and mail capture enter through Telegram (separate foreman and superintendent bots) and AgentMail project inboxes. In the middle, a Hermes multiplex gateway runs two role profiles that share one FieldClaw skill pack but keep separate SOUL files, session spaces, allowlists, and Mem0 buckets; speech goes through smallest.ai STT/TTS when voice notes or spoken replies are needed. On the right, FieldClaw owns structured state in FastAPI/SQLite and narrative knowledge in per-project filesystem wikis, with Datalab/Chandra OCR and PageIndex for documents, while the web UI on `:8000` projects ops, wiki, maps, PDFs, and crew pairing from that same API.

### How to read the diagram

Field capture never writes the database directly. Hermes skills call the FieldClaw HTTP API with an API key and, on Telegram turns, an actor Telegram id so role checks can distinguish superintendent from foreman. Mail attachments and site plans land in `kb/projects/{id}/raw/` and compiled wiki pages under `wiki/`. Zones only count as “live” when `GET /zones` returns polygons in the API; wiki markdown alone is not enough. The UI reads the same project id the agent resolves, which is why browser `localStorage` and stale `FIELDCLAW_PROJECT_ID` values caused early multi-project confusion and why the dashboard now prefers explicit project selection plus a **Reset cache** control.

---

## Why this architecture

### Vectorless RAG (folder wiki + PageIndex)

Most agent stacks default to embeddings. FieldClaw does not. Each project has an isolated knowledge base under `kb/projects/{id}/` with `raw/` for originals and `wiki/` for markdown the agent walks like a Karpathy-style notebook: start at `index.md`, follow `[[wiki links]]`, use `rg`/`cat` for lookup. Large PDFs additionally get a **PageIndex** JSON tree for structure-aware navigation, while full text still comes from **Datalab** (Chandra-class OCR) rather than brittle pypdf extraction.

That choice is deliberate. Site facts must stay inspectable by a human superintendent, editable without re-embedding, and strictly project-isolated so one job’s PO notes never bleed into another. Vector search hides provenance and mixes tenants; folder wiki keeps provenance on disk. Hermes skills are written to prefer filesystem tools over legacy wiki “lookup” endpoints.

Wiki folders are also **not hardcoded by the API**. Project create only scaffolds `raw/` and `wiki/index.md`. Supervisor Claw runs **`/init`** (or `wiki_fs.py scaffold`) to create `ops`, `zones`, `people`, `sources`, `maps`, `pos`, `rfis`, `media`, `pageindex`, and any custom folders the site needs. The API discovers whatever directories exist and the UI renders them.

### Structured logbook vs narrative wiki

Zones, tasks, people, events, and the superintendent queue live in SQLite behind FastAPI because they need queries, role gates, and kanban semantics. Long-form context (RFI outlines, PO notes, safety log, OCR of bid docs) lives in markdown because that is what agents and humans already know how to read. Status events posted to the API are mirrored into `wiki/ops/log.md` so the narrative trail and the structured trail stay aligned.

### Supervisor / foreman isolation (and what broke before)

Hermes is extended into two **role profiles**, not company tenants:

| Profile | Home | Bot | Users |
|---------|------|-----|-------|
| Supervisor Claw | `~/.hermes-fieldclaw` | Superintendent Telegram bot | Superintendent |
| Foreman Claw | `~/.hermes-fc-foreman` (mux profile) | Separate foreman bot | All foremen, keyed by Telegram user id |

Both profiles symlink the same `apps/hermes-skill/fieldclaw` skill tree so tools, wiki rules, and HTTP contracts stay identical. Isolation is enforced at several layers: separate SOUL / session / pairing allowlists, `people.telegram_id` → project + role in the API, per-project `kb/projects/{id}/`, Mem0 scoped per Telegram user (never a shared `MEM0_USER_ID`), and a `protect-identity` plugin that blocks agents from rewriting `SOUL.md`, `config.yaml`, or `.env`.

Early demos collapsed identity by auto-binding one Telegram id onto every new project’s superintendent, sharing one AgentMail inbox across multiple projects, and leaving the UI stuck on an empty “My Site” in `localStorage` while Wilbarger had the real zones. That produced contradictory mail events, wrong cron escalate targets, and pairing confusion. The fix was blank-slate wipes of DB/wiki/pairing, removal of Wilbarger hardcoding from the UI, optional inbox reuse at project create, resolve-by-project instead of “newest project wins,” and explicit `/init` for wiki taxonomy.

### Multi-project support

The API lists projects with inbox email and KB path. Hermes mail and cron skills must map `inbox_email` → `project_id` before ingesting threads, and must not trust a stale env project id. Skills under `multi-project-inbox-polling`, `fieldclaw-mail-poll`, and `fieldclaw-cron-escalation` document the failure modes we hit in production-like runs: orphan-thread false positives, duplicate same-name projects on one inbox, and resolve-by-newest landing on an empty sibling. Dedup is event-based (`payload.thread_id` on `email.*` / `wiki.updated`), and escalation must scan shortages across tenant projects when needed.

### Images, STT, TTS

Telegram photos are not auto-saved. Hermes uploads proofs with `POST /proofs` or `POST /wiki/ingest`, which write `wiki/media/` and link the photo into `ops/log`. Site-plan images and PDFs whose filenames contain hints like `sitemap`, `site-plan`, or `zone-map` go through Datalab OCR into zone import (`/sitemap/upload`) and are mirrored under `wiki/maps/` for the Wiki **Maps** gallery; all PDFs/images are listable via `/wiki/assets` and render inline in **PDFs & photos**. Voice notes use **smallest.ai** STT; spoken or voice replies can use TTS. Vision-capable models can describe photos when the Hermes profile is configured for them, but the durable artifact is always the file in the project KB.

### Extending Hermes

FieldClaw is not a thin wrapper. The Hermes extension surface includes:

- A full skill pack: site `/init`, geojson/sitemap import, mail poll/sweep, cron transport routing (browser_console for local API vs curl for AgentMail), notify delivery discipline, supplier delay watchers, escalation with dedup, and more under `apps/hermes-skill/fieldclaw/`.
- Multiplexed Supervisor + Foreman profiles with provision script (`deploy/hermes/provision_role.sh`).
- Identity templates (`SOUL.md`, `SOUL.foreman.md`) and operating notes (`AGENTS.md`).
- Cron jobs on the mux profile for shortages, supplier delays, mail, daily report, and supplier check-in.
- One-command local bring-up: `./scripts/start_fieldclaw.sh` starts API/UI and `hermes-fieldclaw gateway run --replace`.

Hermes Hermes setup detail lives in [`deploy/hermes/README.md`](deploy/hermes/README.md).

---

## Demo reality: Wilbarger RWWTF corpus and mail

For a credible live demo we avoided inventing a fake plant map. Public bid and award documents for **Wilbarger Creek Regional Wastewater Treatment Facility** (City of Round Rock / Legistar / Granicus) were located and indexed under `kb/samples/wilbarger/SOURCES.md`. Multi-hundred-page GMP bid books were split into mail-safe PDF parts because Gmail SMTP and AgentMail practical limits sit well below a single 30MB+ attachment. A process-area **GeoJSON** (`kb/samples/sitemaps/wilbarger-rwwtf-zones.geojson`) encodes plant zones from the drawing list so the Ops map is real geometry, not a decorative template.

Mail seeding uses `sim/emitters/wilbarger_mail_seed.py` to SMTP historically paced messages into an AgentMail inbox (demo default `fc-my-site8506@agentmail.to`). Chandra/Datalab was probed on the public site-location map PDF: submit succeeded but the job stayed processing, and that file is a road location map anyway—not a process-area plan—so zone truth stays on GeoJSON or a true site-plan image with a sitemap-ish filename. OxBlue-style site cameras and foreman pulse scripts exist for showcase timing; foreman seeding is opt-in and should not run until you ask.

Eval / replay JSONL under `sim/` is for operators only. Site-facing Hermes SOUL instructions forbid discussing simulation.

---

## Repository map

| Path | Role |
|------|------|
| `apps/api/` | FastAPI logbook, wiki ingest, sitemap, pairing |
| `apps/web/` | Dashboard (Ops, Wiki Pages/Maps/Docs, Log, Crew) |
| `apps/hermes-skill/fieldclaw/` | Hermes skills + `wiki_fs.py` + `/init` |
| `deploy/hermes/` | Profile templates, env example, provision, Hermes README |
| `scripts/start_fieldclaw.sh` | Start API/UI + Supervisor gateway |
| `kb/samples/` | GeoJSON + corpus indexes (large PDFs stay local) |
| `deck/` | Pitch deck PDF/PPTX |
| `docs/diagrams/` | Architecture Excalidraw + PNG |

---

## Quick start

### Requirements

Python 3.12+, [`uv`](https://github.com/astral-sh/uv), a Hermes install with `hermes-fieldclaw` on `PATH`, Telegram bot token(s), AgentMail API key, FieldClaw API key matching `apps/api/.env`, and optionally OpenRouter (or your LLM), Datalab, PageIndex, Mem0, and smallest.ai.

### Bring up UI + gateway

```bash
./scripts/start_fieldclaw.sh
```

Open **http://127.0.0.1:8000/**. Logs land in `/tmp/fieldclaw/`. Ctrl+C stops both processes. Use `--no-gateway` or `--no-api` when you only want one side.

### First project

1. In the UI onboard modal, enter your name and project name.
2. Optionally paste an existing AgentMail address (Wilbarger demo inbox: `fc-my-site8506@agentmail.to`); leave blank to provision a new inbox.
3. Create the project, then pair Telegram with the Supervisor bot code (Crew tab or onboard pair field).
4. DM Supervisor and run **`/init`** so Hermes scaffolds wiki folders, pulls mail, and imports a sitemap when present.
5. Confirm zones with the Ops map and Wiki → Maps; open PDFs under Wiki → PDFs & photos.
6. Use **Reset cache** if the browser still points at a deleted project id.

API-only:

```bash
cd apps/api && cp .env.example .env && uv sync
uv run uvicorn fieldclaw_api.main:app --host 127.0.0.1 --port 8000
```

Hermes-only and secrets: see [`deploy/hermes/README.md`](deploy/hermes/README.md).

---

## Honesty rules

Log `notify.sent` only when Telegram delivery confirms. Do not claim wiki or mail success without API/ingest proof. Do not invent POs, ETAs, zones, or people. Do not seed foreman demo traffic until a human asks. Do not put personal Gmail in the agent inbox path—AgentMail only.

---

## License / status

Hackathon and research prototype. Treat API keys, pairing allowlists, and site documents as sensitive.
