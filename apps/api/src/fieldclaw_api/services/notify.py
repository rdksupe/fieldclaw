import logging

import httpx
from sqlalchemy.orm import Session

from fieldclaw_api.config import settings
from fieldclaw_api.models import Event, Person
from fieldclaw_api.schemas import EventCreate
from fieldclaw_api.services.logbook import append_event

log = logging.getLogger(__name__)


async def send_telegram(chat_id: str, text: str) -> dict:
    token = settings.telegram_bot_token
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN not configured")
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(url, json={"chat_id": chat_id, "text": text})
        r.raise_for_status()
        return r.json()


def resolve_telegram_chat_id(db: Session, project_id: str, role: str) -> str | None:
    person = (
        db.query(Person)
        .filter(Person.project_id == project_id, Person.role == role)
        .first()
    )
    if person and person.telegram_id:
        return person.telegram_id
    if role == "foreman":
        return settings.telegram_foreman_chat_id
    if role in ("superintendent", "super"):
        return settings.telegram_super_chat_id
    return None


async def notify_role_telegram(
    db: Session, project_id: str, role: str, message: str
) -> Event:
    """Send Telegram and only log notify.sent when delivery succeeds.

    Failures log notify.failed — never claim email+telegram without proof.
    """
    chat_id = resolve_telegram_chat_id(db, project_id, role)
    if not chat_id:
        outs = append_event(
            db,
            project_id,
            EventCreate(
                type="notify.failed",
                source="api",
                payload={
                    "channel": "telegram",
                    "role": role,
                    "message": message,
                    "error": f"No {role} telegram_id configured",
                    "delivered": False,
                },
            ),
        )
        raise RuntimeError(f"No {role} telegram_id configured")

    try:
        result = await send_telegram(chat_id, message)
    except Exception as e:
        outs = append_event(
            db,
            project_id,
            EventCreate(
                type="notify.failed",
                source="api",
                payload={
                    "channel": "telegram",
                    "role": role,
                    "chat_id": chat_id,
                    "message": message,
                    "error": str(e)[:500],
                    "delivered": False,
                },
            ),
        )
        raise

    ok = bool(result.get("ok"))
    outs = append_event(
        db,
        project_id,
        EventCreate(
            type="notify.sent" if ok else "notify.failed",
            source="api",
            payload={
                "channel": "telegram",
                "role": role,
                "chat_id": chat_id,
                "message": message,
                "telegram_response_ok": ok,
                "delivered": ok,
            },
        ),
    )
    if not ok:
        raise RuntimeError(f"Telegram API rejected message: {result}")
    return db.get(Event, outs[-1].id)  # type: ignore[return-value]


async def notify_foreman_telegram(db: Session, project_id: str, message: str) -> Event:
    return await notify_role_telegram(db, project_id, "foreman", message)


def parse_mail_intent(subject: str, body: str) -> dict:
    text = f"{subject}\n{body}".lower()
    intent = "update"
    if "delay" in text or "eta" in text or "thursday" in text or "monday" in text:
        intent = "schedule_change"
    if "confirm" in text:
        intent = "confirm"
    if "rfi" in text:
        intent = "rfi"
    return {"intent": intent, "summary": (body or subject)[:240]}
