"""API routes for acoustic room measurement, echo distance calculation, and compact storage."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from batsight.application.api.schemas.contracts import (
    MeasurementCreate,
    MeasurementResponse,
    ProcessMeasurementRequest,
    ProcessMeasurementResponse,
    RoomReconstructionRequest,
    RoomReconstructionResponse,
)
from batsight.application.api.serializers import utc_datetime
from batsight.application.dependencies import database_session
from batsight.application.models.entities import Measurement, Project
from batsight.application.services.measurement_service import MeasurementService

router = APIRouter(prefix="/api/measurements", tags=["measurements"])


def _to_response(m: Measurement) -> MeasurementResponse:
    return MeasurementResponse(
        id=m.id,
        project_id=m.project_id,
        name=m.name,
        description=m.description,
        chirp_config=m.chirp_config,
        speed_of_sound_m_s=m.speed_of_sound_m_s,
        direct_lag_s=m.direct_lag_s,
        direct_distance_m=m.direct_distance_m,
        echo_candidates=m.echo_candidates,
        echo_count=m.echo_count,
        closest_reflector_m=m.closest_reflector_m,
        farthest_reflector_m=m.farthest_reflector_m,
        scan_angle_deg=m.scan_angle_deg,
        created_at=utc_datetime(m.created_at),
    )


@router.post(
    "",
    response_model=MeasurementResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Save a compact measurement record",
)
def create_measurement(
    payload: MeasurementCreate,
    session: Session = Depends(database_session),
):
    if payload.project_id is not None:
        project = session.get(Project, payload.project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")

    measurement = Measurement(
        project_id=payload.project_id,
        name=payload.name.strip(),
        description=payload.description,
        chirp_config=payload.chirp_config,
        speed_of_sound_m_s=payload.speed_of_sound_m_s,
        direct_lag_s=payload.direct_lag_s,
        direct_distance_m=payload.direct_distance_m,
        echo_candidates=payload.echo_candidates,
        echo_count=payload.echo_count,
        closest_reflector_m=payload.closest_reflector_m,
        farthest_reflector_m=payload.farthest_reflector_m,
        scan_angle_deg=payload.scan_angle_deg,
    )
    session.add(measurement)
    session.commit()
    session.refresh(measurement)
    return _to_response(measurement)


@router.get(
    "",
    response_model=list[MeasurementResponse],
    summary="List saved measurements",
)
def list_measurements(
    project_id: int | None = None,
    session: Session = Depends(database_session),
):
    query = select(Measurement).order_by(Measurement.created_at.desc())
    if project_id is not None:
        query = query.where(Measurement.project_id == project_id)
    return [_to_response(row) for row in session.scalars(query).all()]


@router.get(
    "/{measurement_id}",
    response_model=MeasurementResponse,
    summary="Get single measurement by ID",
)
def get_measurement(
    measurement_id: int,
    session: Session = Depends(database_session),
):
    m = session.get(Measurement, measurement_id)
    if m is None:
        raise HTTPException(status_code=404, detail="Measurement not found")
    return _to_response(m)


@router.delete(
    "/{measurement_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a measurement record",
)
def delete_measurement(
    measurement_id: int,
    session: Session = Depends(database_session),
):
    m = session.get(Measurement, measurement_id)
    if m is None:
        raise HTTPException(status_code=404, detail="Measurement not found")
    session.delete(m)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/process",
    response_model=ProcessMeasurementResponse,
    summary="Process an existing recording and calculate echo distances",
)
def process_measurement(
    payload: ProcessMeasurementRequest,
    request: Request,
    session: Session = Depends(database_session),
):
    if payload.recording_id is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="recording_id is required for JSON processing endpoint. Use /process-upload to upload audio directly.",
        )
    service = MeasurementService(request.app.state.settings)
    try:
        result = service.process_recording(
            session,
            payload.recording_id,
            channel_index=payload.channel_index,
            waveform=payload.waveform,
            duration_s=payload.duration_s,
            start_frequency_hz=payload.start_frequency_hz,
            end_frequency_hz=payload.end_frequency_hz,
            amplitude=payload.amplitude,
            speed_of_sound_m_s=payload.speed_of_sound_m_s,
            window_length_samples=payload.window_length_samples,
            thr1=payload.thr1,
            thr2=payload.thr2,
            normalization=payload.normalization,
        )
        return ProcessMeasurementResponse(**result)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.post(
    "/process-upload",
    response_model=ProcessMeasurementResponse,
    summary="Upload a WAV file directly and calculate echo distances in-memory",
)
async def process_measurement_upload(
    request: Request,
    file: UploadFile = File(..., description="WAV audio recording file"),
    waveform: Literal["linear_sweep", "sine"] = Form(default="linear_sweep"),
    duration_s: float = Form(default=1.0),
    start_frequency_hz: float = Form(default=300.0),
    end_frequency_hz: float = Form(default=4000.0),
    amplitude: float = Form(default=0.9),
    speed_of_sound_m_s: float = Form(default=343.0),
    channel_index: int = Form(default=0),
    window_length_samples: int = Form(default=200),
    thr1: float = Form(default=0.35),
    thr2: float = Form(default=0.04),
    normalization: Literal["reference_energy", "none"] = Form(default="reference_energy"),
):
    service = MeasurementService(request.app.state.settings)
    try:
        content = await file.read()
        result = service.process_wav_bytes(
            content,
            channel_index=channel_index,
            waveform=waveform,
            duration_s=duration_s,
            start_frequency_hz=start_frequency_hz,
            end_frequency_hz=end_frequency_hz,
            amplitude=amplitude,
            speed_of_sound_m_s=speed_of_sound_m_s,
            window_length_samples=window_length_samples,
            thr1=thr1,
            thr2=thr2,
            normalization=normalization,
        )
        return ProcessMeasurementResponse(**result)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.post(
    "/reconstruct-room",
    response_model=RoomReconstructionResponse,
    summary="Estimate 2D/3D rectangular room geometry from measured echoes",
)
def reconstruct_room(
    payload: RoomReconstructionRequest,
    request: Request,
    session: Session = Depends(database_session),
):
    service = MeasurementService(request.app.state.settings)
    distances = payload.distances_m or []
    if payload.measurement_id is not None:
        m = session.get(Measurement, payload.measurement_id)
        if m is None:
            raise HTTPException(status_code=404, detail="Measurement not found")
        distances = [
            float(e["distance_m"])
            for e in m.echo_candidates
            if isinstance(e, dict) and "distance_m" in e and float(e["distance_m"]) > 0.05
        ]

    result = service.estimate_room_geometry(
        distances,
        default_ceiling_height_m=payload.default_ceiling_height_m,
        centered_assumption=payload.centered_assumption,
    )
    return RoomReconstructionResponse(**result)
