"""Reproduce the restricted dEchorate measured-RIR validation experiment.

Run from the repository root with ``pip install -e '.[phase6e]'`` and
``python experiments/phase6e_real_multichannel_validation.py``. This does not
load raw sweep recordings: the supplied dEchorate SOFA file contains RIRs.
The reference impulse therefore exercises the existing RIR peak/TOA path, not
the original ESS-to-RIR deconvolution or raw-sweep matched-filter path.
"""

from __future__ import annotations

import json
import csv
import gzip
import hashlib
import sys
import time
from collections import Counter
from dataclasses import asdict
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

try:
    import h5py
except ImportError as exc:  # pragma: no cover - user-facing environment guard
    raise SystemExit("Install the optional Phase 6E reader with: pip install -e '.[phase6e]'") from exc

from batsight.datasets.calibrated import (  # noqa: E402
    CalibratedMicrophone,
    CalibratedMicrophoneArray,
    CalibratedShoeboxInputs,
    CalibratedSourceEvent,
)
from batsight.signals.models import AudioSignal, KnownReferenceSignal, SamplingFrequency  # noqa: E402
from batsight.signals.recording_analysis import RecordingAnalysisConfig, analyze_multichannel_recording  # noqa: E402
from batsight.validation.real_recordings import (  # noqa: E402
    associate_annotations,
    match_arrivals,
    parse_imported_recording_metadata,
    parse_provider_annotations,
    score_arrivals,
)


DATA_DIR = ROOT / "data" / "raw" / "dechorate_phase6e"
SOFA_NAME = "dEchorate_room000000_src1_arr1_mics1-5.sofa"
ANNOTATION_NAME = "dEchorate_annotations.h5"
SPEED_OF_SOUND_M_S = 346.98  # paper: 24 +/- 0.5 C, 80% RH
MATCH_TOLERANCE_S = 0.0005  # dEchorate paper's reported GoM threshold


def _decode(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, np.bytes_):
        return bytes(value).decode("utf-8", errors="replace")
    return str(value)


def load_sample() -> tuple[AudioSignal, CalibratedShoeboxInputs, dict[str, Any], list[dict[str, Any]]]:
    sofa_path = DATA_DIR / SOFA_NAME
    annotation_path = DATA_DIR / ANNOTATION_NAME
    if not sofa_path.is_file() or not annotation_path.is_file():
        raise FileNotFoundError(f"Expected the included sample files in {DATA_DIR}")
    with h5py.File(sofa_path, "r") as sofa, h5py.File(annotation_path, "r") as annotations:
        fs = float(np.asarray(sofa["Data.SamplingRate"]).reshape(-1)[0])
        delay = np.asarray(sofa["Data.Delay"], dtype=np.float64).reshape(-1)
        if delay.size != 5 or not np.allclose(delay, 0.0, atol=0.0, rtol=0.0):
            raise ValueError("The selected sample requires its documented all-zero Data.Delay time origin")
        rir = np.asarray(sofa["Data.IR"][0], dtype=np.float64).T  # samples x five channels
        source = np.asarray(sofa["SourcePosition"][0], dtype=np.float64)
        mic_xyz = np.asarray(sofa["ReceiverPosition"][:, :, 0], dtype=np.float64)
        corner_a = np.asarray(sofa["RoomCornerA"][0], dtype=np.float64)
        corner_b = np.asarray(sofa["RoomCornerB"][0], dtype=np.float64)
        if source.shape != (3,) or mic_xyz.shape != (5, 3):
            raise ValueError("Unexpected SOFA geometry dimensions")
        if _decode(sofa.attrs.get("DataType", b"")) != "FIR":
            raise ValueError("This experiment expects an FIR/RIR SOFA file")
        if _decode(sofa.attrs.get("RoomType", b"")) != "shoebox":
            raise ValueError("This experiment expects the documented shoebox sample")
        if "m" not in _decode(sofa["SourcePosition"].attrs.get("Units", b"" )).lower():
            raise ValueError("SOFA source coordinates do not declare metre units")
        if "m" not in _decode(sofa["ReceiverPosition"].attrs.get("Units", b"" )).lower():
            raise ValueError("SOFA receiver coordinates do not declare metre units")
        if not np.all(np.isfinite(rir)):
            raise ValueError("SOFA RIR contains non-finite values")

        microphone_ids = tuple(f"mic{index + 1}" for index in range(5))
        microphones = tuple(CalibratedMicrophone(mic_id, tuple(float(v) for v in xyz))
                           for mic_id, xyz in zip(microphone_ids, mic_xyz))
        array = CalibratedMicrophoneArray(microphones, SamplingFrequency(fs), clocks_synchronized=True)
        event = CalibratedSourceEvent("src1", "src1", tuple(float(v) for v in source), 0.0)
        inputs = CalibratedShoeboxInputs(array, (event,), SPEED_OF_SOUND_M_S)
        signal = AudioSignal(rir, SamplingFrequency(fs))
        metadata = {
            "dataset": "dEchorate",
            "dataset_version_record": "Zenodo 6576203, Version 2.0 HDF5 record; sample mirrored in SOFA database",
            "recording_id": SOFA_NAME,
            "source_file_sha256": hashlib.sha256(sofa_path.read_bytes()).hexdigest(),
            "annotation_file_sha256": hashlib.sha256(annotation_path.read_bytes()).hexdigest(),
            "event_id": "src1",
            "provenance": "imported_real_multichannel",
            "sample_rate_hz": fs,
            "channel_count": 5,
            "microphone_ids": list(microphone_ids),
            "microphone_positions_m": mic_xyz.tolist(),
            "source_position_m": source.tolist(),
            "room_dimensions_from_sofa_m": (corner_b - corner_a).tolist(),
            "room_corner_units_note": "RoomCornerA/B do not carry a Units attribute in the inspected file; their values are interpreted in the SOFA room coordinate metre scale and are consistent with the paper's approximately 6 x 6 x 2.4 m room. Room dimensions are metadata only and are not used by extraction.",
            "sofa_room_corner_a_m": corner_a.tolist(),
            "sofa_room_corner_b_m": corner_b.tolist(),
            "data_delay_s_by_channel": delay.tolist(),
            "recording_start_time_s": 0.0,
            "time_origin_s": 0.0,
            "source_emission_time_s": 0.0,
            "speed_of_sound_m_s": SPEED_OF_SOUND_M_S,
            "synchronization_status": "documented_protocol",
            "synchronization_evidence": "dEchorate paper states synchronous multichannel acquisition at 48 kHz; SOFA Data.Delay is zero for all five stored channels; not independently remeasured here.",
            "calibration_provenance": "SOFA coordinates and room corners; paper reports bIPS position acquisition with +/-2 cm error; this is not independent BatSight survey.",
            "license": {
                "sofa_file_attribute": "MIT license text embedded in SOFA file",
                "annotation_hdf5": "CC BY 4.0 as declared by Zenodo API record 6576203",
                "attribution": "Di Carlo et al., dEchorate, 2021; DOI 10.5281/zenodo.6576203",
            },
        }
        # The annotation array is [arrival-rank, global microphone index, source index].
        # The SOFA filename identifies source 1 and microphones 1-5; row 0 is direct,
        # rows 1-6 are the provider's six first-order echo annotations.
        toa = np.asarray(annotations["echo_toa"], dtype=np.float64)
        walls = np.asarray(annotations["echo_wall"])
        if toa.shape != (7, 30, 6) or walls.shape != toa.shape:
            raise ValueError("Unexpected dEchorate annotation tensor shape")
        if _decode(walls[0, 0, 0]) != "d":
            raise ValueError("The selected annotation entry is not direct path")
        if not np.all(np.diff(toa, axis=0) >= 0.0):
            raise ValueError("Provider arrival-rank order is not monotonic")
        first_order_wall_ids = {b"c", b"f", b"n", b"s", b"e", b"w"}
        if any(set(walls[1:, mic_idx, src_idx]) != first_order_wall_ids
               for mic_idx in range(30) for src_idx in range(6)):
            raise ValueError("Provider ranks 1-6 do not carry the six first-order wall labels")
        annotation_rows: list[dict[str, Any]] = []
        for local_mic in range(5):
            for rank in range(7):
                annotation_rows.append({
                    "recording_id": SOFA_NAME,
                    "microphone_id": microphone_ids[local_mic],
                    "event_id": "src1",
                    "kind": "direct" if rank == 0 else "echo",
                    "arrival_time_s": float(toa[rank, local_mic, 0]),
                    "source": "dEchorate_provider_annotation",
                    "wall_label": _decode(walls[rank, local_mic, 0]),
                    "rank_in_provider_TOA_tensor": rank,
                    "uncertainty_s": None,
                })
        metadata["annotation_provenance"] = "independent_provider_annotation"
        metadata["annotation_method"] = "dEchorate GUI annotations: manually tuned peak finder and echo/wall labels; paper provides no per-label numeric uncertainty."
    return signal, inputs, metadata, annotation_rows


def _svg_plot(path: Path, title: str, series: list[tuple[str, list[tuple[float, float]], str]], *, x_label: str, y_label: str) -> None:
    width, height = 1000, 520
    left, right, top, bottom = 90, 30, 75, 70
    all_x = [x for _, points, _ in series for x, _ in points]
    all_y = [y for _, points, _ in series for _, y in points]
    if not all_x or not all_y:
        return
    xmin, xmax = min(all_x), max(all_x)
    ymin, ymax = min(all_y), max(all_y)
    if xmax == xmin:
        xmax = xmin + 1.0
    if ymax == ymin:
        ymax = ymin + 1.0
    pad_y = (ymax - ymin) * 0.06
    ymin, ymax = ymin - pad_y, ymax + pad_y
    xmap = lambda x: left + (x - xmin) / (xmax - xmin) * (width - left - right)
    ymap = lambda y: height - bottom - (y - ymin) / (ymax - ymin) * (height - top - bottom)
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
             '<rect width="100%" height="100%" fill="white"/>',
             f'<text x="{width/2}" y="32" text-anchor="middle" font-family="sans-serif" font-size="20">{title}</text>',
             f'<text x="{width/2}" y="{height-20}" text-anchor="middle" font-family="sans-serif" font-size="14">{x_label}</text>',
             f'<text x="22" y="{height/2}" transform="rotate(-90 22 {height/2})" text-anchor="middle" font-family="sans-serif" font-size="14">{y_label}</text>',
             f'<line x1="{left}" y1="{height-bottom}" x2="{width-right}" y2="{height-bottom}" stroke="#444"/>',
             f'<line x1="{left}" y1="{top}" x2="{left}" y2="{height-bottom}" stroke="#444"/>']
    for index in range(6):
        x = xmin + index * (xmax - xmin) / 5
        y = ymin + index * (ymax - ymin) / 5
        parts.append(f'<line x1="{xmap(x):.2f}" y1="{top}" x2="{xmap(x):.2f}" y2="{height-bottom}" stroke="#eee"/>')
        parts.append(f'<line x1="{left}" y1="{ymap(y):.2f}" x2="{width-right}" y2="{ymap(y):.2f}" stroke="#eee"/>')
    for label, points, color in series:
        coords = " ".join(f"{xmap(x):.2f},{ymap(y):.2f}" for x, y in points)
        if len(points) > 1:
            parts.append(f'<polyline points="{coords}" fill="none" stroke="{color}" stroke-width="1.3" opacity="0.85"/>')
        for x, y in points:
            parts.append(f'<circle cx="{xmap(x):.2f}" cy="{ymap(y):.2f}" r="2.1" fill="{color}"/>')
    legend_x = left + 12
    for index, (label, _, color) in enumerate(series):
        x = legend_x + index * 205
        parts.append(f'<line x1="{x}" y1="55" x2="{x+24}" y2="55" stroke="{color}" stroke-width="3"/>')
        parts.append(f'<text x="{x+30}" y="60" font-family="sans-serif" font-size="12">{label}</text>')
    parts.append('<text x="500" y="499" text-anchor="middle" font-family="sans-serif" font-size="12" fill="#555">IMPORTED REAL MULTICHANNEL RIR — not raw probe audio — dEchorate src1, mics 1–5</text>')
    parts.append('</svg>')
    path.write_text("\n".join(parts), encoding="utf-8")


def _arrival_scatter(path: Path, pairs: list[tuple[float, float]]) -> None:
    width, height, left, right, top, bottom = 760, 650, 90, 35, 70, 90
    maximum_ms = max((max(ref, det) * 1000 for ref, det in pairs), default=1.0) + 1.0
    xmap = lambda value: left + value / maximum_ms * (width - left - right)
    ymap = lambda value: height - bottom - value / maximum_ms * (height - top - bottom)
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
             '<rect width="100%" height="100%" fill="white"/>',
             '<text x="380" y="30" text-anchor="middle" font-family="sans-serif" font-size="20">dEchorate: detected vs provider arrival times</text>',
             '<text x="380" y="625" text-anchor="middle" font-family="sans-serif" font-size="14">Provider annotation time (ms)</text>',
             '<text x="24" y="350" transform="rotate(-90 24 350)" text-anchor="middle" font-family="sans-serif" font-size="14">BatSight candidate time (ms)</text>',
             f'<line x1="{left}" y1="{height-bottom}" x2="{width-right}" y2="{top}" stroke="#555" stroke-dasharray="6 5"/>',
             f'<line x1="{left}" y1="{top}" x2="{left}" y2="{height-bottom}" stroke="#444"/>',
             f'<line x1="{left}" y1="{height-bottom}" x2="{width-right}" y2="{height-bottom}" stroke="#444"/>']
    for ref_ms, det_ms in pairs:
        parts.append(f'<circle cx="{xmap(ref_ms):.2f}" cy="{ymap(det_ms):.2f}" r="5" fill="#245b9e"/>')
    parts.append('<text x="380" y="600" text-anchor="middle" font-family="sans-serif" font-size="12" fill="#555">Imported real multichannel measured RIR; direct and echo matches scored separately at 0.5 ms</text>')
    parts.append('</svg>')
    path.write_text("\n".join(parts), encoding="utf-8")


def _metric_bars(path: Path, direct_precision: float, direct_recall: float, echo_precision: float, echo_recall: float) -> None:
    width, height = 760, 430
    left, top, bottom = 100, 70, 80
    bars = [("Direct precision", direct_precision, "#17834b"), ("Direct recall", direct_recall, "#44a16e"),
            ("Echo precision", echo_precision, "#d47716"), ("Echo recall", echo_recall, "#e7ac48")]
    gap = 30
    bar_w = 115
    plot_h = height - top - bottom
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
             '<rect width="100%" height="100%" fill="white"/>',
             '<text x="380" y="32" text-anchor="middle" font-family="sans-serif" font-size="20">dEchorate annotation match scores</text>',
             '<text x="20" y="230" transform="rotate(-90 20 230)" text-anchor="middle" font-family="sans-serif" font-size="14">Score (0–1)</text>',
             f'<line x1="{left}" y1="{top}" x2="{left}" y2="{height-bottom}" stroke="#444"/>',
             f'<line x1="{left}" y1="{height-bottom}" x2="{width-30}" y2="{height-bottom}" stroke="#444"/>']
    for tick in range(6):
        val = tick / 5
        y = height - bottom - val * plot_h
        parts.append(f'<line x1="{left}" y1="{y:.1f}" x2="{width-30}" y2="{y:.1f}" stroke="#eee"/>')
        parts.append(f'<text x="{left-14}" y="{y+4:.1f}" text-anchor="end" font-family="sans-serif" font-size="11">{val:.1f}</text>')
    for index, (label, value, color) in enumerate(bars):
        x = left + 25 + index * (bar_w + gap)
        bar_h = max(0.0, min(1.0, value)) * plot_h
        parts.append(f'<rect x="{x}" y="{height-bottom-bar_h:.2f}" width="{bar_w}" height="{bar_h:.2f}" fill="{color}"/>')
        parts.append(f'<text x="{x+bar_w/2}" y="{height-bottom-bar_h-8:.2f}" text-anchor="middle" font-family="sans-serif" font-size="12">{value:.3f}</text>')
        parts.append(f'<text x="{x+bar_w/2}" y="{height-bottom+24}" text-anchor="middle" font-family="sans-serif" font-size="11">{label}</text>')
    parts.append('<text x="380" y="407" text-anchor="middle" font-family="sans-serif" font-size="12" fill="#555">Imported real multichannel RIR; one source, five microphones</text></svg>')
    path.write_text("\n".join(parts), encoding="utf-8")


def run() -> dict[str, Any]:
    signal, inputs, metadata, annotations = load_sample()
    metadata_contract = parse_imported_recording_metadata(metadata)
    annotation_contract = parse_provider_annotations({
        "annotation_provenance": metadata["annotation_provenance"],
        "annotation_method": metadata["annotation_method"],
        "arrivals": annotations,
    })
    if len(annotation_contract) != len(annotations):
        raise AssertionError("Provider annotation JSON parser changed annotation count")
    # Exact recording/event/channel association is checked before any scoring.
    for mic_id in metadata_contract.microphone_ids:
        selected = associate_annotations(metadata_contract, annotation_contract, event_id="src1")
        if len([item for item in selected if item.microphone_id == mic_id]) != 7:
            raise AssertionError(f"Expected one direct plus six echo labels for {mic_id}")
    delta = KnownReferenceSignal(AudioSignal(np.array([1.0]), signal.sampling_frequency), "unit impulse for RIR-domain analysis")
    config = RecordingAnalysisConfig()  # frozen existing Phase 5E.1 defaults; no tuning
    start = time.perf_counter()
    analysis = analyze_multichannel_recording(signal, delta, inputs, recording_start_time_s=0.0, config=config)
    elapsed_s = time.perf_counter() - start
    mic_ids = metadata["microphone_ids"]
    by_mic = {mic_id: [] for mic_id in mic_ids}
    for row in annotations:
        by_mic[row["microphone_id"]].append(row)

    pair_reports: list[dict[str, Any]] = []
    direct_errors_ms: list[float] = []
    geometry_direct_errors_ms: list[float] = []
    echo_errors_ms: list[float] = []
    detected_direct_count = 0
    matched_echo_count = 0
    direct_detection_pairs_ms: list[tuple[float, float]] = []
    echo_detection_pairs_ms: list[tuple[float, float]] = []
    channel_direct_errors: list[tuple[int, float]] = []
    channel_echo_mae: list[tuple[int, float]] = []
    candidate_count = rejected_count = 0
    direct_tp = direct_fp = direct_fn = 0
    echo_tp = echo_fp = echo_fn = 0
    rejected_rows: list[dict[str, Any]] = []
    rejected_reason_counts: Counter[str] = Counter()
    for pair in analysis.pair_results:
        mic_id = pair.microphone_id
        refs = by_mic[mic_id]
        direct_refs = [row for row in refs if row["kind"] == "direct"]
        echo_refs = [row for row in refs if row["kind"] == "echo"]
        direct_times = [] if pair.direct_arrival is None else [pair.direct_arrival.arrival_time_s]
        echo_times = [item.arrival_time_s for item in pair.echo_candidates]
        direct_metric = score_arrivals([row["arrival_time_s"] for row in direct_refs], direct_times, tolerance_s=MATCH_TOLERANCE_S)
        echo_metric = score_arrivals([row["arrival_time_s"] for row in echo_refs], echo_times, tolerance_s=MATCH_TOLERANCE_S)
        if direct_metric.matched_errors_s:
            direct_errors_ms.extend(error * 1000 for error in direct_metric.matched_errors_s)
        if echo_metric.matched_errors_s:
            echo_errors_ms.extend(error * 1000 for error in echo_metric.matched_errors_s)
        detected_direct_count += int(pair.direct_arrival is not None)
        matched_echo_count += echo_metric.true_positive
        candidate_count += len(pair.echo_candidates)
        rejected_count += len(pair.rejected_peaks)
        direct_tp += direct_metric.true_positive
        direct_fp += direct_metric.false_positive
        direct_fn += direct_metric.false_negative
        echo_tp += echo_metric.true_positive
        echo_fp += echo_metric.false_positive
        echo_fn += echo_metric.false_negative
        rejected_rows.extend(asdict(item) for item in pair.rejected_peaks)
        rejected_reason_counts.update(item.reason for item in pair.rejected_peaks)
        expected_geometry = pair.expected_direct_time_s
        geometry_direct_errors_ms.append((expected_geometry - direct_refs[0]["arrival_time_s"]) * 1000)
        direct_refs_delta = (pair.direct_arrival.arrival_time_s - direct_refs[0]["arrival_time_s"]) if pair.direct_arrival else None
        direct_matches = match_arrivals([row["arrival_time_s"] for row in direct_refs], direct_times, tolerance_s=MATCH_TOLERANCE_S)
        echo_matches = match_arrivals([row["arrival_time_s"] for row in echo_refs], echo_times, tolerance_s=MATCH_TOLERANCE_S)
        for match in direct_matches:
            direct_detection_pairs_ms.append((direct_refs[match.reference_index]["arrival_time_s"] * 1000,
                                              direct_times[match.detection_index] * 1000))
        for match in echo_matches:
            echo_detection_pairs_ms.append((echo_refs[match.reference_index]["arrival_time_s"] * 1000,
                                            echo_times[match.detection_index] * 1000))
        channel_index = mic_ids.index(mic_id) + 1
        if direct_refs_delta is not None:
            channel_direct_errors.append((channel_index, direct_refs_delta * 1000))
        if echo_metric.mean_absolute_error_s is not None:
            channel_echo_mae.append((channel_index, echo_metric.mean_absolute_error_s * 1000))
        pair_reports.append({
            "microphone_id": mic_id,
            "expected_direct_from_geometry_s": expected_geometry,
            "provider_direct_time_s": direct_refs[0]["arrival_time_s"],
            "geometry_prediction_minus_provider_direct_ms": (expected_geometry - direct_refs[0]["arrival_time_s"]) * 1000,
            "direct_detection_s": pair.direct_arrival.arrival_time_s if pair.direct_arrival else None,
            "direct_detection_diagnostics": asdict(pair.direct_arrival) if pair.direct_arrival else None,
            "direct_detection_minus_provider_ms": None if direct_refs_delta is None else direct_refs_delta * 1000,
            "direct_metrics": asdict(direct_metric),
            "echo_annotations": [{"arrival_time_s": row["arrival_time_s"], "wall_label": row["wall_label"]} for row in echo_refs],
            "echo_candidates": [asdict(item) for item in pair.echo_candidates],
            "echo_metrics": asdict(echo_metric),
            "matched_echo_annotation_candidate_pairs": [
                {"provider_time_s": echo_refs[match.reference_index]["arrival_time_s"],
                 "detection_time_s": echo_times[match.detection_index],
                 "wall_label_for_evaluation_only": echo_refs[match.reference_index]["wall_label"],
                 "absolute_error_s": match.absolute_error_s}
                for match in echo_matches
            ],
            "unmatched_echo_candidate_times_s": [echo_times[index] for index in range(len(echo_times))
                                                   if index not in {match.detection_index for match in echo_matches}],
            "unmatched_provider_echo_times_s": [echo_refs[index]["arrival_time_s"] for index in range(len(echo_refs))
                                                   if index not in {match.reference_index for match in echo_matches}],
            "peak_audit_record_count": len(pair.rejected_peaks),
            "peak_audit_disposition_counts": dict(Counter(item.reason for item in pair.rejected_peaks)),
            "warnings": list(pair.warnings),
        })

    report: dict[str, Any] = {
        "schema_version": "batsight.phase6e.real-validation.v1",
        "evidence_class": "imported_real_multichannel",
        "dataset": metadata,
        "ground_truth": {
            "provenance": "independent_provider_annotation",
            "method": metadata["annotation_method"],
            "annotations": annotations,
            "provider_timing_uncertainty": "not numerically specified in the paper or annotation file",
        },
        "calibration_audit": {
            "channel_order": "SOFA ReceiverPosition order; five named channels mic1..mic5",
            "sample_rate_exact": signal.sampling_frequency.hertz,
            "sound_speed": "346.98 m/s from dEchorate paper environmental condition; not measured on this sample by BatSight",
            "clock_synchronization": "documented_protocol",
            "recording_time_origin": "SOFA Data.Delay is zero for all channels; RIR sample zero treated as common time origin; no raw loopback channel retained in this SOFA file",
            "event_reference": "RIR excitation is represented as a zero-origin impulse response; no raw sweep/loopback waveform is present",
            "independently_verified": False,
        },
        "extraction": {
            "pipeline": "existing analyze_multichannel_recording unchanged",
            "input_kind": "measured deconvolved RIR, not original raw ESS recording",
            "reference": "single-sample unit impulse; matched-filter correlation therefore equals the RIR",
            "config": asdict(config),
            "matching_tolerance_s": MATCH_TOLERANCE_S,
            "matching_tolerance_source": "0.5 ms threshold used by dEchorate paper's goodness-of-match metric; adopted here for external annotation comparison, not inferred annotation uncertainty",
            "runtime_s": elapsed_s,
        },
        "summary": {
            "microphone_event_pairs": len(pair_reports),
            "direct_annotations": len(mic_ids),
            "direct_detected": detected_direct_count,
            "direct_true_positive": direct_tp,
            "direct_false_positive": direct_fp,
            "direct_missed_arrivals": direct_fn,
            "direct_precision_at_tolerance": direct_tp / (direct_tp + direct_fp) if direct_tp + direct_fp else None,
            "direct_recall_at_tolerance": direct_tp / (direct_tp + direct_fn) if direct_tp + direct_fn else None,
            "direct_false_positive_count": direct_fp,
            "direct_mean_absolute_error_ms": float(np.mean(direct_errors_ms)) if direct_errors_ms else None,
            "direct_median_absolute_error_ms": float(np.median(direct_errors_ms)) if direct_errors_ms else None,
            "direct_p95_absolute_error_ms": float(np.percentile(direct_errors_ms, 95)) if direct_errors_ms else None,
            "direct_max_absolute_error_ms": float(np.max(direct_errors_ms)) if direct_errors_ms else None,
            "direct_mean_absolute_error_samples": float(np.mean(direct_errors_ms) * signal.sampling_frequency.hertz / 1000) if direct_errors_ms else None,
            "direct_median_absolute_error_samples": float(np.median(direct_errors_ms) * signal.sampling_frequency.hertz / 1000) if direct_errors_ms else None,
            "direct_p95_absolute_error_samples": float(np.percentile(direct_errors_ms, 95) * signal.sampling_frequency.hertz / 1000) if direct_errors_ms else None,
            "direct_max_absolute_error_samples": float(np.max(direct_errors_ms) * signal.sampling_frequency.hertz / 1000) if direct_errors_ms else None,
            "geometry_predicted_direct_mean_absolute_error_vs_provider_ms": float(np.mean(np.abs(geometry_direct_errors_ms))) if geometry_direct_errors_ms else None,
            "geometry_predicted_direct_max_absolute_error_vs_provider_ms": float(np.max(np.abs(geometry_direct_errors_ms))) if geometry_direct_errors_ms else None,
            "first_order_echo_annotations": 6 * len(mic_ids),
            "first_order_echo_candidates": candidate_count,
            "first_order_echo_matched": matched_echo_count,
            "first_order_echo_false_positive": echo_fp,
            "first_order_echo_missed_annotations": echo_fn,
            "first_order_echo_precision": echo_tp / (echo_tp + echo_fp) if echo_tp + echo_fp else None,
            "first_order_echo_recall": echo_tp / (echo_tp + echo_fn) if echo_tp + echo_fn else None,
            "echo_mean_absolute_error_ms": float(np.mean(echo_errors_ms)) if echo_errors_ms else None,
            "echo_max_absolute_error_ms": float(np.max(echo_errors_ms)) if echo_errors_ms else None,
            "echo_mean_absolute_error_samples": float(np.mean(echo_errors_ms) * signal.sampling_frequency.hertz / 1000) if echo_errors_ms else None,
            "peak_audit_record_count": rejected_count,
            "peak_audit_disposition_counts": dict(rejected_reason_counts),
            "room_geometry_estimation_performed": False,
            "accuracy_claim": "single SOFA RIR configuration/source/array subset only; not raw-sweep validation or broad reliability estimate",
        },
        "per_channel_event": pair_reports,
        "limitations": [
            "Only one source and one five-microphone array subset was evaluated.",
            "SOFA contains deconvolved measured RIRs rather than the raw ESS input; the impulse reference bypasses probe matching and ESS deconvolution.",
            "Provider annotations are manually generated and paper gives no per-label numeric uncertainty; a 0.5 ms comparison threshold does not turn them into independent instrument timing.",
            "Synchronization is supported by acquisition documentation and zero SOFA delays but was not independently verified from raw loopback or hardware clocks.",
            "Echo candidates are compared only against the six provider first-order annotations in this selected event. No wall label is exposed to extraction.",
            "No parameter tuning was performed; the existing Phase 5E.1 defaults were retained.",
        ],
    }

    results_dir = ROOT / "experiments" / "phase6e_results"
    results_dir.mkdir(parents=True, exist_ok=True)
    (results_dir / "dEchorate_real_rir_validation.json").write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    (results_dir / "dEchorate_provider_annotations.json").write_text(json.dumps({
        "annotation_provenance": "independent_provider_annotation",
        "annotation_method": metadata["annotation_method"],
        "arrivals": annotations,
    }, indent=2, allow_nan=False), encoding="utf-8")
    if rejected_rows:
        with gzip.open(results_dir / "dEchorate_peak_audit.csv.gz", "wt", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rejected_rows[0]))
            writer.writeheader()
            writer.writerows(rejected_rows)

    # The existing unit-impulse correlation is numerically the RIR itself. Plot a 0-50 ms view.
    channel0 = signal.samples[:, 0]
    sample_limit = min(channel0.size, int(np.ceil(0.05 * signal.sampling_frequency.hertz)))
    waveform = [(index / signal.sampling_frequency.hertz * 1000.0, float(channel0[index])) for index in range(sample_limit)]
    corr = analysis.pair_results[0]
    pair_response = np.asarray(signal.samples[:, 0], dtype=np.float64)
    response = [(index / signal.sampling_frequency.hertz * 1000.0, float(pair_response[index])) for index in range(sample_limit)]
    _svg_plot(results_dir / "real_rir_waveform_and_correlation.svg", "dEchorate measured RIR and unit-impulse matched-filter response", [
        ("RIR channel mic1", waveform, "#245b9e"), ("correlation response", response, "#d47716")
    ], x_label="Time from SOFA Data.Delay origin (ms)", y_label="RIR / normalized correlation amplitude")
    _arrival_scatter(results_dir / "real_arrival_comparison.svg", direct_detection_pairs_ms + echo_detection_pairs_ms)
    _svg_plot(results_dir / "real_channel_errors.svg", "dEchorate direct and echo timing error by microphone", [
        ("Direct signed error (ms)", [(float(ch), error) for ch, error in channel_direct_errors], "#245b9e"),
        ("Echo mean absolute error (ms)", [(float(ch), error) for ch, error in channel_echo_mae], "#d47716"),
    ], x_label="Microphone channel index", y_label="Direct signed error / echo MAE (ms)")
    _metric_bars(results_dir / "real_precision_recall.svg",
                 report["summary"]["direct_precision_at_tolerance"], report["summary"]["direct_recall_at_tolerance"],
                 report["summary"]["first_order_echo_precision"], report["summary"]["first_order_echo_recall"])
    return report


if __name__ == "__main__":
    output = run()
    print(json.dumps(output["summary"], indent=2))
