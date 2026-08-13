#!/usr/bin/env python3
"""List site cameras for the current FieldClaw project."""
import os, urllib.request, json

BASE = os.environ.get('FIELDCLAW_BASE_URL', 'http://127.0.0.1:8000')
KEY = os.environ.get('FIELDCLAW_API_KEY', '')
P = os.environ.get('FIELDCLAW_PROJECT_ID', '2d32661e-cf1d-422f-9f46-461417af3e28')

def fc(method, path):
    req = urllib.request.Request(f"{BASE}{path}", method=method)
    req.add_header('X-API-Key', KEY)
    try:
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return {'HTTPError': e.code, 'body': e.read().decode()[:400]}

print("=== cameras ===")
print(json.dumps(fc('GET', f"/api/projects/{P}/cameras"), indent=2))
