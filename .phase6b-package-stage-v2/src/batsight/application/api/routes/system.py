"""Health and local capability endpoints."""

import platform

from fastapi import APIRouter, Request
from sqlalchemy import text

from batsight import __version__
from batsight.application.api.schemas.contracts import HealthResponse, SystemInfoResponse

router = APIRouter(prefix="/api", tags=["system"])


@router.get("/health", response_model=HealthResponse, summary="Check backend and database health")
def health(request: Request) -> HealthResponse:
    database_status = "connected"
    try:
        with request.app.state.session_factory() as session:
            session.execute(text("SELECT 1"))
    except Exception:
        database_status = "unavailable"
    settings = request.app.state.settings
    return HealthResponse(
        application=settings.app_name,
        version=settings.version or __version__,
        backend_status="ok",
        database_status=database_status,
    )


@router.get("/system/info", response_model=SystemInfoResponse, summary="Describe local processing capabilities")
def system_info(request: Request) -> SystemInfoResponse:
    settings = request.app.state.settings
    return SystemInfoResponse(
        application=settings.app_name,
        version=settings.version,
        python_version=platform.python_version(),
        capabilities={
            "wav_upload_and_metadata_validation": "available; original file bytes stored without resampling",
            "generic_chirp_generation": "available; engineering waveform only",
            "matched_filter_and_peak_detection": "available through scientific service layer and single-channel recording analysis endpoint; peaks unclassified",
            "recording_audio_download": "available; original managed WAV bytes",
            "calibrated_multichannel_toa_extraction": "available; echo candidates remain unlabeled",
            "shoebox_room_simulation": "available; forward synthetic simulation only",
            "synthetic_experiment_execution": "available; forward pipeline only",
            "labeled_shoebox_dimension_estimation": "existing experimental module; not run by this API",
            "uncalibrated_3d_room_reconstruction": "not implemented",
            "real_world_room_reconstruction": "not validated or exposed",
        },
        storage={
            "data_directory": str(settings.data_dir.resolve()),
            "recordings_directory": str(settings.recordings_dir.resolve()),
            "exports_directory": str(settings.exports_dir.resolve()),
            "maximum_upload_size_bytes": settings.max_upload_size_bytes,
            "maximum_analysis_samples_per_channel": settings.max_analysis_samples,
        },
    )
