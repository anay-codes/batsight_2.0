"""Reproducible synthetic audio-to-unlabeled-TOA experiment runner."""

from __future__ import annotations

import json
from pathlib import Path
from time import perf_counter

import numpy as np
from scipy.optimize import linear_sum_assignment

from batsight.datasets import (
    CalibratedMicrophone,
    CalibratedMicrophoneArray,
    CalibratedShoeboxInputs,
    CalibratedSourceEvent,
)
from batsight.datasets.audio_toa import recording_analysis_to_observations
from batsight.signals import AudioSignal, KnownReferenceSignal, RecordingMetadata, SamplingFrequency, generate_linear_sweep
from batsight.signals.recording_analysis import RecordingAnalysisConfig, analyze_multichannel_recording
from batsight.simulation import ShoeboxRoom, simulate_recordings
from batsight.reconstruction import estimate_dimensions_from_unlabeled_echoes


FS_HZ = 48_000.0
SPEED_M_S = 343.0


def build_case(name, dimensions, *, seed, snr_db=None, reflection_coefficient=0.7, alternate=False, close_arrivals=False):
    fs = SamplingFrequency(FS_HZ)
    chirp = generate_linear_sweep(900.0, 11_000.0, 0.01, fs, amplitude=0.8)
    reference = KnownReferenceSignal(chirp, "generic BatSight synthetic experiment chirp")
    if close_arrivals:
        mic_positions = ((2.0, 2.0, 1.5),)
        source_positions = ((2.3, 1.7, 1.8),)
        emissions = (0.02,)
    elif alternate:
        mic_positions = ((0.8, 0.9, 0.8), (2.4, 1.2, 1.6), (1.3, 2.8, 2.2), (3.1, 2.1, 1.1))
        source_positions = ((3.8, 3.4, 2.8), (2.9, 1.7, 2.5))
        emissions = (0.02, 0.14)
    else:
        mic_positions = ((2.0, 1.7, 1.2), (3.2, 2.3, 1.4), (1.3, 2.8, 2.1))
        source_positions = ((1.1, 1.0, 1.6), (2.2, 1.2, 2.4))
        emissions = (0.02, 0.14)
    microphones = tuple(CalibratedMicrophone(f"mic-{i}", point) for i, point in enumerate(mic_positions))
    events = tuple(
        CalibratedSourceEvent(f"event-{i}", f"source-{i}", point, emissions[i], reference)
        for i, point in enumerate(source_positions)
    )
    inputs = CalibratedShoeboxInputs(
        CalibratedMicrophoneArray(microphones, fs, clocks_synchronized=True), events, SPEED_M_S
    )
    coefficients = {
        wall: reflection_coefficient
        for wall in ("x_min", "x_max", "y_min", "y_max", "z_min", "z_max")
    }
    room = ShoeboxRoom(tuple(dimensions), SPEED_M_S, coefficients)
    frame_count = int(0.28 * FS_HZ)
    multichannel = np.zeros((frame_count, len(microphones)), dtype=np.float64)
    truth_paths = {}
    for event in events:
        start = fs.time_to_sample_index(event.emission_time_s)
        event_input = AudioSignal(np.pad(chirp.samples, (start, 0)), fs)
        rendered = simulate_recordings(
            room,
            event.position_m,
            [mic.position_m for mic in microphones],
            event_input,
            max_reflection_order=2,
            impulse_placement="linear",
        )
        used = min(frame_count, rendered.recordings.sample_count)
        multichannel[:used] += rendered.recordings.samples[:used]
        for mic, response in zip(microphones, rendered.impulse_responses):
            truth_paths[(mic.microphone_id, event.event_id)] = tuple(
                {
                    "order": path.reflection_order,
                    "wall": path.reflection_sequence[0] if path.reflection_order == 1 else None,
                    "toa_s": event.emission_time_s + path.time_of_flight_s,
                }
                for path in response.paths
            )
    if snr_db is not None:
        rng = np.random.default_rng(seed)
        signal_power = float(np.mean(multichannel**2))
        noise_std = float(np.sqrt(signal_power * 10.0 ** (-snr_db / 10.0)))
        multichannel += rng.normal(0.0, noise_std, multichannel.shape)
    recording = AudioSignal(
        multichannel,
        fs,
        RecordingMetadata(
            recording_id=f"synthetic-{name}-{seed}",
            notes="Shoebox image-source convolution; seeded white noise added after event summation.",
            attributes={"sample_rate_hz": int(FS_HZ), "channel_count": len(microphones)},
        ),
    )
    return {
        "name": name,
        "dimensions_for_evaluation_only_m": tuple(dimensions),
        "room": room,
        "reference": reference,
        "inputs": inputs,
        "recording": recording,
        "truth_paths": truth_paths,
        "seed": seed,
        "snr_db": snr_db,
    }


def evaluate(case, extraction):
    fs = extraction.recording.sampling_frequency.hertz
    direct_errors_s = []
    expected_first_order = 0
    matched_first_order = 0
    first_order_errors_s = []
    total_candidates = 0
    duplicate_candidates = 0
    minimum_first_order_gap_s = None
    for pair in extraction.pair_results:
        if pair.direct_arrival:
            direct_errors_s.append(pair.direct_arrival.arrival_time_s - pair.expected_direct_time_s)
        truth = case["truth_paths"][(pair.microphone_id, pair.event_id)]
        first_order = [record["toa_s"] for record in truth if record["order"] == 1]
        if len(first_order) > 1:
            pair_gap = min(
                abs(first_order[i] - first_order[j])
                for i in range(len(first_order))
                for j in range(i + 1, len(first_order))
            )
            minimum_first_order_gap_s = (
                pair_gap if minimum_first_order_gap_s is None else min(minimum_first_order_gap_s, pair_gap)
            )
        expected_first_order += len(first_order)
        candidates = list(pair.echo_candidates)
        total_candidates += len(candidates)
        if first_order and candidates:
            costs = np.abs(np.subtract.outer(first_order, [item.arrival_time_s for item in candidates]))
            rows, cols = linear_sum_assignment(costs)
            used_candidate_indices = set()
            for row, col in zip(rows, cols):
                if costs[row, col] <= max(2.0 / fs, 5e-5):
                    matched_first_order += 1
                    first_order_errors_s.append(candidates[col].arrival_time_s - first_order[row])
                    used_candidate_indices.add(int(col))
            for index, candidate in enumerate(candidates):
                if index not in used_candidate_indices and any(
                    abs(candidate.arrival_time_s - toa) <= 2.0 / fs for toa in first_order
                ):
                    duplicate_candidates += 1
    rejected = [item for pair in extraction.pair_results for item in pair.rejected_peaks]
    reasons = {}
    for item in rejected:
        reasons[item.reason] = reasons.get(item.reason, 0) + 1
    echo_false_count = max(0, total_candidates - matched_first_order)
    return {
        "direct_detection_rate": sum(pair.direct_arrival is not None for pair in extraction.pair_results)
        / max(1, len(extraction.pair_results)),
        "direct_expected_count": len(extraction.pair_results),
        "direct_detected_count": sum(pair.direct_arrival is not None for pair in extraction.pair_results),
        "direct_toa_error_mean_absolute_us": float(np.mean(np.abs(direct_errors_s)) * 1e6) if direct_errors_s else None,
        "direct_toa_error_maximum_absolute_us": float(np.max(np.abs(direct_errors_s)) * 1e6) if direct_errors_s else None,
        "direct_toa_error_maximum_absolute_samples": float(np.max(np.abs(direct_errors_s)) * fs) if direct_errors_s else None,
        "first_order_truth_count": expected_first_order,
        "minimum_first_order_arrival_gap_us": (
            minimum_first_order_gap_s * 1e6 if minimum_first_order_gap_s is not None else None
        ),
        "first_order_candidate_recall": matched_first_order / expected_first_order if expected_first_order else None,
        "matched_first_order_count": matched_first_order,
        "unclassified_candidate_count": total_candidates,
        "unmatched_candidate_count_as_first_order_false_or_higher_order": echo_false_count,
        "unmatched_candidate_rate": echo_false_count / total_candidates if total_candidates else None,
        "duplicate_candidate_count_near_already_matched_first_order_arrivals": duplicate_candidates,
        "first_order_toa_error_mean_absolute_us": float(np.mean(np.abs(first_order_errors_s)) * 1e6) if first_order_errors_s else None,
        "first_order_toa_error_maximum_absolute_us": float(np.max(np.abs(first_order_errors_s)) * 1e6) if first_order_errors_s else None,
        "first_order_toa_error_maximum_absolute_samples": float(np.max(np.abs(first_order_errors_s)) * fs) if first_order_errors_s else None,
        "rejected_peak_count_by_reason": reasons,
        "timing_uncertainty_calibrated": False,
        "timing_uncertainty_note": "uncertainty_s is unset unless caller supplies an externally validated value; robust peak/noise scores are not calibrated probabilities",
    }


def run_case(case):
    started = perf_counter()
    extraction = analyze_multichannel_recording(
        case["recording"],
        case["reference"],
        case["inputs"],
        config=RecordingAnalysisConfig(
            direct_tolerance_s=0.0015,
            minimum_echo_excess_delay_s=1.0 / FS_HZ,
            maximum_echo_excess_delay_s=0.035,
            minimum_peak_separation_s=0.00012,
            window_length_samples=12,
            thr1=0.9,
            thr2=0.008,
            minimum_peak_prominence=0.0,
        ),
    )
    metrics = evaluate(case, extraction)
    adapted = recording_analysis_to_observations(extraction, origin="synthetic")
    initial = (5.2, 4.8, 4.1)
    reconstruction = estimate_dimensions_from_unlabeled_echoes(
        adapted,
        initial_dimensions_m=initial,
        upper_bounds_m=(9.0, 8.0, 7.0),
        association_scale_s=1e-4,
        max_match_error_s=0.005,
        missing_path_penalty=9.0,
        false_detection_penalty=9.0,
        max_iterations=12,
        max_nfev=300,
    )
    dimensions = reconstruction.estimated_dimensions_m
    truth_dimensions = case["dimensions_for_evaluation_only_m"]
    room_error = [abs(a - b) for a, b in zip(dimensions, truth_dimensions)] if dimensions else None
    return {
        "case": case["name"],
        "seed": case["seed"],
        "requested_snr_db": case["snr_db"],
        "recording_sample_rate_hz": FS_HZ,
        "recording_channels": case["recording"].channel_count,
        "recording_duration_s": case["recording"].duration_seconds,
        "dimensions_for_post_run_evaluation_only_m": truth_dimensions,
        "extraction": metrics,
        "extraction_warning_count": len(extraction.warnings),
        "candidate_count_per_microphone_event": {
            f"{pair.microphone_id}/{pair.event_id}": len(pair.echo_candidates)
            for pair in extraction.pair_results
        },
        "candidate_classification": "unclassified; can include first-order, higher-order, and false peaks",
        "observation_adapter": {
            "direct_records": len(adapted.direct_paths),
            "unlabeled_echo_records": len(adapted.unlabeled_echoes),
            "ground_truth_wall_labels_passed": False,
        },
        "phase5d3_reconstruction": {
            "status": reconstruction.status,
            "converged": reconstruction.converged,
            "estimated_dimensions_m": dimensions,
            "absolute_dimension_error_m": room_error,
            "maximum_absolute_dimension_error_m": max(room_error) if room_error else None,
            "matched_association_count": len(reconstruction.final_assignments),
            "ambiguous_association_count": len(reconstruction.ambiguous_echo_ids),
            "unassigned_detection_count": reconstruction.unassigned_detection_count,
            "missed_predicted_path_count": reconstruction.missed_path_count,
            "dimension_fit_status": reconstruction.dimension_fit.status if reconstruction.dimension_fit else None,
            "dimension_fit_toa_rms_s": (
                reconstruction.dimension_fit.residual_statistics.rms_s
                if reconstruction.dimension_fit and reconstruction.dimension_fit.residual_statistics else None
            ),
            "jacobian_rank": reconstruction.dimension_fit.jacobian_rank if reconstruction.dimension_fit else None,
            "jacobian_condition_number": reconstruction.dimension_fit.jacobian_condition_number if reconstruction.dimension_fit else None,
            "physical_valid": reconstruction.dimension_fit.physical_valid if reconstruction.dimension_fit else None,
            "warnings": reconstruction.warnings,
        },
        "total_runtime_s": perf_counter() - started,
    }


def main():
    case_specs = (
        ("noiseless_room_a", (4.5, 4.1, 3.4), 101, None, 0.7, False),
        ("noise_30db_room_b", (5.4, 4.8, 3.8), 202, 30.0, 0.7, True),
        ("noise_18db_weak_reflections", (4.8, 4.4, 3.7), 303, 18.0, 0.16, False),
        ("noise_24db_alternate_room", (6.0, 5.2, 4.2), 404, 24.0, 0.7, True),
        ("close_arrival_symmetry", (4.0, 4.0, 3.0), 505, None, 0.7, False, True),
    )
    results = []
    for spec in case_specs:
        name, dimensions, seed, snr_db, reflection_coefficient, alternate = spec[:6]
        close_arrivals = spec[6] if len(spec) > 6 else False
        case = build_case(
            name,
            dimensions,
            seed=seed,
            snr_db=snr_db,
            reflection_coefficient=reflection_coefficient,
            alternate=alternate,
            close_arrivals=close_arrivals,
        )
        results.append(run_case(case))
    output = {
        "title": "Phase 5E.1 synthetic multichannel waveform to TOA extraction",
        "synthetic_only": True,
        "generic_engineering_chirp_not_paper_eq10_reproduction": True,
        "higher_order_echoes_are_not_classified_by_extractor": True,
        "cases": results,
    }
    path = Path(__file__).with_name("shoebox_audio_toa_recovery_results.json")
    path.write_text(json.dumps(output, indent=2), encoding="utf-8")
    for result in results:
        reconstruction = result["phase5d3_reconstruction"]
        print(
            f"{result['case']}: direct={result['extraction']['direct_detection_rate']:.3f} "
            f"first_order_recall={result['extraction']['first_order_candidate_recall']:.3f} "
            f"false_or_higher_rate={result['extraction']['unmatched_candidate_rate']:.3f} "
            f"dimension_status={reconstruction['status']} "
            f"dimension_error_m={reconstruction['maximum_absolute_dimension_error_m']} "
            f"runtime_s={result['total_runtime_s']:.3f}"
        )
    print(f"Wrote {path}")


if __name__ == "__main__":
    main()
