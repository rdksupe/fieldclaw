from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class EventCreate(BaseModel):
    type: str
    zone_id: str | None = None
    actor_id: str | None = None
    task_id: str | None = None
    po_id: str | None = None
    source: str = "api"
    payload: dict[str, Any] = Field(default_factory=dict)
    proof_ids: list[str] = Field(default_factory=list)


class EventOut(BaseModel):
    id: str
    project_id: str
    type: str
    zone_id: str | None
    actor_id: str | None
    task_id: str | None
    po_id: str | None
    source: str
    payload: dict[str, Any]
    proof_ids: list[str]
    created_at: datetime

    model_config = {"from_attributes": True}


class ZoneOut(BaseModel):
    id: str
    project_id: str
    label: str
    polygon: list[list[float]]
    status: str
    progress_pct: float


class ProjectOut(BaseModel):
    id: str
    name: str
    inbox_email: str | None = None
    kb_relpath: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ProjectCreate(BaseModel):
    name: str
    inbox_username: str | None = None
    inbox_email: str | None = None
    provision_inbox: bool = True
    with_demo_zones: bool = False


class ZoneCreate(BaseModel):
    label: str
    polygon: list[list[float]] | None = None
    status: str = "grey"
    progress_pct: float = 0.0


class SitemapImportIn(BaseModel):
    """GeoJSON FeatureCollection (or Feature) body. Prefer POST multipart /sitemap/upload."""

    geojson: dict[str, Any]
    replace: bool = True
    source_name: str | None = "sitemap.geojson"


class PairingApproveIn(BaseModel):
    code: str
    platform: str = "telegram"
    project_id: str | None = None
    bind_role: str = "foreman"
    person_name: str | None = None


class ForemanRegisterIn(BaseModel):
    name: str = "James Ortiz"
    email: str | None = None


class AdminRegisterIn(BaseModel):
    name: str
    email: str | None = None
    telegram_id: str | None = None


class SuperReplyIn(BaseModel):
    event_id: str
    message: str


class MailInjectIn(BaseModel):
    thread_id: str
    subject: str
    body: str
    in_reply_to: str | None = None
    depth: int = 0
    from_addr: str | None = None


class MailSendIn(BaseModel):
    thread_id: str
    to: str
    subject: str
    body: str
    in_reply_to: str | None = None


class WikiLookupIn(BaseModel):
    query: str


class SeekIn(BaseModel):
    cursor: int = 0
    speed: float = 1.0


class PersonOut(BaseModel):
    id: str
    project_id: str
    name: str
    role: str
    telegram_id: str | None
    email: str | None

    model_config = {"from_attributes": True}


class PersonTelegramIn(BaseModel):
    telegram_id: str | None


class TaskOut(BaseModel):
    id: str
    project_id: str
    zone_id: str | None
    title: str
    status: str
    at_risk: bool

    model_config = {"from_attributes": True}


class TaskCreate(BaseModel):
    title: str
    zone_id: str | None = None
    status: str = "todo"
    at_risk: bool = False


class TaskPatch(BaseModel):
    title: str | None = None
    zone_id: str | None = None
    status: str | None = None
    at_risk: bool | None = None


class UiWidgetsIn(BaseModel):
    """Generative dashboard widgets the agent can push after reading map/wiki content."""

    widgets: list[dict[str, Any]]
    replace: bool = True
