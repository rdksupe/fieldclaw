#!/usr/bin/env python3
"""Import the Wilbarger site-logistics geojson into FieldClaw zones."""
import os, urllib.request, json

BASE = os.environ.get('FIELDCLAW_BASE_URL', 'http://127.0.0.1:8000')
KEY = os.environ.get('FIELDCLAW_API_KEY', '')
P = os.environ.get('FIELDCLAW_PROJECT_ID', '2d32661e-cf1d-422f-9f46-461417af3e28')
GEO = '/home/rdksupe/building_shit/buildsync/kb/samples/sitemaps/wilbarger-rwwtf-zones.geojson'

geojson = json.load(open(GEO))

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
        return {'HTTPError': e.code, 'body': e.read().decode()[:800]}

print("=== POST sitemap (replace) ===")
res = fc('POST', f"/api/projects/{P}/sitemap", {"geojson": geojson, "replace": True})
print(json.dumps(res, indent=2)[:2000])

print("\n=== GET zones ===")
zones = fc('GET', f"/api/projects/{P}/zones")
if isinstance(zones, list):
    for z in zones:
        props = z.get('properties', z)
        print(" -", props.get('name'), props.get('code'), "polygon:", bool(z.get('polygon')))
else:
    print(zones)
