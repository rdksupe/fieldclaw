# FieldClaw

**Ground truth in. Decisions out.**

FieldClaw is the brain for what is actually happening on a construction site. Foremen report from Telegram, documents and mail get into a project knowledge base, and the superintendent sees a live picture of zones, shortages, the log, and the wiki — then can send decisions back to the field.

It is built on [Hermes](https://github.com/NousResearch/hermes-agent). We did not replace Hermes. We extended it with FieldClaw skills, two role profiles (Supervisor and Foreman), a small HTTP API, and a web UI.

- Pitch deck: [deck/FieldClaw_Pitch_Deck.pdf](deck/FieldClaw_Pitch_Deck.pdf)
- Hermes setup detail: [deploy/hermes/README.md](deploy/hermes/README.md)

---

## Architecture

<p align="center">
  <img src="docs/diagrams/fieldclaw-architecture.png" alt="FieldClaw architecture" width="100%" />
</p>

Capture comes in through Telegram and project mail. Hermes runs Supervisor and Foreman as separate profiles that share the same FieldClaw skills. FieldClaw stores structured state in the API and long-form knowledge in a per-project wiki. The web UI on port 8000 reads that same API.

---

## Introduction

On a real job, field knowledge lives in heads and chat threads. Office knowledge lives in inboxes. The superintendent sits in the middle and still waits for truth. FieldClaw closes that loop: capture → structure → live ops picture → human decision → answer back to the crew.

We keep two kinds of memory on purpose. Structured things (zones, tasks, people, events) go through the FieldClaw API. Long-form site knowledge (POs, RFIs, PDF outlines, safety notes) lives in a folder wiki per project. Agents and humans can both open those files with normal tools.

---

## The various components

| Piece | What it does |
| --- | --- |
| FieldClaw API | Projects, zones, events, tasks, people, pairing, wiki ingest, sitemap import |
| Web UI (`:8000`) | Ops map, kanban, wiki pages, maps gallery, PDF/photo viewer, crew pairing |
| Hermes Supervisor | Superintendent bot, `/init`, mail, cron, notify |
| Hermes Foreman | Separate bot for field capture and proofs |
| Project wiki | `kb/projects/{id}/raw/` + `wiki/` (Karpathy-style LLM wiki) |
| Skills pack | `apps/hermes-skill/fieldclaw/` — shared by both roles |

---

## API design

The API is the system of record for structured site state. Hermes never invents zone geometry or task status in chat alone — it calls HTTP.

All calls need `X-API-Key`. On Telegram turns, also send `X-Actor-Telegram` so role checks work.

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` / `POST` | `/api/projects` | List / create sites (optional existing inbox email) |
| `GET` / `POST` | `/api/projects/{id}/zones` | Zone registry (live map) |
| `GET` / `POST` | `/api/projects/{id}/events` | Logbook events |
| `GET` / `POST` / `PATCH` | `/api/projects/{id}/tasks` | Kanban |
| `GET` | `/api/projects/{id}/people` | Crew + roles |
| `GET` | `/api/projects/{id}/super-queue` | Items waiting on the superintendent |
| `POST` | `/api/projects/{id}/sitemap` | Import GeoJSON → zones |
| `POST` | `/api/projects/{id}/sitemap/upload` | Site-plan PDF/PNG → OCR → zones |
| `POST` | `/api/projects/{id}/mail/pull-attachments` | Pull inbox files into the wiki |
| `GET` | `/api/projects/{id}/wiki/pages` | List wiki pages |
| `GET` | `/api/projects/{id}/wiki/assets` | List PDFs / images / GeoJSON |
| `GET` | `/api/projects/{id}/wiki/file/{path}` | Serve a wiki binary |
| `GET` / `PUT` | `/api/projects/{id}/ui/widgets` | Map chips / callouts |

Status events also append to `wiki/ops/log.md`. Photos go through `POST .../proofs` into `wiki/media/`. Wiki folders are not hardcoded at project create — Supervisor `/init` (or ingest) creates them, and the API discovers what exists.

Skill-oriented HTTP notes: [apps/hermes-skill/fieldclaw/tools_http.md](apps/hermes-skill/fieldclaw/tools_http.md).

---

## Hermes extensions

Out of the box Hermes is a general agent. FieldClaw adds a skill pack under `apps/hermes-skill/fieldclaw/`:

- `/init` — bootstrap a project from scratch (folders, mail pull, map import, short report back)
- Site setup / GeoJSON / site-plan OCR import
- Mail poll and multi-project inbox routing
- Cron helpers (shortages, supplier delays, mail, daily report) with transport notes
- Notify delivery discipline (only log success when Telegram actually delivered)
- `wiki_fs.py` for ingest / PageIndex / scaffold

We also ship identity templates (`SOUL.md`, `SOUL.foreman.md`), a provision script for the foreman profile, and `scripts/start_fieldclaw.sh` so API + gateway come up together.

You still get normal Hermes behavior: gateway, pairing, cron, tools, model config, Mem0 hooks, and so on. FieldClaw sits on top; it does not lock you out of the rest of Hermes.

---

## Separation at the Hermes layer

Superintendent and foreman are two Hermes profiles, not one bot with two moods.

| | Supervisor Claw | Foreman Claw |
| --- | --- | --- |
| Home | `~/.hermes-fieldclaw` | `~/.hermes-fc-foreman` |
| Bot | Superintendent Telegram token | Separate foreman token |
| Users | Superintendent | Many foremen (keyed by Telegram user id) |
| Skills | Same FieldClaw pack | Same FieldClaw pack |

They share skills so tools and wiki rules stay consistent. They do not share SOUL, session space, pairing allowlist, or Mem0 bucket. The API stores `people.telegram_id` + role so a foreman cannot act as superintendent by accident.

An early mistake was binding one Telegram id onto every new project and sharing one inbox across projects. The UI then stuck on an empty site while another project had the real map. We fixed that with blank-slate wipes, no demo hardcoding in the UI, inbox chosen at create time, resolve-by-project (not “newest wins”), and explicit `/init`.

---

## Memory, STT / TTS, and demo data

**Personal memory (Mem0)** — per Telegram user. Do not set a global `MEM0_USER_ID` or everyone shares one brain. This is for prefs and personal notes, not the site logbook.

**Site memory** — the project wiki + API events (see next section). That is the shared job memory.

**STT / TTS** — optional. Voice notes can go through speech-to-text; replies can use TTS. We wired smallest.ai scripts next to the skills; you can point the same hooks at another provider.

**Demo / simulation data** — under `sim/` and `kb/samples/`. For a credible demo we used public Wilbarger Creek RWWTF bid docs (Legistar / Granicus), split large PDFs for mail size limits, built zone GeoJSON from process areas, and seeded mail into a demo inbox. See [kb/samples/wilbarger/SOURCES.md](kb/samples/wilbarger/SOURCES.md) and [kb/samples/sitemaps/wilbarger-rwwtf-zones.geojson](kb/samples/sitemaps/wilbarger-rwwtf-zones.geojson). Eval replay JSONL is for operators only — live Telegram SOUL rules say not to talk about simulation on site channels. Foreman “pulse” seeding stays opt-in.

---

## Knowledge base (Karpathy) and why vectorless RAG

We follow Andrej Karpathy’s LLM wiki pattern instead of default embedding RAG.

Original write-up: [llm-wiki.md (gist)](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f).

Idea in plain terms: keep raw sources immutable, let the agent compile a real markdown wiki (`index.md`, entity pages, links), and at question time walk the index and pages — compile once, keep current — instead of re-deriving everything from chunks every query.

Per project:

```text
kb/projects/{id}/
  raw/     originals (PDFs, extracts)
  wiki/    agent-maintained pages (ops, zones, sources, maps, …)
```

Why vectorless here: site facts must stay readable by a human super, editable without re-embedding, and isolated per job so one site’s POs never bleed into another. Vector search hides provenance and mixes tenants too easily. Hermes uses `ls` / `rg` / `cat` on the wiki. Large PDFs can also get a PageIndex tree for structure; OCR text comes from whatever convert service you configure (Datalab today).

Folders are created by `/init` or on ingest — the API does not force a fixed A/B/C layout.

---

## Mail integration

Each project can have its own inbox address. Hermes (or cron) polls mail, posts `email.inbound` / `email.parsed`, and pulls attachments into the wiki. Files named like `sitemap` / `site-plan` can also drive zone import.

Multi-project rule: map `inbox_email` → `project_id` from `GET /api/projects`. Do not trust a stale env project id. Dedup on thread ids so the same message is not processed forever. One inbox shared by two projects will confuse routing — prefer one inbox per project.

We used AgentMail (`*.agentmail.to`) while building. That is a default, not a hard requirement — see the swap section below.

---

## Security measures

- **API key** on FieldClaw HTTP (`X-API-Key`). Optional actor Telegram id for role checks.
- **Pairing** — Telegram users must be approved before they act as super or foreman.
- **Role separation** — separate bots + `people.role` so field users are not treated as superintendent.
- **Project isolation** — each site has its own `kb/projects/{id}/`.
- **`protect-identity` plugin** ([deploy/hermes/plugins/protect-identity](deploy/hermes/plugins/protect-identity)) — blocks the agent from rewriting `SOUL.md`, `config.yaml`, or `.env` under Hermes home. Personality and secrets stay operator-owned.

---

## Swapping services and customizing Hermes

Nothing in the vendor column is the product core. Change what you like in `.env` and Hermes config. Standard Hermes features (gateway, pairing, cron, tools, model routing) remain.

| Concern | Default we used | Swap how |
| --- | --- | --- |
| Chat model | OpenRouter / Hermes model config | Hermes model settings |
| Project email | AgentMail | Adapt the mail poll skill to your mailbox API |
| PDF / image OCR | Datalab | Swap the convert client; keep ingest paths |
| Large PDF structure | PageIndex | Optional |
| STT / TTS | smallest.ai | Point the skill scripts at another provider |
| Personal memory | Mem0 | Or turn off / replace; never force one global user id |
| DB | SQLite | Change API storage later; keep the HTTP shape |
| Chat transport | Telegram | Pairing + people table are the hooks |

What you usually keep: FieldClaw API contracts, per-project wiki layout, FieldClaw skill pack, Supervisor / Foreman separation.

Customize SOUL, cron schedules, which skills are enabled, inbox mapping, and `/init` behavior however you want for your site. Hermes stays Hermes — FieldClaw is the construction layer on top.

---

## Setup

### 1. Requirements

- Python 3.12+ and [`uv`](https://github.com/astral-sh/uv)
- Hermes Agent installed, with `hermes-fieldclaw` on your `PATH`
- Telegram bot token for the superintendent (and a second token for foreman when you are ready)
- API keys for whatever LLM, mail, OCR, Mem0, and STT/TTS you choose (see swap table)

### 2. FieldClaw API

```bash
cd apps/api
cp .env.example .env
# set FIELDCLAW_API_KEY to something stable
uv sync
```

### 3. Hermes home (Supervisor)

```bash
mkdir -p ~/.hermes-fieldclaw
cp deploy/hermes/env.fieldclaw.example ~/.hermes-fieldclaw/.env
chmod 600 ~/.hermes-fieldclaw/.env
```

Fill in at least: Telegram bot token, LLM key, `FIELDCLAW_BASE_URL=http://127.0.0.1:8000`, the same `FIELDCLAW_API_KEY` as the API, and `FIELDCLAW_KB_DIR` pointing at this repo’s `kb/` directory. Do not set `MEM0_USER_ID`.

Link skills and the identity plugin:

```bash
REPO=/absolute/path/to/fieldclaw

ln -sfn "$REPO/apps/hermes-skill/fieldclaw" \
  ~/.hermes-fieldclaw/skills/fieldclaw

mkdir -p ~/.hermes-fieldclaw/plugins
ln -sfn "$REPO/deploy/hermes/plugins/protect-identity" \
  ~/.hermes-fieldclaw/plugins/protect-identity
```

Copy identity templates into the Hermes home if needed (`deploy/hermes/identity/SOUL.md`, and so on). More detail: [deploy/hermes/README.md](deploy/hermes/README.md).

### 4. Foreman profile (optional until you need field users)

```bash
deploy/hermes/provision_role.sh foreman "<FOREMAN_TELEGRAM_BOT_TOKEN>"
```

### 5. Start API + gateway

```bash
./scripts/start_fieldclaw.sh
```

- UI: http://127.0.0.1:8000/
- Logs: `/tmp/fieldclaw/api.log` and `/tmp/fieldclaw/gateway.log`
- Ctrl+C stops both

API only: `cd apps/api && uv run uvicorn fieldclaw_api.main:app --host 127.0.0.1 --port 8000`  
Gateway only: `hermes-fieldclaw gateway run --replace`

### 6. First project on the UI

1. Open the UI. If you wiped the DB before, click **Reset cache** so old localStorage project ids are gone.
2. Enter your name and project name.
3. Optional: paste an existing project inbox email. Leave blank to provision a new one.
4. Create the project.
5. DM the Supervisor bot on Telegram, get a pairing code, approve it in onboard or the Crew tab (`bind_role` = superintendent).

### 7. Bootstrap the site

In Telegram to Supervisor, run `/init`. That scaffolds wiki folders, pulls mail attachments if any, tries to import a site map, and reports what is ready.

Confirm:

- Ops map has zones only after `GET .../zones` is populated (wiki pages alone are not enough)
- Wiki → Pages / Maps / PDFs & photos show what was ingested
- Crew tab shows the superintendent bound

### 8. Add a foreman

DM the **foreman** bot (different token). Approve pairing with `bind_role` = foreman on the same project. Field reports and photos then go through that profile.

### 9. Day-to-day

- Foreman: status / shortage / safety / quality on Telegram (+ photo upload via Hermes proofs)
- Superintendent: dashboard + Telegram; answer items on the super-queue
- Mail: cron or manual `POST .../mail/pull-attachments`
- Maps: GeoJSON upload, sitemap-named PDF/PNG, or ask for area names and create zones

If something looks empty after a wipe, use **Reset cache**, re-select the project, and re-run `/init` if the wiki folders are missing.
