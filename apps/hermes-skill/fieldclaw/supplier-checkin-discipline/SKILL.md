---
name: supplier-checkin-discipline
description: FieldClaw cron decision discipline for supplier check-in / at-risk-PO runs — resolve the live project, assess whether an open shortage is actually actionable, and stay [SILENT] when there is no PO/supplier on file instead of fabricating a check-in email.
version: 0.1.0
---

# Supplier Check-In Discipline (FieldClaw cron)

Companion to `supplier-delay-polling` and `fieldclaw-cron-escalation`. Covers the
specific cron task: **"draft and send supplier check-in emails for open shortages /
at-risk POs."** An open shortage alone is NOT a reason to send a check-in.

## Core rule: no PO/supplier on file is NOT actionable

A supplier check-in email needs a **PO number and a supplier email address** to
be addressed to. When the shortage has no PO match on file and the project KB has
no `pos/` records, no vendor reference, and no replacement ETA:

- Do NOT invent a recipient or PO number to fabricate a check-in (honesty rule).
- Do NOT log `notify.sent` — there was no delivery to prove.
- The shortage may still be on the `super-queue`, but if its origin
  (`schedule.flagged` → `payload.source_event_id`) is already covered by a prior
  `notify.failed`, it is already escalated → respond exactly `[SILENT]`.
- Conclude "nothing actionable to send" rather than forcing a send.

## AgentMail inboxes are NOT supplier addresses

The project inbox (`fc-<project>@agentmail.to`) and the webapp inbox
(`fc-my-site@agentmail.to`) are FieldClaw's own mailboxes, not vendors. Do not
misread them as a supplier contact and fire a check-in at a project's own inbox.

## Verify before acting

1. `GET /api/projects` → resolve live project (env id, else `kaya-meow`/newest).
2. Poll `super-queue` + `events` for the shortage/schedule.flagged origin.
3. Search the project wiki (`pos/`, supplier/vendor references, ETA) to confirm
   whether ANY PO or supplier exists to check in with.
4. Check prior `notify.failed`/`notify.sent` for the `source_event_id` to dedup.
5. Only when a real PO + supplier address exist should you draft and send; log
   `email.outbound` + `notify.sent` **only** on confirmed delivery.

## Pitfalls

| Pitfall | Fix |
|---------|-----|
| Treating an open shortage as auto-actionable | A check-in has no meaning without a PO + supplier address to address it to |
| Firing a check-in at a project/webapp inbox | Those are FieldClaw mailboxes, not vendors |
| Logging `notify.sent` without delivery proof | Only log on confirmed delivery; otherwise `notify.failed` with error |
| `curl -H "X-API-Key: $VAR"` → 401 under cron | Shell key interpolation gets masked (`***`) on re-serialization. Use a `/tmp` Python script reading `os.environ["FIELDCLAW_API_KEY"]` and build the header in-process via `urllib.request` |

## See also

- `supplier-delay-polling` — delay-signal detection + dedup mechanics.
- `fieldclaw-cron-escalation` — when to notify vs. `[SILENT]` judgment.
- `fieldclaw-notify-delivery-discipline` — delivery-honesty ordering.
