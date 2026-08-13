---
name: supplier-delay-polling
description: Cron job workflow for detecting supplier-delay signals in FieldClaw — multi-project polling, email.inbound parsing, schedule.flagged projection, task at-risk flagging, and notify.sent/notify.failed logging.
version: 0.2.5
---

# Supplier Delay Polling (FieldClaw cron)

Cron job that polls FieldClaw for `schedule.flagged` and `email.inbound`/`email.parsed`
events with supplier-delay intent, alerts the superintendent, and projects
`notify.sent` back into the logbook.

## When to run

Triggered by Hermes cron (`watch-supplier-delays`). Runs autonomously — no user
present. Follows all `cron-api-polling` conventions (Python scripts in `/tmp/`,
`[SILENT]` when nothing to report, server startup if needed).

## Prerequisites

- FieldClaw API server running at `FIELDCLAW_BASE_URL` (default `http://127.0.0.1:8000`)
- `FIELDCLAW_API_KEY` set
- `FIELDCLAW_PROJECT_ID` set (but see multi-project polling below — env var may be stale)

## Workflow

### 1. Health check + server startup

```bash
curl -sf -o /dev/null "http://127.0.0.1:8000/health"
```

If refused (exit 7), start the server:

```bash
cd /home/rdksupe/building_shit/buildsync/apps/api && \
  uv run uvicorn fieldclaw_api:main --host 127.0.0.1 --port 8000
```

Use `terminal(background=true)`. Wait 3s, retry health check.

**Correct uvicorn entrypoint:** `fieldclaw_api:main` — NOT `fieldclaw_api.main:app`.
The latter fails with connection errors.

### 2. Multi-project polling

`FIELDCLAW_PROJECT_ID` may be stale or point at a non-existent project. Always
list all projects first, then iterate:

```python
import os, json, urllib.request

base = os.environ.get("FIELDCLAW_BASE_URL", "http://127.0.0.1:8000")
key = os.environ.get("FIELDCLAW_API_KEY", "")

# GET /api/projects → list of {id, name, inbox_email, ...}
req = urllib.request.Request(f"{base}/api/projects", headers={"X-API-Key": key})
with urllib.request.urlopen(req, timeout=10) as resp:
    projects = json.loads(resp.read().decode())
```

For each project, fetch events — **use `limit=100`, NOT `limit=500`** (see the
`limit=500` timeout pitfall):

```python
for proj in projects:
    pid = proj["id"]
    req = urllib.request.Request(
        f"{base}/api/projects/{pid}/events?limit=100",
        headers={"X-API-Key": key}
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        events = json.loads(resp.read().decode())
```

### 3. Detect supplier-delay signals

#### 3a. Email-based signals

Look for `email.inbound` or `email.parsed` events whose subject/body contains
supplier-delay keywords. **Always skip events with empty payload `{}`** —
these are malformed events (often from `agentmail` source) that produce
garbage notifications with all "Unknown" fields.

```python
DELAY_KEYWORDS = ['eta', 'delay', 'rebar', 'delivery', 'po-', 'ship', 'truck', 'supplier', 'backorder', 'shortage', 'lead time', 'reschedule']

for ev in events:
    if ev["type"] in ("email.inbound", "email.parsed"):
        p = ev.get("payload", {})
        if not p:
            continue  # skip empty-payload events
        subject = (p.get("subject", "") or "").lower()
        body_text = (p.get("body", "") or p.get("body_preview", "") or "").lower()
        combined = subject + " " + body_text
        if any(kw in combined for kw in DELAY_KEYWORDS):
            # This is a supplier-delay signal
```

Also look for `schedule.flagged` events — but again, **skip empty-payload events**:

```python
schedule_flagged = [ev for events
                    if ev.get("type") == "schedule.flagged"
                    and ev.get("payload") and len(ev.get("payload", {})) > 0]
```

**⚠️ Naive keyword match on subject+summary False-positives on `document/*` ingests
(observed 2026-08-12, "My Site").** A keyword scan over subject + body_preview +
summary will flag benign document-ingestion emails whose payload summary literally
contains "delay" or "eta" — but in the NEGATION, e.g. `intent: document/estimate`,
summary "Reference doc — no PO/ETA/delay." The word appears, the intent is a document
ingest, there is no delay. Before treating a matched email as a supplier-delay signal,
check the intent family and any explicit negation in the summary:

```python
intent = (p.get("intent") or "").lower()
summary = (p.get("summary") or "").lower()
negated = "no po/eta/delay" in summary or "no delay" in summary or "reference doc" in summary
if negated or intent.startswith("document/") or intent in ("map", "site", "sitemap", "import"):
    continue  # document ingest, NOT a supplier-delay signal
```

Document-intent emails (map / estimate / recommendation / RFQ / reference) are
site-logistics or packet material, never supply-delay — even when "delivery" or
"delay" appears in the subject line (e.g. "Letter of Recommendation", "Total
Project Estimate"). The reliable tell is `intent` (document/*) plus a summary that
negates delay. Only treat the email as a delay signal when intent is a genuine
delivery/receipt/supplier action (e.g. `intent: purchase`, `delivery`, `reschedule`,
`delay`) or a `schedule.flagged` projection confirms it.

#### 3b. Telegram status.reported shortage signals (IMPORTANT — added 2026-08-12)
(observed 2026-08-12).** `schedule.flagged` is ALREADY a delay signal (the server
projects it from a `shortage.reported`/delay origin), so it needs no DELAY_KEYWORDS
match to count as a candidate. Its payload keys are `reason`/`material`/`zone`/
`impact_task`/`note` (e.g. `reason: "Rebar shortage — #4 rebar, 120 sticks needed…"`)
— NOT `summary`. A detection loop that lowercases `p.get("summary","")` for a
`schedule.flagged` gets an empty string, fails the keyword check, and silently
drops the candidate → a false "no signals" → wrong quiet/[SILENT] run. Correct
shape: treat every non-empty-payload `schedule.flagged` as a candidate directly and
lean on dedup (§5) to decide if it's new — dedup handles exactly this projection via
`source_event_id`↦`trigger_event_id`, `super_queue_id`↔queue-event-id, and the
top-level `(po_id, task_id, zone_id)` tuple.

#### 3b. Telegram status.reported shortage signals (IMPORTANT — added 2026-08-12)

**The super-queue also contains `status.reported` events from foreman Telegram reports.**
These can contain shortage signals like "waiting on bolts", "need more X", "ran out of Y"
that are NOT `email.inbound` or `schedule.flagged` type. You MUST scan these too.

```python
SHORTAGE_KEYWORDS = ['waiting on', 'need', 'short', 'out of', 'missing', 'ran out', 'shortage', 'bolts', 'rebar', 'concrete']

for ev in events:
    if ev["type"] == "status.reported":
        summary = (ev.get("payload", {}).get("summary", "") or "").lower()
        if any(kw in summary for kw in SHORTAGE_KEYWORDS):
            # This is a shortage signal from the field
            # Check if already notified, if not → alert superintendent
```

**Zone-map imports are NOT delays — and their sibling `email.inbound` event has no
intent/has_delay fields, so you must exclude by SUBJECT too (observed 2026-08-12,
Smoke Site).** A GeoJSON site-logistics zone-map import surfaces as TWO events with
DIFFERENT shapes:

- `email.parsed` — RICH payload: `has_delay: false`, `intent` like `"Import Phase-1
  site logistics / zone map"` or `"site logistics map import / zone map setup"`.
  Exclude on `payload.has_delay` / `intent` (do NOT flag just because the body mentions
  "site logistics" / "delivery").
- `email.inbound` — SIBLING, THIN payload: carries ONLY `thread_id/from/subject/
  received_at` (+ sometimes `inbox`). It has NO `has_delay` and NO `intent`, so a
  detector that excludes zone-map email only by checking `payload.has_delay`/`intent`
  will FAIL to exclude this sibling (absent fields → `has_delay=None` → it looks like a
  real candidate). Exclude the inbound sibling by SUBJECT pattern instead.

Robust exclusion predicate for BOTH event shapes:

```python
subj = (p.get("subject") or "").lower()
intent = (p.get("intent") or "").lower()
has_delay = p.get("has_delay")
is_zonemap = (str(has_delay).lower() == "false") or \
             ("import zone" in intent) or ("sitemap" in intent) or \
             ("logistics" in intent) or ("geojson" in subj) or \
             ("logistics map" in subj) or ("zone map" in subj)
if is_zonemap:
    continue  # site-logistics / zone-map import, not a supplier delay
```

Also note the `email.parsed` intent string may itself contain a "Zones: Structure,
Electrical, ..." enumeration — that still means zone-map import, not delay. The
`email.inbound` subject is the reliable marker there (`... Site Logistics Map (GeoJSON)`).

### 4. Read the supplier reply

Cross-reference with mail threads to extract structured fields:

```python
# GET /api/projects/{pid}/mail/threads
# Returns {thread_id, messages: [{direction, subject, body, parsed: {intent, eta}}]}
```

The inbound message body contains the supplier's actual reply (new ETA, reason,
ship date). Extract these for the `schedule.flagged` payload.

### 5. Dedup against existing notifications

Build dedup set from **two sources**:

```python
notified_trigger_ids = set()  # payload.trigger_event_id
notified_tuples = set()       # (po_id, task_id, zone_id)

for ev in events:
    if ev["type"] == "notify.sent":
        tid = ev.get("payload", {}).get("trigger_event_id")
        if tid:
            notified_trigger_ids.add(tid)
        notified_tuples.add((ev.get("po_id"), ev.get("task_id"), ev.get("zone_id")))

# A signal is already notified if:
# - Its event ID is in notified_trigger_ids, OR
# - Its (po_id, task_id, zone_id) tuple is in notified_tuples
```

**Dedup must ALSO include `notify.failed`.** A dead-end `notify.failed` keyed to a
signal (or its `source_event_id`) proves escalation was already attempted and no
working channel exists. Add those ids to the dedup sets too (see
`fieldclaw-cron-escalation` for the full rule).

**⚠️ `schedule.flagged` candidates — match on `payload.source_event_id`, not just the flagged event's own id.**

A `schedule.flagged` event *projects* a pre-existing signal (e.g. `shortage.reported` →
`schedule.flagged`) and carries the origin in its payload:

```json
{"type": "schedule.flagged", "id": "c6d7659f...", "payload": {
    "source_event_id": "98be8d55...", ...}}
```

A naive `candidate_id in notified_trigger_ids` check returns `already_notified: false`
for the flagged event's own id even when its origin is already in
`notified_failed_ids`/`notified_trigger_ids`. A `notify.failed` recorded for the origin
id proves the signal was already escalated (honestly, as a failed delivery). Treat a
`schedule.flagged` as handled when EITHER its own id OR its `payload.source_event_id`
is in the notified set:

```python
src_id = (ev.get("payload", {}) or {}).get("source_event_id")
already = ev["id"] in notified_trigger_ids or src_id in notified_trigger_ids
```

**⚠️ A `schedule.flagged` can be covered by its OWN top-level `(po_id, task_id, zone_id)` tuple** — not just by id/source_event_id/super_queue_id matching (added 2026-08-12). A `notify.sent` for a rebar shortage stores the PO/task/zone at the **top level** of BOTH the notify event and the projected `schedule.flagged` it was created from. So a flagged event whose own id and `source_event_id` are NOT in the notify trigger sets can still be already-notified when its own `(po_id, task_id, zone_id)` column matches a `notify.sent` tuple. Naive id-based dedup then reports `already_notified: false` and triggers a spurious escalation. Include the candidate's own tuple in the dedup test:

```python
tpl = (ev.get("po_id"), ev.get("task_id"), ev.get("zone_id"))
already = (ev["id"] in notified_trigger_ids) or (src_id in notified_trigger_ids) \
       or (tpl in notified_tuples)
```

**Extra dedup hint (observed 2026-08-12):** an escalated `notify.sent` for a projected
`schedule.flagged` can carry `payload.super_queue_id` (= the flagged event's id) in
addition to `payload.trigger_event_id` (= the origin `shortage.reported` id). So if a
candidate flagged event id doesn't match `trigger_event_id`, also collect the
`super_queue_id` values from `notify.sent`/`notify.failed` and match against those.

**⚠️ CRITICAL: schedule.flagged delivery may be proved ONLY by the top-level tuple, with
no payload trigger id at all** (observed 2026-08-12, DC Campus Demo). Two HIGH
`schedule.flagged` rebar-delay events (`c13b3788`, `9200e4fc`) looked un-notified under
a trigger-id-only check, but full detail showed each had an exact-time `notify.sent`
(`5c8ac44d`, `0d3aac88`) carrying **no `trigger_event_id` / `source_event_id` / `super_queue_id`**
— the only link was the **top-level tuple** `(po_id=031e6726, task_id=0cf6712f,
zone_id=9b1b5d60)` matching the flagged event's top-level fields. A script that dedups
solely on `ev['id'] in notify_ids or payload_source_event_id in notify_ids` will report
these as NEW and re-escalate already-delivered delays every cycle. Correct rule for a
`schedule.flagged`/`email.inbound` candidate: it is already-handled if its `id` OR its
`payload.source_event_id` OR its **top-level `(po_id, task_id, zone_id)` tuple** appears in
ANY `notify.sent`/`notify.failed` record (build `notified_tuples` from the notify events'
top-level fields and match the candidate's top-level fields against it). Always fetch the
full event detail before declaring a flagged item new.

Observed 2026-08-12 (Human_DC1): a `schedule.flagged` (`c6d7659f`) had
`source_event_id 98be8d55`, already in `notified_failed_ids` via a prior run's honest
`notify.failed` (`e21e5258`). Correct call: `[SILENT]` — the origin was escalated, the
payload was unchanged, and re-escalating the flagged projection would be notification spam.

**Observed 2026-08-12 (FieldClaw DC Campus — Demo): a `schedule.flagged`'s paired
`notify.sent` can carry NO `trigger_event_id` in its payload at all.** Two
`schedule.flagged` PO-9905 rebar events (`c13b3788`, `9200e4fc`) each had a sibling
`notify.sent` (`5c8ac44d`, `0d3aac88`) whose payload was just
`{channel, recipient, severity}` — no `trigger_event_id`, no `source_event_id`. A dedup
scan keyed only on trigger/source/super-queue ids therefore flags them `already=False`
(false "new" signal). The ONLY reliable dedup was the **shared top-level
`(po_id, task_id, zone_id)` tuple** on both the flagged event and its `notify.sent`
(matched `031e6726 / 0cf6712f / 9b1b5d60`). Lesson: for `schedule.flagged` candidates,
ALWAYS also check `notify.sent`/`notify.failed` whose top-level `(po_id, task_id, zone_id)`
matches the candidate — id-linkage dedup alone produces false positives that force manual
reconciliation via a full event dump (sort by `created_at`, print the payloads).

**⚠️ New 2026-08-13: there is NO per-event detail endpoint** (`GET .../events/{event_id}`
returns 404), so the "fetch the full event detail" step means re-fetching `events?limit=100`
and filtering the list for the candidate id — the list row already carries the complete
`payload`, top-level `zone_id`/`po_id`/`task_id`, and `created_at`. Never depend on an
individual-detail call.

### 6. Act on new signals

For each unnotified supplier-delay signal:

#### a. POST schedule.flagged event

```python
payload = {
    "type": "schedule.flagged",
    "zone_id": zone_id,
    "task_id": task_id,
    "po_id": po_id,
    "source": "cron-supplier-delay",
    "payload": {
        "reason": "Rebar delivery delayed — new ETA Thursday afternoon",
        "po": "PO-9905",
        "material": "rebar (200 bundles)",
        "original_eta": "Wednesday",
        "new_eta": "Thursday afternoon",
        "zone": "Zone C",
        "impact_task": "Structural Framing — Zone C",
        "thread_id": thread_id,
        "severity": "high",
        "supplier_reply": "Delayed — new ETA Thursday afternoon. Truck leaves Wednesday night."
    }
}
```

**⚠️ Event POST returns a list, not a single object.** Access the created id
with `response[0].get("id")`, NOT `response.get("id")` — the latter raises
`'list' object has no attribute 'get'`.

#### b. PATCH the impacted task to at-risk

```python
# PATCH /api/projects/{pid}/tasks/{task_id}
# Body: {"at_risk": true, "status": "in_progress"}
```

#### c. Attempt notification delivery

Try in order:
1. **Telegram via `hermes send --to telegram:<chat_id>`** (see
   `fieldclaw-cron-telegram-send`) — the WORKING channel for Telegram-only
   superintendent/foreman, with real delivery proof. NOT the old assumed dead-end.
2. AgentMail MCP (`mcp_agentmail_send_message`) — requires recipient email; may be
   unreachable under cron.
3. AgentMail REST API — **GET-only with Bearer auth; POST returns 404** (verified 2026-08-12)
4. FieldClaw mail API (`POST /api/projects/{pid}/mail/send`) — needs SMTP + recipient email

#### d. Log notification result (honesty-critical)

**Always attempt delivery BEFORE logging.** Only log `notify.sent` when the delivery
channel confirms (`delivered: true`, e.g. `hermes send --json` returns
`{"success":true,...}` with a message_id).

**If delivery succeeded:** POST `notify.sent` with `delivered: true`.

```python
payload = {
    "type": "notify.sent",
    "zone_id": zone_id,
    "task_id": task_id,
    "po_id": po_id,
    "source": "cron-supplier-delay",
    "payload": {
        "channel": "telegram",       # or "email"
        "recipient": "Superintendent",
        "recipient_telegram": "6009530821",
        "subject": "SUPPLIER DELAY: PO-9905 rebar — Zone C Structural Framing at risk",
        "message": "Rebar delivery for PO-9905 delayed to Thursday afternoon...",
        "severity": "high",
        "trigger_event_id": signal_event_id,
        "delivered": True,
        "message_id": "...",
        "mirrored": True
    }
}
```

**If delivery failed:** POST `notify.failed` with the error — do NOT log `notify.sent`.

```python
payload = {
    "type": "notify.failed",
    "zone_id": zone_id,
    "source": "cron-supplier-delay",
    "payload": {
        "channel": "email+telegram",
        "recipient": "Superintendent",
        "subject": "SUPPLIER DELAY: ...",
        "message": "...",
        "severity": "high",
        "trigger_event_id": signal_event_id,
        "error": "..."
    }
}
```

**Never log `notify.sent` without proof of delivery.** The logbook honesty rule is:
`notify.sent` only when Telegram/email API confirms delivery; `notify.failed` with
error on failure.

### 7. Resolve superintendent contact info

```python
# GET /api/projects/{pid}/people
# Find role == "superintendent" → get telegram_id and email
```

### 8. Output or [SILENT]

If new signals were found and acted on: produce a report with signal details,
actions taken, and any delivery failures.

If no new signals (all already notified or no supplier-delay emails): respond
with exactly `[SILENT]`.

**Completeness check before a quiet `[SILENT]` — sweep the mapped inbox for unparsed inbound.
(verified 2026-08-12):** A supplier-delay signal can sit in the project's AgentMail inbox but
NOT yet be registered as an `email.inbound`/`email.parsed` event. So when the primary project
returns `0` events AND an empty `/super-queue`, do a read-only sweep of its mapped `inbox_email`
before declaring the cycle quiet:
- GET-only AgentMail `/v0/inboxes/{email}/messages` from a `/tmp` Python script (reads the key from
  `os.environ` at runtime; address the inbox by EMAIL, not `id` — AgentMail REST inboxes have
  `id: null`; set a User-Agent header), filter to `received`/`unread`.
- If every message is genuinely non-delay (old project docs: estimates, recommendation letters,
  RFQ scoring, site maps — no ETA change, no shortage/delivery/rebar keyword, no PO delay), then
  `[SILENT]` is correct and NO `notify.sent`/`notify.failed` should be logged (nothing was attempted).
- A mapped inbox can hold old inbound docs that were never parsed into FieldClaw events at all; their
  existence alone is not a signal. Judge by content, not by "there are unread messages."
- Skip any `email.parsed` whose payload has `has_delay:false` / intent "Import zone map" / site-logistics
  GeoJSON — that is a map import, not a delay (see §3a pitfall).

This mirrors `fieldclaw-mail-sweep` / `multi-project-inbox-polling`; the point here is that the
supplier-delay cron does the sweep *before* answering `[SILENT]`, not only when it already suspects a signal.

## Verification discipline

A detection script's printed candidate counts (e.g. "status.reported shortage: 0")
are NOT authoritative for the already-handled decision. They can false-negative even
when super-queue visibly holds a status.reported shortage (observed 2026-08-12, DC
Campus Demo: `e0daaef2` "waiting on bolts" printed 0). Ground truth for "already
escalated" = the `notify.sent`/`notify.failed` record keyed to the trigger id /
`source_event_id` (`notify.failed 3d90fdf7` keyed to `e0daaef2` justified the
`[SILENT]`). When a count disagrees with what super-queue holds, run a small
verification read that fetches raw events and prints the notify records keyed to
that trigger with `delivered`/`channel` — this also surfaces supersession
(older `notify.failed` → later `notify.sent` delivered:true = handled).

## Pitfalls

| Pitfall | Fix |
|---------|-----|
| `FIELDCLAW_PROJECT_ID` points at wrong/non-existent project | List all projects via `GET /api/projects`, iterate |
| `POST /events` returns list, not object | Use `response[0].get("id")` |
| `fieldclaw_api.main:app` uvicorn entrypoint fails | Use `fieldclaw_api:main` |
| SMTP not configured → email delivery fails | Log `notify.failed` with error; do NOT log `notify.sent` without delivery proof |
| AgentMail MCP unreachable | Log `notify.failed`; report delivery gap in output |
| **AgentMail REST API is GET-only with Bearer auth** | POST/send returns 404 "Route not found". Cannot send email under cron with API key. |
| **Telegram-only super under cron** | NOT a dead-end — use `hermes send --to telegram:<chat_id>` (`fieldclaw-cron-telegram-send`). Real delivery proof → `notify.sent`. |
| `curl \| python3` blocked by security scanner | Write Python to `/tmp/`, run with `python3 /tmp/script.py` |
| `execute_code` blocked in cron | Use `terminal` tool with `/tmp/` Python scripts |
| Inline `$FIELDCLAW_API_KEY` in shell mangled by write_file | Use Python `os.environ.get()` instead |
| **Empty-payload events** (`schedule.flagged` or `email.inbound` with `payload={}`) | Skip them — they produce garbage `notify.sent` entries with all "Unknown" fields. Filter with `if not ev.get("payload"): continue` |
| **Dedup mismatch**: `notify.sent` stores `po_id`/`task_id`/`zone_id` at top level, not in `payload` | Build dedup set from **top-level** event fields: `ev.get("po_id")`, not `ev.get("payload", {}).get("po_id")` |
| **`schedule.flagged` dedup by own id gives `already_notified: false` even when its origin is handled** | Also match `ev.payload.source_event_id` against `notified_trigger_ids`/`notified_failed_ids`. A flagged projection of an already-escalated origin is NOT new (see §5). Bonus: collect `payload.super_queue_id` from notify events and match against it too |
| **`notify.sent` can have `trigger_event_id: null` + `super_queue_id: null` yet still prove handling** (observed 2026-08-12) | These null-id notify records (e.g. the PO-9905 rebar escalation) carry the signal only at the TOP-LEVEL `(po_id, task_id, zone_id)` tuple. When verifying dedup, never conclude "not handled" from a missing trigger/super_queue id — match the candidate's top-level po/task/zone tuple against EVERY notify.sent/notify.failed event's top-level tuple. `email.inbound`/`schedule.flagged`/`status.reported` candidates for the same PO/zone are handled regardless of null ids. A verify script must dump the raw top-level tuple columns, not just `payload.*` ids |
| **`schedule.flagged` with `source_event_id: null` gets flagged "unnotified" by an id/source-event scan** (observed 2026-08-12, Demo project) | A `schedule.flagged` whose `payload.source_event_id` is **null** WILL pass id-based dedup and look like a brand-new HIGH signal. It is NOT — dedup is carried by the top-level `(po_id, task_id, zone_id)` tuple on the flagged event vs the `notify.sent` records. Always ALSO match the flagged event's top-level tuple against `notified_tuples`; if a `notify.sent` shares the exact `(po, task, zone)`, the projection is already handled even with no `source_event_id` and no matching trigger id. Dedup predicate must be id-OR-source_event_id-OR-super_queue_id-OR-fresh-tuple, not id/source-only |
| **Scan that checks ONLY ID keys (trigger/super_queue/source_event_id) false-flags already-sent `schedule.flagged`** (observed 2026-08-12, DC Campus Demo) | Two `schedule.flagged` events (`c13b3788`, `9200e4fc`) had NO `trigger_event_id`/`super_queue_id`/`source_event_id` linkage, so an ID-only scan called them `already_notified: False`. They were actually delivered: each matched a `notify.sent` on the **top-level `(po_id, task_id, zone_id)` tuple** (flags and their `notify.sent` shared po `031e6726…`, task `0cf6712f…`, zone `9b1b5d60…`). Fix: ALWAYS include the top-level tuple check alongside the ID-key checks — a flag is handled if `(po_id, task_id, zone_id)` is in `notified_tuples`, independent of any ID linkage. The reference script does this; replicate it in any ad-hoc scan you write |
| **`events?limit=100` on a noisy project may still truncate** (DC Campus had 125 events) | `limit=100` returns only the first 100; an ad-hoc scan can miss older events (including earlier `notify.sent` records that dedup a candidate). If a project has >100 events and you see an unexpected "new" flag, re-fetch with a larger limit (200/500) for the notify history before escalating |
| **`schedule.flagged` dedup STILL false even after source_event_id + super_queue_id checks** | Match the flagged event's OWN top-level `(po_id, task_id, zone_id)` tuple against `notified_tuples`. A `notify.sent` for the same PO/task/zone (top-level fields on both events) covers it even when no id linkage exists (2026-08-12, DC Campus). See `references/dedup-tuple-check.md` |
| **Event deletion unsupported**: `DELETE /api/projects/{pid}/events/{id}` returns 404 | Cannot remove bad `notify.sent` entries. Prevention (skip empty payloads) is the only fix |
| **Per-event detail GET `.../events/{event_id}` returns 404** (observed 2026-08-13 fc_demo1) | There is NO per-event detail endpoint. The "fetch full event detail" guidance means re-fetching `GET .../events?limit=100` and filtering the returned list for the candidate id — the list row carries the complete `payload`, top-level `zone_id`/`po_id`/`task_id`, and `created_at`. Never depend on an individual-detail call to inspect a candidate (verified: `events/{event_id}` → 404). See `references/no-per-event-detail-endpoint.md` |
| **Super-queue dedup by id-only → false "NEW" flags on delivered items** (observed 2026-08-12) | A `/super-queue` `schedule.flagged` is a *projection* of an already-delivered origin; it matches `notify.sent` by the **top-level `(po_id, task_id, zone_id)` tuple**, not by its own id or `source_event_id`. If the queue-reconciliation loop calls `handled()` with `None` for po/task/zone while the events loop uses the full tuple, the same already-delivered item prints `handled=***NEW***` in the queue branch — forcing manual reinterpretation and risking a false re-escalation. Fix: thread the queue item's top-level `po_id/task_id/zone_id` (`q.get(...)`, not payload) into the SAME shared `handled()` check used for events so both loops agree. |
| **`email.parsed` events use `body_preview`** not `body` | Check both: `p.get("body", "") or p.get("body_preview", "")` |
| **`status.reported` events are shortage signals too** | Scan super-queue for `status.reported` with shortage keywords ("waiting on", "need", "short", "out of"), not just `email.inbound`/`schedule.flagged` |
| **Logging `notify.sent` without delivery proof** | NEVER do this. Use `notify.failed` with error when delivery fails. The skill's previous guidance ("log notify.sent anyway") was wrong and has been corrected. |
| **Site-logistics map import emails look like delay signals** | `email.parsed` for a GeoJSON/zone-map import has `has_delay: false` + intent "Import zone map". Check `payload.has_delay`/`intent` before flagging — the word "logistics"/"delivery" in the subject is not a delay. **Broader case (observed 2026-08-12, My Site):** batch document imports — site/design maps, RFQ scoring, CMAR recommendation, GMP letter, project estimate — carry `has_delay: None` (the field is **absent**, not `false`) with `intent` of `document/map`, `document/recommendation`, `document/estimate`. Keyword scan (subj+body has no ETA/PO/delay/shine words) correctly skips them. A `has_delay` of `None`/absent is NOT a delay signal; rely on combined keyword scan over subject+body and the intent label, not on `has_delay` being present at all. |
| **Zone-map import's `email.inbound` sibling carries NO `has_delay`/`intent`** (observed 2026-08-12, Smoke Site) | A GeoJSON import surfaces as a pair: `email.parsed` is rich (`has_delay:false`, `intent:"Import … site logistics / zone map"`), but its `email.inbound` sibling only has `thread_id/from/subject/received_at`. Payload-only exclusion misses the inbound sibling (absent fields → `has_delay=None` → looks like a real candidate). Exclude BOTH by subject too (`"geojson" in subject` / `"logistics map" in subject` / `"zone map" in subject`). See §3a predicate. |
| **The super-queue is a SUPERSET — don't drive escalation off it alone** (observed 2026-08-12, RFI Isolation & DC Campus Demo) | `GET .../super-queue` lists ANY awaiting-reply item (schedule.flagged, safety.reported, quality.reported, status.reported) and can include items whose underlying event has an **empty payload `{}`** (malformed). Presence on the queue is NOT a supplier-delay signal by itself. Filter by event type at the event level (`status.reported`+shortage keywords, `schedule.flagged`+non-empty payload, `email.inbound/parsed`+delay keywords, skip empty payloads), then dedup against notify records. On RFI Isolation the queue's only `schedule.flagged` (d24ed7e8) had `payload={}` and already had a `notify.sent` — correctly SILENT. |
| **`events?limit=500` times out on large/noisy projects** (observed 2026-08-12) | The events endpoint is slow on big projects (125+ events, e.g. DC Campus Demo ingesting a flood of sim safety/quality events). A `limit=500` fetch raised a connection exception (`EVENTS_ERR None`) on 3 of 4 projects, while `limit=100` or a plain no-limit fetch of the SAME endpoints returned 200 cleanly. Fetch with `limit=100` (or omit the param) rather than `limit=500`; if a fetch fails mid-iteration, retry it with a smaller/no limit before treating the project as unreachable. |
| **Resolve returns an empty projects list — do NOT assume the system is genuinely empty** (observed 2026-08-12) | `GET /api/projects` returning `200 []` (and `FIELDCLAW_PROJECT_ID` unset) is a valid reason to `[SILENT]` ONLY after confirming it is real. Verify against the system of record before concluding "no project to poll": the resolver (`resolve_project.py`) + `data/fieldclaw.db` SQLite rowcounts (`SELECT count(*) FROM projects/people/events/mail_messages`) both returning 0 proves an empty env. If the API returns `[]` but tenant project dirs exist under `kb/tenants/*/projects/`, the API and KB are out of sync — re-check the DB / that the server is pointing at the right `fieldclaw.db` rather than trusting the empty API alone. On a genuinely empty env the correct output is `[SILENT]` (no project id, no signals), not a `notify.failed`. |
| **Cross-job collision on shared `/tmp` script names** (observed 2026-08-12) | `watch-supplier-delays`, `mail-poll`, and `watch-shortages` all write cursor/Poll logic to sharded paths (`/tmp/fc_supplier_poll.py`, `/tmp/poll_mail.py`). A `write_file` to `/tmp/fc_supplier_poll.py` came back "modified by sibling subagent" — a concurrent FieldClaw job was using the same path. If the write/run ordering flips, you could silently run a sibling job's script against your project. Fix: give the temp script a unique per-run suffix (e.g. `/tmp/fc_supplier_poll_<job>_<ts>.py`) and always run the file you just wrote, or check the "modified by sibling" warning and re-write before running. |
| **Sibling cron jobs collide on shared `/tmp` script names** (observed 2026-08-12) | Several FieldClaw jobs (watch-shortages, watch-supplier-delays, mail-poll) run every 3–5m and each writes `/tmp/{fc_resolve,fc_poll}.py`. A concurrent sibling overwrote my script between `write_file` and `run`, surfacing a "modified by sibling subagent" warning. Namespace your /tmp scripts per run (e.g. append the project id: `/tmp/fc_cron_81989611.py`) and re-read before running if a warning fires. |
| **skill_manage patch/write_file cannot reach the fieldclaw store from default profile** | Only `action='create'` resolves `~/.hermes-fieldclaw/skills/`. To patch an existing fieldclaw skill, recreate it with `create` + full updated content, or edit the file on disk with file/write tools in a full session. |

## HTTP-only (browser_console) multi-project poll

When the job spec forbids terminal/eval/execute_code for the resolve step, poll via
`browser_console` `fetch` carrying the `X-API-Key` header, chaining resolve + all-project
scan in ONE async IIFE. **On noisy projects return a per-project event-type HISTOGRAM
(counts per `type`), not the raw event array** — a project like DC Campus Demo returns 125
events in `events?limit=100` and raw JSON floods context. The `types` histogram immediately
reveals `notify.sent`/`notify.failed`/`schedule.flagged`/`shortage.reported` presence per
project; drill into just the supplier-relevant events on projects that have them. Full
verified JS pattern in `references/browser-multiproject-poll.md`.

## Reference scripts

- `scripts/fc_supplier_poll.py` — full AUTOMATION scaffold (posts notify.sent,
  patches tasks, attempts delivery). NOTE: it logs `notify.sent` BEFORE delivery
  succeeds — mis-ordered per `fieldclaw-notify-delivery-discipline`. Re-order
  deliver-then-log before relying on it.
- `scripts/fc_delay_scan.py` — READ-ONLY probe (safe to run repeatedly, never
  POSTs). Iterates all projects and prints every candidate signal with ALL dedup
  handles (`source_event_id`, `trigger_event_id`, `super_queue_id`, `delivered`)
  plus `has_delay`/`intent`/summary and the super-queue count. Use this when you
  must hand-judge SILENT-vs-escalate from real API evidence before committing to a
  delivery — it surfaces the second/third dedup handles the automation script's
  ID/tuple-only scan misses.

## Compact browser_console multi-project poll (no-shell-for-resolve spec)

When a cron job spec forbids terminal/eval/execute_code for resolve, do the whole
resolve + poll in ONE `browser_console` IIFE that filters events down to the relevant
types + dedup payload keys, so raw JSON never floods context. Full working pattern +
minimal IIFE skeleton: `references/browser-console-compact-poll.md`.
NOTE it POSTs `notify.sent` BEFORE attempting delivery; re-order per
`fieldclaw-notify-delivery-discipline` before relying on it).

Prefer **`scripts/fc_sweep_signals.py`** for the DETECTION/dedup pass: a verified
(2026-08-12) read-only GET-only sweep over all projects that prints which
supplier-delay signals exist and whether each is already handled, before you
attempt any delivery or POST any event. It dedups on BOTH ids and the top-level
`(po_id, task_id, zone_id)` tuple (so `notify.sent` records that carry a tuple but
NO `trigger_event_id` are still matched), skips empty-payload events and
`has_delay:false` zone-map imports, scans `status.reported` for shortage keywords,
and uses `events?limit=100` to avoid the noisy-project timeout.

## Pitfall: dedup sets and the top-level tuple may contain `None`

The dedup sets you build from event top-level fields hold tuples like
`(po_id, task_id, zone_id)` where any field can be `None`. Calling
`sorted(notified_tuples)` on them raises `TypeError: '<' not supported between
instances of 'str' and 'NoneType'`. Stringify before sorting/printing:
`sorted([str(t) for t in notified_tuples])`. Same guard applies to any set of
tuples you sort for a summary line.

A **dedup-decision scan** is at `scripts/fc_sd_scan_dedup.py` — iterates ALL
projects and prints `already=bool` per candidate by unioning every dedup key
(`payload.trigger_event_id`, `payload.super_queue_id`, the top-level
`(po_id, task_id, zone_id)` tuple, and a `schedule.flagged`'s
`payload.source_event_id`) from a FRESH event fetch. If every candididate prints
`already=True`, the run is `[SILENT]` (verified 2026-08-12: all signals across 4
projects already notified). Use this instead of hand-tracing notify state. **Treat it as a
scaffold** — it POSTs `notify.sent` BEFORE attempting delivery; re-order (deliver
first, then log) before relying on it, or future runs inherit the false-notify bug
(see `fieldclaw-notify-delivery-discipline`).
