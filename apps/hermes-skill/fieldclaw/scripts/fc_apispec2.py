#!/usr/bin/env python3
"""Dump SitemapImportIn + ZoneCreate schema, and re-test zones GET."""
import os, urllib.request, json

BASE = os.environ.get('FIELDCLAW_BASE_URL', 'http://127.0.0.1:8000')
KEY = os.environ.get('FIELDCLAW_API_KEY', '')
P = os.environ.get('FIELDCLAW_PROJECT_ID', '2d32661e-cf1d-422f-9f46-461417af3e28')

req = urllib.request.Request(BASE + '/openapi.json')
spec = json.load(urllib.request.urlopen(req))
for sname in ('SitemapImportIn', 'ZoneCreate'):
    print("===", sname, "===")
    print(json.dumps(spec['components']['schemas'].get(sname), indent=2))

# re-test zones GET
print("\n=== zones GET ===")
r = urllib.request.Request(f"{BASE}/api/projects/{P}/zones")
r.add_header('X-API-Key', KEY)
try:
    with urllib.request.urlopen(r) as resp:
        print("status", resp.status, "body:", resp.read().decode()[:800])
except urllib.error.HTTPError as e:
    print("HTTPError", e.code, e.read().decode()[:500])
