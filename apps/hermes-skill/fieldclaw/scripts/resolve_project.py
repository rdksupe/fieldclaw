#!/usr/bin/env python3
"""Resolve the live FieldClaw project. Never trust a stale FIELDCLAW_PROJECT_ID alone.

Usage:
  python resolve_project.py                 # print JSON active project
  python resolve_project.py --id <uuid>     # validate / re-resolve if 404
  python resolve_project.py --inbox ADDR    # match by inbox_email
  python resolve_project.py --name SUBSTR   # match by name substring
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request


def _req(path: str) -> dict | list:
    base = os.environ.get("FIELDCLAW_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
    key = os.environ.get("FIELDCLAW_API_KEY", "dev-key-change-me")
    req = urllib.request.Request(
        f"{base}{path}",
        headers={"X-API-Key": key, "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def list_projects() -> list[dict]:
    data = _req("/api/projects")
    return data if isinstance(data, list) else []


def resolve(
    *,
    project_id: str | None = None,
    inbox: str | None = None,
    name: str | None = None,
) -> dict:
    projects = list_projects()
    if not projects:
        raise SystemExit("no projects in FieldClaw API — seed or create one")

    if project_id:
        for p in projects:
            if p["id"] == project_id:
                return p
        # stale id — fall through

    if inbox:
        inbox_l = inbox.lower().strip()
        for p in projects:
            if (p.get("inbox_email") or "").lower() == inbox_l:
                return p

    if name:
        needle = name.lower().strip()
        hits = [p for p in projects if needle in (p.get("name") or "").lower()]
        if len(hits) == 1:
            return hits[0]
        if len(hits) > 1:
            raise SystemExit(
                "ambiguous name; matches: "
                + ", ".join(f'{h["id"][:8]}={h["name"]}' for h in hits)
            )

    # env hint
    env_id = (os.environ.get("FIELDCLAW_PROJECT_ID") or "").strip()
    if env_id:
        for p in projects:
            if p["id"] == env_id:
                return p

    # default: prefer demo / kaya-meow, else newest
    for p in projects:
        if (p.get("inbox_email") or "").startswith("kaya-meow@"):
            return p
    return projects[0]


def kb_root(project: dict) -> str:
    rel = project.get("kb_relpath") or f"projects/{project['id']}"
    base = os.environ.get(
        "FIELDCLAW_KB_DIR",
        os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "kb"),
    )
    return os.path.realpath(os.path.join(base, rel) if not os.path.isabs(rel) else rel)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--id", default=None)
    ap.add_argument("--inbox", default=None)
    ap.add_argument("--name", default=None)
    ap.add_argument("--export-env", action="store_true", help="print export lines")
    args = ap.parse_args()
    try:
        p = resolve(project_id=args.id, inbox=args.inbox, name=args.name)
    except urllib.error.HTTPError as e:
        print(f"API error: {e}", file=sys.stderr)
        return 1
    out = {
        **p,
        "kb_abs": kb_root(p),
        "resolved_from_env_stale": bool(
            os.environ.get("FIELDCLAW_PROJECT_ID")
            and os.environ.get("FIELDCLAW_PROJECT_ID") != p["id"]
        ),
    }
    if args.export_env:
        print(f'export FIELDCLAW_PROJECT_ID="{p["id"]}"')
        print(f'export FIELDCLAW_KB_DIR="{kb_root(p)}"')
        if p.get("inbox_email"):
            print(f'# project inbox: {p["inbox_email"]}')
        return 0
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
