#!/usr/bin/env python3
"""Hermes-facing FieldClaw sim control — HTTP only (no FieldClaw internals).

Usage:
  export FIELDCLAW_BASE_URL=http://127.0.0.1:8000
  export FIELDCLAW_API_KEY=dev-key-change-me
  export FIELDCLAW_PROJECT_ID=<uuid from seed>

  python sim_ctl.py status
  python sim_ctl.py play [--speed 12]
  python sim_ctl.py pause
  python sim_ctl.py seek --cursor 0
  python sim_ctl.py reset
  python sim_ctl.py watch   # poll until finished; print new event counts
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

SCENARIO = os.environ.get("FIELDCLAW_SIM_SCENARIO", "kaggle_site")


def _env(name: str, default: str | None = None) -> str:
    v = os.environ.get(name, default)
    if not v:
        raise SystemExit(f"missing env {name}")
    return v


def _req(method: str, path: str, body: dict | None = None) -> dict:
    base = _env("FIELDCLAW_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
    key = _env("FIELDCLAW_API_KEY", "dev-key-change-me")
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(
        f"{base}{path}",
        data=data,
        method=method,
        headers={
            "X-API-Key": key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        err = e.read().decode()
        raise SystemExit(f"HTTP {e.code}: {err}") from e


def project_id() -> str:
    return _env("FIELDCLAW_PROJECT_ID")


def cmd_status(_: argparse.Namespace) -> int:
    pid = project_id()
    q = urllib.parse.urlencode({"project_id": pid})
    out = _req("GET", f"/api/sim/{SCENARIO}?{q}")
    print(json.dumps(out, indent=2))
    return 0


def cmd_play(args: argparse.Namespace) -> int:
    pid = project_id()
    q = urllib.parse.urlencode({"project_id": pid, "speed": args.speed})
    out = _req("POST", f"/api/sim/{SCENARIO}/play?{q}")
    print(json.dumps(out, indent=2))
    return 0


def cmd_pause(_: argparse.Namespace) -> int:
    pid = project_id()
    q = urllib.parse.urlencode({"project_id": pid})
    out = _req("POST", f"/api/sim/{SCENARIO}/pause?{q}")
    print(json.dumps(out, indent=2))
    return 0


def cmd_seek(args: argparse.Namespace) -> int:
    pid = project_id()
    q = urllib.parse.urlencode({"project_id": pid})
    out = _req(
        "POST",
        f"/api/sim/{SCENARIO}/seek?{q}",
        {"cursor": args.cursor, "speed": args.speed},
    )
    print(json.dumps(out, indent=2))
    return 0


def cmd_reset(_: argparse.Namespace) -> int:
    pid = project_id()
    q = urllib.parse.urlencode({"project_id": pid})
    out = _req("POST", f"/api/sim/{SCENARIO}/reset?{q}")
    print(json.dumps(out, indent=2))
    return 0


def cmd_watch(args: argparse.Namespace) -> int:
    """Poll sim meta + event count until finished/paused (for Hermes tool loops)."""
    pid = project_id()
    q_meta = urllib.parse.urlencode({"project_id": pid})
    q_ev = urllib.parse.urlencode({"source": f"sim.{SCENARIO}"})
    last = -1
    deadline = time.time() + args.timeout
    while time.time() < deadline:
        meta = _req("GET", f"/api/sim/{SCENARIO}?{q_meta}")
        ev = _req("GET", f"/api/projects/{pid}/events?{q_ev}")
        n = len(ev) if isinstance(ev, list) else 0
        if n != last:
            print(
                json.dumps(
                    {
                        "status": meta.get("status"),
                        "cursor": meta.get("cursor"),
                        "total": meta.get("total"),
                        "events": n,
                    }
                ),
                flush=True,
            )
            last = n
        if meta.get("status") in ("finished", "paused", "idle") and meta.get("cursor", 0) > 0:
            if meta.get("status") == "finished" or (
                meta.get("status") == "paused" and n > 0 and args.stop_on_pause
            ):
                break
        if meta.get("status") == "finished":
            break
        time.sleep(args.interval)
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="FieldClaw sim control for Hermes")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("status").set_defaults(func=cmd_status)

    play = sub.add_parser("play")
    play.add_argument("--speed", type=float, default=12.0)
    play.set_defaults(func=cmd_play)

    sub.add_parser("pause").set_defaults(func=cmd_pause)

    seek = sub.add_parser("seek")
    seek.add_argument("--cursor", type=int, default=0)
    seek.add_argument("--speed", type=float, default=12.0)
    seek.set_defaults(func=cmd_seek)

    sub.add_parser("reset").set_defaults(func=cmd_reset)

    watch = sub.add_parser("watch")
    watch.add_argument("--interval", type=float, default=1.0)
    watch.add_argument("--timeout", type=float, default=120.0)
    watch.add_argument("--stop-on-pause", action="store_true")
    watch.set_defaults(func=cmd_watch)

    args = p.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
