import json
import threading
from pathlib import Path

from sqlalchemy.orm import Session

from fieldclaw_api.config import settings
from fieldclaw_api.db import SessionLocal
from fieldclaw_api.models import Event, SimRun, Zone
from fieldclaw_api.schemas import EventCreate
from fieldclaw_api.services.logbook import append_event

_lock = threading.Lock()
_runners: dict[str, threading.Thread] = {}
_stop_flags: dict[str, threading.Event] = {}


def _scenario_path(scenario: str) -> Path:
    name = {
        "kaggle_site": "kaggle_site_replay.jsonl",
        "dc_campus": "dc_campus_replay.jsonl",  # legacy Epoch-flavored
        "shortage": "shortage_day.jsonl",
    }.get(scenario, f"{scenario}.jsonl")
    return settings.fieldclaw_sim_dir / name


def load_ticks(scenario: str) -> list[dict]:
    path = _scenario_path(scenario)
    if not path.exists():
        return []
    ticks = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            ticks.append(json.loads(line))
    return ticks


def get_or_create_run(db: Session, project_id: str, scenario: str) -> SimRun:
    run = (
        db.query(SimRun)
        .filter(SimRun.project_id == project_id, SimRun.scenario == scenario)
        .first()
    )
    if not run:
        run = SimRun(project_id=project_id, scenario=scenario)
        db.add(run)
        db.commit()
        db.refresh(run)
    return run


def _resolve_zone_id(db: Session, project_id: str, zone_key: str | None) -> str | None:
    if not zone_key:
        return None
    zones = db.query(Zone).filter(Zone.project_id == project_id).all()
    for z in zones:
        if zone_key.lower() in z.label.lower() or zone_key.lower() in z.id.lower():
            return z.id
    # seed uses zone-a style labels
    for z in zones:
        label = z.label.lower()
        if zone_key.replace("_", " ").lower() in label:
            return z.id
    mapping_hints = {
        "zone_a": "zone a",
        "zone_b": "zone b",
        "zone_c": "zone c",
        "white_space": "white space",
        "electrical": "electrical",
        "mechanical": "mechanical",
        "structure": "structure",
    }
    hint = mapping_hints.get(zone_key, zone_key)
    for z in zones:
        if hint in z.label.lower():
            return z.id
    return zones[0].id if zones else None


def _play_loop(project_id: str, scenario: str, start_cursor: int, speed: float) -> None:
    key = f"{project_id}:{scenario}"
    stop = _stop_flags[key]
    ticks = load_ticks(scenario)
    cursor = start_cursor
    last_t = ticks[cursor]["t_offset_sec"] if cursor < len(ticks) else 0

    while cursor < len(ticks) and not stop.is_set():
        tick = ticks[cursor]
        t = tick["t_offset_sec"]
        delay = max(0.0, (t - last_t) / max(speed, 0.1))
        if delay and stop.wait(delay):
            break
        last_t = t

        db = SessionLocal()
        try:
            zone_id = _resolve_zone_id(db, project_id, tick.get("zone"))
            etype = tick.get("type", "sim.dc_tick")
            payload = dict(tick.get("payload") or {})
            payload["sim_cursor"] = cursor
            payload["scenario"] = scenario
            append_event(
                db,
                project_id,
                EventCreate(
                    type=etype,
                    zone_id=zone_id,
                    source=f"sim.{scenario}"
                    if not scenario.startswith("sim.")
                    else scenario,
                    payload=payload,
                ),
            )
            run = get_or_create_run(db, project_id, scenario)
            run.cursor = cursor + 1
            run.status = "playing"
            run.speed = speed
            db.add(run)
            db.commit()
        finally:
            db.close()
        cursor += 1

    db = SessionLocal()
    try:
        run = get_or_create_run(db, project_id, scenario)
        run.status = "paused" if stop.is_set() else "finished"
        db.add(run)
        db.commit()
    finally:
        db.close()


def play(db: Session, project_id: str, scenario: str, speed: float = 8.0) -> dict:
    ticks = load_ticks(scenario)
    run = get_or_create_run(db, project_id, scenario)
    key = f"{project_id}:{scenario}"
    with _lock:
        if key in _runners and _runners[key].is_alive():
            return {
                "status": "already_playing",
                "cursor": run.cursor,
                "total": len(ticks),
            }
        stop = threading.Event()
        _stop_flags[key] = stop
        run.status = "playing"
        run.speed = speed
        db.add(run)
        db.commit()
        t = threading.Thread(
            target=_play_loop,
            args=(project_id, scenario, run.cursor, speed),
            daemon=True,
        )
        _runners[key] = t
        t.start()
    return {
        "status": "playing",
        "cursor": run.cursor,
        "total": len(ticks),
        "speed": speed,
    }


def pause(db: Session, project_id: str, scenario: str) -> dict:
    key = f"{project_id}:{scenario}"
    with _lock:
        if key in _stop_flags:
            _stop_flags[key].set()
    run = get_or_create_run(db, project_id, scenario)
    run.status = "paused"
    db.add(run)
    db.commit()
    return {"status": "paused", "cursor": run.cursor}


def seek(
    db: Session, project_id: str, scenario: str, cursor: int, speed: float
) -> dict:
    pause(db, project_id, scenario)
    run = get_or_create_run(db, project_id, scenario)
    run.cursor = max(0, cursor)
    run.speed = speed
    run.status = "paused"
    db.add(run)
    db.commit()
    return {"status": "paused", "cursor": run.cursor, "speed": speed}


def reset(db: Session, project_id: str, scenario: str) -> dict:
    pause(db, project_id, scenario)
    source = f"sim.{scenario}"
    db.query(Event).filter(
        Event.project_id == project_id,
        Event.source == source,
    ).delete()
    run = get_or_create_run(db, project_id, scenario)
    run.cursor = 0
    run.status = "idle"
    db.add(run)
    db.commit()
    return {"status": "idle", "cursor": 0, "cleared_source": source}
