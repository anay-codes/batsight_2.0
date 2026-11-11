"""Managed recording upload, WAV validation, and safe deletion."""

from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Any

from fastapi import UploadFile
from sqlalchemy.orm import Session

from batsight.application.config import Settings
from batsight.application.models.entities import Project, Recording
from batsight.application.services.audio_service import AudioService


class UploadTooLargeError(ValueError):
    """An upload exceeded its configured maximum size."""


class RecordingService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.audio_service = AudioService(settings)

    async def register_upload(
        self, session: Session, upload: UploadFile, *, name: str,
        description: str | None, project_id: int | None,
        metadata: dict[str, Any] | None = None,
    ) -> Recording:
        supplied_name = upload.filename or ""
        basename = supplied_name.replace("\\", "/").split("/")[-1]
        if Path(basename).suffix.lower() != ".wav":
            raise ValueError("Only WAV uploads with a .wav filename are supported")
        if project_id is not None and session.get(Project, project_id) is None:
            raise LookupError("Project not found")

        token = uuid.uuid4().hex
        temp_path = self.settings.recordings_dir / f".{token}.uploading"
        managed_filename = f"{token}.wav"
        final_path = self.settings.recordings_dir / managed_filename
        byte_count = 0
        try:
            with temp_path.open("xb") as handle:
                while chunk := await upload.read(1024 * 1024):
                    byte_count += len(chunk)
                    if byte_count > self.settings.max_upload_size_bytes:
                        raise UploadTooLargeError("Upload exceeds the configured file-size limit")
                    handle.write(chunk)
                handle.flush()
                os.fsync(handle.fileno())
            if byte_count == 0:
                raise ValueError("Uploaded file is empty")
            wav = self.audio_service.validate_wav(temp_path)
            # UUID names are internal; exclusive creation prevents accidental overwrite.
            os.rename(temp_path, final_path)
            recording = Recording(
                project_id=project_id,
                name=name,
                description=description,
                original_filename=basename[:255],
                managed_filename=managed_filename,
                file_path=str(final_path.resolve()),
                file_size_bytes=wav.file_size_bytes,
                sample_rate_hz=wav.sample_rate_hz,
                channel_count=wav.channel_count,
                sample_count=wav.sample_count,
                duration_s=wav.duration_s,
                audio_metadata={**(metadata or {}), "sample_dtype": wav.sample_dtype},
            )
            session.add(recording)
            session.commit()
            session.refresh(recording)
            return recording
        except Exception:
            session.rollback()
            final_path.unlink(missing_ok=True)
            raise
        finally:
            temp_path.unlink(missing_ok=True)
            await upload.close()

    def safe_managed_path(self, recording: Recording) -> Path:
        root = self.settings.recordings_dir.resolve()
        candidate = Path(recording.file_path).resolve()
        if candidate.parent != root or candidate.name != recording.managed_filename:
            raise ValueError("Stored recording path is outside managed storage")
        if Path(recording.managed_filename).suffix != ".wav" or len(recording.managed_filename) != 36:
            raise ValueError("Stored recording filename is not a managed WAV name")
        return candidate

    def delete_managed_file(self, recording: Recording) -> None:
        self.safe_managed_path(recording).unlink(missing_ok=True)
