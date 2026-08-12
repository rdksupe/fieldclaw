#!/usr/bin/env python3
"""Blank-slate wipe: FieldClaw DB/wiki + Hermes mux/foreman sessions/pairing."""
from __future__ import annotations

import shutil
import subprocess
import time
from pathlib import Path

REPO = Path("/home/rdksupe/building_shit/buildsync")
H = Path("/home/rdksupe/.hermes-fieldclaw")
F = Path("/home/rdksupe/.hermes-fc-foreman")
LOG = Path("/tmp/fieldclaw_wipe.log")


def log(msg: str) -> None:
    line = msg + "\n"
    print(msg, flush=True)
    with LOG.open("a") as f:
        f.write(line)


def unlink(p: Path) -> None:
    try:
        p.unlink()
        log(f"unlinked {p}")
    except FileNotFoundError:
        log(f"missing {p}")
    except Exception as e:
        log(f"FAIL unlink {p}: {e}")


def rmtree(p: Path) -> None:
    if p.exists():
        shutil.rmtree(p)
        log(f"rmtree {p}")


def main() -> None:
    LOG.write_text("wipe start\n")
    for pat in ("uvicorn fieldclaw", "hermes gateway"):
        subprocess.run(["pkill", "-9", "-f", pat], check=False)
    subprocess.run(["fuser", "-k", "8000/tcp"], check=False, capture_output=True)
    time.sleep(1.5)

    for p in [
        REPO / "data/fieldclaw.db",
        REPO / "data/fieldclaw.db-wal",
        REPO / "data/fieldclaw.db-shm",
        REPO / "data/week_loop_state.json",
        REPO / "data/oxblue_poll_state.json",
    ]:
        unlink(p)

    for d in [REPO / "data/proofs", REPO / "kb/projects", REPO / "kb/tenants"]:
        rmtree(d)
        d.mkdir(parents=True, exist_ok=True)
        log(f"mkdir {d}")

    for p in [
        H / "state.db",
        H / "state.db-wal",
        H / "state.db-shm",
        H / "kanban.db",
        H / "kanban.db-wal",
        H / "kanban.db-shm",
        H / "kanban.db.dispatch.lock",
        H / "kanban.db.init.lock",
        H / "channel_directory.json",
        H / "mem0.json",
        H / "gateway.lock",
        H / "gateway.pid",
        H / "gateway_state.json",
        H / "processes.json",
        H / "cron/ticker_heartbeat",
        H / "cron/ticker_last_success",
    ]:
        unlink(p)

    rmtree(H / "sessions")
    (H / "sessions").mkdir(parents=True, exist_ok=True)
    (H / "sessions" / "sessions.json").write_text("{}\n")
    (H / "pairing").mkdir(parents=True, exist_ok=True)
    (H / "pairing" / "telegram-approved.json").write_text("[]\n")
    (H / "pairing" / "telegram-pending.json").write_text("[]\n")
    (H / "pairing" / "_rate_limits.json").write_text("{}\n")

    for name in ("memories", "audio_cache", "image_cache", "cache", "sandboxes", "cron/output"):
        d = H / name
        rmtree(d)
        d.mkdir(parents=True, exist_ok=True)

    if F.exists():
        rmtree(F / "sessions")
        (F / "sessions").mkdir(parents=True, exist_ok=True)
        (F / "sessions" / "sessions.json").write_text("{}\n")
        (F / "pairing").mkdir(parents=True, exist_ok=True)
        (F / "pairing" / "telegram-approved.json").write_text("[]\n")
        (F / "pairing" / "telegram-pending.json").write_text("[]\n")
        for p in [F / "state.db", F / "state.db-wal", F / "state.db-shm"]:
            unlink(p)

    log("--- verify ---")
    log(f"db_exists={ (REPO / 'data/fieldclaw.db').exists() }")
    log(f"projects={ list((REPO / 'kb/projects').iterdir()) }")
    log(f"approved={ (H / 'pairing' / 'telegram-approved.json').read_text().strip() }")
    log(f"sessions={ (H / 'sessions' / 'sessions.json').read_text().strip() }")
    log(f"state_exists={ (H / 'state.db').exists() }")
    log("DONE")


if __name__ == "__main__":
    main()
