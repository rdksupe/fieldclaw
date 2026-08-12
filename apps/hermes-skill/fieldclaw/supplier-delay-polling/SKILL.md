---
name: supplier-delay-polling
description: Cron job workflow for detecting supplier-delay signals in FieldClaw — multi-project polling, email.inbound parsing, schedule.flagged projection, task at-risk flagging, and notify.sent/notify.failed logging.
version: 0.2.2
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

**Also note:** `email.inbound`/`email.parsed` traffic that is a zone-map / site-logistics
import has `has_delay: false` and intent like "Import zone map" — that is NOT a
supplier-delay signal. Don't flag it just because the body mentions "site logistics".
Check `payload.has_delay` / `intent` too.

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

**Extra dedup hint (observed 2026-08-12):** an escalated `notify.sent` for a projected
`schedule.flagged` can carry `payload.super_queue_id` (= the flagged event's id) in
addition to `payload.trigger_event_id` (= the origin `shortage.reported` id). So if a
candidate flagged event id doesn't match `trigger_event_id`, also collect the
`super_queue_id` values from `notify.sent`/`notify.failed` and match against those.

Observed 2026-08-12 (Human_DC1): a `schedule.flagged` (`c6d7659f`) had
`source_event_id 98be8d55`, already in `notified_failed_ids` via a prior run's honest
`notify.failed` (`e21e5258`). Correct call: `[SILENT]` — the origin was escalated, the
payload was unchanged, and re-escalating the flagged projection would be notification spam.

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
1. AgentMail MCP (`mcp_agentmail_send_message`) — may be unreachable under cron
2. AgentMail REST API — **GET-only with Bearer auth; POST returns 404** (verified 2026-08-12)
3. FieldClaw mail API (`POST /api/projects/{pid}/mail/send`) — needs SMTP config

#### d. Log notification result (honesty-critical)

**If delivery succeeded:** POST `notify.sent` with `delivered: true`.

```python
payload = {
    "type": "notify.sent",
    "zone_id": zone_id,
    "task_id": task_id,
    "po_id": po_id,
    "source": "cron-supplier-delay",
    "payload": {
        "channel": "email",
        "recipient": "Superintendent",
        "subject": "SUPPLIER DELAY: PO-9905 rebar — Zone C Structural Framing at risk",
        "message": "Rebar delivery for PO-9905 delayed to Thursday afternoon...",
        "severity": "high",
        "trigger_event_id": signal_event_id,
        "delivered": True
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
        "error": "AgentMail MCP server unreachable (N consecutive failures). REST API v0 does not support POST with Bearer auth (404). No delivery channel succeeded."
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

## Pitfalls

| Pitfall | Fix |
|---------|-----|
| `FIELDCLAW_PROJECT_ID` points at wrong/non-existent project | List all projects via `GET /api/projects`, iterate |
| `POST /events` returns list, not object | Use `response[0].get("id")` |
| `fieldclaw_api.main:app` uvicorn entrypoint fails | Use `fieldclaw_api:main` |
| SMTP not configured → email delivery fails | Log `notify.failed` with error; do NOT log `notify.sent` without delivery proof |
| AgentMail MCP unreachable | Log `notify.failed`; report delivery gap in output |
| **AgentMail REST API is GET-only with Bearer auth** | POST/send returns 404 "Route not found". Cannot send email under cron with API key. |
| `curl \| python3` blocked by security scanner | Write Python to `/tmp/`, run with `python3 /tmp/script.py` |
| `execute_code` blocked in cron | Use `terminal` tool with `/tmp/` Python scripts |
| Inline `$FIELDCLAW_API_KEY` in shell mangled by write_file | Use Python `os.environ.get()` instead |
| **Empty-payload events** (`schedule.flagged` or `email.inbound` with `payload={}`) | Skip them — they produce garbage `notify.sent` entries with all "Unknown" fields. Filter with `if not ev.get("payload"): continue` |
| **Dedup mismatch**: `notify.sent` stores `po_id`/`task_id`/`zone_id` at top level, not in `payload` | Build dedup set from **top-level** event fields: `ev.get("po_id")`, not `ev.get("payload", {}).get("po_id")` |
| **`schedule.flagged` dedup by own id gives `already_notified: false` even when its origin is handled** | Also match `ev.payload.source_event_id` against `notified_trigger_ids`/`notified_failed_ids`. A flagged projection of an already-escalated origin is NOT new (see §5). Bonus: collect `payload.super_queue_id` from notify events and match against it too |
| **Event deletion unsupported**: `DELETE /api/projects/{pid}/events/{id}` returns 404 | Cannot remove bad `notify.sent` entries. Prevention (skip empty payloads) is the only fix |
| **`email.parsed` events use `body_preview`** not `body` | Check both: `p.get("body", "") or p.get("body_preview", "")` |
| **`status.reported` events are shortage signals too** | Scan super-queue for `status.reported` with shortage keywords ("waiting on", "need", "short", "out of"), not just `email.inbound`/`schedule.flagged` |
| **Logging `notify.sent` without delivery proof** | NEVER do this. Use `notify.failed` with error when delivery fails. The skill's previous guidance ("log notify.sent anyway") was wrong and has been corrected. |
| **Site-logistics map import emails look like delay signals** | `email.parsed` for a GeoJSON/zone-map import has `has_delay: false` + intent "Import zone map". Check `payload.has_delay`/`intent` before flagging — the word "logistics"/"delivery" in the subject is not a delay. |
| **`events?limit=500` times out on large/noisy projects** (observed 2026-08-12) | The events endpoint is slow on big projects (125+ events, e.g. DC Campus Demo ingesting a flood of sim safety/quality events). A `limit=500` fetch raised a connection exception (`EVENTS_ERR None`) on 3 of 4 projects, while `limit=100` or a plain no-limit fetch of the SAME endpoints returned 200 cleanly. Fetch with `limit=100` (or omit the param) rather than `limit=500`; if a fetch fails mid-iteration, retry it with a smaller/no limit before treating the project as unreachable. |

## Reference script

A ready-to-run polling script is at `scripts/fc_supplier_poll.py`.
