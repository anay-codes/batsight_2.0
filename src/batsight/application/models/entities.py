"""SQLAlchemy entities; large audio data stays in managed files."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
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
    recording_sessions: Mapped[list["RecordingSession"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    measurements: Mapped[list["Measurement"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    rooms: Mapped[list["Room"]] = relationship(back_populates="project", cascade="all, delete-orphan")


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
    session_links: Mapped[list["RecordingSessionRecording"]] = relationship(back_populates="recording", cascade="all, delete-orphan")


class RecordingSession(Base):
    __tablename__ = "recording_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    provenance: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    calibration_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    analysis_configuration_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    project: Mapped[Project] = relationship(back_populates="recording_sessions")
    recordings: Mapped[list["RecordingSessionRecording"]] = relationship(back_populates="recording_session", cascade="all, delete-orphan")
    extractions: Mapped[list["RecordingSessionExtraction"]] = relationship(back_populates="recording_session", cascade="all, delete-orphan")


class RecordingSessionRecording(Base):
    __tablename__ = "recording_session_recordings"
    __table_args__ = (UniqueConstraint("session_id", "recording_id", name="uq_session_recording"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("recording_sessions.id", ondelete="CASCADE"), index=True, nullable=False)
    recording_id: Mapped[int] = mapped_column(ForeignKey("recordings.id", ondelete="CASCADE"), index=True, nullable=False)
    recording_start_time_s: Mapped[float | None] = mapped_column(Float)
    channel_mapping_json: Mapped[list] = mapped_column(JSON, nullable=False)
    event_ids_json: Mapped[list | None] = mapped_column(JSON)

    recording_session: Mapped[RecordingSession] = relationship(back_populates="recordings")
    recording: Mapped[Recording] = relationship(back_populates="session_links")


class RecordingSessionExtraction(Base):
    __tablename__ = "recording_session_extractions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("recording_sessions.id", ondelete="CASCADE"), index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="queued", index=True)
    result_json: Mapped[dict | None] = mapped_column(JSON)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    recording_session: Mapped[RecordingSession] = relationship(back_populates="extractions")


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


class Measurement(Base):
    __tablename__ = "measurements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    chirp_config: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    speed_of_sound_m_s: Mapped[float] = mapped_column(Float, nullable=False, default=343.0)
    direct_lag_s: Mapped[float | None] = mapped_column(Float)
    direct_distance_m: Mapped[float | None] = mapped_column(Float)
    echo_candidates: Mapped[list[dict]] = mapped_column(JSON, nullable=False, default=list)
    echo_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    closest_reflector_m: Mapped[float | None] = mapped_column(Float)
    farthest_reflector_m: Mapped[float | None] = mapped_column(Float)
    scan_angle_deg: Mapped[float | None] = mapped_column(Float)
    raw_wav_path: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    project: Mapped[Project | None] = relationship(back_populates="measurements")


class Room(Base):
    __tablename__ = "rooms"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    length_x_m: Mapped[float] = mapped_column(Float, nullable=False)
    width_y_m: Mapped[float] = mapped_column(Float, nullable=False)
    height_z_m: Mapped[float] = mapped_column(Float, nullable=False, default=2.8)
    floor_area_m2: Mapped[float] = mapped_column(Float, nullable=False)
    room_volume_m3: Mapped[float] = mapped_column(Float, nullable=False)
    device_position_m: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    wall_distances: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    obstacles: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    scan_metadata: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    project: Mapped[Project | None] = relationship(back_populates="rooms")
