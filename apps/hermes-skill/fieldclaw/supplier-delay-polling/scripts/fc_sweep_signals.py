#!/usr/bin/env python3
"""FieldClaw supplier-delay read-only sweep + dedup probe.

Known-good scaffold (verified 2026-08-12 supplier-delay cron run). Use this to
DETECT which projects hold supplier-delay signals and whether each is already
handled BEFORE you attempt any delivery or POST any notify event. It performs a
GET-only sweep and prints a compact per-project report; it writes nothing.

Why this over scripts/fc_supplier_poll.py: that scaffold POSTs notify.sent BEFORE
attempting delivery (a known bug per fieldclaw-notify-delivery-discipline). This
script is read-only and correctly dedups against BOTH payload ids AND the
top-level (po_id, task_id, zone_id) tuple.

Run:
    FIELDCLAW_API_KEY=$FIELD..._KEY FIELDCLAW_BASE_URL=${FIELDCLAW_BASE_URL} \
        python3 fc_sweep_signals.py

Key correctness points baked in:
  * Reads FIELDCLAW_API_KEY from os.environ at runtime (never hardcode).
  * events?limit=100 (NOT 500) -- the events endpoint times out on noisy projects.
  * Skips empty-payload events (they produce garbage "Unknown" notify entries).
  * Dedups on ids AND the top-level (po,task,zone) tuple: notify.sent records for
    rebar delays often carry the tuple but NO trigger_event_id, so an id-only scan
    false-positives them as NEW.
  * None-safe tuple handling: top-level po_id/task_id/zone_id may be None; stringify
    before sorting/printing.
  * Skips email.parsed events with has_delay is False (zone-map/site-logistics
    imports are NOT delay signals).
  * Scans status.reported summaries for shortage keywords too (bolt/rebar shortages
    surface as status.reported, not just schedule.flagged).
"""
import os, json, urllib.request

base = os.environ.get("FIELDCLAW_BASE_URL", "http://127.0.0.1:8000")
key = os.environ.get("FIELDCLAW_API_KEY", "")

def get(path):
    req = urllib.request.Request(f"{base}{path}", headers={"X-API-Key": key})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode())

projects = get("/api/projects")
print("PROJECTS:")
for p in projects:
    print(f"  {p['id']} | {p['name']} | inbox={p.get('inbox_email')}")

DELAY_KW = ['eta','delay','rebar','delivery','po-','ship','truck','supplier',
            'backorder','shortage','lead time','reschedule']
SHORT_KW = ['waiting on','need','short','out of','missing','ran out','shortage',
            'bolts','rebar','concrete']

for p in projects:
    pid = p['id']; name = p['name']
    try:
        events = get(f"/api/projects/{pid}/events?limit=100")
    except Exception as e:
        print(f"\n== {name} ({pid}) EVENTS_ERR {e}"); continue
    print(f"\n== {name} ({pid}) — {len(events)} events")

    sent_ids=set(); sent_tuples=set(); failed_ids=set(); failed_tuples=set()
    for ev in events:
        if ev.get("type") in ("notify.sent","notify.failed"):
            pl=ev.get("payload") or {}
            tid=pl.get("trigger_event_id"); sqid=pl.get("super_queue_id")
            tup=(ev.get("po_id"),ev.get("task_id"),ev.get("zone_id"))
            if ev["type"]=="notify.sent":
                if tid: sent_ids.add(tid)
                if sqid: sent_ids.add(sqid)
                sent_tuples.add(tup)
            else:
                if tid: failed_ids.add(tid)
                if sqid: failed_ids.add(sqid)
                failed_tuples.add(tup)

    cands=[]
    for ev in events:
        et=ev["type"]; pl=ev.get("payload") or {}
        if not pl: continue
        if et in ("email.inbound","email.parsed"):
            if pl.get("has_delay") is False: continue
            subj=(pl.get("subject","") or "").lower()
            body=(pl.get("body","") or pl.get("body_preview","") or "").lower()
            if any(kw in (subj+" "+body) for kw in DELAY_KW):
                cands.append((et,ev["id"],pl.get("subject"),pl.get("intent"),pl.get("has_delay")))
        elif et=="schedule.flagged":
            cands.append((et,ev["id"],pl.get("reason"),pl.get("source_event_id"),pl.get("severity")))
        elif et=="status.reported":
            summary=(pl.get("summary","") or "").lower()
            if any(kw in summary for kw in SHORT_KW):
                cands.append((et,ev["id"],pl.get("summary"),None,None))

    print(f"  notify.sent ids={sorted(sent_ids)} tuples={sorted([str(t) for t in sent_tuples])}")
    print(f"  notify.failed ids={sorted(failed_ids)} tuples={sorted([str(t) for t in failed_tuples])}")
    print(f"  candidate signal events: {len(cands)}")
    for c in cands:
        print(f"    {c}")

print("\nDONE")
