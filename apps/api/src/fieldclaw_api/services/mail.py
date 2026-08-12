import json
from email.message import EmailMessage

import aiosmtplib
from sqlalchemy.orm import Session

from fieldclaw_api.config import settings
from fieldclaw_api.models import MailMessage
from fieldclaw_api.schemas import EventCreate, MailInjectIn, MailSendIn
from fieldclaw_api.services.logbook import append_event
from fieldclaw_api.services.notify import parse_mail_intent


def list_threads(db: Session, project_id: str) -> list[dict]:
    rows = (
        db.query(MailMessage)
        .filter(MailMessage.project_id == project_id)
        .order_by(MailMessage.created_at.asc())
        .all()
    )
    threads: dict[str, list] = {}
    for m in rows:
        threads.setdefault(m.thread_id, []).append(
            {
                "id": m.id,
                "thread_id": m.thread_id,
                "direction": m.direction,
                "subject": m.subject,
                "body": m.body,
                "in_reply_to": m.in_reply_to,
                "depth": m.depth,
                "parsed": json.loads(m.parsed_json),
                "created_at": m.created_at.isoformat(),
            }
        )
    return [{"thread_id": tid, "messages": msgs} for tid, msgs in threads.items()]


def inject_mail(db: Session, project_id: str, body: MailInjectIn) -> dict:
    parsed = parse_mail_intent(body.subject, body.body)
    msg = MailMessage(
        project_id=project_id,
        thread_id=body.thread_id,
        direction="inbound",
        subject=body.subject,
        body=body.body,
        in_reply_to=body.in_reply_to,
        depth=body.depth,
        parsed_json=json.dumps(parsed),
    )
    db.add(msg)
    db.flush()

    events = append_event(
        db,
        project_id,
        EventCreate(
            type="email.inbound",
            source="mail",
            payload={
                "thread_id": body.thread_id,
                "mail_id": msg.id,
                "subject": body.subject,
                "depth": body.depth,
                "from": body.from_addr,
            },
        ),
    )
    parsed_ev = append_event(
        db,
        project_id,
        EventCreate(
            type="email.parsed",
            source="mail",
            payload={"mail_id": msg.id, "thread_id": body.thread_id, **parsed},
        ),
    )
    if parsed.get("intent") == "schedule_change":
        append_event(
            db,
            project_id,
            EventCreate(
                type="schedule.flagged",
                source="mail",
                payload={
                    "reason": "email_schedule_change",
                    "mail_id": msg.id,
                    "thread_id": body.thread_id,
                },
            ),
        )

    return {
        "mail_id": msg.id,
        "parsed": parsed,
        "events": [e.model_dump(mode="json") for e in events + parsed_ev],
    }


async def send_mail(db: Session, project_id: str, body: MailSendIn) -> dict:
    if not settings.smtp_user or not settings.smtp_password:
        raise RuntimeError("SMTP_USER / SMTP_PASSWORD not configured")

    from_addr = settings.smtp_from or settings.smtp_user
    message = EmailMessage()
    message["From"] = from_addr
    message["To"] = body.to
    message["Subject"] = body.subject
    if body.in_reply_to:
        message["In-Reply-To"] = body.in_reply_to
        message["References"] = body.in_reply_to
    message.set_content(body.body)

    await aiosmtplib.send(
        message,
        hostname=settings.smtp_host,
        port=settings.smtp_port,
        username=settings.smtp_user,
        password=settings.smtp_password,
        start_tls=True,
    )

    depth = 0
    if body.in_reply_to:
        parent = db.get(MailMessage, body.in_reply_to)
        if parent:
            depth = parent.depth + 1

    msg = MailMessage(
        project_id=project_id,
        thread_id=body.thread_id,
        direction="outbound",
        subject=body.subject,
        body=body.body,
        in_reply_to=body.in_reply_to,
        depth=depth,
        parsed_json=json.dumps({"intent": "outbound"}),
    )
    db.add(msg)
    db.flush()

    outs = append_event(
        db,
        project_id,
        EventCreate(
            type="email.outbound",
            source="mail",
            payload={
                "thread_id": body.thread_id,
                "mail_id": msg.id,
                "to": body.to,
                "subject": body.subject,
                "depth": depth,
            },
        ),
    )
    return {"mail_id": msg.id, "events": [e.model_dump(mode="json") for e in outs]}
