import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


def _id() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Dataset(Base):
    __tablename__ = "datasets"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    name: Mapped[str] = mapped_column(String(200))
    ext: Mapped[str] = mapped_column(String(8))
    status: Mapped[str] = mapped_column(String(20), default="Processing")
    n_rows: Mapped[int] = mapped_column(Integer, default=0)
    n_cols: Mapped[int] = mapped_column(Integer, default=0)
    quality_before: Mapped[float | None] = mapped_column(Float, nullable=True)
    quality_after: Mapped[float | None] = mapped_column(Float, nullable=True)
    analysis: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # profil, issues, steps, skor
    after_analysis: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Pipeline(Base):
    __tablename__ = "pipelines"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.id"))
    name: Mapped[str] = mapped_column(String(200))
    version: Mapped[str] = mapped_column(String(20), default="1.0.0")
    steps: Mapped[list] = mapped_column(JSON)
    quality_after: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="Ready")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class PipelineRun(Base):
    __tablename__ = "pipeline_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    pipeline_id: Mapped[str] = mapped_column(ForeignKey("pipelines.id"))
    dataset_id: Mapped[str] = mapped_column(String(36))
    summary: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    action: Mapped[str] = mapped_column(String(60))
    entity_id: Mapped[str] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
