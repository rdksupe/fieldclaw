# FieldClaw

**Ground truth in. Decisions out.**

FieldClaw is the brain for what is actually happening on a construction site. Foremen report from Telegram, documents and mail get into a project knowledge base, and the superintendent sees a live picture of zones, shortages, the log, and the wiki — then can send decisions back to the field.

It is built on [Hermes](https://github.com/NousResearch/hermes-agent). We did not replace Hermes. We extended it with FieldClaw skills, two role profiles (Supervisor and Foreman), a small HTTP API, and a web UI.

Pitch deck: [`deck/FieldClaw_Pitch_Deck.pdf`](deck/FieldClaw_Pitch_Deck.pdf)  
Hermes setup: [`deploy/hermes/README.md`](deploy/hermes/README.md)

---

## Architecture

![FieldClaw architecture](docs/diagrams/fieldclaw-architecture.png)

Same hand style as the pitch deck (rough.js + Kalam). Regenerate with:

```bash
cd deck && node ../docs/diagrams/render-architecture.mjs
```

---

## Introduction

On a real job, field knowledge lives in heads and chat threads. Office knowledge lives in inboxes. The superintendent sits in the middle and still waits for truth. FieldClaw closes that loop: capture → structure → live ops picture → human decision → answer back to the crew.

We keep two kinds of memory on purpose. Structured things (zones, tasks, people, events) go through the FieldClaw API. Long-form site knowledge (POs, RFIs, PDF outlines, safety notes) lives in a folder wiki per project. Agents and humans can both open those files with normal tools.

---

## The various components

| Piece | What it does |
|-------|----------------|
| **FieldClaw API** | Projects, zones, events, tasks, people, pairing, wiki ingest, sitemap import |
| **Web UI** (`:8000`) | Ops map, kanban, wiki pages, maps gallery, PDF/photo viewer, crew pairing |
| **Hermes Supervisor** | Superintendent bot, `/init`, mail, cron, notify |
| **Hermes Foreman** | Separate bot for field capture and proofs |
| **Project wiki** | `kb/projects/{id}/raw/` + `wiki/` (Karpathy-style LLM wiki) |
| **Skills pack** | `apps/hermes-skill/fieldclaw/` — shared by both roles |

Start everything locally with:

```bash
./scripts/start_fieldclaw.sh
# UI → http://127.0.0.1:8000/
```

---

## API design

The API is the system of record for structured site state. Hermes never invents zone geometry or task status in chat alone — it calls HTTP.

Typical surface (all need `X-API-Key`; Telegram turns also send `X-Actor-Telegram`):

- `GET/POST /api/projects` — create and list sites (optional existing inbox email)
- `GET/POST .../zones`, `.../events`, `.../tasks`, `.../people`
- `GET .../super-queue` — things waiting on the superintendent
- `POST .../sitemap` / `.../sitemap/upload` — GeoJSON or site-plan PDF/PNG → zones
- `POST .../mail/pull-attachments` — pull inbox files into the wiki
- `GET .../wiki/pages`, `.../wiki/assets`, `.../wiki/file/...` — browse and render docs
- `GET/PUT .../ui/widgets` — optional map chips / callouts on the dashboard

Status events mirror into `wiki/ops/log.md`. Photos go through `POST .../proofs` into `wiki/media/`. Wiki folders are **not** hardcoded at project create — Supervisor `/init` (or ingest) creates them, and the API discovers what exists.

More detail: `apps/hermes-skill/fieldclaw/tools_http.md`.

---

## Hermes extensions

Out of the box Hermes is a general agent. FieldClaw adds a full skill pack under `apps/hermes-skill/fieldclaw/`:

- **`/init`** — bootstrap a project from scratch (folders, mail pull, map import, short report back)
- Site setup / GeoJSON / site-plan OCR import
- Mail poll and multi-project inbox routing
- Cron helpers (shortages, supplier delays, mail, daily report) with transport notes
- Notify delivery discipline (only log success when Telegram actually delivered)
- `wiki_fs.py` for ingest / PageIndex / scaffold

We also ship identity templates (`SOUL.md`, `SOUL.foreman.md`), a provision script for the foreman profile, and `./scripts/start_fieldclaw.sh` so API + gateway come up together.

You still get normal Hermes behavior: gateway, pairing, cron, tools, model config, Mem0 hooks, and so on. FieldClaw sits on top; it does not lock you out of the rest of Hermes.

---

## Separation at the Hermes layer

Superintendent and foreman are **two Hermes profiles**, not one bot with two moods.

| | Supervisor Claw | Foreman Claw |
|--|-----------------|--------------|
| Home | `~/.hermes-fieldclaw` | `~/.hermes-fc-foreman` |
| Bot | Superintendent Telegram token | Separate foreman token |
| Users | Superintendent | Many foremen (keyed by Telegram user id) |
| Skills | Same FieldClaw pack | Same FieldClaw pack |

They share skills so tools and wiki rules stay consistent. They do **not** share SOUL, session space, pairing allowlist, or Mem0 bucket. The API stores `people.telegram_id` + role so a foreman cannot act as superintendent by accident.

This matters because an early mistake was binding one Telegram id onto every new project and sharing one inbox across projects. The UI then stuck on an empty site while another project had the real map. We fixed that with blank-slate wipes, no demo hardcoding in the UI, inbox chosen at create time, resolve-by-project (not “newest wins”), and explicit `/init`.

---

## Memory, STT / TTS, and demo data

**Personal memory (Mem0)** — per Telegram user. Do not set a global `MEM0_USER_ID` or everyone shares one brain. This is for prefs and personal notes, not the site logbook.

**Site memory** — the project wiki + API events (see next section). That is the shared job memory.

**STT / TTS** — optional. Voice notes can go through speech-to-text; replies can use TTS. We wired smallest.ai scripts next to the skills; you can point the same hooks at another provider.

**Demo / simulation data** — under `sim/` and `kb/samples/`. For a credible demo we used public **Wilbarger Creek RWWTF** bid docs (Legistar / Granicus), split large PDFs for mail size limits, built zone GeoJSON from process areas, and seeded mail into a demo inbox. See `kb/samples/wilbarger/SOURCES.md` and `kb/samples/sitemaps/wilbarger-rwwtf-zones.geojson`. Eval replay JSONL is for operators only — live Telegram SOUL rules say not to talk about simulation on site channels. Foreman “pulse” seeding stays opt-in.

---

## Knowledge base (Karpathy) and why vectorless RAG

We follow Andrej Karpathy’s **LLM wiki** pattern instead of default embedding RAG.

Original write-up: [llm-wiki.md (gist)](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f).

Idea in plain terms: keep **raw** sources immutable, let the agent **compile** a real markdown wiki (`index.md`, entity pages, links), and at question time walk the index and pages — compile once, keep current — instead of re-deriving everything from chunks every query.

Per project:

```
kb/projects/{id}/
  raw/     originals (PDFs, extracts)
  wiki/    agent-maintained pages (ops, zones, sources, maps, …)
```

**Why vectorless here:** site facts must stay readable by a human super, editable without re-embedding, and isolated per job so one site’s POs never bleed into another. Vector search hides provenance and mixes tenants too easily. Hermes uses `ls` / `rg` / `cat` on the wiki. Large PDFs can also get a PageIndex tree for structure; OCR text comes from whatever convert service you configure (Datalab today).

Folders are created by `/init` or on ingest — the API does not force a fixed A/B/C layout.

---

## Mail integration

Each project can have its own inbox address. Hermes (or cron) polls mail, posts `email.inbound` / `email.parsed`, and pulls attachments into the wiki. Files named like `sitemap` / `site-plan` can also drive zone import.

Multi-project rule: map `inbox_email` → `project_id` from `GET /api/projects`. Do not trust a stale env project id. Dedup on thread ids so the same message is not processed forever. One inbox shared by two projects will confuse routing — prefer one inbox per project.

We used AgentMail (`*.agentmail.to`) while building. That is a default, not a hard requirement — see swap section below.

---

## Security measures

A few practical locks:

- **API key** on FieldClaw HTTP (`X-API-Key`). Optional **actor Telegram id** for role checks.
- **Pairing** — Telegram users must be approved before they act as super or foreman.
- **Role separation** — separate bots + `people.role` so field users are not treated as superintendent.
- **Project isolation** — each site has its own `kb/projects/{id}/`.
- **`protect-identity` plugin** (`deploy/hermes/plugins/protect-identity`) — blocks the agent from rewriting `SOUL.md`, `config.yaml`, or `.env` under Hermes home. Personality and secrets stay operator-owned.
- **Honesty rules in skills / SOUL** — don’t log notify success without delivery proof; don’t invent site facts; don’t discuss sim on live channels.

---

## Swapping services and customizing Hermes

Nothing in the vendor column is the product core. Change what you like in `.env` and Hermes config. Standard Hermes features (gateway, pairing, cron, tools, model routing) remain.

| Concern | Default we used | Swap how |
|---------|-----------------|----------|
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

## Quick start

```bash
./scripts/start_fieldclaw.sh
```

1. Open `http://127.0.0.1:8000/` and create a project (optional: paste an existing inbox).
2. Pair Supervisor Telegram.
3. DM Supervisor and run **`/init`**.
4. Pair Foreman on the other bot when you are ready.
5. Use **Reset cache** in the UI if the browser still points at a deleted project.

Full Hermes/Telegram steps: [`deploy/hermes/README.md`](deploy/hermes/README.md)
