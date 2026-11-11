"""Versioned contracts for calibrated multichannel recording sessions."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, FiniteFloat, model_validator


Position = tuple[FiniteFloat, FiniteFloat, FiniteFloat]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SynchronizationMetadata(StrictModel):
    status: Literal["synchronized", "unsynchronized", "unknown"] = "unknown"
    evidence_description: str | None = Field(default=None, max_length=2000)


class MicrophoneMetadata(StrictModel):
    microphone_id: str = Field(min_length=1, max_length=120)
    position_m: Position | None = None


class ReferenceSignalMetadata(StrictModel):
    waveform: Literal["sine", "linear_sweep"]
    duration_s: FiniteFloat = Field(gt=0, le=10)
    start_frequency_hz: FiniteFloat = Field(gt=0)
    end_frequency_hz: FiniteFloat | None = Field(default=None, gt=0)
    amplitude: FiniteFloat = Field(default=0.8, gt=0, le=1)


class SourceEventMetadata(StrictModel):
    event_id: str = Field(min_length=1, max_length=120)
    source_id: str = Field(min_length=1, max_length=120)
    position_m: Position | None = None
    emission_time_s: FiniteFloat | None = None
    reference_signal: ReferenceSignalMetadata | None = None


class CalibrationMetadata(StrictModel):
    schema_version: Literal["1.0"]
    coordinate_frame: Literal["corner_origin_x_length_y_width_z_height"] | None = None
    position_unit: Literal["m"] | None = None
    time_unit: Literal["s"] | None = None
    time_reference: str | None = Field(default=None, max_length=200)
    sample_rate_hz: int | None = Field(default=None, ge=1)
    speed_of_sound_m_s: FiniteFloat | None = Field(default=None, gt=0)
    synchronization: SynchronizationMetadata = Field(default_factory=SynchronizationMetadata)
    microphones: list[MicrophoneMetadata] = Field(default_factory=list)
    events: list[SourceEventMetadata] = Field(default_factory=list)

    @model_validator(mode="after")
    def unique_ids(self):
        microphone_ids = [microphone.microphone_id for microphone in self.microphones]
        event_ids = [event.event_id for event in self.events]
        if len(microphone_ids) != len(set(microphone_ids)):
            raise ValueError("microphone_id values must be unique")
        if len(event_ids) != len(set(event_ids)):
            raise ValueError("event_id values must be unique")
        return self


class AnalysisSettings(StrictModel):
    direct_tolerance_s: FiniteFloat = Field(default=0.002, gt=0)
    minimum_echo_excess_delay_s: FiniteFloat = Field(default=0.0002, ge=0)
    maximum_echo_excess_delay_s: FiniteFloat = Field(default=0.05, gt=0)
    minimum_peak_separation_s: FiniteFloat = Field(default=0.00015, ge=0)
    window_length_samples: int = Field(default=8, ge=1)
    thr1: FiniteFloat = Field(default=0.9, ge=0, le=1)
    thr2: FiniteFloat = Field(default=0.02, ge=0, le=1)
    minimum_peak_prominence: FiniteFloat = Field(default=0, ge=0)
    polarity: Literal["either", "positive"] = "either"
    timing_uncertainty_s: FiniteFloat | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def valid_echo_window(self):
        if self.maximum_echo_excess_delay_s <= self.minimum_echo_excess_delay_s:
            raise ValueError("maximum_echo_excess_delay_s must exceed minimum_echo_excess_delay_s")
        return self


class ChannelMapping(StrictModel):
    channel_index: int = Field(ge=0)
    microphone_id: str = Field(min_length=1, max_length=120)


class SessionRecordingInput(StrictModel):
    recording_id: int = Field(gt=0)
    recording_start_time_s: FiniteFloat | None = None
    channel_mapping: list[ChannelMapping] = Field(min_length=1)
    event_ids: list[str] | None = None

    @model_validator(mode="after")
    def unique_mapping(self):
        channels = [mapping.channel_index for mapping in self.channel_mapping]
        microphones = [mapping.microphone_id for mapping in self.channel_mapping]
        if len(channels) != len(set(channels)):
            raise ValueError("channel_index values must be unique within a recording")
        if len(microphones) != len(set(microphones)):
            raise ValueError("microphone_id values must be unique within a recording")
        if self.event_ids is not None and len(self.event_ids) != len(set(self.event_ids)):
            raise ValueError("event_ids must be unique within a recording")
        return self


class RecordingSessionCreate(StrictModel):
    project_id: int = Field(gt=0)
    name: str = Field(min_length=1, max_length=200)
    provenance: Literal["synthetic", "imported_real_multichannel", "laptop_single_device"]
    calibration: CalibrationMetadata
    analysis_configuration: AnalysisSettings = Field(default_factory=AnalysisSettings)
    recordings: list[SessionRecordingInput] = Field(default_factory=list)


class RecordingSessionUpdate(StrictModel):
    calibration: CalibrationMetadata
    analysis_configuration: AnalysisSettings = Field(default_factory=AnalysisSettings)
    provenance: Literal["synthetic", "imported_real_multichannel", "laptop_single_device"]


class SessionRecordingAttach(SessionRecordingInput):
    pass


class SessionIdResponse(StrictModel):
    session_id: str
    status: str


class ValidationIssue(StrictModel):
    code: str
    message: str
    field: str | None = None


class RecordingSessionValidationResponse(StrictModel):
    session_id: str
    valid: bool
    errors: list[ValidationIssue]
    warnings: list[ValidationIssue]
    synchronization_interpretation: str


class ExtractionQueuedResponse(StrictModel):
    session_id: str
    extraction_id: str
    status: Literal["queued"]
    message: str


class RecordingSessionResponse(StrictModel):
    session_id: str
    project_id: int
    name: str
    provenance: str
    status: str
    calibration: dict[str, Any]
    analysis_configuration: dict[str, Any]
    recordings: list[dict[str, Any]]
    latest_extraction_id: str | None = None
    created_at: str


class ExtractionResponse(StrictModel):
    session_id: str
    extraction_id: str
    status: Literal["queued", "running", "completed", "failed"]
    error_message: str | None = None
    result: dict[str, Any] | None = None
    created_at: str
    completed_at: str | None = None
