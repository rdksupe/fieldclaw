#!/usr/bin/env python3
"""Print recent FieldClaw events."""
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

ev = fc('GET', f"/api/projects/{P}/events")
if isinstance(ev, list):
    ev.sort(key=lambda x: x.get('created_at',''))
    for e in ev[-15:]:
        print(f"[{e.get('created_at','?')}] {e.get('type')} | {e.get('payload',{}).get('summary','')}")
        print(f"    actor={e.get('actor_id')} zone={e.get('zone_id')}")
else:
    print(ev)
