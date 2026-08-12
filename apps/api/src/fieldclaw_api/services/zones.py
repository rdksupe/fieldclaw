import json

from sqlalchemy.orm import Session

from fieldclaw_api.models import Event, Zone


def recompute_zone_status(db: Session, project_id: str, zone_id: str | None) -> None:
    if not zone_id:
        return
    zone = db.get(Zone, zone_id)
    if not zone or zone.project_id != project_id:
        return

    events = (
        db.query(Event)
        .filter(Event.project_id == project_id, Event.zone_id == zone_id)
        .order_by(Event.created_at.desc())
        .all()
    )

    open_shortage = False
    schedule_flag = False
    progress = zone.progress_pct
    saw_progress = False

    for ev in events:
        if ev.type == "shortage.raised":
            # closed if a later super.replied references this event
            closed = any(
                e.type == "super.replied"
                and json.loads(e.payload_json).get("reply_to_event_id") == ev.id
                for e in events
            )
            if not closed:
                open_shortage = True
        elif ev.type == "schedule.flagged":
            schedule_flag = True
        elif ev.type in ("progress.reported", "sim.dc_tick"):
            payload = json.loads(ev.payload_json)
            if "progress_pct" in payload:
                progress = float(payload["progress_pct"])
                saw_progress = True

    if open_shortage:
        zone.status = "red"
    elif schedule_flag:
        zone.status = "amber"
    elif saw_progress or progress > 0:
        zone.status = "green"
    else:
        zone.status = "grey"
    zone.progress_pct = progress
    db.add(zone)
