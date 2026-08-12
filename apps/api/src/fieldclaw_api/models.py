import uuid
from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from fieldclaw_api.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(UTC)


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String, nullable=False)
    inbox_email: Mapped[str | None] = mapped_column(String, nullable=True)
    kb_relpath: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    people = relationship("Person", back_populates="project")
    zones = relationship("Zone", back_populates="project")
    events = relationship("Event", back_populates="project")


class Person(Base):
    __tablename__ = "people"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    role: Mapped[str] = mapped_column(String, nullable=False)
    telegram_id: Mapped[str | None] = mapped_column(String, nullable=True)
    email: Mapped[str | None] = mapped_column(String, nullable=True)

    project = relationship("Project", back_populates="people")


class Zone(Base):
    __tablename__ = "zones"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False)
    label: Mapped[str] = mapped_column(String, nullable=False)
    polygon_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    status: Mapped[str] = mapped_column(String, nullable=False, default="grey")
    progress_pct: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    project = relationship("Project", back_populates="zones")


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False)
    zone_id: Mapped[str | None] = mapped_column(ForeignKey("zones.id"), nullable=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="todo")
    at_risk: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class PurchaseOrder(Base):
    __tablename__ = "pos"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False)
    po_number: Mapped[str] = mapped_column(String, nullable=False)
    material: Mapped[str] = mapped_column(String, nullable=False)
    qty: Mapped[str] = mapped_column(String, nullable=False, default="")
    supplier: Mapped[str] = mapped_column(String, nullable=False, default="")
    eta: Mapped[str] = mapped_column(String, nullable=False, default="")
    status: Mapped[str] = mapped_column(String, nullable=False, default="ordered")


class Event(Base):
    __tablename__ = "events"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False)
    type: Mapped[str] = mapped_column(String, nullable=False)
    zone_id: Mapped[str | None] = mapped_column(ForeignKey("zones.id"), nullable=True)
    actor_id: Mapped[str | None] = mapped_column(ForeignKey("people.id"), nullable=True)
    task_id: Mapped[str | None] = mapped_column(ForeignKey("tasks.id"), nullable=True)
    po_id: Mapped[str | None] = mapped_column(ForeignKey("pos.id"), nullable=True)
    source: Mapped[str] = mapped_column(String, nullable=False, default="api")
    payload_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    proof_ids_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    project = relationship("Project", back_populates="events")


class Proof(Base):
    __tablename__ = "proofs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False)
    event_id: Mapped[str | None] = mapped_column(ForeignKey("events.id"), nullable=True)
    kind: Mapped[str] = mapped_column(String, nullable=False)
    path: Mapped[str] = mapped_column(String, nullable=False)
    meta_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class MailMessage(Base):
    __tablename__ = "mail_messages"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False)
    thread_id: Mapped[str] = mapped_column(String, nullable=False)
    direction: Mapped[str] = mapped_column(String, nullable=False)
    subject: Mapped[str] = mapped_column(String, nullable=False, default="")
    body: Mapped[str] = mapped_column(Text, nullable=False, default="")
    in_reply_to: Mapped[str | None] = mapped_column(String, nullable=True)
    depth: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    parsed_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class UiSession(Base):
    """Browser login. Holds the selected project so it follows the session
    rather than whichever machine the dashboard was last opened on."""

    __tablename__ = "ui_sessions"

    token: Mapped[str] = mapped_column(String, primary_key=True)
    project_id: Mapped[str | None] = mapped_column(
        ForeignKey("projects.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now
    )


class SimRun(Base):
    __tablename__ = "sim_runs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False)
    scenario: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="idle")
    speed: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    cursor: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
