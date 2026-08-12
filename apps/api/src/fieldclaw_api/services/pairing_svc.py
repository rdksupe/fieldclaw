"""Telegram DM pairing via Hermes PairingStore."""

from __future__ import annotations

import json
import os
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


def _pairing_store():
    os.environ["HERMES_HOME"] = str(settings.hermes_home)
    hermes_root = Path("/home/rdksupe/building_shit/hermes-agent")
    if hermes_root.is_dir() and str(hermes_root) not in sys.path:
        sys.path.insert(0, str(hermes_root))
    from gateway.pairing import PairingStore  # type: ignore

    _repair_store_files()
    return PairingStore()


def list_pairing(platform: str | None = "telegram") -> dict:
    store = _pairing_store()
    return {
        "pending": store.list_pending(platform),
        "approved": store.list_approved(platform),
        "bot_username": settings.telegram_bot_username,
        "instructions": (
            f"1. Foreman opens Telegram and DMs @{settings.telegram_bot_username}\n"
            "2. Bot replies with an 8-character pairing code\n"
            "3. Paste that code below and Approve → bind as foreman"
        ),
    }


def approve_code(platform: str, code: str) -> dict:
    platform = (platform or "telegram").lower().strip()
    code = (code or "").upper().strip()
    if not platform or not code:
        raise ValueError("platform and code required")
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
