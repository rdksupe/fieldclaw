---
name: fieldclaw-cron-notify-dedup
description: Decide whether a FieldClaw queue/event item has ALREADY been notified before escalating, by reading the LATEST delivery record per trigger. Covers the notify.failed → notify.sent supersession lifecycle (an older dead-end can later be succeeded on the same source_event_id), the top-level (po_id, task_id, zone_id) tuple dedup that ID-only scans miss, the super_queue_id → schedule.flagged-id second handle, tuple-match verification, confirming project-match before deduping against prior-run history, and identical-signal duplicate events. 
version: 0.1.8
---

# FieldClaw Cron Notify Dedup (lifecycle-aware)

Complements `fieldclaw-cron-escalation` (which project to poll and when a queue
item is worth escalating at all) and `fieldclaw-cron-telegram-send` (the working
Telegram channel). This skill is the **dedup evidence check**: before you send or
re-send, confirm whether THIS trigger was already delivered, using the freshest
state — not just "any record exists."

## Core rule: read the LATEST record per trigger, not just any failure

A single trigger (a `shortage.reported` `source_event_id`, or a
`schedule.flagged`'s `payload.source_event_id`) can accumulate MULTIPLE delivery
events over time:

1. `notify.failed` — an early attempt hit a real dead-end (e.g. recipient was
   Telegram-only and no send tool was thought available). Written by e.g.
   `cron-supplier-delay` at 01:13.
2. `notify.sent` — a LATER attempt succeeded once a real channel opened (e.g.
   `hermes send --to telegram:<chat_id>`). Written at 03:41 with `delivered: true,
   message_id, mirrored`.

A `notify.failed` that predates a `notify.sent` for the SAME `trigger_event_id` is
**superseded**. The item is fully handled once `delivered: true` exists — do NOT
re-escalate, do NOT re-send. Check `delivered` on the newest record rather than
treating the mere existence of a `notify.failed` as a permanent dead-end.

Observed (Human_DC1, rebar shortage `98be8d55`):
`notify.failed` `e21e5258` at 01:13 (old dead-end) → `notify.sent` `3ed82697` at
03:41 (`delivered:true`, message_id 94). Correct call: the shortage is already
delivered → `[SILENT]`, even though a failure record is also present.

## Supersession is NOT always possible — check the recipient actually has a channel first

The "notify.failed is not terminal, check for a later superseding notify.sent" rule
assumes a real channel exists that a LATER run can reach (the classic case: a
Telegram-only superintendent WITH a `telegram_id`, reachable via `hermes send`).
Before treating a `notify.failed` as supersession-eligible, confirm the recipient has
a contact you could ever deliver to:

- **Has `telegram_id`** → a later `hermes send --to telegram:<chat_id>` CAN supersede
  the dead-end. Check for a later `notify.sent` `delivered:true`.
- **`telegram_id: null` AND only a placeholder email** (e.g. `admin@example.com`,
  `alex.pm@example.com` — example-domain addresses are not real delivery targets) →
  the dead-end is **genuinely terminal**. There is no channel to re-attempt, and you
  must NOT log a `notify.sent` (no delivery ever occurred or could). Correct call:
  `[SILENT]`, and do NOT emit a fresh `notify.failed` for something you never attempted
  to send this run. Re-surfacing the same no-channel dead-end cycle after cycle is spam.

Observed 2026-08-12 (supplier-delay poll): DC Campus Demo bolt shortage (`e0daaef2`)
had only `notify.failed 3d90fdf7` (8-11 23:20, no later superseding notify.sent) but its
superintendent (Test Admin) had `telegram_id: null` + `email: admin@example.com` — no
reachable channel. Correct call `[SILENT]`, distinguishing it from the Human_DC1 rebar
case where Rishi DID have a telegram_id and was later genuinely delivered.

## Dedup MUST include the top-level `(po_id, task_id, zone_id)` tuple — ID-only scans false-positive handled items (observed 2026-08-12)

A scan script that dedups ONLY on id fields (`trigger_event_id`, `source_event_id`,
`super_queue_id`, event `id`) will flag already-escalated `schedule.flagged` events as
NEW. Concrete case (DC Campus Demo): rebar `schedule.flagged`s `c13b3788`/`9200e4fc`
carried top-level tuple `(po=031e6726, task=0cf6712f, zone=9b1b5d60)` but NO
`trigger_event_id`/`source_event_id`, so an ID-only scan called them unnotified — yet
`notify.sent 5c8ac44d`/`0d3aac88` (also no trigger id) dedup them by the exact tuple
match. Fix: build a `notified_tuples = {(po_id, task_id, zone_id)}` set from ALL
notify events' top-level fields and treat a candidate as handled if its own top-level
`(po_id, task_id, zone_id)` is in that set — not just id matches. `schedule.flagged`
events DO carry top-level `po_id`/`task_id`/`zone_id`; read them.

## `super_queue_id` is a SECOND dedup handle for `schedule.flagged` — use it alongside the id chain (observed 2026-08-12, Human_DC1)

A `notify.sent` may carry BOTH `payload.trigger_event_id` (the originating
`shortage.reported` id) AND `payload.super_queue_id`, and that `super_queue_id` can
**equal the `schedule.flagged` queue event's own `id`**. That means a
`schedule.flagged` candidate can be deduped two independent ways:

- **id chain:** candidate's `payload.source_event_id` → notify `payload.trigger_event_id`
  (matches when the notify was keyed to the originating shortage).
- **super_queue_id ↔ event id:** candidate's own `id` → notify `payload.super_queue_id`.
  Even if the `source_event_id` link is absent, if the queue event id equals some
  notify record's `super_queue_id`, the item was escalated → it is handled.

Concrete case: Human_DC1 `schedule.flagged c6d7659f` (rebar shortage) had
`payload.source_event_id = 98be8d55` but a **null** top-level
`(po_id, task_id, zone_id)`. Its matching `notify.sent 3ed82697` carried
`super_queue_id: c6d7659f` (the queue event's own id) AND `trigger_event_id: 98be8d55`.
Both handles independently prove delivery. Also note: this `schedule.flagged` had a
`source_event_id` yet a NULL tuple — so a scan that only checks the tuple would have
missed it. Dedup should combine all three: `trigger_event_id`/`source_event_id` id
chain, `super_queue_id` ↔ event id, and the top-level tuple.

## Verify tuple-deduped candidates by PRINTING the matching notify record too

When a candidate `schedule.flagged` (or email-delay) is deduped ONLY via the top-level
`(po_id, task_id, zone_id)` tuple — i.e. it carries no `trigger_event_id` /
`source_event_id` / `super_queue_id` in the id chain, as with the DC Campus rebar
`c13b3788`/`9200e4fc` — a verification dump that filters notify events by
`trigger_event_id`/`super_queue_id` will show NO proof line for it. You'd infer it's
handled from the first-pass scanner's `already=True` boolean alone, which is not
verification. In the verify pass, ALSO print any `notify.sent`/`notify.failed` whose
top-level `(po_id, task_id, zone_id)` equals the candidate's tuple, so the tuple-matched
delivery record is visible. (Observed supplying a clean `[SILENT]` supplier-delay run on
2026-08-12: Human_DC1 `98be8d55` verified via the id chain and `delivered:true`; DC
Campus tuple-only items needed a tuple-match in the dump to confirm their notify.sent.)

**Tuple-match can OVER-match other triggers' notify records in the same project — confirm
each returned record actually keys THIS candidate.** A verify dump that matches on
`(po_id, task_id, zone_id)` (or a broad OR-chain across trigger_event_id / source_event_id /
super_queue_id / tuple) will pull in notify records belonging to OTHER signals on the same
project when tuples are shared or nulls collide (observed 2026-08-12 DC Campus: the bolt
shortage's `notify.failed` surfaced in the match set for a rebar `schedule.flagged`). A raw
"match count >= 1" is therefore NOT proof of delivery for the candidate. For each returned
record, read its OWN `_id`, `payload.trigger_event_id`, `payload.super_queue_id`, and
top-level tuple and verify that at least one of those equals the candidate's handle before
declaring the candidate handled. Print the records and reason over them; don't treat the
tuple filter's output as the answer.

## Poll the super-queue too — a typed-events query can come back empty while the shortage still needs evaluation (observed 2026-08-12, Human_DC1)

`GET /api/projects/{pid}/events?type=shortage.raised` returned `[]` this run even
though a live rebar shortage existed. The shortage had NOT been written as a
`shortage.raised` typed event — it surfaced as a `schedule.flagged` queue item
(`c6d7659f`, `payload.source_event_id 98be8d55`) carrying the shortage signal, on
`GET /api/projects/{pid}/super-queue`. So a shortage-detection cron must NOT return
early/`[SILENT]` on an empty typed-events query: poll the super-queue and evaluate
`schedule.flagged` items as shortage candidates too, then dedup them against prior
notify history (see the `super_queue_id` and tuple handles above). The shortage
channel (supplier-delay) writes `schedule.flagged`, not necessarily a dedicated
`shortage.raised` event.

## Dedup identical-signal DUPLICATE events by payload content, not just trigger id (observed 2026-08-13, fc_demo1)

Shortage/delay signals are frequently **duplicated at creation** — the same material/zone
is written twice under different event ids (an older twin + a newer twin) carrying the
SAME `payload.summary`. Real case (fc_demo1): `shortage.raised` `2982e0b2` (4in DI
fittings) had a `notify.sent 1564d323` `delivered:true`, while an older identical twin
`ae551b5d` (same "Short 3 crates of 4in DI fittings" summary) sat with NO notify record
of its own. Likewise the blower ETA slip existed as `schedule.flagged 95f4d805`
(notified, `delivered:true`) and twin `059c0912` (identical "Blower equipment ETA slipped
5 days" summary, unnotified by id).

A trigger-id-only scan flags these older twins as NEW — false escalation. Fix: after the
id/tuple/super_queue_id pass, **group candidates by normalized signal content**
(`payload.summary` + `zone_id` / `zone_label`). If ANY member of the group already has a
`notify.sent` with `delivered:true`, the whole group is handled → `[SILENT]`; do not
escalate the twin. Re-sending the same physical signal twice (once per duplicate id) is
notification spam. Confirm the twins truly share a payload before coalescing (do not
merge distinct signals that merely mention the same zone).

## Difference between "delivered flag" and "already escalated"

`payload.delivered` (and `message_id`/`mirrored`) tells you whether YOUR send
succeeded and whether to log `notify.sent` with `delivered: true`. It does NOT gate
dedup: a notify record with `delivered: None`/absent (e.g. email-path `notify.sent`)
still proves the trigger was escalated → treat the item as handled and stay
`[SILENT]`. Do not re-escalate just because a prior record lacks a delivered flag.

## Always re-fetch fresh each run

Dedup must come from the actual API, not a prior run's narrative (other FieldClaw
jobs — `cron-supplier-delay`, mail-poll — mutate events between runs):

- `GET /api/projects/{pid}/events?limit=100` (NOT 500 — see the timeout pitfall, and
  NEVER build an offset/limit pagination loop — see the hang pitfall below),
  filter `notify.sent` / `notify.failed`, group by `payload.trigger_event_id` AND
  `payload.super_queue_id` (both handles, see above).
- Confirm the current env `FIELDCLAW_PROJECT_ID` still points at the project whose
  history you're reading (poll `GET /api/projects`, match id). If the env target
  shifted between runs, prior-run dedup must NOT apply (see
  `fieldclaw-cron-escalation` CRITICAL section).
- Before escalating any candidate, re-fetch the notify events' top-level
  `po_id`/`task_id`/`zone_id` and confirm the tuple/id — don't trust your first
  ID-only pass or a prior run's summary.

## Confirm an item was surfaced before staying SILENT (prior-run evidence)

To confirm a queue item (e.g. a medium `safety.reported`) was already surfaced by
THIS job on THIS project (not merely that some event exists), grep the job's own
output history for the item id AND the project id:

```
~/.hermes-fieldclaw/cron/output/<job_id>/
```

`search_files(pattern="<event_id>|<project_id>|<keyword>", path=.../output/<job_id>/)`
— if the majority of recent runs already carried the identical escalation with no
state change, stay `[SILENT]`. Match the JOB ID (several fieldclaw jobs run every
3–5 min); `watch-shortages` = `7884049f…`, `watch-supplier-delays` = `c1a23501…`.

## Pitfalls

| Pitfall | Fix |
|---------|-----|
| Seeing a `notify.failed` and assuming a permanent dead-end, missing the later `notify.sent` | The trigger already delivered: look for the LATEST `notify.sent` with `delivered:true` same-behaved `trigger_event_id`. Palatable supersession: old failure → later success = handled. |
| Treating a `notify.failed` as supersession-eligible when the recipient has NO real channel | Check the recipient's contact first: `telegram_id: null` + placeholder/example email = genuinely terminal dead-end. Never log `notify.sent`; stay `[SILENT]`, don't re-emit a fresh `notify.failed`. |
| ID-only scan flags already-handled `schedule.flagged` as NEW | Dedup on the top-level `(po_id, task_id, zone_id)` tuple too (see section above). notify.sent records often carry the tuple but NO trigger_event_id. |
| A `schedule.flagged` carries `source_event_id` but a NULL `(po_id,task_id,zone_id)` tuple | Tuple-only dedup misses it. Also check the `super_queue_id` ↔ queue-event-id and `source_event_id` ↦ `trigger_event_id` handles (see section above). Use all three: id chain, super_queue_id, tuple. |
| Shortage cron returns `[SILENT]`/early on an empty `events?type=shortage.raised` | Poll the super-queue too and evaluate `schedule.flagged` items as shortage candidates; the shortage channel writes there, possibly with no matching `shortage.raised` event (see section above). |
| Treating absence of `payload.delivered` as "not escalated" | Dedup on any existing notify record regardless of the delivered flag; `delivered` only governs whether YOU log `delivered:true`. |
| Deduping against a prior run's *description* of notify state | Re-fetch `events?limit=100` fresh; derive dedup from the response, not claims. |
| Confusing this job's history with a sibling job's | Use `<job_id>/` matching THIS job (see above). |
| Project shifted between runs → prior-run dedup silently misfires | Confirm current env project id first; only dedup against prior run(s) on the SAME project id. |
| `events?limit=500` times out on noisy projects | Use `limit=100` or omit the param. |
| An **offset/limit pagination loop** over events hangs to the terminal timeout (180s), freezing the whole cron | Do NOT build `while True: fetch(limit=100, offset+=len(batch))`. The FieldClaw events endpoint (uvicorn) does not page reliably via `offset` — the loop re-fetches the same window forever and never terminates. Fetch **one** bounded `events?limit=100` and close the poll in single requests per resource; the newest `notify.sent`/`notify.failed`/`schedule.flagged`/`shortage.*` records for dedup all sit in that one window (observed 2026-08-13 fc_demo1). |
| An identical-signal event under a DIFFERENT id than the delivered one looks "unnotified" | Signals are often duplicated at creation (older + newer ids, same `payload.summary`). Group candidates by normalized signal content (summary+zone); if one twin has `delivered:true`, the whole group is handled → `[SILENT]`. Re-escalating the older twin is spam (observed 2026-08-13 fc_demo1). |
| **Verify dump filters only by trigger/super_queue id, so tuple-only candidates show NO proof line** | In the verify pass ALSO match notify records by top-level `(po_id, task_id, zone_id)` = candidate tuple, so tuple-deduped items get a visible delivery record (see section above). |
| **Tuple/OR-match in the verify pass returns OTHER triggers' notify records; a "match count >= 1" is mistaken for proof** | For each returned record, confirm its OWN `_id`/`trigger_event_id`/`super_queue_id`/top-level tuple equals the candidate's handle before declaring it handled. The tuple filter broad-matches within a project — reason over the printed records, don't trust the count. |

## Editing these skills

`fieldclaw-cron-escalation`, `fieldclaw-notify-delivery-discipline`, and this skill
live in the write-locked fieldclaw store where skill_manage `patch`/`edit`/`write_file`
fail ("not found in active profile"); only `action='create'` (with the same `name` +
`category`) resolves there and updates the file in place. To patch an existing
fieldclaw SKILL.md, pass the FULL updated content in a `create` call (as done here).
Note: a same-named skill also existing at the ROOT skill dir
(`~/.hermes-fieldclaw/skills/<name>/`) makes `create` collide — use a name with no
root-dir duplicate, or edit the file directly.

## See also / overlap note

Overlaps `fieldclaw-cron-escalation` (dedup rules 1–4) and `supplier-delay-polling`
(§5 tuple dedup, §3a/3b signal detection) — these stores overlap on the tuple dedup
rule. The curator should consider consolidating escalation + notify-dedup.
