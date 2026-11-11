"""Signal generation and analysis primitives for BatSight."""

from .generation import generate_linear_sweep, generate_sine_wave
from .matched_filter import MatchedFilterResult, matched_filter
from .models import (
    AudioSignal,
    DetectedArrivalTime,
    KnownReferenceSignal,
    RecordingMetadata,
    SamplingFrequency,
)
from .peaks import detect_peaks

__all__ = [
    "AudioSignal",
    "DetectedArrivalTime",
    "KnownReferenceSignal",
    "MatchedFilterResult",
    "RecordingMetadata",
    "SamplingFrequency",
    "detect_peaks",
    "generate_linear_sweep",
    "generate_sine_wave",
    "matched_filter",
]
