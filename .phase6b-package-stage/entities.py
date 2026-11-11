"""SQLAlchemy entities; large audio data stays in managed files."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, ForeignKey, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from batsight.application.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text)
    project_metadata: Mapped[dict] = mapped_column("metadata", JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    recordings: Mapped[list["Recording"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    experiments: Mapped[list["Experiment"]] = relationship(back_populates="project", cascade="all, delete-orphan")


class Recording(Base):
    __tablename__ = "recordings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    managed_filename: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    sample_rate_hz: Mapped[int] = mapped_column(Integer, nullable=False)
    channel_count: Mapped[int] = mapped_column(Integer, nullable=False)
    sample_count: Mapped[int] = mapped_column(Integer, nullable=False)
    duration_s: Mapped[float] = mapped_column(Float, nullable=False)
    audio_metadata: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    project: Mapped[Project | None] = relationship(back_populates="recordings")


class Experiment(Base):
    __tablename__ = "experiments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    kind: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending", index=True)
    configuration: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    project: Mapped[Project] = relationship(back_populates="experiments")
    result: Mapped["ExperimentResult | None"] = relationship(
        back_populates="experiment", cascade="all, delete-orphan", uselist=False
    )


class ExperimentResult(Base):
    __tablename__ = "experiment_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    experiment_id: Mapped[int] = mapped_column(ForeignKey("experiments.id", ondelete="CASCADE"), unique=True, nullable=False)
    result_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    experiment: Mapped[Experiment] = relationship(back_populates="result")
