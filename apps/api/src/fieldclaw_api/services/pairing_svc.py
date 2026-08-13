"""Telegram DM pairing via Hermes PairingStore."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from fieldclaw_api.config import settings


def _repair_store_files() -> None:
    """PairingStore keys its state by id and calls .items() on it, so a file
    holding a JSON list raises AttributeError on every read. Reset those to {}.
    """
    pairing_dir = Path(settings.hermes_home) / "pairing"
    if not pairing_dir.is_dir():
        return
    for path in pairing_dir.glob("*.json"):
        try:
            if not isinstance(json.loads(path.read_text(encoding="utf-8")), dict):
                path.write_text("{}", encoding="utf-8")
        except (json.JSONDecodeError, OSError):
            continue


def _hermes_python_roots() -> list[Path]:
    return [
        Path("/opt/hermes-agent"),
        Path("/home/rdksupe/building_shit/hermes-agent"),
        Path.home() / "building_shit" / "hermes-agent",
    ]


def _ensure_hermes_on_path() -> None:
    for hermes_root in _hermes_python_roots():
        if hermes_root.is_dir() and str(hermes_root) not in sys.path:
            sys.path.insert(0, str(hermes_root))
            return


def _remote_ssh() -> str | None:
    """When API and Hermes are on different hosts (OCI), pair via SSH."""
    host = (os.environ.get("FIELDCLAW_HERMES_SSH") or "").strip()
    return host or None


def _ssh_run(remote_cmd: str) -> subprocess.CompletedProcess[str]:
    host = _remote_ssh()
    assert host
    return subprocess.run(
        ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8", host, remote_cmd],
        capture_output=True,
        text=True,
        check=False,
    )


def _pairing_store():
    os.environ["HERMES_HOME"] = str(settings.hermes_home)
    _ensure_hermes_on_path()
    from gateway.pairing import PairingStore  # type: ignore

    _repair_store_files()
    return PairingStore()


def list_pairing(platform: str | None = "telegram") -> dict:
    platform = (platform or "telegram").lower().strip()
    if _remote_ssh():
        pending_path = f"{settings.hermes_home}/pairing/{platform}-pending.json"
        approved_path = f"{settings.hermes_home}/pairing/{platform}-approved.json"
        pending_raw = _ssh_run(f"cat {pending_path} 2>/dev/null || echo '{{}}'").stdout
        approved_raw = _ssh_run(f"cat {approved_path} 2>/dev/null || echo '{{}}'").stdout
        try:
            pending = json.loads(pending_raw or "{}")
        except json.JSONDecodeError:
            pending = {}
        try:
            approved = json.loads(approved_raw or "{}")
        except json.JSONDecodeError:
            approved = {}
        # PairingStore.list_pending returns a list of dicts; normalize dict→list
        if isinstance(pending, dict):
            pending_list = [
                {"user_id": uid, **(val if isinstance(val, dict) else {"raw": val})}
                for uid, val in pending.items()
            ]
        else:
            pending_list = pending if isinstance(pending, list) else []
        if isinstance(approved, dict):
            approved_list = [
                {"user_id": uid, **(val if isinstance(val, dict) else {"raw": val})}
                for uid, val in approved.items()
            ]
        else:
            approved_list = approved if isinstance(approved, list) else []
    else:
        store = _pairing_store()
        pending_list = store.list_pending(platform)
        approved_list = store.list_approved(platform)

    return {
        "pending": pending_list,
        "approved": approved_list,
        "bot_username": settings.telegram_foreman_bot_username,
        "admin_bot_username": settings.telegram_bot_username,
        "instructions": (
            f"1. Foreman opens Telegram and DMs @{settings.telegram_foreman_bot_username}\n"
            f"   (not @{settings.telegram_bot_username} — that is the superintendent bot)\n"
            "2. Bot replies with an 8-character pairing code\n"
            "3. Paste that code below and Approve → bind as foreman"
        ),
    }


def approve_code(platform: str, code: str) -> dict:
    platform = (platform or "telegram").lower().strip()
    code = (code or "").upper().strip()
    if not platform or not code:
        raise ValueError("platform and code required")

    if _remote_ssh():
        # Prefer supervisor CLI first (admin codes); foreman CLI for field codes.
        for cli, home in (
            ("hermes-fieldclaw", "$HOME/.hermes-fieldclaw"),
            ("hermes-fc-foreman", "$HOME/.hermes-fc-foreman"),
        ):
            proc = _ssh_run(
                f"PATH=$HOME/.local/bin:$PATH {cli} pairing approve {platform} {code}"
            )
            out = ((proc.stdout or "") + (proc.stderr or "")).strip()
            if proc.returncode != 0:
                continue
            approved_path = f"{home}/pairing/{platform}-approved.json"
            raw = _ssh_run(f"cat {approved_path} 2>/dev/null || echo '{{}}'").stdout
            try:
                approved = json.loads(raw or "{}")
            except json.JSONDecodeError:
                approved = {}
            user = None
            if isinstance(approved, dict) and approved:
                uid, meta = next(reversed(list(approved.items())))
                user = {"user_id": uid, **(meta if isinstance(meta, dict) else {})}
            return {"ok": True, "user": user or {"user_id": None}, "via": cli, "raw": out[-500:]}
        raise RuntimeError(
            f"Code '{code}' not found or expired for platform '{platform}' "
            f"(tried supervisor + foreman CLIs over SSH)"
        )

    store = _pairing_store()
    if store._is_locked_out(platform):
        raise RuntimeError(
            f"Platform '{platform}' is locked out after failed approvals"
        )
    result = store.approve_code(platform, code)
    if not result:
        raise RuntimeError(
            f"Code '{code}' not found or expired for platform '{platform}'"
        )
    return {"ok": True, "user": result}
