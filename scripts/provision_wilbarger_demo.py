#!/usr/bin/env python3
"""Provision Wilbarger demo project: reuse inbox, pair super, import zones, UI widgets.

Usage:
  FIELDCLAW_BASE_URL=http://127.0.0.1:8000 \\
  FIELDCLAW_API_KEY=dev-key-change-me \\
  apps/api/.venv/bin/python scripts/provision_wilbarger_demo.py \\
    --inbox fc-my-site8506@agentmail.to \\
    --telegram-id 6009530821
"""

from __future__ import annotations

import argparse
import json
import os
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
GEOJSON = REPO / "kb" / "samples" / "sitemaps" / "wilbarger-rwwtf-zones.geojson"


def req(method: str, url: str, body=None, key: str = ""):
    data = json.dumps(body).encode() if body is not None else None
    headers = {"X-API-Key": key, "Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    r = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(r, timeout=120) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            payload = json.loads(raw)
        except Exception:
            payload = {"detail": raw}
        raise SystemExit(f"{method} {url} -> {e.code} {payload}") from e


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=os.environ.get("FIELDCLAW_BASE_URL", "http://127.0.0.1:8000"))
    ap.add_argument("--key", default=os.environ.get("FIELDCLAW_API_KEY", "dev-key-change-me"))
    ap.add_argument("--name", default="Wilbarger RWWTF")
    ap.add_argument("--inbox", default="fc-my-site8506@agentmail.to")
    ap.add_argument("--telegram-id", default=os.environ.get("TELEGRAM_SUPER_CHAT_ID", "6009530821"))
    ap.add_argument("--super-name", default="Rishi")
    args = ap.parse_args()
    base, key = args.base.rstrip("/"), args.key

    code, created = req(
        "POST",
        f"{base}/api/projects",
        {
            "name": args.name,
            "provision_inbox": False,
            "inbox_email": args.inbox,
            "with_demo_zones": False,
        },
        key,
    )
    pid = created["project_id"]
    print("project", pid, created.get("inbox_email"))

    code, admin = req(
        "POST",
        f"{base}/api/projects/{pid}/admin/register",
        {"name": args.super_name, "telegram_id": args.telegram_id},
        key,
    )
    print("admin", admin.get("id"), "tg", admin.get("telegram_id"))

    # Ensure superintendent row has telegram (admin/register may create separate person)
    code, people = req("GET", f"{base}/api/projects/{pid}/people", None, key)
    for p in people:
        if p.get("role") == "superintendent" and not p.get("telegram_id"):
            req(
                "PATCH",
                f"{base}/api/projects/{pid}/people/{p['id']}",
                {"telegram_id": args.telegram_id},
                key,
            )
            print("patched superintendent telegram", p["id"])

    gj = json.loads(GEOJSON.read_text(encoding="utf-8"))
    code, sm = req(
        "POST",
        f"{base}/api/projects/{pid}/sitemap",
        {"geojson": gj, "replace": True, "source_name": GEOJSON.name},
        key,
    )
    print("zones", sm.get("count"), [z["label"] for z in sm.get("zones", [])])

    widgets = [
        {
            "type": "legend",
            "items": [z["label"] for z in sm.get("zones", [])[:6]],
        },
        {
            "type": "callout",
            "zone": "Aeration Basins",
            "text": "Wilbarger Phase 1 — GMP2 BOP packages active; OxBlue cams on site.",
        },
        {"type": "stat", "label": "zones mapped", "value": str(sm.get("count") or 0)},
        {"type": "stat", "label": "inbox", "value": (args.inbox.split("@")[0])},
    ]
    code, ui = req(
        "PUT",
        f"{base}/api/projects/{pid}/ui/widgets",
        {"replace": True, "widgets": widgets},
        key,
    )
    print("widgets", len(ui.get("widgets") or []))
    print(
        json.dumps(
            {
                "project_id": pid,
                "inbox_email": args.inbox,
                "open": f"{base}/? hint set localStorage FIELDCLAW_PROJECT_ID={pid}",
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
