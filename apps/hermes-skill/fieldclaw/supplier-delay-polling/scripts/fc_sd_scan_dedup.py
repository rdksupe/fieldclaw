#!/usr/bin/env python3
"""Multi-project supplier-delay scan that prints an `already=bool` per candidate.

The dedup decision is computed INLINE, per candidate, by unioning every key the
notify events carry (payload.trigger_event_id, payload.super_queue_id, and the
top-level po_id/task_id/zone_id tuple). It also matches a schedule.flagged by its
payload.source_event_id. Print compact lines so the escalation call is visible
without flooding context with raw JSON.

RATIONALE FROM A CLEAN RUN (2026-08-12): every supplier-delay signal across all
projects (rebar shortage on Human_DC1; rebar/bolt signals on the sim Demo flood)
already carried a notify.sent (delivered:true) or notify.failed keyed to its
trigger/super_queue id or tuple -> all `already=True` -> [SILENT]. Add this pattern
for future runs instead of hand-tracing notify state across projects.

Run:  python3 fc_sd_scan_dedup.py
"""
import os, json, urllib.request, urllib.error

base = os.environ.get("FIELDCLAW_BASE_URL", "http://127.0.0.1:8000")
key = os.environ.get("FIELDCLAW_API_KEY", "dev-key-change-me")

# Scan width == ALL projects, not just the env/id-resolved one. Delay signals
# often live on a different project than FIELDCLAW_PROJECT_ID points at.
DELAY_KEYWORDS = ['eta', 'delay', 'rebar', 'delivery', 'po-', 'ship', 'truck',
                  'supplier', 'backorder', 'shortage', 'lead time', 'reschedule']
SHORTAGE_KEYWORDS = ['waiting on', 'need', 'short', 'out of', 'missing',
                     'ran out', 'shortage', 'bolts', 'rebar', 'concrete']


def api_get(path):
    url = f"{base}{path}"
    req = urllib.request.Request(url, headers={"X-API-Key": key})
    with urllib.request.urlopen(req, timeout=12) as resp:
        return json.loads(resp.read().decode())


def main():
    projects = api_get("/api/projects")
    for proj in projects:
        pid, name = proj.get("id"), proj.get("name")
        try:
            events = api_get(f"/api/projects/{pid}/events?limit=100")  # NOT limit=500 (timeouts)
        except Exception as e:
            print(f"### {name} ({pid}): EVENTS_ERR {e}")
            continue
        print(f"\n### {name} ({pid}) events={len(events) if isinstance(events, list) else events}")
        if not isinstance(events, list):
            continue

        # Build the dedup set FROM THIS FRESH FETCH (never a prior run's narrative).
        notified_ids = set()      # trigger_event_id + super_queue_id values
        notified_tuples = set()   # (po_id, task_id, zone_id)
        for ev in events:
            if ev.get("type") in ("notify.sent", "notify.failed"):
                p = ev.get("payload") or {}
                for k in ("trigger_event_id", "super_queue_id"):
                    if p.get(k):
                        notified_ids.add(p[k])
                notified_tuples.add((ev.get("po_id"), ev.get("task_id"), ev.get("zone_id")))

        for ev in events:
            et, p = ev.get("type"), ev.get("payload") or {}
            if not p:
                continue  # empty-payload events -> garbage notify, skip
            if et == "schedule.flagged":
                src = p.get("source_event_id")
                already = (ev.get("id") in notified_ids or src in notified_ids
                           or (ev.get("po_id"), ev.get("task_id"), ev.get("zone_id")) in notified_tuples)
                print(f"  schedule.flagged {ev.get('id')} src={src} already={already} "
                      f"sev={p.get('severity')} reason={str(p.get('reason'))[:60]}")
            elif et in ("email.inbound", "email.parsed"):
                if p.get("has_delay") is False:
                    continue  # zone-map / site-logistics import, not a delay
                subj = (p.get("subject", "") or "").lower()
                body = (p.get("body", "") or p.get("body_preview", "") or "").lower()
                if any(kw in subj + " " + body for kw in DELAY_KEYWORDS):
                    already = (ev.get("id") in notified_ids
                               or (ev.get("po_id"), ev.get("task_id"), ev.get("zone_id")) in notified_tuples)
                    print(f"  {et} id={ev.get('id')} already={already} intent={p.get('intent')} "
                          f"has_delay={p.get('has_delay')} subj={str(p.get('subject'))[:60]}")
            elif et == "status.reported":
                summary = (p.get("summary", "") or "").lower()
                if any(kw in summary for kw in SHORTAGE_KEYWORDS):
                    already = (ev.get("id") in notified_ids
                               or (ev.get("po_id"), ev.get("task_id"), ev.get("zone_id")) in notified_tuples)
                    print(f"  status.reported id={ev.get('id')} already={already} summary={str(p.get('summary'))[:60]}")

        try:
            sq = api_get(f"/api/projects/{pid}/super-queue")
            print(f"  super-queue open types: {[s.get('type') for s in sq] if isinstance(sq, list) else sq}")
        except Exception as e:
            print(f"  super-queue ERR {e}")


if __name__ == "__main__":
    main()
