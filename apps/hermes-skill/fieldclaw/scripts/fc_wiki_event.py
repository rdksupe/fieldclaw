#!/usr/bin/env python3
"""Log wiki.updated for the /init scaffold + confirm wiki pages."""
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

ev = {
    "type": "wiki.updated",
    "payload": {
        "summary": "/init scaffold: created wiki taxonomy (ops, zones, people, sources, maps, pos, rfis, media, pageindex); imported 11 Wilbarger WWTF zones from sitemap rev A; refresh of wiki/index.md.",
        "details": "zones: ILS,HW,AB,BLR,RAS,UV,BIO,OPS,MNT,ELE,LAY"
    }
}
print("=== POST wiki.updated ===")
print(json.dumps(fc('POST', f"/api/projects/{P}/events", ev), indent=2)[:800])

print("\n=== GET wiki/pages ===")
pg = fc('GET', f"/api/projects/{P}/wiki/pages")
if isinstance(pg, list):
    print(f"{len(pg)} pages")
    for p in pg[:40]:
        print("  -", p if isinstance(p, str) else p.get('path', p.get('name', p)))
else:
    print(pg)
