"""Measurement contracts for the calibrated shoebox experiment profile.

This schema contains known acquisition inputs and TOA observations only. It
does not contain an inverse estimator or unknown room dimensions.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np

from batsight.geometry.shoebox import WallIdentifier
from batsight.signals import KnownReferenceSignal, RecordingMetadata, SamplingFrequency
from batsight.simulation.shoebox import WALLS

Position3D = tuple[float, float, float]
ObservationStatus = Literal["observed", "missing", "invalid"]
DatasetOrigin = Literal["synthetic", "real"]
ReflectionLabelSource = Literal[
    "synthetic_ground_truth", "external_annotation", "estimated_association"
]
DetectionProvenance = Literal["synthetic_audio", "multichannel_file", "unknown"]


@dataclass(frozen=True, slots=True)
class CalibratedMicrophone:
    """One known microphone location and optional channel provenance."""

    microphone_id: str
    position_m: Position3D
    recording_metadata: RecordingMetadata | None = None

    def __post_init__(self) -> None:
        _identifier(self.microphone_id, "microphone_id")
        object.__setattr__(self, "position_m", _position(self.position_m, "position_m"))
        if self.recording_metadata is not None and not isinstance(self.recording_metadata, RecordingMetadata):
            raise TypeError("recording_metadata must be RecordingMetadata or None")


@dataclass(frozen=True, slots=True)
class CalibratedMicrophoneArray:
    """Known microphones with a common sampling rate and synchronized clocks.

    This class represents the frozen calibrated profile. Unsynchronized clocks
    are rejected and belong to a future profile with explicit clock variables.
    """

    microphones: tuple[CalibratedMicrophone, ...]
    sampling_frequency: SamplingFrequency
    clocks_synchronized: bool = True

    def __post_init__(self) -> None:
        microphones = tuple(self.microphones)
        if not microphones or not all(isinstance(item, CalibratedMicrophone) for item in microphones):
            raise ValueError("microphones must contain at least one CalibratedMicrophone")
        identifiers = [item.microphone_id for item in microphones]
        if len(set(identifiers)) != len(identifiers):
            raise ValueError("microphone_id values must be unique")
        if not isinstance(self.sampling_frequency, SamplingFrequency):
            raise TypeError("sampling_frequency must be SamplingFrequency")
        if self.clocks_synchronized is not True:
            raise ValueError("this calibrated profile requires synchronized microphone clocks")
        object.__setattr__(self, "microphones", microphones)


@dataclass(frozen=True, slots=True)
class CalibratedSourceEvent:
    """Known source pose and emission time for one event."""

    event_id: str
    source_id: str
    position_m: Position3D
    emission_time_s: float
    reference_signal: KnownReferenceSignal | None = None

    def __post_init__(self) -> None:
        _identifier(self.event_id, "event_id")
        _identifier(self.source_id, "source_id")
        object.__setattr__(self, "position_m", _position(self.position_m, "position_m"))
        if not np.isfinite(self.emission_time_s):
            raise ValueError("emission_time_s must be finite seconds")
        if self.reference_signal is not None and not isinstance(self.reference_signal, KnownReferenceSignal):
            raise TypeError("reference_signal must be KnownReferenceSignal or None")


@dataclass(frozen=True, slots=True)
class CalibratedShoeboxInputs:
    """Known scene and acquisition values for the calibrated room mode.

    Room dimensions are intentionally absent: they are the target unknowns.
    Coordinates use the axis-aligned room frame in metres; timing values are
    seconds and ``speed_of_sound_m_s`` is metres per second.
    """

    microphone_array: CalibratedMicrophoneArray
    source_events: tuple[CalibratedSourceEvent, ...]
    speed_of_sound_m_s: float

    def __post_init__(self) -> None:
        if not isinstance(self.microphone_array, CalibratedMicrophoneArray):
            raise TypeError("microphone_array must be CalibratedMicrophoneArray")
        events = tuple(self.source_events)
        if not events or not all(isinstance(item, CalibratedSourceEvent) for item in events):
            raise ValueError("source_events must contain at least one CalibratedSourceEvent")
        event_ids = [item.event_id for item in events]
        if len(set(event_ids)) != len(event_ids):
            raise ValueError("event_id values must be unique")
        if not np.isfinite(self.speed_of_sound_m_s) or self.speed_of_sound_m_s <= 0.0:
            raise ValueError("speed_of_sound_m_s must be finite and greater than 0")
        sample_rate = self.microphone_array.sampling_frequency.hertz
        if any(
            event.reference_signal is not None
            and event.reference_signal.signal.sampling_frequency.hertz != sample_rate
            for event in events
        ):
            raise ValueError("known reference signals must use the calibrated array sampling frequency")
        object.__setattr__(self, "source_events", events)


@dataclass(frozen=True, slots=True)
class TOAReading:
    """A measured arrival state with optional standard uncertainty.

    ``arrival_time_s`` is relative to the experiment's common synchronized
    time origin. Missing/invalid entries are explicit and carry no numeric
    time, preventing placeholder values from entering calculations.
    """

    arrival_time_s: float | None
    uncertainty_s: float | None = None
    status: ObservationStatus = "observed"
    reason: str | None = None

    def __post_init__(self) -> None:
        if self.status not in ("observed", "missing", "invalid"):
            raise ValueError("status must be observed, missing, or invalid")
        if self.status == "observed":
            if self.arrival_time_s is None or not np.isfinite(self.arrival_time_s):
                raise ValueError("observed readings require a finite arrival_time_s")
            if self.uncertainty_s is not None and (
                not np.isfinite(self.uncertainty_s) or self.uncertainty_s < 0.0
            ):
                raise ValueError("uncertainty_s must be finite and non-negative seconds")
            if self.reason is not None:
                raise ValueError("reason is only used for missing or invalid readings")
        else:
            if self.arrival_time_s is not None or self.uncertainty_s is not None:
                raise ValueError("missing/invalid readings must not carry a time or uncertainty")
            if self.status == "invalid" and not self.reason:
                raise ValueError("invalid readings require a reason")


@dataclass(frozen=True, slots=True)
class DirectPathTOAObservation:
    """Direct-path observation; no wall association is applicable."""

    microphone_id: str
    event_id: str
    reading: TOAReading
    detection_strength: float | None = None
    provenance: DetectionProvenance = "unknown"

    def __post_init__(self) -> None:
        _identifier(self.microphone_id, "microphone_id")
        _identifier(self.event_id, "event_id")
        if not isinstance(self.reading, TOAReading):
            raise TypeError("reading must be TOAReading")
        _detection_metadata(self.detection_strength, self.provenance)


@dataclass(frozen=True, slots=True)
class FirstOrderReflectionTOAObservation:
    """First-order reflection carrying an explicit, auditable wall label."""

    microphone_id: str
    event_id: str
    wall_id: WallIdentifier
    reading: TOAReading
    label_source: ReflectionLabelSource

    def __post_init__(self) -> None:
        _identifier(self.microphone_id, "microphone_id")
        _identifier(self.event_id, "event_id")
        if self.wall_id not in WALLS:
            raise ValueError(f"wall_id must be one of {WALLS}")
        if not isinstance(self.reading, TOAReading):
            raise TypeError("reading must be TOAReading")
        if self.label_source not in (
            "synthetic_ground_truth", "external_annotation", "estimated_association"
        ):
            raise ValueError("label_source must state the origin of the wall label")


@dataclass(frozen=True, slots=True)
class UnlabeledEchoTOAObservation:
    """Real or unassociated echo detection with no assumed wall identity."""

    microphone_id: str
    event_id: str
    echo_id: str
    reading: TOAReading
    reflection_order_hint: int | None = None
    detection_strength: float | None = None
    provenance: DetectionProvenance = "unknown"
    candidate_classification: Literal["unclassified_echo_candidate"] = "unclassified_echo_candidate"

    def __post_init__(self) -> None:
        _identifier(self.microphone_id, "microphone_id")
        _identifier(self.event_id, "event_id")
        _identifier(self.echo_id, "echo_id")
        if not isinstance(self.reading, TOAReading):
            raise TypeError("reading must be TOAReading")
        if self.reflection_order_hint not in (None, 1):
            raise ValueError("this model only supports an absent or first-order hint")
        _detection_metadata(self.detection_strength, self.provenance)
        if self.candidate_classification != "unclassified_echo_candidate":
            raise ValueError("unlabeled echo candidates must remain explicitly unclassified")


@dataclass(frozen=True, slots=True)
class CalibratedTOAObservationSet:
    """TOA records bound to calibrated inputs and explicit data provenance."""

    inputs: CalibratedShoeboxInputs
    origin: DatasetOrigin
    direct_paths: tuple[DirectPathTOAObservation, ...] = ()
    labeled_first_order_reflections: tuple[FirstOrderReflectionTOAObservation, ...] = ()
    unlabeled_echoes: tuple[UnlabeledEchoTOAObservation, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.inputs, CalibratedShoeboxInputs):
            raise TypeError("inputs must be CalibratedShoeboxInputs")
        if self.origin not in ("synthetic", "real"):
            raise ValueError("origin must be synthetic or real")
        direct = tuple(self.direct_paths)
        labeled = tuple(self.labeled_first_order_reflections)
        unlabeled = tuple(self.unlabeled_echoes)
        if not all(isinstance(item, DirectPathTOAObservation) for item in direct):
            raise TypeError("direct_paths contains an invalid observation type")
        if not all(isinstance(item, FirstOrderReflectionTOAObservation) for item in labeled):
            raise TypeError("labeled_first_order_reflections contains an invalid observation type")
        if not all(isinstance(item, UnlabeledEchoTOAObservation) for item in unlabeled):
            raise TypeError("unlabeled_echoes contains an invalid observation type")
        microphone_ids = {item.microphone_id for item in self.inputs.microphone_array.microphones}
        event_ids = {item.event_id for item in self.inputs.source_events}
        all_items = (*direct, *labeled, *unlabeled)
        for item in all_items:
            if item.microphone_id not in microphone_ids:
                raise ValueError(f"unknown microphone_id: {item.microphone_id}")
            if item.event_id not in event_ids:
                raise ValueError(f"unknown event_id: {item.event_id}")
        if self.origin == "synthetic" and any(
            item.label_source not in ("synthetic_ground_truth", "estimated_association")
            for item in labeled
        ):
            raise ValueError("synthetic reflection labels must identify their ground-truth or inferred origin")
        if self.origin == "real" and any(
            item.label_source not in ("external_annotation", "estimated_association")
            for item in labeled
        ):
            raise ValueError(
                "real reflection labels require external annotation or inferred-association provenance"
            )
        direct_keys = [(item.microphone_id, item.event_id) for item in direct]
        if len(set(direct_keys)) != len(direct_keys):
            raise ValueError("direct path observations must be unique per microphone/event")
        reflection_keys = [(item.microphone_id, item.event_id, item.wall_id) for item in labeled]
        if len(set(reflection_keys)) != len(reflection_keys):
            raise ValueError("labeled reflection observations must be unique per microphone/event/wall")
        echo_keys = [(item.microphone_id, item.event_id, item.echo_id) for item in unlabeled]
        if len(set(echo_keys)) != len(echo_keys):
            raise ValueError("unlabeled echo_id values must be unique per microphone/event")
        object.__setattr__(self, "direct_paths", direct)
        object.__setattr__(self, "labeled_first_order_reflections", labeled)
        object.__setattr__(self, "unlabeled_echoes", unlabeled)


def _identifier(value: str, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")


def _position(values: Position3D, name: str) -> Position3D:
    try:
        point = tuple(float(value) for value in values)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must contain three finite coordinates in metres") from exc
    if len(point) != 3 or not all(np.isfinite(value) for value in point):
        raise ValueError(f"{name} must contain three finite coordinates in metres")
    return point  # type: ignore[return-value]


def _detection_metadata(strength: float | None, provenance: DetectionProvenance) -> None:
    if strength is not None and (not np.isfinite(strength) or strength < 0.0):
        raise ValueError("detection_strength must be finite and non-negative")
    if provenance not in ("synthetic_audio", "multichannel_file", "unknown"):
        raise ValueError("provenance must be synthetic_audio, multichannel_file, or unknown")
