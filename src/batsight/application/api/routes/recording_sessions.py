"""Versioned API for calibrated multichannel recording sessions."""

from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from batsight.application.api.schemas.recording_sessions import (
    ExtractionQueuedResponse,
    ExtractionResponse,
    RecordingSessionCreate,
    RecordingSessionResponse,
    RecordingSessionValidationResponse,
    SessionRecordingAttach,
    RecordingSessionUpdate,
)
from batsight.application.dependencies import database_session
from batsight.application.models.entities import (
    Project,
    RecordingSession,
    RecordingSessionExtraction,
    RecordingSessionRecording,
)
from batsight.application.services.recording_session_service import RecordingSessionService

router = APIRouter(prefix="/api/v1/recording-sessions", tags=["recording sessions"])


def _service(request):
    return RecordingSessionService(request.app.state.settings, request.app.state.session_factory)


def _response(session: RecordingSession) -> RecordingSessionResponse:
    latest = max(session.extractions, key=lambda item: item.created_at, default=None)
    return RecordingSessionResponse(
        session_id=session.id,
        project_id=session.project_id,
        name=session.name,
        provenance=session.provenance,
        status=session.status,
        calibration=session.calibration_json,
        analysis_configuration=session.analysis_configuration_json,
        recordings=[{
            "recording_id": link.recording.id,
            "filename": link.recording.original_filename,
            "sample_rate_hz": link.recording.sample_rate_hz,
            "channel_count": link.recording.channel_count,
            "duration_s": link.recording.duration_s,
            "recording_start_time_s": link.recording_start_time_s,
            "channel_mapping": link.channel_mapping_json,
            "event_ids": link.event_ids_json,
        } for link in session.recordings],
        latest_extraction_id=latest.id if latest else None,
        created_at=session.created_at.isoformat(),
    )


def _extraction_response(row: RecordingSessionExtraction) -> ExtractionResponse:
    return ExtractionResponse(
        session_id=row.session_id,
        extraction_id=row.id,
        status=row.status,
        error_message=row.error_message,
        result=row.result_json,
        created_at=row.created_at.isoformat(),
        completed_at=row.completed_at.isoformat() if row.completed_at else None,
    )


@router.post("", response_model=RecordingSessionResponse, status_code=status.HTTP_201_CREATED,
            summary="Create a calibrated multichannel recording session")
def create_recording_session(payload: RecordingSessionCreate, request: Request, db: Session = Depends(database_session)):
    if db.get(Project, payload.project_id) is None:
        raise HTTPException(404, "Project not found")
    session = RecordingSession(
        id=str(uuid4()),
        project_id=payload.project_id,
        name=payload.name.strip(),
        provenance=payload.provenance,
        status="draft",
        calibration_json=payload.calibration.model_dump(mode="json"),
        analysis_configuration_json=payload.analysis_configuration.model_dump(mode="json"),
    )
    if not session.name:
        raise HTTPException(422, "Session name cannot be blank")
    db.add(session)
    db.commit()
    if payload.recordings:
        try:
            _service(request).attach_recordings(db, session.id, payload.recordings)
        except LookupError as exc:
            db.delete(session)
            db.commit()
            raise HTTPException(404, str(exc)) from exc
        except ValueError as exc:
            db.delete(session)
            db.commit()
            raise HTTPException(422, str(exc)) from exc
    db.refresh(session)
    return _response(session)


@router.get("", response_model=list[RecordingSessionResponse], summary="List project recording sessions")
def list_recording_sessions(project_id: int | None = None, db: Session = Depends(database_session)):
    query = select(RecordingSession).order_by(RecordingSession.created_at.desc())
    if project_id is not None:
        query = query.where(RecordingSession.project_id == project_id)
    return [_response(row) for row in db.scalars(query).all()]


@router.get("/{session_id}", response_model=RecordingSessionResponse, summary="Read session metadata and channel mapping")
def get_recording_session(session_id: str, db: Session = Depends(database_session)):
    row = db.get(RecordingSession, session_id)
    if row is None:
        raise HTTPException(404, "Recording session not found")
    return _response(row)


@router.put("/{session_id}/metadata", response_model=RecordingSessionResponse,
            summary="Replace calibration metadata and analysis configuration")
def update_session_metadata(session_id: str, payload: RecordingSessionUpdate,
                            db: Session = Depends(database_session)):
    row = db.get(RecordingSession, session_id)
    if row is None:
        raise HTTPException(404, "Recording session not found")
    if row.status in ("queued", "running"):
        raise HTTPException(409, "Cannot update calibration metadata while extraction is active")
    row.calibration_json = payload.calibration.model_dump(mode="json")
    row.analysis_configuration_json = payload.analysis_configuration.model_dump(mode="json")
    row.provenance = payload.provenance
    row.status = "draft"
    db.commit()
    db.refresh(row)
    return _response(row)


@router.post("/{session_id}/recordings", response_model=RecordingSessionResponse,
            summary="Attach imported WAV and map its channels")
def attach_recording(session_id: str, payload: SessionRecordingAttach, request: Request,
                     db: Session = Depends(database_session)):
    try:
        _service(request).attach_recordings(db, session_id, [payload])
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    row = db.get(RecordingSession, session_id)
    return _response(row)


@router.post("/{session_id}/validate", response_model=RecordingSessionValidationResponse,
            summary="Validate calibration, synchronization, recordings, and channel mappings")
def validate_session(session_id: str, request: Request, db: Session = Depends(database_session)):
    row = db.get(RecordingSession, session_id)
    if row is None:
        raise HTTPException(404, "Recording session not found")
    try:
        errors, warnings = _service(request).validate(db, row)
    except ValueError as exc:
        raise HTTPException(422, f"Stored session metadata is invalid: {exc}") from exc
    return RecordingSessionValidationResponse(
        session_id=session_id,
        valid=not errors,
        errors=errors,
        warnings=warnings,
        synchronization_interpretation=(
            "asserted_by_metadata_not_independently_verified"
            if row.calibration_json.get("synchronization", {}).get("status") == "synchronized"
            else "not_asserted_as_synchronized"
        ),
    )


@router.post("/{session_id}/extractions", response_model=ExtractionQueuedResponse,
            status_code=status.HTTP_202_ACCEPTED, summary="Queue Phase 5E.1 multichannel TOA extraction")
def queue_extraction(session_id: str, request: Request, background_tasks: BackgroundTasks,
                     db: Session = Depends(database_session)):
    row = db.get(RecordingSession, session_id)
    if row is None:
        raise HTTPException(404, "Recording session not found")
    errors, _ = _service(request).validate(db, row)
    if errors:
        raise HTTPException(422, detail={"message": "Session is not ready for extraction", "errors": [item.model_dump() for item in errors]})
    extraction_id = str(uuid4())
    db.add(RecordingSessionExtraction(id=extraction_id, session_id=session_id, status="queued"))
    row.status = "queued"
    db.commit()
    background_tasks.add_task(_service(request).run_extraction, extraction_id)
    return ExtractionQueuedResponse(
        session_id=session_id,
        extraction_id=extraction_id,
        status="queued",
        message="Extraction queued; reported arrivals remain candidates and echo identities remain unclassified.",
    )


@router.get("/{session_id}/extractions/{extraction_id}", response_model=ExtractionResponse,
           summary="Retrieve extraction job status or result")
def get_extraction(session_id: str, extraction_id: str, db: Session = Depends(database_session)):
    row = db.get(RecordingSessionExtraction, extraction_id)
    if row is None or row.session_id != session_id:
        raise HTTPException(404, "Extraction not found for this session")
    return _extraction_response(row)


@router.get("/{session_id}/results", response_model=ExtractionResponse | None,
           summary="Retrieve the latest extraction result")
def get_latest_result(session_id: str, db: Session = Depends(database_session)):
    if db.get(RecordingSession, session_id) is None:
        raise HTTPException(404, "Recording session not found")
    row = db.scalar(select(RecordingSessionExtraction).where(
        RecordingSessionExtraction.session_id == session_id
    ).order_by(RecordingSessionExtraction.created_at.desc()))
    return _extraction_response(row) if row else None
