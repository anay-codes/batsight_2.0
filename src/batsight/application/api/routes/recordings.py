"""Safe WAV upload and recording metadata routes."""

import json

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from batsight.application.api.schemas.contracts import RecordingResponse
from batsight.application.api.serializers import utc_datetime
from batsight.application.dependencies import database_session
from batsight.application.models.entities import Recording
from batsight.application.services.recording_service import RecordingService, UploadTooLargeError
from batsight.application.api.schemas.contracts import RecordingAnalysisRequest, RecordingAnalysisResponse
from batsight.application.services.recording_analysis_service import RecordingAnalysisService
from batsight.application.services.signal_service import SignalProcessingService

router = APIRouter(prefix="/api/recordings", tags=["recordings"])


def _response(recording: Recording) -> RecordingResponse:
    return RecordingResponse(
        id=recording.id, project_id=recording.project_id, name=recording.name,
        description=recording.description, original_filename=recording.original_filename,
        file_size_bytes=recording.file_size_bytes, sample_rate_hz=recording.sample_rate_hz,
        channel_count=recording.channel_count, sample_count=recording.sample_count,
        duration_s=recording.duration_s, metadata=recording.audio_metadata,
        created_at=utc_datetime(recording.created_at),
    )


@router.post("", response_model=RecordingResponse, status_code=status.HTTP_201_CREATED,
            summary="Upload and register a WAV recording")
async def create_recording(
    request: Request,
    file: UploadFile = File(..., description="PCM or floating-point WAV; original bytes are preserved"),
    name: str = Form(..., min_length=1, max_length=200),
    description: str | None = Form(default=None, max_length=4000),
    project_id: int | None = Form(default=None),
    metadata_json: str = Form(default="{}", description="Optional JSON object with acquisition metadata"),
    session: Session = Depends(database_session),
):
    try:
        metadata = json.loads(metadata_json)
        if not isinstance(metadata, dict):
            raise ValueError("metadata_json must encode an object")
        if not name.strip():
            raise ValueError("Recording name cannot be blank")
        recording = await RecordingService(request.app.state.settings).register_upload(
            session, file, name=name.strip(), description=description,
            project_id=project_id, metadata=metadata,
        )
    except UploadTooLargeError as exc:
        raise HTTPException(413, str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except (ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(422, str(exc)) from exc
    return _response(recording)


@router.get("", response_model=list[RecordingResponse], summary="List recordings")
def list_recordings(project_id: int | None = None, session: Session = Depends(database_session)):
    query = select(Recording).order_by(Recording.created_at.desc())
    if project_id is not None:
        query = query.where(Recording.project_id == project_id)
    return [_response(row) for row in session.scalars(query).all()]


@router.get("/{recording_id}", response_model=RecordingResponse, summary="Retrieve recording metadata")
def get_recording(recording_id: int, session: Session = Depends(database_session)):
    recording = session.get(Recording, recording_id)
    if recording is None:
        raise HTTPException(404, "Recording not found")
    return _response(recording)


@router.get("/{recording_id}/audio", summary="Download original managed WAV bytes")
def download_recording(recording_id: int, request: Request, session: Session = Depends(database_session)):
    recording = session.get(Recording, recording_id)
    if recording is None:
        raise HTTPException(404, "Recording not found")
    try:
        path = RecordingService(request.app.state.settings).safe_managed_path(recording)
    except ValueError as exc:
        raise HTTPException(500, "Recording path is outside managed storage") from exc
    if not path.is_file():
        raise HTTPException(404, "Recording audio file is unavailable")
    return FileResponse(path, media_type="audio/wav", filename=recording.original_filename)


@router.post("/{recording_id}/analysis", response_model=RecordingAnalysisResponse,
             summary="Matched-filter and peak analysis for one recording channel")
def analyze_recording(recording_id: int, payload: RecordingAnalysisRequest, request: Request,
                      session: Session = Depends(database_session)):
    recording = session.get(Recording, recording_id)
    if recording is None:
        raise HTTPException(404, "Recording not found")
    service = RecordingService(request.app.state.settings)
    try:
        path = service.safe_managed_path(recording)
        signal_service = SignalProcessingService()
        reference = signal_service.generate_reference(
            waveform=payload.waveform,
            sample_rate_hz=recording.sample_rate_hz,
            duration_s=payload.reference_duration_s,
            start_frequency_hz=payload.start_frequency_hz,
            end_frequency_hz=payload.end_frequency_hz,
            amplitude=payload.amplitude,
        )
        return RecordingAnalysisService(request.app.state.settings).analyze(
            path,
            recording_id=str(recording_id),
            channel_index=payload.channel_index,
            reference=reference,
            normalization=payload.normalization,
            window_length_samples=payload.window_length_samples,
            thr1=payload.thr1,
            thr2=payload.thr2,
            spectrogram_nperseg=payload.spectrogram_nperseg,
        )
    except IndexError as exc:
        raise HTTPException(422, str(exc)) from exc
    except (ValueError, OSError) as exc:
        raise HTTPException(422, str(exc)) from exc


@router.delete("/{recording_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete recording metadata and managed WAV")
def delete_recording(recording_id: int, request: Request, session: Session = Depends(database_session)):
    recording = session.get(Recording, recording_id)
    if recording is None:
        raise HTTPException(404, "Recording not found")
    service = RecordingService(request.app.state.settings)
    try:
        path = service.safe_managed_path(recording)
    except ValueError as exc:
        raise HTTPException(500, "Recording path is outside managed storage") from exc
    session.delete(recording)
    session.commit()
    path.unlink(missing_ok=True)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
