#!/usr/bin/env python3
"""Inject foreman-style field logs into FieldClaw for a live demo.

Cycles progress / shortage / safety / quality events with short pauses so the
dashboard log updates in real time while you watch.

Usage:
  FIELDCLAW_PROJECT_ID=<uuid> \\
  apps/api/.venv/bin/python scripts/demo_foreman_pulse.py --interval 2.5

Optional: --telegram-id to stamp X-Actor-Telegram (foreman person must exist).
"""

from __future__ import annotations

import argparse
import json
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone


PULSE = [
    {
        "type": "progress.reported",
        "payload": {
            "summary": "Headworks — mechanical screen install ~35%",
            "progress_pct": 35,
            "activity": "mech screen install",
            "zone_label": "Headworks",
        },
    },
    {
        "type": "progress.reported",
        "payload": {
            "summary": "Aeration basin wall pour complete Bay 1",
            "progress_pct": 42,
            "activity": "concrete walls",
            "zone_label": "Aeration Basins",
        },
    },
    {
        "type": "shortage.raised",
        "payload": {
            "summary": "Short 3 crates of 4\" DI fittings for yard piping",
            "material": "4in DI fittings",
            "qty": 3,
            "zone_label": "Laydown / Site Logistics",
        },
    },
    {
        "type": "safety.reported",
        "payload": {
            "summary": "Near-miss: unsecured trench plate at ILS excavation",
            "severity": "medium",
            "action": "barricade + plate secured",
            "zone_label": "Influent Lift Station",
        },
    },
    {
        "type": "quality.reported",
        "payload": {
            "summary": "UV channel embed locations verified against shop drawings",
            "result": "pass",
            "zone_label": "UV Disinfection",
        },
    },
    {
        "type": "progress.reported",
        "payload": {
            "summary": "Biosolids building — steel erection started",
            "progress_pct": 18,
            "activity": "steel erection",
            "zone_label": "Biosolids Handling",
        },
    },
    {
        "type": "schedule.flagged",
        "payload": {
            "summary": "Blower equipment ETA slipped 5 days — vendor notified",
            "has_delay": True,
            "days": 5,
            "zone_label": "Blower Facility",
        },
    },
    {
        "type": "progress.reported",
        "payload": {
            "summary": "Ops/lab — interior framing 60%",
            "progress_pct": 60,
            "activity": "framing",
            "zone_label": "Ops & Laboratory",
        },
    },
]


def req(method, url, body, key, telegram_id=None):
    data = json.dumps(body).encode() if body is not None else None
    headers = {"X-API-Key": key, "Content-Type": "application/json", "Accept": "application/json"}
    if telegram_id:
        headers["X-Actor-Telegram"] = str(telegram_id)
    r = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(r, timeout=60) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        raise SystemExit(f"{e.code} {e.read().decode()[:400]}") from e


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=os.environ.get("FIELDCLAW_BASE_URL", "http://127.0.0.1:8000"))
    ap.add_argument("--key", default=os.environ.get("FIELDCLAW_API_KEY", "dev-key-change-me"))
    ap.add_argument("--project-id", default=os.environ.get("FIELDCLAW_PROJECT_ID", ""))
    ap.add_argument("--interval", type=float, default=2.5)
    ap.add_argument("--loops", type=int, default=1, help="how many times to replay the pulse list")
    ap.add_argument("--telegram-id", default=os.environ.get("TELEGRAM_FOREMAN_CHAT_ID", ""))
    ap.add_argument("--source", default="foreman")
    args = ap.parse_args()
    if not args.project_id:
        raise SystemExit("Set --project-id or FIELDCLAW_PROJECT_ID")

    base = args.base.rstrip("/")
    zones = req("GET", f"{base}/api/projects/{args.project_id}/zones", None, args.key)
    by_label = {z["label"]: z["id"] for z in zones}
    print(f"zones={len(zones)} interval={args.interval}s")

    n = 0
    for _ in range(max(args.loops, 1)):
        for item in PULSE:
            payload = dict(item["payload"])
            payload["at"] = datetime.now(timezone.utc).isoformat()
            zid = by_label.get(payload.get("zone_label") or "")
            body = {
                "type": item["type"],
                "source": args.source,
                "zone_id": zid,
                "payload": payload,
            }
            ev = req(
                "POST",
                f"{base}/api/projects/{args.project_id}/events",
                body,
                args.key,
                telegram_id=args.telegram_id or None,
            )
            n += 1
            print(f"[{n}] {item['type']}  {payload.get('summary','')[:70]}")
            # bump zone % when progress
            if zid and item["type"] == "progress.reported" and "progress_pct" in payload:
                # best-effort: some APIs expose zone patch via events only — skip if none
                pass
            time.sleep(args.interval)
    print("done", n, "events")


if __name__ == "__main__":
    main()
