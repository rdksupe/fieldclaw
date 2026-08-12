"""API-key or dashboard-session auth + optional Telegram actor role checks."""

from __future__ import annotations

from fastapi import Cookie, Depends, Header, HTTPException, Query, status
from sqlalchemy.orm import Session

from fieldclaw_api.config import settings
from fieldclaw_api.db import get_db
from fieldclaw_api.models import Person, Project
from fieldclaw_api.services import ui_auth


def require_api_key(
    x_api_key: str | None = Header(default=None),
    api_key: str | None = Query(default=None),
    fc_session: str | None = Cookie(default=None),
    db: Session = Depends(get_db),
) -> str:
    """Machines present the API key; browsers present a login cookie."""
    key = (x_api_key or api_key or "").strip()
    expected = (settings.fieldclaw_api_key or "").strip()
    if expected and key == expected:
        return key
    if ui_auth.get_session(db, fc_session):
        return "session"
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Sign in to the dashboard, or send a valid X-API-Key",
    )


# Back-compat alias
require_auth = require_api_key


def get_project_or_404(
    project_id: str,
    db: Session = Depends(get_db),
    _key: str = Depends(require_api_key),
) -> Project:
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "project not found")
    return project


# Back-compat alias used by older Depends(project_for_tenant)
project_for_tenant = get_project_or_404


def require_actor(
    project_id: str,
    roles: set[str],
    *,
    required: bool,
    x_actor_telegram: str | None,
    db: Session,
) -> Person | None:
    """Resolve X-Actor-Telegram against project people.

    When required=True, missing/unbound/wrong-role → 403.
    When required=False (cron/system), missing header is allowed.
    """
    tid = (x_actor_telegram or "").strip()
    if not tid:
        if required:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="X-Actor-Telegram required for this action",
            )
        return None
    person = (
        db.query(Person)
        .filter(Person.project_id == project_id, Person.telegram_id == tid)
        .first()
    )
    if not person or person.role not in roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"actor not authorized (need role in {sorted(roles)})",
        )
    return person


def actor_super(
    project_id: str,
    x_actor_telegram: str | None = Header(default=None, alias="X-Actor-Telegram"),
    db: Session = Depends(get_db),
) -> Person:
    person = require_actor(
        project_id,
        {"superintendent"},
        required=True,
        x_actor_telegram=x_actor_telegram,
        db=db,
    )
    assert person is not None
    return person


def actor_crew_optional(
    project_id: str,
    x_actor_telegram: str | None = Header(default=None, alias="X-Actor-Telegram"),
    db: Session = Depends(get_db),
) -> Person | None:
    """Foreman or superintendent when header present; cron may omit."""
    return require_actor(
        project_id,
        {"foreman", "superintendent"},
        required=False,
        x_actor_telegram=x_actor_telegram,
        db=db,
    )
