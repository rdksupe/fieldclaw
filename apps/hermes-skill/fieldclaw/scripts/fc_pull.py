#!/usr/bin/env python3
"""Pull mail attachments, then check sitemap & zones."""
import os, urllib.request, json

BASE = os.environ.get('FIELDCLAW_BASE_URL', 'http://127.0.0.1:8000')
KEY = os.environ.get('FIELDCLAW_API_KEY', '')
P = os.environ.get('FIELDCLAW_PROJECT_ID', '2d32661e-cf1d-422f-9f46-461417af3e28')

def fc(method, path, body=None, raw=False):
    url = f"{BASE}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header('X-API-Key', KEY)
    if data:
        req.add_header('Content-Type', 'application/json')
    try:
        with urllib.request.urlopen(req) as r:
            b = r.read().decode()
            return b if raw else json.loads(b)
    except urllib.error.HTTPError as e:
        return {'HTTPError': e.code, 'body': e.read().decode()[:500]}

print("=== POST mail/pull-attachments ===")
print(json.dumps(fc('POST', f"/api/projects/{P}/mail/pull-attachments"), indent=2)[:2500])
print("=== GET sitemap ===")
print(json.dumps(fc('GET', f"/api/projects/{P}/sitemap"), indent=2)[:1500])
print("=== GET zones ===")
print(json.dumps(fc('GET', f"/api/projects/{P}/zones"), indent=2)[:2500])
