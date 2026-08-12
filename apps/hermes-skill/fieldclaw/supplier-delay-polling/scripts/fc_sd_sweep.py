#!/usr/bin/env python3
"""FieldClaw supplier-delay read-only sweep — computes per-project `new_count`.

READ-ONLY: this script NEVER POSTs. It is the safe, deterministic "scan width +
dedup first" probe for a supplier-delay cron run. Run it, review `new_count` per
project, and only then decide which (if any) signals to escalate — do all
POSTing (schedule.flagged / notify.sent / notify.failed / PATCH task) in a SEPARATE
step, AFTER a delivery channel actually confirms success.

Why this exists: the `supplier-delay-polling` skill's reference script
`scripts/fc_supplier_poll.py` is known (fieldclaw-notify-delivery-discipline) to
POST `notify.sent` BEFORE attempting delivery, leaving false notify entries you
cannot delete. Use THIS sweep to enumerate candidates first; never POST from it.

Run: python3 /tmp/fc_sd_sweep.py   (place unique per-run name to avoid /tmp clash)
Env: FIELDCLAW_BASE_URL, FIELDCLAW_API_KEY
"""

import os
import json
import urllib.request

base = os.environ.get("FIELDCLAW_BASE_URL", "http://127.0.0.1:8000")
key = os.environ.get("FIELDCLAW_API_KEY", "")

DELAY_KEYWORDS = ['eta', 'delay', 'rebar', 'delivery', 'po-', 'ship', 'truck',
                  'supplier', 'backorder', 'shortage', 'lead time', 'reschedule']
SHORTAGE_KEYWORDS = ['waiting on', 'need', 'short', 'out of', 'missing',
                     'ran out', 'shortage', 'bolts', 'rebar', 'concrete']

def api_get(path):
    req = urllib.request.Request(f"{base}{path}", headers={"X-API-Key": key})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode())

def is_candidate(et, payload):
    """Return (bool, reason) for whether an event is an unnotified supplier-delay signal candidate."""
    if not payload:
        return False, "empty-payload: skip"
    if et == "schedule.flagged":
        return True, "schedule.flagged"
    if et in ("email.inbound", "email.parsed"):
        subject = (payload.get("subject", "") or "").lower()
        body = (payload.get("body", "") or payload.get("body_preview", "") or "").lower()
        intent = (payload.get("intent", "") or "").lower()
        combined = subject + " " + body
        kw_hit = any(k in combined for k in DELAY_KEYWORDS)
        # Site-logistics/zone-map imports are NOT delay signals
        if "import zone map" in intent or "logistics" in intent.lower():
            kw_hit = False
        if kw_hit:
            return True, "email " + et
    if et == "status.reported":
        summary = (payload.get("summary", "") or "").lower()
        if any(k in summary for k in SHORTAGE_KEYWORDS):
            return True, "status.reported shortage"
    return False, "no-match"

out = {"projects": []}
for proj in api_get("/api/projects"):
    pid = proj["id"]
    rec = {"id": pid, "name": proj["name"], "inbox_email": proj.get("inbox_email")}
    try:
        events = api_get(f"/api/projects/{pid}/events?limit=100")  # NOT limit=500
    except Exception as e:
        rec["events_err"] = repr(e)
        out["projects"].append(rec)
        continue

    # Dedup set from notify events: trigger_event_id + source_event_id +
    # super_queue_id (all can key the same escalation) + top-level (po,task,zone).
    notified_ids = set()      # trigger + source ids
    notified_sq = set()       # super_queue_ids
    notified_tuples = set()   # (po_id, task_id, zone_id) at TOP level
    for ev in events:
        if ev.get("type") in ("notify.sent", "notify.failed"):
            p = ev.get("payload") or {}
            if p.get("trigger_event_id"):
                notified_ids.add(p["trigger_event_id"])
            if p.get("source_event_id"):
                notified_ids.add(p["source_event_id"])
            if p.get("super_queue_id"):
                notified_sq.add(p["super_queue_id"])
            notified_tuples.add((ev.get("po_id"), ev.get("task_id"), ev.get("zone_id")))

    candidates = []
    for ev in events:
        payload = ev.get("payload") or {}
        flagged, reason = is_candidate(ev.get("type"), payload)
        if not flagged:
            continue
        src_id = payload.get("source_event_id")
        already = (
            ev["id"] in notified_ids
            or (src_id and src_id in notified_ids)
            or ev["id"] in notified_sq
            or (ev.get("po_id"), ev.get("task_id"), ev.get("zone_id")) in notified_tuples
        )
        candidates.append({
            "id": ev["id"], "type": ev.get("type"), "created": ev.get("created_at"),
            "reason": reason, "src_id": src_id, "sq_id": payload.get("super_queue_id"),
            "summary": str(payload.get("summary", ""))[:90],
            "subject": str(payload.get("subject", ""))[:70],
            "severity": payload.get("severity"), "already_notified": already,
        })

    rec["signal_count"] = len(candidates)
    rec["new_count"] = len([c for c in candidates if not c["already_notified"]])
    rec["candidates"] = candidates
    out["projects"].append(rec)

print(json.dumps(out, indent=1))
