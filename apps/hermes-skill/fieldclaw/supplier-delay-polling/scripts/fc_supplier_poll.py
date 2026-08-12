#!/usr/bin/env python3
"""FieldClaw supplier-delay polling cron job.
Polls schedule.flagged and email.parsed/inbound events with supplier-delay intent.
Alerts superintendent, projects notify.sent, dedup against existing notifications.
"""
import json
import os
import urllib.error
import urllib.request

base = os.environ.get("FIELDCLAW_BASE_URL", "http://127.0.0.1:8000")
key = os.environ.get("FIELDCLAW_API_KEY", "")

DELAY_KEYWORDS = ['eta', 'delay', 'rebar', 'delivery', 'po-', 'ship', 'truck', 'supplier', 'backorder', 'shortage', 'lead time', 'reschedule']

def api_get(path):
    url = f"{base}{path}"
    req = urllib.request.Request(url, headers={"X-API-Key": key})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode())

def api_post(path, data):
    url = f"{base}{path}"
    body = json.dumps(data).encode()
    req = urllib.request.Request(url, data=body, headers={
        "X-API-Key": key,
        "Content-Type": "application/json"
    }, method="POST")
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode())

def api_patch(path, data):
    url = f"{base}{path}"
    body = json.dumps(data).encode()
    req = urllib.request.Request(url, data=body, headers={
        "X-API-Key": key,
        "Content-Type": "application/json"
    }, method="PATCH")
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode())

# Step 1: List all projects
try:
    projects = api_get("/api/projects")
except Exception as e:
    print(f"ERROR: Could not list projects: {e}")
    raise SystemExit(0) from e

if not projects:
    print("[SILENT]")
    raise SystemExit(0)

results = []

for proj in projects:
    pid = proj["id"]
    pname = proj.get("name", "Unknown")
    
    # Step 2: Fetch events for this project
    try:
        events = api_get(f"/api/projects/{pid}/events?limit=100")
    except Exception as e:
        results.append(f"⚠️ Project {pname} ({pid}): could not fetch events: {e}")
        continue

    if not events:
        continue

    # Step 3: Build dedup set from existing notify.sent events
    # Match on top-level fields (po_id, task_id, zone_id) — these are set by the API
    notified = set()
    for ev in events:
        if ev.get("type") == "notify.sent":
            notified.add((ev.get("po_id"),
                         ev.get("task_id"),
                         ev.get("zone_id")))

    # Step 4: Find schedule.flagged events (new ones not yet notified yet)
    # Skip events with empty payload — they're malformed and produce garbage notifications
    schedule_flagged = [ev for ev in events
                        if ev.get("type") == "schedule.flagged"
                        and ev.get("payload") and len(ev.get("payload", {})) > 0]
    
    # Step 5: Find email.inbound / email.parsed events with supplier-delay keywords
    # Skip events with empty payload
    delay_emails = []
    for ev in events:
        if ev.get("type") in ("email.inbound", "email.parsed"):
            p = ev.get("payload", {})
            if not p:
                continue  # skip empty-payload events
            subject = (p.get("subject", "") or "").lower()
            body_text = (p.get("body", "") or p.get("body_preview", "") or "").lower()
            combined = subject + " " + body_text
            if any(kw in combined for kw in DELAY_KEYWORDS):
                delay_emails.append(ev)

    # Step 6: Get people for this project (find superintendent)
    try:
        people = api_get(f"/api/projects/{pid}/people")
    except Exception:
        people = []
    
    super_contact = None
    for person in people:
        if person.get("role", "").lower() in ("superintendent", "super"):
            super_contact = person
            break
    
    # Step 7: Process schedule.flagged events that haven't been notified yet
    for ev in schedule_flagged:
        p = ev.get("payload", {})
        # Dedup on top-level fields (where notify.sent stores them)
        dedup_key = (ev.get("po_id"),
                     ev.get("task_id"),
                     ev.get("zone_id"))
        
        if dedup_key in notified:
            continue  # Already notified
        
        # New schedule.flagged — alert superintendent
        zone = p.get("zone", "Unknown zone")
        task = p.get("impact_task") or p.get("task", "Unknown task")
        po = p.get("po", p.get("po_id", "N/A"))
        reason = p.get("reason", "Schedule flag raised")
        new_eta = p.get("new_eta", "TBD")
        severity = p.get("severity", "high")
        material = p.get("material", "")
        thread_id = p.get("thread_id")
        
        # PATCH task to at-risk if we have a task_id
        task_id = p.get("task_id") or ev.get("task_id")
        if task_id:
            try:
                api_patch(f"/api/projects/{pid}/tasks/{task_id}", {"at_risk": True, "status": "in_progress"})
            except Exception as e:
                results.append(f"⚠️ Could not PATCH task {task_id} to at-risk: {e}")
        
        # POST notify.sent event
        notify_payload = {
            "type": "notify.sent",
            "zone_id": p.get("zone_id") or ev.get("zone_id"),
            "task_id": task_id,
            "po_id": p.get("po_id") or ev.get("po_id"),
            "source": "cron-supplier-delay",
            "payload": {
                "channel": "email+telegram",
                "recipient": f"{super_contact.get('name', 'Superintendent')}" if super_contact else "Superintendent",
                "subject": f"SCHEDULE FLAG: {po} — {zone} {task} at risk",
                "message": f"Schedule flag detected for {zone}.\nTask: {task}\nPO: {po}\nMaterial: {material}\nReason: {reason}\nNew ETA: {new_eta}\nSeverity: {severity}",
                "severity": severity,
                "trigger_event_id": ev.get("id")
            }
        }
        try:
            api_post(f"/api/projects/{pid}/events", notify_payload)
        except Exception as e:
            results.append(f"⚠️ Could not POST notify.sent for {po} {zone}: {e}")
        
        # Attempt email delivery via FieldClaw mail/send
        if super_contact and super_contact.get("email"):
            try:
                api_post(f"/api/projects/{pid}/mail/send", {
                    "to": super_contact["email"],
                    "subject": notify_payload["payload"]["subject"],
                    "body": notify_payload["payload"]["message"],
                    "thread_id": thread_id
                })
                delivery = "email sent"
            except urllib.error.HTTPError as e:
                body_err = e.read().decode() if hasattr(e, 'read') else str(e)
                delivery = f"email FAILED: {body_err}"
            except Exception as e:
                delivery = f"email FAILED: {e}"
        else:
            delivery = "no superintendent email on file"
        
        results.append(
            f"🔴 SCHEDULE FLAG — Project: {pname}\n"
            f"   Zone: {zone} | Task: {task}\n"
            f"   PO: {po} | Material: {material}\n"
            f"   Reason: {reason}\n"
            f"   New ETA: {new_eta} | Severity: {severity}\n"
            f"   Superintendent: {super_contact.get('name', 'N/A') if super_contact else 'N/A'}\n"
            f"   Delivery: {delivery}\n"
            f"   Task {task_id} patched to at-risk\n"
            f"   notify.sent projected to logbook"
        )
        
        notified.add(dedup_key)

    # Step 8: Process supplier-delay emails that aren't from schedule.flagged
    for ev in delay_emails:
        p = ev.get("payload", {})
        # Dedup on top-level fields
        dedup_key = (ev.get("po_id"),
                     ev.get("task_id"),
                     ev.get("zone_id"))
        
        if dedup_key in notified:
            continue
        
        subject = p.get("subject", "(no subject)")
        body = p.get("body", "")[:500]
        thread_id = p.get("thread_id")
        
        # Try to get thread details for structured data
        supplier_reply = body
        if thread_id:
            try:
                threads = api_get(f"/api/projects/{pid}/mail/threads")
                for t in threads:
                    if t.get("thread_id") == thread_id:
                        for msg in t.get("messages", []):
                            if msg.get("direction") == "inbound":
                                supplier_reply = msg.get("body", supplier_reply)
                                break
            except Exception:
                pass
        
        # POST notify.sent
        notify_payload = {
            "type": "notify.sent",
            "zone_id": p.get("zone_id") or ev.get("zone_id"),
            "task_id": p.get("task_id") or ev.get("task_id"),
            "po_id": p.get("po_id") or ev.get("po_id"),
            "source": "cron-supplier-delay",
            "payload": {
                "channel": "email+telegram",
                "recipient": f"{super_contact.get('name', 'Superintendent')}" if super_contact else "Superintendent",
                "subject": f"SUPPLIER DELAY SIGNAL: {subject}",
                "message": f"Supplier email with delay intent detected.\nSubject: {subject}\nReply excerpt: {supplier_reply[:300]}",
                "severity": "medium",
                "trigger_event_id": ev.get("id")
            }
        }
        try:
            api_post(f"/api/projects/{pid}/events", notify_payload)
        except Exception as e:
            results.append(f"⚠️ Could not POST notify.sent for email signal {subject}: {e}")
        
        # Attempt email delivery to superintendent
        delivery = "no superintendent email on file"
        if super_contact and super_contact.get("email"):
            try:
                api_post(f"/api/projects/{pid}/mail/send", {
                    "to": super_contact["email"],
                    "subject": notify_payload["payload"]["subject"],
                    "body": notify_payload["payload"]["message"],
                    "thread_id": thread_id
                })
                delivery = "email sent"
            except urllib.error.HTTPError as e:
                body_err = e.read().decode() if hasattr(e, 'read') else str(e)
                delivery = f"email FAILED: {body_err}"
            except Exception as e:
                delivery = f"email FAILED: {e}"
        
        results.append(
            f"📧 SUPPLIER DELAY EMAIL — Project: {pname}\n"
            f"   Subject: {subject}\n"
            f"   Reply excerpt: {supplier_reply[:200]}\n"
            f"   Thread: {thread_id or 'N/A'}\n"
            f"   Superintendent: {super_contact.get('name', 'N/A') if super_contact else 'N/A'}\n"
            f"   Delivery: {delivery}\n"
            f"   notify.sent projected to logbook"
        )
        
        notified.add(dedup_key)

# Step 9: Output or SILENT
if results:
    print("\n".join(results))
else:
    print("[SILENT]")
