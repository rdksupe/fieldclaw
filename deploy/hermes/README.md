# Hermes setup for FieldClaw

This guide configures **Hermes** as Supervisor Claw and Foreman Claw for FieldClaw. It assumes you already have the FieldClaw API reachable (typically `http://127.0.0.1:8000` via `./scripts/start_fieldclaw.sh` from the repo root). Product architecture, wiki design, and demo corpus notes live in the [root README](../../README.md).

FieldClaw treats Hermes as the conversational and automation runtime: Telegram gateways, skill loading, Mem0, STT/TTS, and cron. FieldClaw itself remains the system of record for zones, events, tasks, people, and the per-project filesystem wiki. Getting isolation right between superintendent and foreman—and between multiple projects—matters more than any single model choice.

---

## What you are installing

| Piece | Purpose |
|-------|---------|
| Mux / Supervisor home | `~/.hermes-fieldclaw` — superintendent bot, crons, shared skill symlink |
| Foreman home | `~/.hermes-fc-foreman` linked as `~/.hermes-fieldclaw/profiles/foreman` |
| Skill pack | `apps/hermes-skill/fieldclaw` → `~/.hermes-fieldclaw/skills/fieldclaw` |
| Wrappers | `hermes-fieldclaw`, `hermes-fc-foreman` on your `PATH` |
| Protect-identity plugin | Blocks agent writes to `SOUL.md`, `config.yaml`, `.env` |

Both roles load the **same** FieldClaw skills so HTTP tools, wiki rules, and mail behavior stay consistent. They do **not** share SOUL, Telegram bot token, pairing allowlist, or Mem0 user scope.

---

## Architecture of the Hermes extension

Hermes out of the box is a general agent runtime. FieldClaw extends it into a construction ops stack in several concrete ways.

**Role multiplexing.** One gateway process (`hermes-fieldclaw gateway run`) owns the supervisor profile and loads the foreman profile as a multiplexed child. Foremen never talk to the superintendent bot; each DM is routed by bot token and then bound to a `people` row via Telegram user id. That fixed an earlier failure mode where a single Telegram id was stamped onto every new project as superintendent and foreman traffic became ambiguous.

**Skill depth.** Under `apps/hermes-skill/fieldclaw/` you get `/init` for from-scratch project context, site-setup and GeoJSON/sitemap import (including PDF/PNG site plans through Datalab), AgentMail polling and multi-inbox routing, cron helpers that document which transport works where (browser_console `fetch` is reliable for the local FieldClaw API; external AgentMail REST needs `curl`/terminal), notify delivery discipline, supplier-delay watchers, and escalation dedup. These skills encode production lessons: stale `FIELDCLAW_PROJECT_ID`, duplicate projects on one inbox, thread-id dedup, and “wiki zones ≠ API zones.”

**Vectorless project memory.** Skills are instructed to resolve the live project, set the KB root to `kb/projects/{id}/`, read `wiki/index.md`, and walk markdown with normal filesystem tools. PageIndex JSON trees support large PDFs; Datalab supplies OCR markdown. Mem0 is reserved for **personal** preferences per Telegram user—not for the site logbook.

**Speech.** Optional smallest.ai STT/TTS scripts live beside the skills for voice notes and spoken replies when those keys are present.

**Identity hardening.** `deploy/hermes/plugins/protect-identity` stops the model from “helpfully” rewriting SOUL or env files. Templates in `deploy/hermes/identity/` define Supervisor vs Foreman voice and explicitly forbid simulation talk on site channels.

---

## Paths

Adjust the Hermes source path if your clone differs.

| What | Typical path |
|------|----------------|
| Hermes source / venv | `/home/rdksupe/building_shit/hermes-agent` |
| Supervisor `HERMES_HOME` | `~/.hermes-fieldclaw` |
| Foreman profile | `~/.hermes-fc-foreman` |
| This repo | wherever you cloned `fieldclaw` |
| Skill symlink target | `<repo>/apps/hermes-skill/fieldclaw` |

---

## One-time setup

### 1. Create the supervisor home and env

```bash
mkdir -p ~/.hermes-fieldclaw
cp deploy/hermes/env.fieldclaw.example ~/.hermes-fieldclaw/.env
chmod 600 ~/.hermes-fieldclaw/.env
```

Fill at least:

| Variable | Role |
|----------|------|
| `TELEGRAM_BOT_TOKEN` | Supervisor bot |
| `OPENROUTER_API_KEY` (or your LLM config in `config.yaml`) | Chat model |
| `AGENTMAIL_API_KEY` + inbox-related fields | Site mail |
| `FIELDCLAW_BASE_URL` | e.g. `http://127.0.0.1:8000` |
| `FIELDCLAW_API_KEY` | Must match `apps/api/.env` |
| `FIELDCLAW_KB_DIR` | Absolute path to this repo’s `kb/` |
| `DATALAB_API_KEY` | PDF / site-plan OCR |
| `MEM0_API_KEY` | Personal memory |
| `SMALLEST_API_KEY` | Optional STT/TTS |

Do **not** set `MEM0_USER_ID`. If you set it, every Telegram user shares one memory bucket.

Copy identity files into the Hermes home if you have not already (SOUL, AGENTS, memories templates). Keep `FIELDCLAW_PROJECT_ID` empty or treat it as a hint only—skills must re-resolve via `GET /api/projects`.

### 2. Link skills and plugin

```bash
REPO=/absolute/path/to/fieldclaw
ln -sfn "$REPO/apps/hermes-skill/fieldclaw" ~/.hermes-fieldclaw/skills/fieldclaw
mkdir -p ~/.hermes-fieldclaw/plugins
ln -sfn "$REPO/deploy/hermes/plugins/protect-identity" \
  ~/.hermes-fieldclaw/plugins/protect-identity
```

In chat after changes: `/reload-skills`.

### 3. Install PATH wrappers

Ensure `hermes-fieldclaw` points at the Hermes CLI with `HERMES_HOME=~/.hermes-fieldclaw` (see repo history / your local `~/.local/bin/hermes-fieldclaw`). Same pattern for `hermes-fc-foreman` with the foreman home.

### 4. Provision the foreman profile

```bash
deploy/hermes/provision_role.sh foreman "<FOREMAN_TELEGRAM_BOT_TOKEN>"
```

That script creates the foreman home, links SOUL.foreman, shares FieldClaw API settings, and registers the profile under the mux. Restart the multiplexer afterward:

```bash
hermes-fieldclaw gateway run --replace
```

Do **not** run a second standalone `gateway start` on the foreman profile while multiplexing is enabled.

### 5. Harden the profile

```bash
deploy/hermes/harden_profile.sh                        # ~/.hermes-fieldclaw
deploy/hermes/harden_profile.sh ~/.hermes-fc-foreman   # provision_role.sh already does this
```

Idempotent, and worth re-running after any manual profile edit. It applies four things a fresh profile gets wrong:

| Fix | Why |
|-----|-----|
| Installs `scripts/fc_gate.py` and attaches it to every agent-backed cron job | Hermes runs a job's pre-check script before building the prompt; a last line of `{"wakeAgent": false}` skips the agent entirely. The gate returns that whenever `GET /api/projects` is empty or unreachable, so a site with no project costs nothing instead of running a full agent per tick. When a project does exist, the resolved list is injected as context and the job skips its own resolve call. |
| Comments out `EMAIL_*` | Those keys enable the Hermes email *chat* adapter, which treats inbound site mail as DMs and auto-replies to it. FieldClaw parses mail through the `mail-poll` cron against the AgentMail REST API instead. |
| Empties `TELEGRAM_ALLOWED_USERS` | An allowlisted id bypasses pairing. Clearing it makes unknown DMs get a pairing code, which is also the flow you demo. |
| Moves duplicate top-level skill dirs aside | `skill_manage` can only *create* in the nested `fieldclaw` store, so edits land as a second top-level copy. Cron then fails with `Ambiguous skill name` and refuses to load the skill. Copies are moved to a timestamped backup, not deleted. |

---

## Day-to-day start

Preferred (API + gateway):

```bash
# from fieldclaw repo root
./scripts/start_fieldclaw.sh
```

Gateway only:

```bash
hermes-fieldclaw gateway run --replace
```

Logs from the start script: `/tmp/fieldclaw/gateway.log`. Pairing: DM the correct bot → paste the code in the FieldClaw UI Crew tab, or:

```bash
hermes-fieldclaw pairing approve telegram <CODE>
hermes-fc-foreman pairing approve telegram <CODE>
```

On a blank project, the superintendent should run **`/init`** in Telegram so Hermes scaffolds wiki folders, pulls AgentMail attachments, and imports GeoJSON or site-plan files when present.

---

## Cron jobs (supervisor / mux)

| Name | Schedule | Intent |
|------|----------|--------|
| `watch-shortages` | every ~3m | Escalate open shortages with notify discipline |
| `watch-supplier-delays` | every ~5m | Supplier ETA / delay signals |
| `mail-poll` | every ~3m | AgentMail → project routing → wiki/events |
| `daily-site-report` | `0 18 * * *` | End-of-day digest |
| `supplier-checkin` | `0 9 * * 1-5` | Weekday supplier nudge |

Keep any “site sim pulse” job paused. Hermes must not drive a simulation narrative on live Telegram.

Cron skills document transport pitfalls in detail: local FieldClaw calls can use `browser_console` async `fetch` with `X-API-Key`; AgentMail REST should use terminal `curl` with the key read from the environment without echoing it into chat.

---

## Multi-project and mail routing

Each FieldClaw project may carry its own `inbox_email`. Polling skills must:

1. `GET /api/projects` and build inbox → id maps.
2. Ignore stale `FIELDCLAW_PROJECT_ID` when it 404s or points at an empty duplicate.
3. Dedup on `payload.thread_id` for `email.inbound` / `email.parsed` / `wiki.updated`.
4. Pull attachments through FieldClaw `POST .../mail/pull-attachments` (or ingest helpers) so GeoJSON and sitemap-named PDFs/PNGs become zones as well as wiki pages.

When two projects accidentally share one inbox, mail events split across ids and cron escalate “loses” shortages. Prefer one inbox per project, or always resolve by explicit inbox match and verify with `GET .../events`.

---

## Verification checklist

1. `hermes-fieldclaw memory status` shows Mem0 without a forced global user id.
2. DM Supervisor bot → pairing required → approve → `/init` scaffolds `wiki/` folders.
3. `GET http://127.0.0.1:8000/api/projects` with your API key lists the project and inbox.
4. Foreman bot is a different token; foreman pairing binds `role=foreman` on the same project.
5. A test photo upload via Hermes hits `wiki/media/` and appears under Wiki → PDFs & photos.
6. A GeoJSON or sitemap-named plan produces rows on `GET .../zones`, not only markdown under `wiki/zones/`.

---

## Related files

| File | Role |
|------|------|
| `env.fieldclaw.example` | Secret template |
| `identity/SOUL.md` | Supervisor voice and scope |
| `identity/SOUL.foreman.md` | Foreman voice and scope |
| `provision_role.sh` | Create/link foreman profile |
| `harden_profile.sh` | Pairing-only DMs, no email chat adapter, cron gated on a live project |
| `scripts/fc_gate.py` | Cron wake gate — no model call until a project exists |
| `plugins/protect-identity/` | Lock identity files |
| `../../apps/hermes-skill/fieldclaw/init/SKILL.md` | `/init` checklist |
| `../../apps/hermes-skill/fieldclaw/tools_http.md` | HTTP tool surface |
