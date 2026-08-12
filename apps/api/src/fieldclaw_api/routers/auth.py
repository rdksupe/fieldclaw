"""Dashboard login and the server-side state the UI boots from.

Mounted outside the api-key dependency: login cannot be pre-authenticated, and
everything else here checks the session cookie directly.
"""

from __future__ import annotations

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from fieldclaw_api.db import get_db
from fieldclaw_api.models import Person, Project, UiSession
from fieldclaw_api.services import pairing_svc, ui_auth
from fieldclaw_api.services import projects as projects_svc

router = APIRouter(prefix="/api/auth", tags=["auth"])

PLACEHOLDER_ADMIN = "Superintendent"


class LoginIn(BaseModel):
    password: str


class SelectProjectIn(BaseModel):
    project_id: str


def _require_session(
    fc_session: str | None = Cookie(default=None),
    db: Session = Depends(get_db),
) -> UiSession:
    session = ui_auth.get_session(db, fc_session)
    if not session:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "not signed in")
    ui_auth.touch(db, session)
    return session


def _set_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        ui_auth.COOKIE_NAME,
        token,
        httponly=True,
        samesite="lax",
        max_age=int(ui_auth.SESSION_TTL.total_seconds()),
        path="/",
    )


def build_state(db: Session, session: UiSession | None) -> dict:
    """Everything the dashboard needs to decide what to show next."""
    if session is None:
        return {"authenticated": False, "next_step": "login"}

    projects = projects_svc.list_projects(db)
    project_id = session.project_id
    if project_id and not any(p.id == project_id for p in projects):
        project_id = None
    if not project_id and projects:
        project_id = projects[0].id
    if project_id != session.project_id:
        session.project_id = project_id
        db.commit()

    admin = None
    if project_id:
        admin = (
            db.query(Person)
            .filter(Person.project_id == project_id, Person.role == "superintendent")
            .first()
        )

    try:
        pairing = pairing_svc.list_pairing("telegram")
    except Exception as exc:  # Hermes may not be running; not fatal for the UI.
        pairing = {"pending": [], "approved": [], "error": str(exc)}

    # create_project seeds a superintendent row named "Superintendent" so role
    # lookups resolve; admin/register renames it. An untouched placeholder means
    # nobody has actually claimed the site yet.
    claimed = admin is not None and (
        admin.name != PLACEHOLDER_ADMIN or admin.telegram_id or admin.email
    )

    if not projects:
        next_step = "create_project"
    elif not claimed:
        next_step = "register_admin"
    elif not admin.telegram_id:
        next_step = "pair_telegram"
    else:
        next_step = "ready"

    return {
        "authenticated": True,
        "next_step": next_step,
        "project_id": project_id,
        "projects": [
            {
                "id": p.id,
                "name": p.name,
                "inbox_email": p.inbox_email,
                "kb_relpath": p.kb_relpath,
            }
            for p in projects
        ],
        "admin": (
            {
                "id": admin.id,
                "name": admin.name,
                "email": admin.email,
                "telegram_id": admin.telegram_id,
            }
            if admin
            else None
        ),
        "pairing": pairing,
    }


@router.post("/login")
def login(body: LoginIn, response: Response, db: Session = Depends(get_db)):
    if not ui_auth.check_password(body.password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "wrong password")
    session = ui_auth.create_session(db)
    _set_cookie(response, session.token)
    return build_state(db, session)


@router.post("/logout")
def logout(
    response: Response,
    fc_session: str | None = Cookie(default=None),
    db: Session = Depends(get_db),
):
    ui_auth.delete_session(db, fc_session)
    response.delete_cookie(ui_auth.COOKIE_NAME, path="/")
    return {"authenticated": False, "next_step": "login"}


@router.get("/state")
def state(fc_session: str | None = Cookie(default=None), db: Session = Depends(get_db)):
    session = ui_auth.get_session(db, fc_session)
    if session:
        ui_auth.touch(db, session)
    return build_state(db, session)


@router.post("/project")
def select_project(
    body: SelectProjectIn,
    session: UiSession = Depends(_require_session),
    db: Session = Depends(get_db),
):
    if not db.get(Project, body.project_id):
        raise HTTPException(404, "project not found")
    session.project_id = body.project_id
    db.commit()
    return build_state(db, session)
