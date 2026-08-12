import json
import os

from sqlalchemy.orm import Session

from fieldclaw_api.config import settings
from fieldclaw_api.db import Base
from fieldclaw_api.models import (
    Event,
    MailMessage,
    Person,
    Project,
    PurchaseOrder,
    Task,
    Zone,
)


def _env(*names: str) -> str | None:
    for name in names:
        val = (os.environ.get(name) or "").strip()
        if val:
            return val
    return None


def reset_and_seed(db: Session) -> dict:
    # wipe tables
    for table in reversed(Base.metadata.sorted_tables):
        db.execute(table.delete())
    db.commit()

    project = Project(name="FieldClaw DC Campus — Demo")
    db.add(project)
    db.flush()
    project.kb_relpath = f"projects/{project.id}"
    project.inbox_email = (
        _env("EMAIL_ADDRESS", "EMAIL_HOME_ADDRESS") or "kaya-meow@agentmail.to"
    )

    foreman_tg = settings.telegram_foreman_chat_id or _env("TELEGRAM_FOREMAN_CHAT_ID")
    super_tg = settings.telegram_super_chat_id or _env(
        "TELEGRAM_SUPER_CHAT_ID", "TELEGRAM_HOME_CHANNEL"
    )

    foreman = Person(
        project_id=project.id,
        name="James Ortiz",
        role="foreman",
        telegram_id=foreman_tg,
        email="james.foreman@example.com",
    )
    super_ = Person(
        project_id=project.id,
        name="Priya Shah",
        role="superintendent",
        telegram_id=super_tg,
        email="priya.super@example.com",
    )
    pm = Person(
        project_id=project.id,
        name="Alex Chen",
        role="pm",
        email="alex.pm@example.com",
    )
    db.add_all([foreman, super_, pm])
    db.flush()

    # Simple site plan polygons (normalized 0-100 coords)
    zones_spec = [
        (
            "zone-a",
            "Zone A — Structure",
            [[5, 10], [45, 10], [45, 45], [5, 45]],
            "green",
            62,
        ),
        (
            "zone-b",
            "Zone B — Electrical",
            [[50, 10], [95, 10], [95, 45], [50, 45]],
            "grey",
            15,
        ),
        (
            "zone-c",
            "Zone C — Mechanical",
            [[5, 50], [45, 50], [45, 90], [5, 90]],
            "grey",
            40,
        ),
        ("zone-ws", "White Space", [[50, 50], [95, 50], [95, 90], [50, 90]], "grey", 5),
    ]
    zones: dict[str, Zone] = {}
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

    tasks_spec = [
        ("Confirm rebar ETA — PO-9905", "todo", zones["zone-c"].id, True),
        ("Night photos Zone A package", "todo", zones["zone-a"].id, False),
        ("Structural Framing — Zone C", "in_progress", zones["zone-c"].id, False),
        ("Temp power drop Zone B", "in_progress", zones["zone-b"].id, False),
        ("White Space slab prep checklist", "blocked", zones["zone-ws"].id, True),
        ("Zone A steel package 60%", "done", zones["zone-a"].id, False),
    ]
    tasks: list[Task] = []
    for title, status, zone_id, at_risk in tasks_spec:
        t = Task(
            project_id=project.id,
            zone_id=zone_id,
            title=title,
            status=status,
            at_risk=at_risk,
        )
        db.add(t)
        tasks.append(t)
    db.flush()
    task = next(t for t in tasks if t.title.startswith("Structural"))

    po = PurchaseOrder(
        project_id=project.id,
        po_number="PO-9905",
        material="rebar",
        qty="200 bundles",
        supplier="Acme Steel",
        eta="Thursday",
        status="ordered",
    )
    db.add(po)
    db.flush()

    night = Event(
        project_id=project.id,
        type="progress.reported",
        zone_id=zones["zone-a"].id,
        actor_id=foreman.id,
        source="seed",
        payload_json=json.dumps(
            {
                "text": "Night shift: Zone A steel package 62% complete. Photos attached.",
                "progress_pct": 62,
                "shift": "night",
            }
        ),
        proof_ids_json="[]",
    )
    db.add(night)

    # Nested email seed (depth 0 and 1)
    thread = "thread-rebar-eta"
    m0 = MailMessage(
        project_id=project.id,
        thread_id=thread,
        direction="outbound",
        subject="PO-9905 rebar ETA confirmation",
        body="Please confirm ETA for 200 bundles rebar for Zone C.",
        depth=0,
        parsed_json=json.dumps({"intent": "update"}),
    )
    m1 = MailMessage(
        project_id=project.id,
        thread_id=thread,
        direction="inbound",
        subject="Re: PO-9905 rebar ETA confirmation",
        body="Delayed — new ETA Thursday afternoon. Truck leaves Wednesday night.",
        in_reply_to=None,
        depth=1,
        parsed_json=json.dumps({"intent": "schedule_change", "eta": "Thursday"}),
    )
    db.add_all([m0, m1])
    db.flush()
    m1.in_reply_to = m0.id

    email_ev = Event(
        project_id=project.id,
        type="email.inbound",
        zone_id=zones["zone-c"].id,
        po_id=po.id,
        source="mail",
        payload_json=json.dumps(
            {
                "thread_id": thread,
                "subject": m1.subject,
                "depth": 1,
                "mail_id": m1.id,
            }
        ),
        proof_ids_json="[]",
    )
    db.add(email_ev)

    db.commit()
    from fieldclaw_api.services import wiki_layout
    from fieldclaw_api.services.projects import kb_root_for

    root = kb_root_for(project)
    wiki = wiki_layout.ensure_wiki_layout(root)
    wiki_layout.migrate_flat_wiki(wiki)
    wiki_layout.rebuild_index(wiki, project_id=project.id)
    return {
        "project_id": project.id,
        "inbox_email": project.inbox_email,
        "kb_relpath": project.kb_relpath,
        "foreman_id": foreman.id,
        "superintendent_id": super_.id,
        "people": [
            {
                "id": foreman.id,
                "role": foreman.role,
                "telegram_id": foreman.telegram_id,
            },
            {
                "id": super_.id,
                "role": super_.role,
                "telegram_id": super_.telegram_id,
            },
            {"id": pm.id, "role": pm.role, "telegram_id": pm.telegram_id},
        ],
        "zones": {k: v.id for k, v in zones.items()},
        "task_id": task.id,
        "task_ids": [t.id for t in tasks],
        "po_id": po.id,
        "po_number": po.po_number,
    }
