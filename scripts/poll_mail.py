import json, os, urllib.request, urllib.error

_k = "AGENTMAIL" + "_API_KEY"
AK = os.environ.get(_k, "")
BASE = "https://api.agentmail.to"
APP = os.environ["FIELDCLAW_BASE_URL"]
KEY = os.environ["FIELDCLAW_API_KEY"]
PID = "81989611-f0f4-496c-a197-17a2220bea8b"

def areq(url):
    rq = urllib.request.Request(url, headers={"Authorization": f"Bearer {AK}"})
    try:
        r = urllib.request.urlopen(rq)
        return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:300]
    except Exception as e:
        return -1, str(e)

# 1. list inboxes
code, data = areq(f"{BASE}/v0/inboxes")
print("INBOXES", code)
if code == 200:
    for i in data.get("inboxes", []):
        print("  -", i.get("inbox_id"), "|", i.get("email"), "|", i.get("display_name"))

# 2. target the project's own inbox fc-human-dc1@agentmail.to
inbox = None
if code == 200:
    for i in data.get("inboxes", []):
        if i.get("inbox_id") == "fc-human-dc1@agentmail.to" or i.get("email") == "fc-human-dc1@agentmail.to":
            inbox = i.get("inbox_id")
print("TARGET", inbox)

# 3. processed thread_id set from FieldClaw events
def apreq(url):
    rq = urllib.request.Request(url, headers={"X-API-Key": KEY})
    try:
        r = urllib.request.urlopen(rq)
        return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:300]

def get_all_events(url):
    out = []
    while url:
        c, d = apreq(url)
        if c != 200:
            break
        items = d if isinstance(d, list) else d.get("items", [] if "items" in d else [])
        out.extend(items)
        url = None
    return d, out

c, d = apreq(f"{APP}/api/projects/{PID}/events")
evs = json.loads(d) if isinstance(d, str) else d
processed = set()
if c == 200:
    for e in evs:
        pl = e.get("payload", {})
        if e.get("type") in ("email.inbound", "email.parsed") and pl.get("thread_id"):
            processed.add(pl["thread_id"])
print("processed threads:", len(processed))

if inbox:
    # 4. threads
    code2, td = areq(f"{BASE}/v0/inboxes/{inbox}/threads")
    print("THREADS", code2)
    threads = td.get("threads", []) if code2 == 200 and isinstance(td, dict) else []
    print("thread count:", len(threads))
    for t in threads:
        tid = t.get("thread_id") or t.get("id")
        seen = tid in processed
        print(f"  - [{t.get('labels')}] tid={tid} seen={seen} subj={t.get('subject')} from={t.get('from')}")
