"""Create / list projects with isolated KB + AgentMail inbox."""

from __future__ import annotations

import json
import re

from sqlalchemy.orm import Session

from fieldclaw_api.config import settings
from fieldclaw_api.models import Person, Project, Task, Zone
from fieldclaw_api.services import agentmail_svc


def kb_root_for(project: Project):
    rel = project.kb_relpath or f"projects/{project.id}"
    root = settings.fieldclaw_kb_dir / rel
    (root / "raw").mkdir(parents=True, exist_ok=True)
    (root / "wiki").mkdir(parents=True, exist_ok=True)
    index = root / "wiki" / "index.md"
    if not index.exists():
        index.write_text(
            f"# {project.name} — Wiki Index\n\n"
            "Project-isolated wiki. Supervisor runs `/init` to create folders "
            "and load site context from scratch.\n\n",
            encoding="utf-8",
        )
    return root


def _username_from_name(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return f"fc-{s}"[:36] or "fc-project"


def create_project(
    db: Session,
    name: str,
    *,
    inbox_username: str | None = None,
    provision_inbox: bool = True,
    inbox_email: str | None = None,
    with_demo_zones: bool = False,
) -> dict:
    project = Project(name=name.strip() or "Untitled project")
    db.add(project)
    db.flush()
    project.kb_relpath = f"projects/{project.id}"

    if inbox_email:
        project.inbox_email = inbox_email
    elif provision_inbox:
        created = agentmail_svc.create_inbox(
            username=inbox_username or _username_from_name(name),
            display_name=name,
        )
        project.inbox_email = created["email"]

    foreman = Person(
        project_id=project.id,
        name="Foreman (unbound)",
        role="foreman",
        telegram_id=None,
    )
    # Do NOT auto-bind TELEGRAM_SUPER_CHAT_ID — that stamped one id onto every
    # new project and confused role resolution across sites.
    super_ = Person(
        project_id=project.id,
        name="Superintendent",
        role="superintendent",
        telegram_id=None,
    )
    db.add_all([foreman, super_])

    zones: dict[str, Zone] = {}
    if with_demo_zones:
        zones_spec = [
            (
                "zone-a",
                "Zone A — Structure",
                [[5, 10], [45, 10], [45, 45], [5, 45]],
                "grey",
                0,
            ),
            (
                "zone-b",
                "Zone B — Electrical",
                [[50, 10], [95, 10], [95, 45], [50, 45]],
                "grey",
                0,
            ),
            (
                "zone-c",
                "Zone C — Mechanical",
                [[5, 50], [45, 50], [45, 90], [5, 90]],
                "grey",
                0,
            ),
            (
                "zone-ws",
                "White Space",
                [[50, 50], [95, 50], [95, 90], [50, 90]],
                "grey",
                0,
            ),
        ]
        for key, label, poly, status, pct in zones_spec:
            z = Zone(
                project_id=project.id,
                label=label,
                polygon_json=json.dumps(poly),
                status=status,
                progress_pct=pct,
            )
            db.add(z)
            db.flush()
            zones[key] = z
        db.add(
            Task(
                project_id=project.id,
                zone_id=zones["zone-a"].id,
                title="Kickoff — site walk",
                status="todo",
            )
        )

    db.commit()
    db.refresh(project)
    root = kb_root_for(project)
    from fieldclaw_api.services import wiki_layout

    wiki_layout.ensure_wiki_layout(root)
    return {
        "project_id": project.id,
        "name": project.name,
        "inbox_email": project.inbox_email,
        "kb_relpath": project.kb_relpath,
        "foreman_id": foreman.id,
        "superintendent_id": super_.id,
        "zones": {k: v.id for k, v in zones.items()},
        "wiki": {"layout": "folders", "root": str(root)},
    }


def list_projects(db: Session) -> list[Project]:
    return db.query(Project).order_by(Project.created_at.desc()).all()
