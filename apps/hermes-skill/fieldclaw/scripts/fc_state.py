#!/usr/bin/env python3
"""Print FieldClaw project state: mail threads, people, events, zones."""
import os, urllib.request, json

BASE = os.environ.get('FIELDCLAW_BASE_URL', 'http://127.0.0.1:8000')
KEY = os.environ.get('FIELDCLAW_API_KEY', '')
P = os.environ.get('FIELDCLAW_PROJECT_ID', '2d32661e-cf1d-422f-9f46-461417af3e28')

def fc(method, path, body=None):
    url = f"{BASE}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header('X-API-Key', KEY)
    if data:
        req.add_header('Content-Type', 'application/json')
    try:
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return {'HTTPError': e.code, 'body': e.read().decode()[:500]}

print("=== mail/threads ===")
print(json.dumps(fc('GET', f"/api/projects/{P}/mail/threads"), indent=2)[:2000])
print("=== people ===")
print(json.dumps(fc('GET', f"/api/projects/{P}/people"), indent=2))
print("=== zones ===")
print(json.dumps(fc('GET', f"/api/projects/{P}/zones"), indent=2))
print("=== events count ===")
ev = fc('GET', f"/api/projects/{P}/events")
print(len(ev) if isinstance(ev, list) else ev)
print("=== tasks ===")
print(json.dumps(fc('GET', f"/api/projects/{P}/tasks"), indent=2))
