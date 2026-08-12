"""AgentMail inbox + attachment helpers for per-project mail isolation."""

from __future__ import annotations

import base64
import re
from pathlib import Path

import httpx

from fieldclaw_api.config import settings


def _api_key() -> str:
    key = (settings.agentmail_api_key or "").strip()
    if not key:
        # fall back to Hermes env file
        env_path = settings.hermes_home / ".env"
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                if line.startswith("AGENTMAIL_API_KEY="):
                    key = line.split("=", 1)[1].strip().strip('"').strip("'")
                    break
    if not key:
        raise RuntimeError("AGENTMAIL_API_KEY not configured")
    return key


def _client() -> httpx.Client:
    return httpx.Client(
        base_url="https://api.agentmail.to",
        headers={
            "Authorization": f"Bearer {_api_key()}",
            "Accept": "application/json",
        },
        timeout=60.0,
    )


def _slug_username(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return (s or "fieldclaw")[:40]


def create_inbox(username: str | None = None, display_name: str | None = None) -> dict:
    """Create an AgentMail inbox. Returns {inbox_id, email, ...}."""
    uname = _slug_username(username or "fieldclaw-proj")
    body: dict = {"username": uname}
    if display_name:
        body["display_name"] = display_name
    with _client() as client:
        r = client.post("/v0/inboxes", json=body)
        if r.status_code == 403 and "already_exists" in r.text:
            # try suggested username or reuse exact address if listed
            try:
                payload = r.json()
                suggestions = payload.get("suggestions") or []
                if suggestions:
                    body["username"] = suggestions[0]
                    r = client.post("/v0/inboxes", json=body)
                else:
                    email = f"{uname}@agentmail.to"
                    return {"inbox_id": email, "email": email, "reused": True}
            except Exception:
                pass
        r.raise_for_status()
        data = r.json()
    email = data.get("email") or data.get("inbox_id")
    return {
        "inbox_id": data.get("inbox_id") or email,
        "email": email,
        "reused": False,
        "raw": data,
    }


def send_with_attachments(
    from_inbox: str,
    to: str | list[str],
    subject: str,
    text: str,
    files: list[tuple[str, bytes, str]],
) -> dict:
    """Send mail from an AgentMail inbox with binary attachments (base64)."""
    from agentmail import AgentMail
    from agentmail.attachments.types.send_attachment import SendAttachment

    client = AgentMail(api_key=_api_key())
    attachments = [
        SendAttachment(
            filename=name,
            content_type=ctype,
            content=base64.b64encode(data).decode("ascii"),
            content_disposition="attachment",
        )
        for name, data, ctype in files
    ]
    resp = client.inboxes.messages.send(
        inbox_id=from_inbox,
        to=to,
        subject=subject,
        text=text,
        attachments=attachments,
    )
    return {"message_id": getattr(resp, "message_id", None) or str(resp)}


def pull_attachments_into_dir(
    inbox_id: str, dest_dir: Path, limit: int = 20
) -> list[dict]:
    """Download recent attachments from an inbox into dest_dir."""
    from agentmail import AgentMail

    client = AgentMail(api_key=_api_key())
    dest_dir.mkdir(parents=True, exist_ok=True)
    listed = client.inboxes.messages.list(inbox_id=inbox_id, limit=limit)
    messages = getattr(listed, "messages", None) or []
    saved: list[dict] = []
    for msg in messages:
        mid = getattr(msg, "message_id", None) or getattr(msg, "id", None)
        # list payload can omit attachment bodies; fetch full message
        if mid:
            try:
                full = client.inboxes.messages.get(inbox_id=inbox_id, message_id=mid)
                atts = (
                    getattr(full, "attachments", None)
                    or getattr(msg, "attachments", None)
                    or []
                )
            except Exception:
                atts = getattr(msg, "attachments", None) or []
        else:
            atts = getattr(msg, "attachments", None) or []
        for att in atts:
            aid = getattr(att, "attachment_id", None) or getattr(att, "id", None)
            fname = getattr(att, "filename", None) or f"{aid or 'file'}.bin"
            if not mid or not aid:
                continue
            blob = client.inboxes.messages.get_attachment(
                inbox_id=inbox_id, message_id=mid, attachment_id=aid
            )
            data = (
                blob
                if isinstance(blob, (bytes, bytearray))
                else getattr(blob, "content", None)
            )
            if isinstance(data, str):
                data = base64.b64decode(data)
            if not data:
                url = getattr(blob, "download_url", None)
                if url:
                    with httpx.Client(timeout=120.0) as http:
                        r = http.get(url)
                        r.raise_for_status()
                        data = r.content
            if not data:
                continue
            path = dest_dir / Path(fname).name
            path.write_bytes(data)
            saved.append(
                {
                    "message_id": mid,
                    "filename": path.name,
                    "path": str(path),
                    "bytes": len(data),
                }
            )
    return saved
