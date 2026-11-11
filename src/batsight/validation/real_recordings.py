"""Small, provenance-strict helpers for evaluating independently annotated data.

These functions do not detect arrivals. The existing Phase 5E.1 extractor is
the only detector used in the Phase 6E experiment; this module only validates
metadata contracts and scores its output against external annotations.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Sequence

import numpy as np


@dataclass(frozen=True, slots=True)
class ImportedRecordingMetadata:
    recording_id: str
    dataset: str
    provenance: Literal["imported_real_multichannel"]
    sample_rate_hz: float
    channel_count: int
    microphone_ids: tuple[str, ...]
    synchronization_status: Literal[
        "independently_verified", "documented_protocol", "asserted_metadata_only", "unknown"
    ]
    time_origin_s: float


@dataclass(frozen=True, slots=True)
class ProviderArrivalAnnotation:
    recording_id: str
    microphone_id: str
    event_id: str
    kind: Literal["direct", "echo"]
    arrival_time_s: float
    source: str
    annotation_method: str
    uncertainty_s: float | None = None
    wall_label: str | None = None


@dataclass(frozen=True, slots=True)
class ArrivalMatch:
    reference_index: int
    detection_index: int
    absolute_error_s: float


@dataclass(frozen=True, slots=True)
class DetectionMetrics:
    true_positive: int
    false_positive: int
    false_negative: int
    precision: float | None
    recall: float | None
    f1: float | None
    matched_errors_s: tuple[float, ...]
    mean_absolute_error_s: float | None
    median_absolute_error_s: float | None
    p95_absolute_error_s: float | None


def parse_imported_recording_metadata(payload: Any) -> ImportedRecordingMetadata:
    """Parse an explicit imported-real envelope; synthetic/laptop data reject."""
    if not isinstance(payload, dict):
        raise ValueError("recording metadata must be a JSON object")
    required = {
        "recording_id", "dataset", "provenance", "sample_rate_hz", "channel_count",
        "microphone_ids", "synchronization_status", "time_origin_s",
    }
    if not required.issubset(payload):
        raise ValueError(f"recording metadata missing keys: {sorted(required - set(payload))}")
    if payload["provenance"] != "imported_real_multichannel":
        raise ValueError("this evaluator accepts only imported_real_multichannel provenance")
    recording_id, dataset = payload["recording_id"], payload["dataset"]
    if not isinstance(recording_id, str) or not recording_id.strip() or not isinstance(dataset, str) or not dataset.strip():
        raise ValueError("recording_id and dataset must be non-empty strings")
    try:
        sample_rate = float(payload["sample_rate_hz"])
        channels = int(payload["channel_count"])
        time_origin = float(payload["time_origin_s"])
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("sample rate, channel count and time origin must be numeric") from exc
    if not np.isfinite(sample_rate) or sample_rate <= 0 or channels < 1 or not np.isfinite(time_origin):
        raise ValueError("sample rate, channel count or time origin is invalid")
    mic_ids = payload["microphone_ids"]
    if not isinstance(mic_ids, list) or len(mic_ids) != channels or any(not isinstance(v, str) or not v for v in mic_ids):
        raise ValueError("microphone_ids must identify every channel in channel order")
    if len(set(mic_ids)) != len(mic_ids):
        raise ValueError("microphone_ids must be unique")
    sync = payload["synchronization_status"]
    allowed = {"independently_verified", "documented_protocol", "asserted_metadata_only", "unknown"}
    if sync not in allowed:
        raise ValueError("unrecognized synchronization status")
    return ImportedRecordingMetadata(recording_id, dataset, payload["provenance"], sample_rate, channels,
                                     tuple(mic_ids), sync, time_origin)


def parse_provider_annotations(payload: Any) -> tuple[ProviderArrivalAnnotation, ...]:
    """Parse provider annotations without accepting detector-derived labels."""
    if not isinstance(payload, dict) or payload.get("annotation_provenance") != "independent_provider_annotation":
        raise ValueError("annotations must be explicitly identified as independent provider annotations")
    method = payload.get("annotation_method")
    rows = payload.get("arrivals")
    if not isinstance(method, str) or not method.strip() or not isinstance(rows, list):
        raise ValueError("annotation_method and arrivals are required")
    result: list[ProviderArrivalAnnotation] = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("annotation rows must be objects")
        try:
            record_id = str(row["recording_id"])
            mic_id = str(row["microphone_id"])
            event_id = str(row["event_id"])
            time_s = float(row["arrival_time_s"])
            kind = row["kind"]
            source = str(row["source"])
            uncertainty = None if row.get("uncertainty_s") is None else float(row["uncertainty_s"])
        except (KeyError, TypeError, ValueError, OverflowError) as exc:
            raise ValueError("annotation row has missing or invalid fields") from exc
        if not record_id or not mic_id or not event_id or not source or kind not in ("direct", "echo"):
            raise ValueError("annotation identity, kind, or source is invalid")
        if not np.isfinite(time_s) or (uncertainty is not None and (not np.isfinite(uncertainty) or uncertainty < 0)):
            raise ValueError("annotation times and uncertainties must be finite and uncertainty non-negative")
        result.append(ProviderArrivalAnnotation(record_id, mic_id, event_id, kind, time_s, source, method,
                                                uncertainty, row.get("wall_label")))
    return tuple(result)


def associate_annotations(
    metadata: ImportedRecordingMetadata,
    annotations: Sequence[ProviderArrivalAnnotation],
    *,
    event_id: str,
) -> tuple[ProviderArrivalAnnotation, ...]:
    """Select annotations by exact recording/event identity and known channels."""
    selected = tuple(item for item in annotations if item.recording_id == metadata.recording_id and item.event_id == event_id)
    if not selected:
        raise ValueError("no provider annotations match the recording/event identity")
    if any(item.microphone_id not in metadata.microphone_ids for item in selected):
        raise ValueError("an annotation refers to a microphone outside the recording channel map")
    return selected


def match_arrivals(reference_times_s: Sequence[float], detected_times_s: Sequence[float], *, tolerance_s: float) -> tuple[ArrivalMatch, ...]:
    """Maximum-cardinality, minimum-error one-to-one matching in time order.

    Dynamic programming is used so a weak nearby detection cannot greedily
    consume a reference that is the only valid match for another detection.
    Equal-score solutions prefer earlier reference and detection times. No
    candidate is forced outside the tolerance.
    """
    refs = np.asarray(reference_times_s, dtype=np.float64)
    dets = np.asarray(detected_times_s, dtype=np.float64)
    if refs.ndim != 1 or dets.ndim != 1 or not np.all(np.isfinite(refs)) or not np.all(np.isfinite(dets)):
        raise ValueError("arrival times must be finite one-dimensional sequences")
    if not np.isfinite(tolerance_s) or tolerance_s < 0:
        raise ValueError("tolerance_s must be finite and non-negative")
    # Sort by time while preserving original indexes, then solve a monotone match.
    rs = sorted(enumerate(refs.tolist()), key=lambda item: (item[1], item[0]))
    ds = sorted(enumerate(dets.tolist()), key=lambda item: (item[1], item[0]))
    nr, nd = len(rs), len(ds)
    # Each cell stores (matched count, negative total error, action).
    score = [[(0, 0.0, "") for _ in range(nd + 1)] for _ in range(nr + 1)]
    for i in range(1, nr + 1):
        score[i][0] = (0, 0.0, "skip_ref")
    for j in range(1, nd + 1):
        score[0][j] = (0, 0.0, "skip_det")
    for i in range(1, nr + 1):
        for j in range(1, nd + 1):
            choices = [(score[i - 1][j][0], score[i - 1][j][1], "skip_ref"),
                       (score[i][j - 1][0], score[i][j - 1][1], "skip_det")]
            error = abs(rs[i - 1][1] - ds[j - 1][1])
            if error <= tolerance_s:
                prev = score[i - 1][j - 1]
                choices.append((prev[0] + 1, prev[1] - error, "match"))
            # max cardinality first, then minimum total absolute error, deterministic preference for match.
            priority = {"skip_ref": 3, "skip_det": 2, "match": 1}
            best = max(choices, key=lambda item: (item[0], item[1], priority[item[2]]))
            score[i][j] = best
    pairs: list[ArrivalMatch] = []
    i, j = nr, nd
    while i or j:
        action = score[i][j][2]
        if action == "match":
            ri, rt = rs[i - 1]
            di, dt = ds[j - 1]
            pairs.append(ArrivalMatch(ri, di, abs(rt - dt)))
            i -= 1
            j -= 1
        elif action == "skip_ref":
            i -= 1
        elif action == "skip_det":
            j -= 1
        else:
            break
    return tuple(reversed(pairs))


def score_arrivals(reference_times_s: Sequence[float], detected_times_s: Sequence[float], *, tolerance_s: float) -> DetectionMetrics:
    """Compute direct/echo detection counts and absolute timing-error summary."""
    refs = tuple(float(value) for value in reference_times_s)
    dets = tuple(float(value) for value in detected_times_s)
    matches = match_arrivals(refs, dets, tolerance_s=tolerance_s)
    tp = len(matches)
    fp, fn = len(dets) - tp, len(refs) - tp
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    f1 = 2 * precision * recall / (precision + recall) if precision is not None and recall is not None and precision + recall else None
    errors = tuple(match.absolute_error_s for match in matches)
    if errors:
        values = np.asarray(errors, dtype=np.float64)
        mae, median, p95 = float(np.mean(values)), float(np.median(values)), float(np.percentile(values, 95))
    else:
        mae = median = p95 = None
    return DetectionMetrics(tp, fp, fn, precision, recall, f1, errors, mae, median, p95)
