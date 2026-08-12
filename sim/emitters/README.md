# External scenario emitters

These run **outside Hermes**. The agent never sees them.

## Week email loop (`week_email_loop.py`)

Packs Kaggle JPC Daily Site Diary / Work Plan / EHS forms + safety/quality tasks into a
**7-day** timed email campaign to the Hermes inbox. Hermes only sees normal IMAP mail and
must update the logbook / wiki / kanban like a real jobsite.

```bash
# Inspect schedule (116 msgs across days 0–6)
apps/api/.venv/bin/python sim/emitters/week_email_loop.py --mode dump --speed 86400

# Eval week: 1 wall-day per scenario-day, real SMTP → Hermes inbox
export HERMES_INBOX=... SMTP_USER=... SMTP_PASSWORD=... SMTP_FROM=...
apps/api/.venv/bin/python sim/emitters/week_email_loop.py --mode smtp --speed 86400 --reset-state

# Fast demo: 60s per scenario-day (~7 minutes total)
WEEK_LOOP_SPEED=60 apps/api/.venv/bin/python sim/emitters/week_email_loop.py --mode smtp --speed 60 --reset-state
```

**Mail split:** Hermes reads **AgentMail** only. This emitter sends with **Gmail**
(`sim/.env.sim` → `SIM_SMTP_*`) **to** `HERMES_INBOX` (the AgentMail address).

Hermes side: keep `mail-poll` cron active; skill has **no** sim language.
FieldClaw `/api/sim/*` remains optional for dashboard/dev replay only — not agent-facing.
