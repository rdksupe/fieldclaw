#!/usr/bin/env python3
"""Inspect FieldClaw OpenAPI spec for sitemap/zones routes+schemas."""
import os, urllib.request, json

BASE = os.environ.get('FIELDCLAW_BASE_URL', 'http://127.0.0.1:8000')

req = urllib.request.Request(BASE + '/openapi.json')
try:
    with urllib.request.urlopen(req) as r:
        spec = json.load(r)
except Exception as e:
    print("ERR", e)
    raise SystemExit

targets = [p for p in spec['paths'] if any(k in p for k in ('zones', 'sitemap'))]
for p in sorted(targets):
    print("===", p)
    for m, op in spec['paths'][p].items():
        print(f"  {m.upper()}: {op.get('summary','')}")
        for name, sc in (op.get('requestBody') or {}).get('content', {}).items():
            print(f"    body[{name}]: {json.dumps(sc)[:400]}")
        # params
        for pp in op.get('parameters', []):
            print(f"    param: {pp.get('name')} in={pp.get('in')} required={pp.get('required')}")
