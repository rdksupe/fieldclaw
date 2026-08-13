#!/usr/bin/env python3
"""Verify zones + super-queue after sitemap import."""
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

print("=== ZONES ===")
zones = fc('GET', f"/api/projects/{P}/zones")
if isinstance(zones, list):
    print(f"total zones: {len(zones)}")
    for z in zones:
        print(f"  - {z.get('label')} | id={z.get('id')[:8]} | polygon={'yes' if z.get('polygon') else 'no'} | status={z.get('status')} | pct={z.get('progress_pct')}")
else:
    print(zones)

print("\n=== SUPER QUEUE ===")
print(json.dumps(fc('GET', f"/api/projects/{P}/super-queue"), indent=2)[:2000])
