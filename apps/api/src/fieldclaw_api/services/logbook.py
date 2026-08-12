import json
from typing import Any

from sqlalchemy.orm import Session

from fieldclaw_api.models import Event, PurchaseOrder, Task
from fieldclaw_api.schemas import EventCreate, EventOut
from fieldclaw_api.services.zones import recompute_zone_status


def event_to_out(ev: Event) -> EventOut:
    return EventOut(
        id=ev.id,
        project_id=ev.project_id,
        type=ev.type,
        zone_id=ev.zone_id,
        actor_id=ev.actor_id,
        task_id=ev.task_id,
        po_id=ev.po_id,
        source=ev.source,
        payload=json.loads(ev.payload_json),
        proof_ids=json.loads(ev.proof_ids_json),
        created_at=ev.created_at,
    )


def match_po(
    db: Session, project_id: str, material: str | None
) -> PurchaseOrder | None:
    if not material:
        return None
    needle = material.lower()
    pos = db.query(PurchaseOrder).filter(PurchaseOrder.project_id == project_id).all()
    for po in pos:
        if needle in po.material.lower() or po.material.lower() in needle:
            return po
    return None


def append_event(db: Session, project_id: str, body: EventCreate) -> list[EventOut]:
    created: list[Event] = []

    ev = Event(
        project_id=project_id,
        type=body.type,
        zone_id=body.zone_id,
        actor_id=body.actor_id,
        task_id=body.task_id,
        po_id=body.po_id,
        source=body.source,
        payload_json=json.dumps(body.payload),
        proof_ids_json=json.dumps(body.proof_ids),
    )
    db.add(ev)
    db.flush()
    created.append(ev)

    if body.type == "shortage.raised":
        material = body.payload.get("material")
        po = match_po(db, project_id, material)
        if po:
            ev.po_id = po.id
            matched = Event(
                project_id=project_id,
                type="po.matched",
                zone_id=body.zone_id,
                actor_id=body.actor_id,
                task_id=body.task_id,
                po_id=po.id,
                source=body.source,
                payload_json=json.dumps(
                    {
                        "shortage_event_id": ev.id,
                        "po_number": po.po_number,
                        "material": po.material,
                        "supplier": po.supplier,
                        "eta": po.eta,
                        "qty": po.qty,
                    }
                ),
                proof_ids_json="[]",
            )
            db.add(matched)
            db.flush()
            created.append(matched)

            if body.task_id:
                task = db.get(Task, body.task_id)
                if task:
                    task.at_risk = True
                    db.add(task)
            else:
                # mark zone task at risk if title matches
                tasks = (
                    db.query(Task)
                    .filter(Task.project_id == project_id, Task.zone_id == body.zone_id)
                    .all()
                )
                for t in tasks:
                    t.at_risk = True
                    db.add(t)

            flag = Event(
                project_id=project_id,
                type="schedule.flagged",
                zone_id=body.zone_id,
                po_id=po.id,
                source=body.source,
                payload_json=json.dumps(
                    {
                        "reason": "material_shortage",
                        "shortage_event_id": ev.id,
                        "po_number": po.po_number,
                    }
                ),
                proof_ids_json="[]",
            )
            db.add(flag)
            db.flush()
            created.append(flag)

    recompute_zone_status(db, project_id, body.zone_id)
    db.commit()
    for e in created:
        db.refresh(e)

    # Mirror field/status traffic into the folder wiki (ops/log + zone pages)
    wiki_types = {
        "shortage.raised",
        "safety.reported",
        "quality.reported",
        "status.reported",
        "schedule.flagged",
        "super.replied",
    }
    if body.type in wiki_types or body.type.startswith("status."):
        try:
            from fieldclaw_api.services.wiki import mirror_event_to_wiki

            for e in created:
                if e.type in wiki_types or e.type.startswith("status."):
                    mirror_event_to_wiki(
                        db,
                        project_id,
                        event_type=e.type,
                        payload=json.loads(e.payload_json),
                        zone_id=e.zone_id,
                        actor_id=e.actor_id,
                        created_at=e.created_at.isoformat() if e.created_at else None,
                    )
        except Exception:
            # Wiki mirror must never fail the logbook write
            pass

    return [event_to_out(e) for e in created]


def list_events(
    db: Session,
    project_id: str,
    *,
    zone_id: str | None = None,
    type_: str | None = None,
    source: str | None = None,
) -> list[EventOut]:
    q = db.query(Event).filter(Event.project_id == project_id)
    if zone_id:
        q = q.filter(Event.zone_id == zone_id)
    if type_:
        q = q.filter(Event.type == type_)
    if source:
        q = q.filter(Event.source == source)
    rows = q.order_by(Event.created_at.desc()).all()
    return [event_to_out(e) for e in rows]


def daily_log(db: Session, project_id: str, day: str) -> dict[str, Any]:
    events = list_events(db, project_id)
    day_events = [e for e in events if e.created_at.strftime("%Y-%m-%d") == day]
    return {
        "date": day,
        "project_id": project_id,
        "count": len(day_events),
        "events": day_events,
    }


def super_queue(db: Session, project_id: str) -> list[EventOut]:
    events = list_events(db, project_id)
    replied_to = {
        e.payload.get("reply_to_event_id") for e in events if e.type == "super.replied"
    }
    actionable = []
    for e in events:
        if e.type in (
            "shortage.raised",
            "safety.reported",
            "quality.reported",
            "status.reported",
        ):
            if e.id not in replied_to:
                actionable.append(e)
        elif e.type == "schedule.flagged":
            actionable.append(e)
    return actionable
