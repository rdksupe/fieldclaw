---
name: fieldclaw-notify-delivery-discipline
description: FieldClaw cron notify-logging honesty discipline. Always attempt delivery (AgentMail MCP, Mail API, or Telegram) BEFORE logging notify.sent - log notify.failed on failure. Also captures scanning width for supplier-delay signals and how to edit fieldclaw skills when skill_manage cannot resolve them.
version: 0.1.0
---

# FieldClaw Notify Delivery Discipline

Covers the honesty-critical ordering when FieldClaw cron jobs alert a superintendent
and project the result back to the logbook. Also captures environmental traps hit
in practice (scanning width, editing the fieldclaw skill store).

## The core rule

`notify.sent` is logged **only after** a delivery channel confirms delivery
(`delivered: true`). On failure, log `notify.failed` with the error. Never log
`notify.sent` "anyway" — it pollutes the logbook and cannot be deleted afterwards
(`DELETE .../events/{id}` returns 404).

### Correct order (per signal to act on)

1. Attempt delivery (try in order):
   - AgentMail MCP `send_message` — may be unreachable under cron.
   - AgentMail REST API — **GET-only with Bearer auth; POST returns 404** (verified).
   - FieldClaw `POST /api/projects/{pid}/mail/send` — needs SMTP config.
   - Telegram `notify`/`send_message` — may be unavailable in cron context.
2. On confirmed delivery → `POST` `notify.sent` (`delivered: true`).
3. On failure → `POST` `notify.failed` with `payload.error` describing the actual error.
4. Patch the impacted task to at-risk (`PATCH .../tasks/{id}` body `{"at_risk": true, "status": "in_progress"}`).

## Pitfall: reference script logs before delivery

The `supplier-delay-polling` skill's reference script `scripts/fc_supplier_poll.py`
POSTs `notify.sent` **before** attempting `mail/send`. That order leaves a false
`notify.sent` if delivery fails, and you cannot delete it. Treat that script as a
scaffold — re-order the two calls (deliver first, then log) before relying on it,
or future runs inherit the false-notify bug.

## Pitfall: scan width vs field report

A valid `FIELDCLAW_PROJECT_ID` (env target) does NOT mean the supplier-delay signals
live there. In practice the env target ("My Site") held only a `safety.reported`,
while all 4 supplier-delay signals (2 `schedule.flagged`, 1 `email.inbound`, 1
`status.reported` bolt shortage) were in a *different* project ("FieldClaw DC Campus —
Demo"). Always iterate **all** projects (`GET /api/projects`), not just the resolved one,
when polling for supplier-delay signals. Dedup against `notify.sent` by BOTH
`payload.trigger_event_id` and the top-level `(po_id, task_id, zone_id)` tuple (the API
stores these at top level, not in `payload`).

## Pitfall: editing fieldclaw skills

FieldClaw skills live under `~/.hermes-fieldclaw/skills/fieldclaw/<name>/` but
skill_manage patch/edit/write_file from the `default` profile fail with
"Skill not found in active profile" — only `action='create'` resolves on this store.
To patch an existing fieldclaw SKILL.md or `scripts/` file directly, edit the file on
the filesystem (`write_file`/`patch` to `~/.hermes-fieldclaw/skills/fieldclaw/<name>/...`).
