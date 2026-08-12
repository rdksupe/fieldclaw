import json
import re
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile
from sqlalchemy.orm import Session

from fieldclaw_api.auth import (
    actor_crew_optional,
    get_project_or_404,
    require_actor,
    require_api_key,
)
from fieldclaw_api.config import settings
from fieldclaw_api.db import get_db
from fieldclaw_api.models import Person, Project, Task, Zone
from fieldclaw_api.schemas import (
    AdminRegisterIn,
    EventCreate,
    EventOut,
    ForemanRegisterIn,
    MailInjectIn,
    MailSendIn,
    PairingApproveIn,
    PersonOut,
    PersonTelegramIn,
    ProjectCreate,
    ProjectOut,
    SeekIn,
    SitemapImportIn,
    SuperReplyIn,
    TaskCreate,
    TaskOut,
    TaskPatch,
    UiWidgetsIn,
    WikiLookupIn,
    ZoneCreate,
    ZoneOut,
)
from fieldclaw_api.services import mail as mail_svc
from fieldclaw_api.services import pairing_svc
from fieldclaw_api.services import projects as projects_svc
from fieldclaw_api.services import sim as sim_svc
from fieldclaw_api.services import sitemap as sitemap_svc
from fieldclaw_api.services import wiki as wiki_svc
from fieldclaw_api.services.logbook import (
    append_event,
    daily_log,
    list_events,
    super_queue,
)
from fieldclaw_api.services.notify import notify_foreman_telegram
from fieldclaw_api.services.seed import reset_and_seed

router = APIRouter(prefix="/api", dependencies=[Depends(require_api_key)])

ALLOWED_TASK_STATUS = {"todo", "in_progress", "blocked", "done"}


@router.post("/seed")
def seed(db: Session = Depends(get_db), _key: str = Depends(require_api_key)):
    return reset_and_seed(db)


@router.get("/projects", response_model=list[ProjectOut])
def list_projects(db: Session = Depends(get_db)):
    return projects_svc.list_projects(db)


@router.post("/projects", response_model=dict)
def create_project(
    body: ProjectCreate,
    db: Session = Depends(get_db),
    x_actor_telegram: str | None = Header(default=None, alias="X-Actor-Telegram"),
):
    # Optional actor must be a superintendent on some project when provided.
    if x_actor_telegram:
        person = (
            db.query(Person)
            .filter(
                Person.telegram_id == x_actor_telegram,
                Person.role == "superintendent",
            )
            .first()
        )
        if not person:
            raise HTTPException(403, "X-Actor-Telegram must be a superintendent")
    try:
        return projects_svc.create_project(
            db,
            body.name,
            inbox_username=body.inbox_username,
            provision_inbox=body.provision_inbox,
            inbox_email=body.inbox_email,
            with_demo_zones=body.with_demo_zones,
        )
    except Exception as e:
        raise HTTPException(400, str(e)) from e


@router.get("/projects/{project_id}", response_model=ProjectOut)
def get_project(project: Project = Depends(get_project_or_404)):
    return project


@router.get("/pairing")
def pairing_status():
    try:
        return pairing_svc.list_pairing("telegram")
    except Exception as e:
        raise HTTPException(500, str(e)) from e


@router.post("/pairing/approve")
def pairing_approve(
    body: PairingApproveIn,
    db: Session = Depends(get_db),
    x_actor_telegram: str | None = Header(default=None, alias="X-Actor-Telegram"),
):
    if body.project_id:
        project = db.get(Project, body.project_id)
        if not project:
            raise HTTPException(404, "project not found")
        # When actor header present, must be superintendent on that project
        if x_actor_telegram:
            require_actor(
                body.project_id,
                {"superintendent"},
                required=True,
                x_actor_telegram=x_actor_telegram,
                db=db,
            )
    try:
        result = pairing_svc.approve_code(body.platform, body.code)
    except Exception as e:
        raise HTTPException(400, str(e)) from e

    user = result.get("user") or {}
    telegram_id = str(user.get("user_id") or "")
    bound = None
    if body.project_id and telegram_id and body.bind_role:
        person = (
            db.query(Person)
            .filter(
                Person.project_id == body.project_id,
                Person.role == body.bind_role,
            )
            .first()
        )
        if not person:
            person = Person(
                project_id=body.project_id,
                name=body.person_name or f"{body.bind_role.title()} (paired)",
                role=body.bind_role,
                telegram_id=telegram_id,
            )
            db.add(person)
        else:
            if body.person_name:
                person.name = body.person_name
            person.telegram_id = telegram_id
        db.commit()
        db.refresh(person)
        bound = PersonOut.model_validate(person)
        if body.bind_role == "foreman":
            settings.telegram_foreman_chat_id = telegram_id
    return {"pairing": result, "bound_person": bound}


@router.post("/projects/{project_id}/foreman/register", response_model=PersonOut)
def register_foreman(
    body: ForemanRegisterIn,
    project: Project = Depends(get_project_or_404),
    db: Session = Depends(get_db),
):
    project_id = project.id
    person = (
        db.query(Person)
        .filter(Person.project_id == project_id, Person.role == "foreman")
        .first()
    )
    if not person:
        person = Person(
            project_id=project_id,
            name=body.name,
            role="foreman",
            email=body.email,
        )
        db.add(person)
    else:
        person.name = body.name
        if body.email is not None:
            person.email = body.email
    db.commit()
    db.refresh(person)
    return person


@router.post("/projects/{project_id}/admin/register", response_model=PersonOut)
def register_admin(
    body: AdminRegisterIn,
    project: Project = Depends(get_project_or_404),
    db: Session = Depends(get_db),
):
    """Register / update the superintendent (site admin) for a project."""
    project_id = project.id
    person = (
        db.query(Person)
        .filter(Person.project_id == project_id, Person.role == "superintendent")
        .first()
    )
    if not person:
        person = Person(
            project_id=project_id,
            name=body.name,
            role="superintendent",
            email=body.email,
            telegram_id=body.telegram_id,
        )
        db.add(person)
    else:
        person.name = body.name
        if body.email is not None:
            person.email = body.email
        if body.telegram_id is not None:
            person.telegram_id = body.telegram_id
    db.commit()
    db.refresh(person)
    if person.telegram_id:
        settings.telegram_super_chat_id = person.telegram_id
    return person


@router.get("/projects/{project_id}/events", response_model=list[EventOut])
def get_events(
    project: Project = Depends(get_project_or_404),
    zone_id: str | None = None,
    type: str | None = None,
    source: str | None = None,
    db: Session = Depends(get_db),
):
    return list_events(db, project.id, zone_id=zone_id, type_=type, source=source)


@router.post("/projects/{project_id}/events", response_model=list[EventOut])
def post_event(
    body: EventCreate,
    project: Project = Depends(get_project_or_404),
    db: Session = Depends(get_db),
    _actor: Person | None = Depends(actor_crew_optional),
):
    return append_event(db, project.id, body)


@router.get("/projects/{project_id}/zones", response_model=list[ZoneOut])
def get_zones(
    project: Project = Depends(get_project_or_404), db: Session = Depends(get_db)
):
    zones = db.query(Zone).filter(Zone.project_id == project.id).all()
    return [
        ZoneOut(
            id=z.id,
            project_id=z.project_id,
            label=z.label,
            polygon=json.loads(z.polygon_json),
            status=z.status,
            progress_pct=z.progress_pct,
        )
        for z in zones
    ]


@router.post("/projects/{project_id}/sitemap")
def import_sitemap_json(
    body: SitemapImportIn,
    project: Project = Depends(get_project_or_404),
    db: Session = Depends(get_db),
    x_actor_telegram: str | None = Header(default=None, alias="X-Actor-Telegram"),
):
    """Import a GeoJSON site logistics map → zones + wiki/zones pages."""
    # Hermes with actor must be superintendent; cron/web may omit header.
    if x_actor_telegram:
        require_actor(
            project.id,
            {"superintendent"},
            required=True,
            x_actor_telegram=x_actor_telegram,
            db=db,
        )
    try:
        return sitemap_svc.import_geojson(
            db,
            project.id,
            body.geojson,
            replace=body.replace,
            source_name=body.source_name,
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.post("/projects/{project_id}/sitemap/upload")
async def import_sitemap_upload(
    file: UploadFile = File(...),
    replace: bool = Form(True),
    project: Project = Depends(get_project_or_404),
    db: Session = Depends(get_db),
    x_actor_telegram: str | None = Header(default=None, alias="X-Actor-Telegram"),
):
    """Upload GeoJSON or PDF/image site plan → zones (OCR via Datalab/Chandra for rasters)."""
    if x_actor_telegram:
        require_actor(
            project.id,
            {"superintendent"},
            required=True,
            x_actor_telegram=x_actor_telegram,
            db=db,
        )
    raw = await file.read()
    name = file.filename or "sitemap.geojson"
    low = name.lower()
    try:
        if low.endswith((".pdf", ".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff")):
            return sitemap_svc.import_from_document(
                db, project.id, raw, filename=name, replace=replace
            )
        return sitemap_svc.import_geojson(
            db, project.id, raw, replace=replace, source_name=name
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except json.JSONDecodeError as e:
        raise HTTPException(400, f"invalid GeoJSON: {e}") from e
    except Exception as e:
        raise HTTPException(400, str(e)) from e


@router.post("/projects/{project_id}/zones", response_model=ZoneOut)
def create_zone(
    body: ZoneCreate,
    project: Project = Depends(get_project_or_404),
    db: Session = Depends(get_db),
    x_actor_telegram: str | None = Header(default=None, alias="X-Actor-Telegram"),
):
    """Create a zone from agent onboarding / site walk — not a fixed template."""
    project_id = project.id
    if x_actor_telegram:
        require_actor(
            project_id,
            {"superintendent"},
            required=True,
            x_actor_telegram=x_actor_telegram,
            db=db,
        )
    # Auto-tile if no polygon: next open quadrant on a 2x2 grid
    poly = body.polygon
    if not poly:
        existing = db.query(Zone).filter(Zone.project_id == project_id).count()
        slots = [
            [[5, 10], [45, 10], [45, 45], [5, 45]],
            [[50, 10], [95, 10], [95, 45], [50, 45]],
            [[5, 50], [45, 50], [45, 90], [5, 90]],
            [[50, 50], [95, 50], [95, 90], [50, 90]],
        ]
        poly = slots[min(existing, len(slots) - 1)]
        if existing >= len(slots):
            # overflow: pack smaller cells
            col, row = existing % 3, existing // 3
            x0, y0 = 5 + col * 30, 5 + row * 30
            poly = [[x0, y0], [x0 + 28, y0], [x0 + 28, y0 + 28], [x0, y0 + 28]]
    z = Zone(
        project_id=project_id,
        label=body.label.strip(),
        polygon_json=json.dumps(poly),
        status=body.status or "grey",
        progress_pct=float(body.progress_pct or 0),
    )
    db.add(z)
    db.commit()
    db.refresh(z)
    # Mirror a zone page into the wiki when layout exists
    try:
        from fieldclaw_api.services import wiki_layout

        root = projects_svc.kb_root_for(project)
        wiki_layout.ensure_wiki_layout(root)
        slug = re.sub(r"[^a-z0-9]+", "-", z.label.lower()).strip("-") or "zone"
        zpath = root / "wiki" / "zones" / f"{slug}.md"
        if not zpath.exists():
            zpath.write_text(
                f"# {z.label}\n\nZone created during site setup.\n\n"
                f"- status: {z.status}\n- progress: {z.progress_pct}%\n",
                encoding="utf-8",
            )
    except Exception:
        pass
    return ZoneOut(
        id=z.id,
        project_id=z.project_id,
        label=z.label,
        polygon=json.loads(z.polygon_json),
        status=z.status,
        progress_pct=z.progress_pct,
    )


@router.get("/projects/{project_id}/people", response_model=list[PersonOut])
def get_people(
    project: Project = Depends(get_project_or_404), db: Session = Depends(get_db)
):
    return (
        db.query(Person)
        .filter(Person.project_id == project.id)
        .order_by(Person.role, Person.name)
        .all()
    )


@router.get(
    "/projects/{project_id}/people/by-telegram/{telegram_id}",
    response_model=PersonOut,
)
def get_person_by_telegram(
    telegram_id: str,
    project: Project = Depends(get_project_or_404),
    db: Session = Depends(get_db),
):
    person = (
        db.query(Person)
        .filter(Person.project_id == project.id, Person.telegram_id == telegram_id)
        .first()
    )
    if not person:
        raise HTTPException(404, "person not found for telegram_id")
    return person


@router.patch(
    "/projects/{project_id}/people/{person_id}",
    response_model=PersonOut,
)
def patch_person_telegram(
    person_id: str,
    body: PersonTelegramIn,
    project: Project = Depends(get_project_or_404),
    db: Session = Depends(get_db),
):
    person = db.get(Person, person_id)
    if not person or person.project_id != project.id:
        raise HTTPException(404, "person not found")
    person.telegram_id = body.telegram_id
    db.commit()
    db.refresh(person)
    return person


@router.get("/projects/{project_id}/tasks", response_model=list[TaskOut])
def get_tasks(
    project: Project = Depends(get_project_or_404), db: Session = Depends(get_db)
):
    return db.query(Task).filter(Task.project_id == project.id).all()


@router.post("/projects/{project_id}/tasks", response_model=TaskOut)
def create_task(
    body: TaskCreate,
    project: Project = Depends(get_project_or_404),
    db: Session = Depends(get_db),
):
    project_id = project.id
    status = body.status if body.status in ALLOWED_TASK_STATUS else "todo"
    task = Task(
        project_id=project_id,
        zone_id=body.zone_id,
        title=body.title,
        status=status,
        at_risk=body.at_risk,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


@router.patch("/projects/{project_id}/tasks/{task_id}", response_model=TaskOut)
def patch_task(
    task_id: str,
    body: TaskPatch,
    project: Project = Depends(get_project_or_404),
    db: Session = Depends(get_db),
):
    task = db.get(Task, task_id)
    if not task or task.project_id != project.id:
        raise HTTPException(404, "task not found")
    if body.title is not None:
        task.title = body.title
    if body.zone_id is not None:
        task.zone_id = body.zone_id
    if body.status is not None:
        if body.status not in ALLOWED_TASK_STATUS:
            raise HTTPException(
                400, f"status must be one of {sorted(ALLOWED_TASK_STATUS)}"
            )
        task.status = body.status
    if body.at_risk is not None:
        task.at_risk = body.at_risk
    db.commit()
    db.refresh(task)
    return task


@router.get("/projects/{project_id}/daily-log")
def get_daily_log(
    project: Project = Depends(get_project_or_404),
    date: str | None = None,
    db: Session = Depends(get_db),
):
    day = date or datetime.now(UTC).strftime("%Y-%m-%d")
    return daily_log(db, project.id, day)


@router.get("/projects/{project_id}/super-queue", response_model=list[EventOut])
def get_super_queue(
    project: Project = Depends(get_project_or_404), db: Session = Depends(get_db)
):
    return super_queue(db, project.id)


@router.post("/projects/{project_id}/super-reply")
async def super_reply(
    body: SuperReplyIn,
    project: Project = Depends(get_project_or_404),
    db: Session = Depends(get_db),
    x_actor_telegram: str | None = Header(default=None, alias="X-Actor-Telegram"),
):
    project_id = project.id
    if x_actor_telegram:
        require_actor(
            project_id,
            {"superintendent"},
            required=True,
            x_actor_telegram=x_actor_telegram,
            db=db,
        )
    outs = append_event(
        db,
        project_id,
        EventCreate(
            type="super.replied",
            source="api",
            payload={"reply_to_event_id": body.event_id, "message": body.message},
        ),
    )
    from fieldclaw_api.models import Event
    from fieldclaw_api.services.zones import recompute_zone_status

    src = db.get(Event, body.event_id)
    if src:
        recompute_zone_status(db, project_id, src.zone_id)
        db.commit()

    telegram_result = None
    try:
        await notify_foreman_telegram(db, project_id, body.message)
        telegram_result = "sent"
    except Exception as e:
        telegram_result = f"error: {e}"

    return {
        "events": [e.model_dump(mode="json") for e in outs],
        "telegram": telegram_result,
    }


@router.post("/projects/{project_id}/proofs")
async def upload_proof(
    event_id: str | None = Form(default=None),
    kind: str = Form(default="photo"),
    caption: str | None = Form(default=None),
    zone_id: str | None = Form(default=None),
    file: UploadFile = File(...),
    project: Project = Depends(get_project_or_404),
    db: Session = Depends(get_db),
    _actor: Person | None = Depends(actor_crew_optional),
):
    """Upload a field photo/proof. Images are also ingested into wiki/media/."""
    from fieldclaw_api.models import Proof

    project_id = project.id
    settings.fieldclaw_proofs_dir.mkdir(parents=True, exist_ok=True)
    data = await file.read()
    dest = settings.fieldclaw_proofs_dir / f"{project_id}_{file.filename}"
    dest.write_bytes(data)
    proof = Proof(
        project_id=project_id,
        event_id=event_id,
        kind=kind,
        path=str(dest),
        meta_json=json.dumps(
            {
                "filename": file.filename,
                "content_type": file.content_type,
                "caption": caption,
            }
        ),
    )
    db.add(proof)
    db.commit()
    db.refresh(proof)

    wiki_info = None
    ct = file.content_type or ""
    name = file.filename or "photo.jpg"
    if ct.startswith("image/") or Path(name).suffix.lower() in {
        ".jpg",
        ".jpeg",
        ".png",
        ".webp",
        ".gif",
        ".heic",
    }:
        wiki_info = wiki_svc.ingest_image(
            db,
            project_id,
            name,
            data,
            caption=caption,
            event_id=event_id,
            zone_id=zone_id,
            content_type=ct,
        )

    append_event(
        db,
        project_id,
        EventCreate(
            type="proof.attached",
            source="api",
            zone_id=zone_id,
            payload={
                "proof_id": proof.id,
                "event_id": event_id,
                "path": str(dest),
                "caption": caption,
                "wiki_page": (wiki_info or {}).get("wiki_page"),
                "wiki_file": (wiki_info or {}).get("wiki_file"),
            },
            proof_ids=[proof.id],
        ),
    )
    return {
        "id": proof.id,
        "path": str(dest),
        "wiki": wiki_info,
    }


@router.get("/projects/{project_id}/mail/threads")
def mail_threads(
    project: Project = Depends(get_project_or_404), db: Session = Depends(get_db)
):
    return mail_svc.list_threads(db, project.id)


@router.post("/projects/{project_id}/mail/inject")
def mail_inject(
    body: MailInjectIn,
    project: Project = Depends(get_project_or_404),
    db: Session = Depends(get_db),
):
    return mail_svc.inject_mail(db, project.id, body)


@router.post("/projects/{project_id}/mail/send")
async def mail_send(
    body: MailSendIn,
    project: Project = Depends(get_project_or_404),
    db: Session = Depends(get_db),
):
    try:
        return await mail_svc.send_mail(db, project.id, body)
    except Exception as e:
        raise HTTPException(400, str(e)) from e


@router.get("/sim/{scenario}")
def sim_meta(
    scenario: str,
    project_id: str,
    db: Session = Depends(get_db),
):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "project not found")
    ticks = sim_svc.load_ticks(scenario)
    run = sim_svc.get_or_create_run(db, project_id, scenario)
    return {
        "scenario": scenario,
        "total": len(ticks),
        "cursor": run.cursor,
        "status": run.status,
        "speed": run.speed,
    }


@router.post("/sim/{scenario}/play")
def sim_play(
    scenario: str,
    project_id: str,
    speed: float = 8.0,
    db: Session = Depends(get_db),
):
    return sim_svc.play(db, project_id, scenario, speed=speed)


@router.post("/sim/{scenario}/pause")
def sim_pause(
    scenario: str,
    project_id: str,
    db: Session = Depends(get_db),
):
    return sim_svc.pause(db, project_id, scenario)


@router.post("/sim/{scenario}/seek")
def sim_seek(
    scenario: str,
    project_id: str,
    body: SeekIn,
    db: Session = Depends(get_db),
):
    return sim_svc.seek(db, project_id, scenario, body.cursor, body.speed)


@router.post("/sim/{scenario}/reset")
def sim_reset(
    scenario: str,
    project_id: str,
    db: Session = Depends(get_db),
):
    return sim_svc.reset(db, project_id, scenario)


@router.post("/projects/{project_id}/wiki/ingest")
async def wiki_ingest(
    file: UploadFile = File(...),
    caption: str | None = Form(default=None),
    event_id: str | None = Form(default=None),
    zone_id: str | None = Form(default=None),
    project: Project = Depends(get_project_or_404),
    db: Session = Depends(get_db),
    _actor: Person | None = Depends(actor_crew_optional),
):
    data = await file.read()
    return wiki_svc.ingest_bytes(
        db,
        project.id,
        file.filename or "upload.bin",
        data,
        file.content_type,
        caption=caption,
        event_id=event_id,
        zone_id=zone_id,
    )


@router.get("/projects/{project_id}/wiki/file/{file_path:path}")
def wiki_file(
    file_path: str,
    project: Project = Depends(get_project_or_404),
):
    """Serve a file under the project wiki/ (e.g. media/photo.jpg, sources/*.pdf)."""
    from fastapi.responses import FileResponse

    from fieldclaw_api.services import wiki_layout
    from fieldclaw_api.services.projects import kb_root_for

    wiki = kb_root_for(project) / "wiki"
    try:
        target = wiki_layout.resolve_wiki_path(wiki, file_path)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e)) from e
    if target.suffix.lower() == ".md":
        raise HTTPException(400, "use /wiki/page for markdown")
    # Allow .json for GeoJSON / sitemap artifacts; block pageindex trees via path check
    if target.suffix.lower() == ".json" and "pageindex" in target.parts:
        raise HTTPException(400, "use /wiki/page for pageindex json")
    media = None
    suf = target.suffix.lower()
    if suf == ".pdf":
        media = "application/pdf"
    elif suf in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}:
        media = f"image/{'jpeg' if suf in {'.jpg', '.jpeg'} else suf.lstrip('.')}"
    elif suf in {".geojson", ".json"}:
        media = "application/geo+json"
    return FileResponse(target, media_type=media)


@router.get("/projects/{project_id}/raw/file/{file_path:path}")
def raw_file(
    file_path: str,
    project: Project = Depends(get_project_or_404),
):
    """Serve a file under the project raw/ attachment store."""
    from pathlib import Path

    from fastapi.responses import FileResponse

    from fieldclaw_api.services.projects import kb_root_for

    raw = kb_root_for(project) / "raw"
    rel = Path(file_path)
    if rel.is_absolute() or ".." in rel.parts:
        raise HTTPException(400, "invalid path")
    target = (raw / rel).resolve()
    if not str(target).startswith(str(raw.resolve())) or not target.is_file():
        raise HTTPException(404, "not found")
    media = "application/pdf" if target.suffix.lower() == ".pdf" else None
    return FileResponse(target, media_type=media)


@router.get("/projects/{project_id}/wiki/assets")
def wiki_assets(project: Project = Depends(get_project_or_404)):
    """List PDFs, images, and GeoJSON for in-browser Maps / Documents viewers."""
    from fieldclaw_api.services import wiki_layout
    from fieldclaw_api.services.projects import kb_root_for

    root = kb_root_for(project)
    wiki_layout.ensure_wiki_layout(root)
    return {
        "kb_relpath": project.kb_relpath,
        "assets": wiki_layout.list_wiki_assets(root),
    }


@router.get("/projects/{project_id}/wiki/index")
def wiki_index(
    project: Project = Depends(get_project_or_404), db: Session = Depends(get_db)
):
    return {"markdown": wiki_svc.read_index(db, project.id)}


@router.get("/projects/{project_id}/ui/widgets")
def get_ui_widgets(project: Project = Depends(get_project_or_404)):
    """Agent-authored dashboard widgets (map callouts, legend, stats)."""
    from fieldclaw_api.services.projects import kb_root_for

    path = kb_root_for(project) / "wiki" / "dashboard.json"
    if not path.exists():
        return {"widgets": [], "path": "wiki/dashboard.json"}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"widgets": [], "path": "wiki/dashboard.json", "error": "invalid json"}
    if isinstance(data, list):
        return {"widgets": data, "path": "wiki/dashboard.json"}
    return {
        "widgets": data.get("widgets") or [],
        "path": "wiki/dashboard.json",
        "updated_at": data.get("updated_at"),
    }


@router.put("/projects/{project_id}/ui/widgets")
def put_ui_widgets(
    body: UiWidgetsIn,
    project: Project = Depends(get_project_or_404),
    db: Session = Depends(get_db),
    x_actor_telegram: str | None = Header(default=None, alias="X-Actor-Telegram"),
):
    """Hermes can push generative UI after ingesting a sitemap / wiki content."""
    if x_actor_telegram:
        require_actor(
            project.id,
            {"superintendent", "foreman"},
            required=True,
            x_actor_telegram=x_actor_telegram,
            db=db,
        )
    from fieldclaw_api.services.projects import kb_root_for

    root = kb_root_for(project)
    wiki = root / "wiki"
    wiki.mkdir(parents=True, exist_ok=True)
    path = wiki / "dashboard.json"
    existing: list = []
    if path.exists() and not body.replace:
        try:
            prev = json.loads(path.read_text(encoding="utf-8"))
            existing = prev if isinstance(prev, list) else (prev.get("widgets") or [])
        except json.JSONDecodeError:
            existing = []
    widgets = body.widgets if body.replace else (existing + body.widgets)
    payload = {
        "widgets": widgets,
        "updated_at": datetime.now(UTC).isoformat(),
        "source": "agent",
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    append_event(
        db,
        project.id,
        EventCreate(
            type="wiki.updated",
            source="ui",
            payload={
                "path": "wiki/dashboard.json",
                "widget_count": len(widgets),
                "summary": f"Dashboard widgets updated ({len(widgets)})",
            },
        ),
    )
    return payload


@router.get("/projects/{project_id}/wiki/pages")
def wiki_pages(project: Project = Depends(get_project_or_404)):
    from fieldclaw_api.services import wiki_layout
    from fieldclaw_api.services.projects import kb_root_for

    root = kb_root_for(project)
    wiki_layout.ensure_wiki_layout(root)
    wiki_layout.migrate_flat_wiki(root / "wiki")
    wiki_layout.rebuild_index(root / "wiki", project_id=project.id)
    return {
        "kb_relpath": project.kb_relpath,
        "kb_abs": str(root),
        "engine": "folders+pageindex",
        "pages": wiki_layout.list_wiki_pages(root),
    }


@router.get("/projects/{project_id}/wiki/page")
def wiki_page(
    path: str,
    project: Project = Depends(get_project_or_404),
    db: Session = Depends(get_db),
):
    try:
        return {"path": path, "markdown": wiki_svc.read_page(db, project.id, path)}
    except FileNotFoundError as e:
        raise HTTPException(404, str(e)) from e


@router.post("/projects/{project_id}/wiki/lookup")
def wiki_lookup(
    body: WikiLookupIn,
    project: Project = Depends(get_project_or_404),
    db: Session = Depends(get_db),
):
    return wiki_svc.lookup(db, project.id, body.query)


@router.post("/projects/{project_id}/mail/pull-attachments")
def mail_pull_attachments(
    project: Project = Depends(get_project_or_404), db: Session = Depends(get_db)
):
    try:
        return wiki_svc.ingest_inbox_attachments(db, project.id)
    except Exception as e:
        raise HTTPException(400, str(e)) from e
