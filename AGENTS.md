# FieldClaw — agent operating notes

## Stack ownership
| Concern | Owner |
|---------|--------|
| Logbook / zones / PO / super queue | FieldClaw HTTP API |
| Wiki + PDF pages | Filesystem under `FIELDCLAW_KB_DIR` → `kb/projects/{id}/` |
| Email | AgentMail via Hermes (`mail-poll` cron on supervisor profile) |
| Field capture | Foreman Telegram bot → Foreman Claw → `POST /events` |
| Superintendent | Supervisor Telegram bot → Supervisor Claw |
| Notifications | Hermes crons on mux/supervisor profile |

## Hermes roles (multiplexed)
- `~/.hermes-fieldclaw` — Supervisor Claw (mux owner, crons)
- `~/.hermes-fc-foreman` — Foreman Claw (shared foreman bot; people distinguished by Telegram id)
- Both: `protect-identity` blocks edits to `SOUL.md` / `config.yaml` / `.env`

## API projection
```
POST {FIELDCLAW_BASE_URL}/api/projects/{FIELDCLAW_PROJECT_ID}/events
Header: X-API-Key: {FIELDCLAW_API_KEY}
Header: X-Actor-Telegram: {telegram_user_id}   # when acting for a bound person
```
Types: `progress.reported`, `shortage.raised`, `safety.reported`, `quality.reported`,
`email.parsed`, `schedule.flagged`, `wiki.updated`, `notify.sent`, …

## Wiki
1. Resolve project → `kb/projects/{id}/wiki/index.md` first
2. Walk linked markdown — no embeddings
3. Folders are created by Supervisor `/init` / Hermes scaffold — not hardcoded by the API
4. Ingest PDFs with `apps/hermes-skill/fieldclaw/wiki_fs.py` (Datalab default)

## Mail
- AgentMail only — see `apps/hermes-skill/fieldclaw/MAIL.md`
- After parsing: project into FieldClaw; do not call FieldClaw `/mail/*` send routes

## Do not
- Discuss or drive any simulation/replay
- Use personal Gmail as the agent inbox
- Invent site facts
