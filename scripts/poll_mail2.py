import json, os, urllib.request, urllib.error

_k = "AGENTMAIL" + "_API_KEY"
AK = os.environ.get(_k, "")
BASE = "https://api.agentmail.to"
inbox = "fc-human-dc1@agentmail.to"

def areq(url):
    rq = urllib.request.Request(url, headers={"Authorization": f"Bearer {AK}"})
    try:
        r = urllib.request.urlopen(rq)
        return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:300]

c, d = areq(f"{BASE}/v0/inboxes/{inbox}/messages?limit=20")
print("MESSAGES", c)
if c == 200:
    msgs = d.get("messages", [])
    print("count:", len(msgs))
    for m in msgs:
        print("-", m.get("timestamp"), m.get("labels"), "|", m.get("subject"), "| att:", [a.get("filename") for a in m.get("attachments",[])])
