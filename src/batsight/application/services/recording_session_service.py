"""Persistence validation and Phase 5E.1 extraction for calibrated sessions."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from batsight.application.api.schemas.recording_sessions import (
    AnalysisSettings,
    CalibrationMetadata,
    RecordingSessionCreate,
    SessionRecordingInput,
    ValidationIssue,
)
from batsight.application.config import Settings
from batsight.application.models.entities import (
    Project,
    Recording,
    RecordingSession,
    RecordingSessionExtraction,
    RecordingSessionRecording,
)
from batsight.application.services.recording_service import RecordingService
from batsight.application.services.signal_service import SignalProcessingService
from batsight.datasets.audio_toa import recording_analysis_to_observations
from batsight.datasets.calibrated import (
    CalibratedMicrophone,
    CalibratedMicrophoneArray,
    CalibratedShoeboxInputs,
    CalibratedSourceEvent,
)
from batsight.signals import SamplingFrequency
from batsight.signals.recording_analysis import RecordingAnalysisConfig, load_multichannel_wav


class RecordingSessionService:
    def __init__(self, settings: Settings, session_factory: sessionmaker) -> None:
        self.settings = settings
        self.session_factory = session_factory
        self.recording_service = RecordingService(settings)

    @staticmethod
    def attach_recordings(db: Session, session_id: str, rows: list[SessionRecordingInput]) -> None:
        session = db.get(RecordingSession, session_id)
        if session is None:
            raise LookupError("Recording session not found")
        existing = {link.recording_id for link in session.recordings}
        for row in rows:
            if row.recording_id in existing:
                raise ValueError(f"recording {row.recording_id} is already attached to this session")
            recording = db.get(Recording, row.recording_id)
            if recording is None:
                raise LookupError(f"Recording {row.recording_id} not found")
            if recording.project_id != session.project_id:
                raise ValueError(f"recording {row.recording_id} must belong to the session project")
            session.recordings.append(RecordingSessionRecording(
                recording=recording,
                recording_start_time_s=row.recording_start_time_s,
                channel_mapping_json=[item.model_dump(mode="json") for item in row.channel_mapping],
                event_ids_json=row.event_ids,
            ))
            existing.add(row.recording_id)
        db.commit()

    def validate(self, db: Session, session: RecordingSession) -> tuple[list[ValidationIssue], list[ValidationIssue]]:
        errors: list[ValidationIssue] = []
        warnings: list[ValidationIssue] = []
        metadata = CalibrationMetadata.model_validate(session.calibration_json)
        config = AnalysisSettings.model_validate(session.analysis_configuration_json)
        microphones = {item.microphone_id: item for item in metadata.microphones}
        events = {item.event_id: item for item in metadata.events}
        if metadata.coordinate_frame is None:
            errors.append(_issue("coordinate_frame_missing", "Select the room coordinate frame.", "calibration.coordinate_frame"))
        if metadata.position_unit != "m":
            errors.append(_issue("position_unit_missing", "Microphone and source coordinates must explicitly use metres.", "calibration.position_unit"))
        if metadata.time_unit != "s":
            errors.append(_issue("time_unit_missing", "Emission and recording start times must explicitly use seconds.", "calibration.time_unit"))
        if not metadata.time_reference or not metadata.time_reference.strip():
            errors.append(_issue("time_reference_missing", "Provide the common time-origin reference used by emission and recording start times.", "calibration.time_reference"))
        if metadata.speed_of_sound_m_s is None or metadata.speed_of_sound_m_s <= 0:
            errors.append(_issue("sound_speed_missing", "Provide a finite positive sound speed in m/s.", "calibration.speed_of_sound_m_s"))
        if metadata.sample_rate_hz is None:
            errors.append(_issue("sample_rate_missing", "Provide the calibrated sample rate in Hz.", "calibration.sample_rate_hz"))
        if len(microphones) < 2:
            errors.append(_issue("insufficient_microphones", "A calibrated multichannel session requires at least two mapped microphones.", "calibration.microphones"))
        if not events:
            errors.append(_issue("events_missing", "Add at least one source event with its transmitted reference description.", "calibration.events"))
        if session.provenance == "laptop_single_device":
            errors.append(_issue("single_device_not_array", "Laptop single-device recordings cannot be analysed as a calibrated synchronized multichannel array.", "provenance"))
        sync = metadata.synchronization
        if sync.status != "synchronized":
            errors.append(_issue("synchronization_not_asserted", "This extraction requires synchronization explicitly asserted in metadata.", "calibration.synchronization.status"))
        elif not sync.evidence_description or not sync.evidence_description.strip():
            errors.append(_issue("synchronization_evidence_missing", "Describe the synchronization evidence or acquisition method; this assertion is not independently verified by BatSight.", "calibration.synchronization.evidence_description"))

        mapped_microphones: set[str] = set()
        total_channels = 0
        rates: set[int] = set()
        for link in session.recordings:
            recording = link.recording
            rates.add(recording.sample_rate_hz)
            total_channels += recording.channel_count
            mappings = link.channel_mapping_json
            if link.event_ids_json is not None:
                unknown_events = sorted(set(link.event_ids_json) - events.keys())
                if unknown_events:
                    errors.append(_issue("unknown_event_reference", f"Recording {recording.id} references unknown event(s): {', '.join(unknown_events)}.", f"recordings.{recording.id}.event_ids"))
                if not link.event_ids_json:
                    errors.append(_issue("recording_events_empty", f"Recording {recording.id} must reference at least one event or leave event_ids unset for all session events.", f"recordings.{recording.id}.event_ids"))
            indices = [item.get("channel_index") for item in mappings]
            mic_ids = [item.get("microphone_id") for item in mappings]
            if len(mappings) != recording.channel_count or set(indices) != set(range(recording.channel_count)):
                errors.append(_issue("channel_mapping_incomplete", f"Recording {recording.id} has {recording.channel_count} channels; map every channel index exactly once.", f"recordings.{recording.id}.channel_mapping"))
            for index, microphone_id in zip(indices, mic_ids):
                if microphone_id not in microphones:
                    errors.append(_issue("unknown_microphone", f"Channel {index} maps to unknown microphone '{microphone_id}'.", f"recordings.{recording.id}.channel_mapping"))
                else:
                    # A calibrated microphone may appear in multiple files (for
                    # example, repeated events); uniqueness is only per file.
                    mapped_microphones.add(microphone_id)
            if link.recording_start_time_s is None:
                errors.append(_issue("recording_start_missing", f"Provide the recording start time for recording {recording.id} in the common time reference.", f"recordings.{recording.id}.recording_start_time_s"))
        if not session.recordings:
            errors.append(_issue("recordings_missing", "Attach at least one imported WAV recording.", "recordings"))
        if rates and len(rates) != 1:
            errors.append(_issue("sample_rate_mismatch", "All session recordings must have the same sample rate; BatSight does not resample.", "recordings"))
        if metadata.sample_rate_hz is not None and rates and rates != {metadata.sample_rate_hz}:
            errors.append(_issue("calibration_sample_rate_mismatch", f"Recorded sample rate(s) {sorted(rates)} do not match calibration sample_rate_hz {metadata.sample_rate_hz}.", "calibration.sample_rate_hz"))
        if mapped_microphones != microphones.keys():
            unmapped = sorted(microphones.keys() - mapped_microphones)
            if unmapped:
                errors.append(_issue("microphones_unmapped", f"No recording channel is mapped to: {', '.join(unmapped)}.", "recordings.channel_mapping"))
        for microphone in metadata.microphones:
            if microphone.position_m is None:
                errors.append(_issue("microphone_position_missing", f"Microphone '{microphone.microphone_id}' has no calibrated position.", f"calibration.microphones.{microphone.microphone_id}.position_m"))
        if total_channels < 2:
            errors.append(_issue("not_multichannel", "At least two calibrated audio channels are required for this session mode.", "recordings"))
        for event in metadata.events:
            if event.position_m is None:
                errors.append(_issue("source_position_missing", f"Event '{event.event_id}' has no calibrated source position.", f"calibration.events.{event.event_id}.position_m"))
            if event.emission_time_s is None:
                errors.append(_issue("emission_time_missing", f"Event '{event.event_id}' has no emission time in seconds.", f"calibration.events.{event.event_id}.emission_time_s"))
            if event.reference_signal is None:
                errors.append(_issue("reference_signal_missing", f"Event '{event.event_id}' has no known transmitted reference description.", f"calibration.events.{event.event_id}.reference_signal"))
            elif metadata.sample_rate_hz:
                reference = event.reference_signal
                nyquist = metadata.sample_rate_hz / 2
                if reference.start_frequency_hz >= nyquist or (reference.waveform == "linear_sweep" and (reference.end_frequency_hz is None or reference.end_frequency_hz >= nyquist)):
                    errors.append(_issue("reference_frequency_out_of_range", f"Event '{event.event_id}' reference frequencies must be below Nyquist ({nyquist:g} Hz).", f"calibration.events.{event.event_id}.reference_signal"))
        if config.maximum_echo_excess_delay_s >= max((recording.duration_s for link in session.recordings for recording in [link.recording]), default=0):
            warnings.append(_issue("echo_window_long", "Configured echo window is at least as long as a recording; some intervals may be uncovered."))
        if sync.status == "synchronized":
            warnings.append(_issue("sync_not_verified", "Synchronization is asserted from session metadata only; BatSight does not independently verify clock synchronization."))
        return _deduplicate_issues(errors), warnings

    def run_extraction(self, extraction_id: str) -> None:
        db = self.session_factory()
        try:
            extraction = db.get(RecordingSessionExtraction, extraction_id)
            if extraction is None:
                return
            session = db.get(RecordingSession, extraction.session_id)
            if session is None:
                extraction.status = "failed"
                extraction.error_message = "Recording session no longer exists."
                db.commit()
                return
            extraction.status = "running"
            session.status = "running"
            db.commit()
            errors, _ = self.validate(db, session)
            if errors:
                raise ValueError("Session validation failed: " + "; ".join(issue.message for issue in errors))
            result = self._extract(session)
            extraction.result_json = result
            extraction.status = "completed"
            extraction.error_message = None
            extraction.completed_at = datetime.now(timezone.utc)
            session.status = "completed"
            db.commit()
        except Exception as exc:
            db.rollback()
            extraction = db.get(RecordingSessionExtraction, extraction_id)
            if extraction is not None:
                extraction.status = "failed"
                extraction.error_message = f"{type(exc).__name__}: {exc}"
                extraction.completed_at = datetime.now(timezone.utc)
                if extraction.recording_session is not None:
                    extraction.recording_session.status = "failed"
                db.commit()
        finally:
            db.close()

    def _extract(self, session: RecordingSession) -> dict[str, Any]:
        metadata = CalibrationMetadata.model_validate(session.calibration_json)
        settings = AnalysisSettings.model_validate(session.analysis_configuration_json)
        config = RecordingAnalysisConfig(**settings.model_dump())
        microphone_lookup = {item.microphone_id: item for item in metadata.microphones}
        signal_service = SignalProcessingService()
        pair_records: list[dict[str, Any]] = []
        observation_records: list[dict[str, Any]] = []
        recording_records: list[dict[str, Any]] = []
        for link in session.recordings:
            recording = link.recording
            path = self.recording_service.safe_managed_path(recording)
            audio = load_multichannel_wav(path, expected_sampling_frequency_hz=metadata.sample_rate_hz)
            channel_mappings = sorted(link.channel_mapping_json, key=lambda item: item["channel_index"])
            calibrated_microphones = tuple(
                CalibratedMicrophone(mapping["microphone_id"], microphone_lookup[mapping["microphone_id"]].position_m)
                for mapping in channel_mappings
            )
            microphone_array = CalibratedMicrophoneArray(
                calibrated_microphones, SamplingFrequency(float(recording.sample_rate_hz)), clocks_synchronized=True
            )
            selected_event_ids = set(link.event_ids_json) if link.event_ids_json is not None else None
            events_for_recording = [event for event in metadata.events if selected_event_ids is None or event.event_id in selected_event_ids]
            for event in events_for_recording:
                reference_spec = event.reference_signal
                if reference_spec is None:
                    raise ValueError(f"Event '{event.event_id}' has no reference signal")
                end_frequency = reference_spec.end_frequency_hz or reference_spec.start_frequency_hz
                reference = signal_service.generate_reference(
                    waveform=reference_spec.waveform,
                    sample_rate_hz=recording.sample_rate_hz,
                    duration_s=reference_spec.duration_s,
                    start_frequency_hz=reference_spec.start_frequency_hz,
                    end_frequency_hz=end_frequency,
                    amplitude=reference_spec.amplitude,
                )
                calibrated_event = CalibratedSourceEvent(
                    event_id=event.event_id,
                    source_id=event.source_id,
                    position_m=event.position_m,
                    emission_time_s=event.emission_time_s,
                    reference_signal=reference,
                )
                inputs = CalibratedShoeboxInputs(microphone_array, (calibrated_event,), metadata.speed_of_sound_m_s)
                analysis = signal_service.extract_toas(
                    audio, reference, inputs,
                    config=config,
                    recording_start_time_s=link.recording_start_time_s,
                )
                origin = "synthetic" if session.provenance == "synthetic" else "real"
                observation_set = recording_analysis_to_observations(analysis, origin=origin)
                observation_records.extend(_observation_json(session.provenance, recording.id, observation_set))
                pair_records.extend(_pair_json(recording.id, recording.original_filename, pair) for pair in analysis.pair_results)
            recording_records.append({
                "recording_id": recording.id,
                "filename": recording.original_filename,
                "sample_rate_hz": recording.sample_rate_hz,
                "channel_count": recording.channel_count,
                "duration_s": recording.duration_s,
                "recording_start_time_s": link.recording_start_time_s,
                "channel_mapping": channel_mappings,
                "waveform_preview": _waveform_preview(audio.samples, recording.sample_rate_hz),
            })
        direct_missing = sum(pair["direct_arrival"] is None for pair in pair_records)
        return {
            "session_id": session.id,
            "data_provenance": session.provenance,
            "synchronization": {
                **metadata.synchronization.model_dump(mode="json"),
                "interpretation": "asserted_by_metadata_not_independently_verified",
            },
            "estimated_room_geometry_available": False,
            "recordings": recording_records,
            "calibration": metadata.model_dump(mode="json"),
            "analysis_configuration": settings.model_dump(mode="json"),
            "pair_results": pair_records,
            "toa_observations": observation_records,
            "summary": {
                "microphone_event_pairs": len(pair_records),
                "missing_direct_path_count": int(direct_missing),
                "unclassified_echo_candidate_count": sum(len(pair["echo_candidates"]) for pair in pair_records),
                "rejected_peak_count": sum(len(pair["rejected_peaks"]) for pair in pair_records),
            },
            "warnings": ["Extracted direct arrivals are candidates gated by declared calibration; echo candidates have no inferred wall identity."],
        }


def _issue(code: str, message: str, field: str | None = None) -> ValidationIssue:
    return ValidationIssue(code=code, message=message, field=field)


def _deduplicate_issues(issues: list[ValidationIssue]) -> list[ValidationIssue]:
    unique: dict[tuple[str, str, str | None], ValidationIssue] = {}
    for issue in issues:
        unique[(issue.code, issue.message, issue.field)] = issue
    return list(unique.values())


def _pair_json(recording_id: int, filename: str, pair) -> dict[str, Any]:
    return {
        "recording_id": recording_id,
        "filename": filename,
        "microphone_id": pair.microphone_id,
        "event_id": pair.event_id,
        "expected_direct_time_s": pair.expected_direct_time_s,
        "direct_arrival": asdict(pair.direct_arrival) if pair.direct_arrival is not None else None,
        "direct_status": "observed" if pair.direct_arrival is not None else "missing",
        "echo_candidates": [asdict(item) for item in pair.echo_candidates],
        "rejected_peaks": [asdict(item) for item in pair.rejected_peaks],
        "robust_noise_scale": pair.robust_noise_scale,
        "warnings": list(pair.warnings),
    }


def _observation_json(provenance: str, recording_id: int, observation_set) -> list[dict[str, Any]]:
    result = []
    for item in observation_set.direct_paths:
        result.append({
            "recording_id": recording_id, "recording_provenance": provenance,
            "observation_type": "direct_path", "microphone_id": item.microphone_id,
            "event_id": item.event_id, "status": item.reading.status,
            "arrival_time_s": item.reading.arrival_time_s,
            "uncertainty_s": item.reading.uncertainty_s,
            "detection_strength": item.detection_strength, "toa_provenance": item.provenance,
        })
    for item in observation_set.unlabeled_echoes:
        result.append({
            "recording_id": recording_id, "recording_provenance": provenance,
            "observation_type": "unclassified_echo_candidate", "microphone_id": item.microphone_id,
            "event_id": item.event_id, "echo_id": item.echo_id, "status": item.reading.status,
            "arrival_time_s": item.reading.arrival_time_s,
            "uncertainty_s": item.reading.uncertainty_s,
            "detection_strength": item.detection_strength,
            "reflection_order_hint": None,
            "toa_provenance": item.provenance,
        })
    return result


def _waveform_preview(samples, sample_rate_hz: int, maximum_bins: int = 512) -> dict[str, Any]:
    """Bounded min/max envelope for display only; source audio remains untouched."""
    import numpy as np

    data = np.asarray(samples, dtype=np.float64)
    if data.ndim == 1:
        data = data[:, None]
    bin_size = max(1, int(np.ceil(data.shape[0] / maximum_bins)))
    points = []
    for channel in range(data.shape[1]):
        envelope = []
        for start in range(0, data.shape[0], bin_size):
            block = data[start:start + bin_size, channel]
            envelope.append({
                "time_s": start / float(sample_rate_hz),
                "minimum": float(np.min(block)),
                "maximum": float(np.max(block)),
            })
        points.append({"channel_index": channel, "envelope": envelope})
    return {"sample_rate_hz": sample_rate_hz, "channel_count": data.shape[1], "channels": points}
