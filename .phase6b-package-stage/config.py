"""Environment-backed local application settings."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Settings:
    app_name: str = "BatSight"
    version: str = "0.1.0"
    data_dir: Path = Path.home() / ".batsight"
    database_url: str | None = None
    max_upload_size_bytes: int = 100 * 1024 * 1024
    max_recording_duration_s: float = 3600.0
    max_analysis_samples: int = 2_000_000
    max_channels: int = 64
    min_sample_rate_hz: int = 8000
    max_sample_rate_hz: int = 192000
    host: str = "127.0.0.1"
    port: int = 8000

    def __post_init__(self) -> None:
        if self.max_upload_size_bytes <= 0 or self.max_recording_duration_s <= 0 or self.max_analysis_samples <= 0:
            raise ValueError("upload size and maximum recording/analysis settings must be positive")
        if self.max_channels < 1 or self.min_sample_rate_hz < 1:
            raise ValueError("channel and sample-rate limits must be positive")
        if self.max_sample_rate_hz < self.min_sample_rate_hz:
            raise ValueError("maximum sample rate must not be below minimum sample rate")
        if not 1 <= self.port <= 65535:
            raise ValueError("port must be in [1, 65535]")

    @classmethod
    def from_environment(cls) -> "Settings":
        data_dir = Path(os.environ.get("BATSIGHT_DATA_DIR", str(Path.home() / ".batsight"))).expanduser()
        return cls(
            app_name=os.environ.get("BATSIGHT_APP_NAME", "BatSight"),
            version=os.environ.get("BATSIGHT_VERSION", "0.1.0"),
            data_dir=data_dir,
            database_url=os.environ.get("BATSIGHT_DATABASE_URL"),
            max_upload_size_bytes=int(os.environ.get("BATSIGHT_MAX_UPLOAD_BYTES", str(100 * 1024 * 1024))),
            max_recording_duration_s=float(os.environ.get("BATSIGHT_MAX_RECORDING_SECONDS", "3600")),
            max_analysis_samples=int(os.environ.get("BATSIGHT_MAX_ANALYSIS_SAMPLES", "2000000")),
            host=os.environ.get("BATSIGHT_HOST", "127.0.0.1"),
            port=int(os.environ.get("BATSIGHT_PORT", "8000")),
        )

    @property
    def recordings_dir(self) -> Path:
        return self.data_dir / "recordings"

    @property
    def exports_dir(self) -> Path:
        return self.data_dir / "exports"

    @property
    def resolved_database_url(self) -> str:
        if self.database_url:
            if not self.database_url.startswith("sqlite:"):
                raise ValueError("BATSIGHT_DATABASE_URL must use SQLite")
            return self.database_url
        return f"sqlite:///{(self.data_dir / 'batsight.sqlite3').as_posix()}"

    def ensure_directories(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.recordings_dir.mkdir(parents=True, exist_ok=True)
        self.exports_dir.mkdir(parents=True, exist_ok=True)
        if self.database_url:
            from sqlalchemy.engine import make_url

            url = make_url(self.database_url)
            if url.get_backend_name() != "sqlite":
                raise ValueError("BATSIGHT_DATABASE_URL must use SQLite")
            database = url.database
            if database and database != ":memory:" and not database.startswith("file:"):
                Path(database).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
