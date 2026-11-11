"""Adapter from recorded-audio peak extraction to calibrated TOA records."""

from __future__ import annotations

from typing import Literal

from batsight.datasets.calibrated import (
    CalibratedTOAObservationSet,
    DirectPathTOAObservation,
    TOAReading,
    UnlabeledEchoTOAObservation,
)
from batsight.signals.recording_analysis import RecordingAnalysisResult


def recording_analysis_to_observations(
    result: RecordingAnalysisResult,
    *,
    origin: Literal["synthetic", "real"] = "real",
) -> CalibratedTOAObservationSet:
    """Adapt detections while preserving missing states and extraction provenance.

    Extracted echo candidates remain unlabeled and have no forced reflection
    order. Accepted and rejected candidate audit details remain available in
    ``RecordingAnalysisResult``; only accepted candidates become TOA records.
    No synthetic ground-truth wall labels are copied.
    """
    if not isinstance(result, RecordingAnalysisResult):
        raise TypeError("result must be RecordingAnalysisResult")
    provenance = "synthetic_audio" if origin == "synthetic" else "multichannel_file"
    direct_records = []
    echo_records = []
    for pair in result.pair_results:
        if pair.direct_arrival is None:
            direct_records.append(DirectPathTOAObservation(
                pair.microphone_id,
                pair.event_id,
                TOAReading(None, status="missing"),
                provenance=provenance,
            ))
        else:
            arrival = pair.direct_arrival
            direct_records.append(DirectPathTOAObservation(
                pair.microphone_id,
                pair.event_id,
                TOAReading(arrival.arrival_time_s, arrival.uncertainty_s),
                detection_strength=arrival.peak_to_noise_ratio,
                provenance=provenance,
            ))
        for arrival in pair.echo_candidates:
            echo_records.append(UnlabeledEchoTOAObservation(
                pair.microphone_id,
                pair.event_id,
                str(arrival.echo_id),
                TOAReading(arrival.arrival_time_s, arrival.uncertainty_s),
                reflection_order_hint=None,
                detection_strength=arrival.peak_to_noise_ratio,
                provenance=provenance,
                candidate_classification="unclassified_echo_candidate",
            ))
    return CalibratedTOAObservationSet(
        result.inputs,
        origin,
        direct_paths=tuple(direct_records),
        unlabeled_echoes=tuple(echo_records),
    )
