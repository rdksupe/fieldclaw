"""Password gate and browser sessions for the FieldClaw dashboard.

The API key stays the machine credential (Hermes, cron, curl). Browsers get a
session cookie instead so the shared key never has to live in page JavaScript.
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from fieldclaw_api.config import settings
from fieldclaw_api.models import UiSession

COOKIE_NAME = "fc_session"
SESSION_TTL = timedelta(days=30)

_WORDS = ("claw", "site", "crew", "zone", "yard", "beam", "deck", "grid")


def _generate() -> str:
    return f"{secrets.choice(_WORDS)}-{secrets.token_hex(2)}-{secrets.token_hex(2)}"


def password_path():
    return settings.fieldclaw_db_path.parent / "ui_password.txt"


def get_or_create_password() -> str:
    """Read the dashboard password, generating it on first run.

    Deleting the file rotates the password on the next start.
    """
    path = password_path()
    if path.exists():
        existing = path.read_text(encoding="utf-8").strip()
        if existing:
            return existing
    password = _generate()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(password + "\n", encoding="utf-8")
    path.chmod(0o600)
    return password


def check_password(candidate: str) -> bool:
    return secrets.compare_digest((candidate or "").strip(), get_or_create_password())


def create_session(db: Session, project_id: str | None = None) -> UiSession:
    session = UiSession(token=secrets.token_urlsafe(32), project_id=project_id)
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def get_session(db: Session, token: str | None) -> UiSession | None:
    if not token:
        return None
    session = db.get(UiSession, token)
    if not session:
        return None
    last_seen = session.last_seen_at
    if last_seen is not None and last_seen.tzinfo is None:
        last_seen = last_seen.replace(tzinfo=UTC)
    if last_seen is not None and datetime.now(UTC) - last_seen > SESSION_TTL:
        db.delete(session)
        db.commit()
        return None
    return session


def touch(db: Session, session: UiSession) -> None:
    session.last_seen_at = datetime.now(UTC)
    db.commit()


def delete_session(db: Session, token: str | None) -> None:
    session = db.get(UiSession, token) if token else None
    if session:
        db.delete(session)
        db.commit()
