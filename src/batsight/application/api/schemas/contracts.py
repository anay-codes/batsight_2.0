"""Pydantic contracts for the local REST API."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120, examples=["Living room capture"])
    description: str | None = Field(default=None, max_length=4000)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProjectResponse(BaseModel):
    id: int
    name: str
    description: str | None
    metadata: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class RecordingResponse(BaseModel):
    id: int
    project_id: int | None
    name: str
    description: str | None
    original_filename: str
    file_size_bytes: int
    sample_rate_hz: int
    channel_count: int
    sample_count: int
    duration_s: float
    metadata: dict[str, Any]
    created_at: datetime


class ExperimentCreate(BaseModel):
    project_id: int
    name: str = Field(min_length=1, max_length=200)
    kind: str = Field(min_length=1, max_length=80, examples=["synthetic_forward"])
    configuration: dict[str, Any] = Field(default_factory=dict, examples=[{
        "room_dimensions_m": [4.5, 4.1, 3.4],
        "source_position_m": [2.2, 2.0, 1.4],
        "microphone_positions_m": [[1.0, 1.0, 1.2], [3.0, 2.8, 1.5]],
        "sampling_frequency_hz": 48000,
        "duration_s": 0.01,
        "random_seed": 23,
    }])


class ExperimentResponse(BaseModel):
    id: int
    project_id: int
    name: str
    kind: str
    status: Literal["pending", "running", "completed", "failed"]
    configuration: dict[str, Any]
    error_message: str | None
    created_at: datetime
    updated_at: datetime


class ExperimentResultResponse(BaseModel):
    experiment_id: int
    result: dict[str, Any] | None


class RunAccepted(BaseModel):
    experiment_id: int
    status: str
    message: str


class HealthResponse(BaseModel):
    application: str
    version: str
    backend_status: Literal["ok"]
    database_status: Literal["connected", "unavailable"]


class SystemInfoResponse(BaseModel):
    application: str
    version: str
    python_version: str
    capabilities: dict[str, str]
    storage: dict[str, str | int]


class WaveformRequest(BaseModel):
    waveform: Literal["sine", "linear_sweep"] = "linear_sweep"
    sample_rate_hz: int = Field(default=48000, ge=8000, le=192000)
    duration_s: float = Field(default=0.02, gt=0, le=10)
    start_frequency_hz: float = Field(default=900, gt=0)
    end_frequency_hz: float = Field(default=11000, gt=0)
    amplitude: float = Field(default=0.8, gt=0, le=1)


class RecordingAnalysisRequest(BaseModel):
    channel_index: int = Field(default=0, ge=0)
    waveform: Literal["sine", "linear_sweep"] = "linear_sweep"
    reference_duration_s: float = Field(default=0.02, gt=0, le=10)
    start_frequency_hz: float = Field(default=900, gt=0)
    end_frequency_hz: float = Field(default=11000, gt=0)
    amplitude: float = Field(default=0.8, gt=0, le=1)
    normalization: Literal["reference_energy", "none"] = "reference_energy"
    window_length_samples: int = Field(default=2400, ge=1)
    thr1: float = Field(default=0.9, ge=0, le=1)
    thr2: float = Field(default=0.1, ge=0, le=1)
    spectrogram_nperseg: int = Field(default=1024, ge=8, le=8192)


class CorrelationCurvePoint(BaseModel):
    time_s: float
    value: float


class CorrelationPeakResponse(BaseModel):
    correlation_sample_index: int
    lag_samples: int
    lag_seconds: float
    amplitude: float
    classification: Literal["unclassified_correlation_peak"]


class PeakDetectionMetadata(BaseModel):
    window_length_samples: int
    thr1: float
    thr2: float
    accepted_peak_count: int
    threshold_rejection_reasons_available: bool


class MatchedFilterAnalysisResponse(BaseModel):
    correlation_convention: str
    normalization: Literal["reference_energy", "none"]
    reference_sample_count: int
    curve: list[CorrelationCurvePoint]
    peak_detection: PeakDetectionMetadata
    peaks: list[CorrelationPeakResponse]
    direct_or_echo_classification_available: bool


class SpectrogramResponse(BaseModel):
    frequencies_hz: list[float]
    times_s: list[float]
    magnitude_db_re_1_sample_amplitude: list[list[float]]
    window: str
    nperseg: int
    noverlap: int
    time_bin_count_is_decimated: bool


class RecordingAnalysisResponse(BaseModel):
    recording_id: str
    channel_index: int
    sample_rate_hz: float
    channel_count: int
    sample_count: int
    duration_s: float
    amplitude_statistics: dict[str, float | str]
    matched_filter: MatchedFilterAnalysisResponse
    spectrogram: SpectrogramResponse
    provenance: str


class SimulationPathsRequest(BaseModel):
    room_dimensions_m: tuple[float, float, float]
    source_position_m: tuple[float, float, float]
    microphone_positions_m: list[tuple[float, float, float]] = Field(min_length=1, max_length=64)
    speed_of_sound_m_s: float = Field(default=343.0, gt=0)
    max_reflection_order: int = Field(default=1, ge=0, le=2)
    wall_reflection_coefficients: dict[str, float] = Field(default_factory=dict)


class SimulatedPathResponse(BaseModel):
    reflection_order: int
    reflection_sequence: list[str]
    image_source_position_m: tuple[float, float, float]
    path_length_m: float
    time_of_flight_s: float
    reflection_coefficient: float
    reflection_point_m: tuple[float, float, float] | None
    finite_wall_bounce_valid: bool | None


class MicrophonePathSetResponse(BaseModel):
    microphone_index: int
    microphone_position_m: tuple[float, float, float]
    paths: list[SimulatedPathResponse]


class SimulationPathsResponse(BaseModel):
    room_dimensions_m: tuple[float, float, float]
    source_position_m: tuple[float, float, float]
    speed_of_sound_m_s: float
    max_reflection_order: int
    microphone_paths: list[MicrophonePathSetResponse]
    provenance: str
    model_description: str


class EchoPeakResponse(BaseModel):
    correlation_sample_index: int
    lag_samples: int
    lag_seconds: float
    amplitude: float
    delay_from_direct_s: float
    distance_m: float
    path_length_m: float
    classification: Literal["direct_path", "echo", "pre_trigger", "direct_sidelobe"]


class ProcessMeasurementRequest(BaseModel):
    recording_id: int | None = None
    waveform: Literal["linear_sweep", "sine"] = "linear_sweep"
    duration_s: float = Field(default=1.0, gt=0)
    start_frequency_hz: float = Field(default=300.0, gt=0)
    end_frequency_hz: float = Field(default=4000.0, gt=0)
    amplitude: float = Field(default=0.9, gt=0, le=1.0)
    speed_of_sound_m_s: float = Field(default=343.0, gt=0)
    channel_index: int = Field(default=0, ge=0)
    window_length_samples: int = Field(default=200, ge=1)
    thr1: float = Field(default=0.35, ge=0, le=1.0)
    thr2: float = Field(default=0.04, ge=0, le=1.0)
    normalization: Literal["reference_energy", "none"] = "reference_energy"


class ProcessMeasurementResponse(BaseModel):
    sample_rate_hz: float
    duration_s: float
    speed_of_sound_m_s: float
    direct_lag_s: float | None
    direct_distance_m: float | None
    peaks: list[EchoPeakResponse]
    echo_count: int
    closest_reflector_m: float | None
    farthest_reflector_m: float | None
    provenance: str = "matched_filter_echo_detection"


class MeasurementCreate(BaseModel):
    project_id: int | None = None
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=4000)
    chirp_config: dict[str, Any] = Field(default_factory=dict)
    speed_of_sound_m_s: float = Field(default=343.0, gt=0)
    direct_lag_s: float | None = None
    direct_distance_m: float | None = None
    echo_candidates: list[dict[str, Any]] = Field(default_factory=list)
    echo_count: int = 0
    closest_reflector_m: float | None = None
    farthest_reflector_m: float | None = None
    scan_angle_deg: float | None = None


class MeasurementResponse(BaseModel):
    id: int
    project_id: int | None
    name: str
    description: str | None
    chirp_config: dict[str, Any]
    speed_of_sound_m_s: float
    direct_lag_s: float | None
    direct_distance_m: float | None
    echo_candidates: list[dict[str, Any]]
    echo_count: int
    closest_reflector_m: float | None
    farthest_reflector_m: float | None
    scan_angle_deg: float | None
    created_at: datetime


class WallDistanceMap(BaseModel):
    x_min: float
    x_max: float
    y_min: float
    y_max: float
    z_min: float
    z_max: float


class RoomReconstructionRequest(BaseModel):
    measurement_id: int | None = None
    distances_m: list[float] | None = None
    default_ceiling_height_m: float = Field(default=2.8, gt=0)
    centered_assumption: bool = True
    speed_of_sound_m_s: float = Field(default=343.0, gt=0)


class RoomReconstructionResponse(BaseModel):
    estimated_dimensions_m: tuple[float, float, float]
    length_x_m: float
    width_y_m: float
    height_z_m: float
    floor_area_m2: float
    room_volume_m3: float
    device_position_m: tuple[float, float, float]
    wall_distances: WallDistanceMap
    echo_distances_used: list[float]
    method: str = "calibrated_rectangular_bounding_box"
    confidence: str = "calibrated_echo_fit"


class RoomCreate(BaseModel):
    project_id: int | None = None
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=4000)
    length_x_m: float = Field(gt=0)
    width_y_m: float = Field(gt=0)
    height_z_m: float = Field(default=2.8, gt=0)
    floor_area_m2: float | None = None
    room_volume_m3: float | None = None
    device_position_m: list[float] = Field(default_factory=lambda: [0.0, 0.0, 1.0])
    wall_distances: dict[str, Any] = Field(default_factory=dict)
    obstacles: list[dict[str, Any]] = Field(default_factory=list)
    scan_metadata: dict[str, Any] = Field(default_factory=dict)


class RoomUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    length_x_m: float | None = Field(default=None, gt=0)
    width_y_m: float | None = Field(default=None, gt=0)
    height_z_m: float | None = Field(default=None, gt=0)
    device_position_m: list[float] | None = None
    wall_distances: dict[str, Any] | None = None
    obstacles: list[dict[str, Any]] | None = None


class RoomResponse(BaseModel):
    id: int
    project_id: int | None
    name: str
    description: str | None
    length_x_m: float
    width_y_m: float
    height_z_m: float
    floor_area_m2: float
    room_volume_m3: float
    device_position_m: list[float]
    wall_distances: dict[str, Any]
    obstacles: list[dict[str, Any]]
    scan_metadata: dict[str, Any]
    created_at: datetime
    updated_at: datetime
