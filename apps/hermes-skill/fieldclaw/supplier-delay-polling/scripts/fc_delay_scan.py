#!/usr/bin/env python3
"""FieldClaw supplier-delay READ-ONLY scan probe (cron-safe).

Complements scripts/fc_supplier_poll.py (which AUTOMATES escalation). This probe
does NOT POST anything. It lists every candidate signal per project and surfaces
ALL the dedup handles + delay-intent flags so a cron analyst can hand-judge a
signal (dedup vs escalate) before committing to a notify.sent — matching the
honesty discipline in fieldclaw-notify-delivery-discipline.

Why this exists:
- The automation script dedups only on the top-level (po_id, task_id, zone_id)
  tuple and does NOT print source_event_id / trigger_event_id / super_queue_id /
  delivered / has_delay / intent, which are the second-third dedup handles and the
  delay-intent discriminators described in fieldclaw-cron-notify-dedup.
- This probe prints those fields compactly so a SILENT-vs-escalate call can be made
  from real API evidence, not a prior run's narrative.

Usage (run from terminal under cron; resolve must be HTTP-only per cron spec):
    python3 scripts/fc_delay_scan.py
- Reads FIELDCLAW_BASE_URL / FIELDCLAW_API_KEY from env (defaults shown below).
- Iterates ALL projects (env FIELDCLAW_PROJECT_ID may be stale/empty).
- Prints candidate lines for schedule.flagged / email.inbound / email.parsed /
  status.reported (shortage) / notify.sent / notify.failed / super.replied.
- Never mutates state; safe to run repeatedly.
"""
import json
import os
import urllib.request

base = os.environ.get("FIELDCLAW_BASE_URL", "http://127.0.0.1:8000")
key = os.environ.get("FIELDCLAW_API_KEY", "dev-key-change-me")

# Signal event types worth a look (covers super-queue AND typed history).
WATCH = {
    "schedule.flagged", "email.inbound", "email.parsed", "status.reported",
    "shortage.reported", "safety.reported", "quality.reported",
    "notify.sent", "notify.failed", "super.replied",
}
# Delay keywords (email-based signals) + shortage keywords (status.reported).
DELAY_KW = ['eta', 'delay', 'rebar', 'delivery', 'po-', 'ship', 'truck',
            'supplier', 'backorder', 'shortage', 'lead time', 'reschedule']
SHORTAGE_KW = ['waiting on', 'need', 'short', 'out of', 'missing', 'ran out',
               'shortage', 'bolts', 'rebar', 'concrete']


def api(path):
    req = urllib.request.Request(f"{base}{path}", headers={"X-API-Key": key})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode())


def flag(p):
    """Return a compact delay-intent tag for an event payload, or '' if none."""
    if not p:
        return "EMPTY_PAYLOAD"
    intent = (p.get("intent") or "").lower()
    if p.get("has_delay") is True or 'delay' in intent or 'eta' in intent:
        return "DELAY"
    if any(w in (intent + ' ' + (p.get("summary") or '').lower()) for w in DELAY_KW):
        return "KW?"
    return "no-delay"


def main():
    projects = api("/api/projects")
    print("PROJECTS:", json.dumps(
        [{"id": p["id"], "name": p["name"], "inbox": p.get("inbox_email")}
         for p in projects]))
    for proj in projects:
        pid = proj["id"]
        print(f"\n=== PROJECT {proj['name']} ({pid}) ===")
        try:
            events = api(f"/api/projects/{pid}/events?limit=100")
        except Exception as e:
            print(f"  events error: {e}")
            events = []
        print(f"  events count: {len(events)}")
        for ev in events:
            t = ev.get("type")
            if t not in WATCH:
                continue
            p = ev.get("payload") or {}
            summ = (p.get("summary") or p.get("subject") or p.get("reason")
                    or "")[:110]
            line = (f"  [{t}] id={ev.get('id')} created={ev.get('created_at')} "
                    f"po={ev.get('po_id')} task={ev.get('task_id')} "
                    f"zone={ev.get('zone_id')} {flag(p)}")
            print(line)
            print(f"      src={p.get('source_event_id')} "
                  f"trig={p.get('trigger_event_id')} "
                  f"sq={p.get('super_queue_id')} "
                  f"delivered={p.get('delivered')} has_delay={p.get('has_delay')} "
                  f"intent={p.get('intent')}")
            if summ:
                print(f"      summ={summ}")
        # Super-queue too — shortage signals can surface here as schedule.flagged
        # even when no typed shortage.* event exists.
        try:
            sq = api(f"/api/projects/{pid}/super-queue")
        except Exception as e:
            print(f"  super-queue error: {e}")
            sq = []
        print(f"  super-queue count: {len(sq)}")
        for item in sq:
            print("   SQ ", json.dumps(item)[:300])


if __name__ == "__main__":
    main()
