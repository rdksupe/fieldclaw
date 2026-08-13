#!/usr/bin/env python3
"""Pull still frames from all site cameras to local media."""
import os, urllib.request, json, time

BASE = os.environ.get('FIELDCLAW_BASE_URL', 'http://127.0.0.1:8000')
KEY = os.environ.get('FIELDCLAW_API_KEY', '')
P = os.environ.get('FIELDCLAW_PROJECT_ID', '2d32661e-cf1d-422f-9f46-461417af3e28')
OUT = os.path.join('/home/rdksupe/building_shit/buildsync/kb/projects', P, 'wiki/media')

os.makedirs(OUT, exist_ok=True)

req = urllib.request.Request(f"{BASE}/api/projects/{P}/cameras")
req.add_header('X-API-Key', KEY)
cams = json.load(urllib.request.urlopen(req))['cameras']

ts = time.strftime('%Y%m%d-%H%M%S')
saved = []
for c in cams:
    still_url = f"{BASE}{c['still_url']}"
    req = urllib.request.Request(still_url)
    req.add_header('X-API-Key', KEY)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            blob = r.read()
            ctype = r.headers.get('Content-Type', 'image/jpeg')
            ext = 'jpg' if 'jpeg' in ctype else ('png' if 'png' in ctype else 'bin')
            label = c['label'].replace('(', '').replace(')', '').replace(' ', '_').replace('(H)', 'H')
            fname = f"{ts}_{P[:8]}_{label}.{ext}"
            path = os.path.join(OUT, fname)
            with open(path, 'wb') as f:
                f.write(blob)
            saved.append((label, ctype, len(blob), path))
    except Exception as e:
        print(f"[{c['label']}] ERROR: {e}")

for label, ctype, size, path in saved:
    print(f"{label}: {ctype} {size}B -> {path}")
print(f"\n{'ERROR' if not saved else 'OK'} — saved {len(saved)} stills to {OUT}")
