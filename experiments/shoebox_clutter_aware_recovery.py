"""Deterministic audio-to-room comparison for clutter-aware association."""

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
    CalibratedTOAObservationSet,
    FirstOrderReflectionTOAObservation,
    TOAReading,
    UnlabeledEchoTOAObservation,
)
from batsight.datasets.audio_toa import recording_analysis_to_observations
from batsight.reconstruction.clutter_aware_association import estimate_dimensions_clutter_aware
from batsight.reconstruction.echo_association import estimate_dimensions_from_unlabeled_echoes
from batsight.reconstruction.shoebox_dimensions import estimate_shoebox_dimensions
from batsight.signals import AudioSignal, KnownReferenceSignal, RecordingMetadata, SamplingFrequency, generate_linear_sweep
from batsight.signals.recording_analysis import RecordingAnalysisConfig, analyze_multichannel_recording
from batsight.simulation import ShoeboxRoom, simulate_recordings


FS = 48_000.0
C = 343.0
UPPER = (8.5, 8.0, 7.0)
STARTS = (
    (4.7, 4.6, 4.0),
    (5.8, 5.8, 5.0),
    (6.8, 6.5, 5.8),
)
RECOVERY_MAX_ABS_M = 0.05  # predeclared synthetic geometry recovery screen
RECOVERY_MAX_PERCENT = 2.0


def _make_case(name, dimensions, *, seed, snr_db, reflection, layout):
    fs = SamplingFrequency(FS)
    chirp = generate_linear_sweep(900.0, 11_000.0, 0.01, fs, amplitude=0.8)
    reference = KnownReferenceSignal(chirp, "generic engineering sweep; not paper Eq. 10")
    if layout == "symmetric":
        mic_positions = ((2.0, 2.0, 1.5),)
        source_positions = ((2.3, 1.7, 1.8),)
    elif layout == "alternate":
        mic_positions = ((0.8, 0.9, 0.8), (2.4, 1.2, 1.6), (1.3, 2.8, 2.2), (3.1, 2.1, 1.1))
        source_positions = ((3.8, 3.4, 2.8), (2.9, 1.7, 2.5))
    else:
        mic_positions = ((0.8, 0.9, 0.7), (2.1, 1.3, 1.4), (1.4, 2.9, 2.0), (3.2, 2.3, 1.1))
        source_positions = ((3.6, 3.3, 2.8), (2.8, 1.8, 2.7), (3.4, 2.8, 1.7))
    emissions = tuple(0.02 + idx * 0.13 for idx in range(len(source_positions)))
    microphones = tuple(CalibratedMicrophone(f"mic-{i}", pos) for i, pos in enumerate(mic_positions))
    events = tuple(
        CalibratedSourceEvent(f"event-{i}", f"source-{i}", pos, emissions[i], reference)
        for i, pos in enumerate(source_positions)
    )
    inputs = CalibratedShoeboxInputs(
        CalibratedMicrophoneArray(microphones, fs, clocks_synchronized=True), events, C
    )
    coeffs = {wall: reflection for wall in ("x_min", "x_max", "y_min", "y_max", "z_min", "z_max")}
    room = ShoeboxRoom(tuple(dimensions), C, coeffs)
    recording_samples = np.zeros((int(0.42 * FS), len(microphones)), dtype=np.float64)
    truth: dict[tuple[str, str], list[dict]] = {}
    for event in events:
        padded = AudioSignal(np.pad(chirp.samples, (fs.time_to_sample_index(event.emission_time_s), 0)), fs)
        simulation = simulate_recordings(
            room,
            event.position_m,
            [mic.position_m for mic in microphones],
            padded,
            max_reflection_order=2,
            impulse_placement="linear",
        )
        used = min(recording_samples.shape[0], simulation.recordings.sample_count)
        recording_samples[:used] += simulation.recordings.samples[:used]
        for mic, rir in zip(microphones, simulation.impulse_responses):
            truth[(mic.microphone_id, event.event_id)] = [
                {
                    "order": path.reflection_order,
                    "wall": path.reflection_sequence[0] if path.reflection_order == 1 else None,
                    "toa_s": event.emission_time_s + path.time_of_flight_s,
                }
                for path in rir.paths
            ]
    if snr_db is not None:
        rng = np.random.default_rng(seed)
        power = float(np.mean(recording_samples**2))
        recording_samples += rng.normal(
            0.0, np.sqrt(power * 10.0 ** (-snr_db / 10.0)), recording_samples.shape
        )
    recording = AudioSignal(
        recording_samples,
        fs,
        RecordingMetadata(
            recording_id=f"{name}-{seed}",
            notes="Synthetic shoebox order-2 convolution, then seeded additive white noise.",
            attributes={"sample_rate_hz": int(FS), "channel_count": len(microphones)},
        ),
    )
    analysis = analyze_multichannel_recording(
        recording,
        reference,
        inputs,
        config=RecordingAnalysisConfig(
            direct_tolerance_s=0.0015,
            minimum_echo_excess_delay_s=1.0 / FS,
            maximum_echo_excess_delay_s=0.035,
            minimum_peak_separation_s=0.00012,
            window_length_samples=12,
            thr1=0.9,
            thr2=0.008,
        ),
    )
    adapter = recording_analysis_to_observations(analysis, origin="synthetic")
    rng = np.random.default_rng(seed + 71)
    # Add a small number of explicit, unlabeled clutter detections in a fixed
    # excess-delay range. This generator does not inspect wall labels/positions.
    false_ids = set()
    echo_list = list(adapter.unlabeled_echoes)
    for i in range(min(2, len(microphones) * len(events))):
        mic = microphones[i % len(microphones)]
        event = events[(i * 3) % len(events)]
        distance = float(np.linalg.norm(np.asarray(event.position_m) - np.asarray(mic.position_m)))
        direct = event.emission_time_s + distance / C
        false_id = f"injected/{name}/{seed}/{i}"
        false_ids.add(false_id)
        echo_list.append(UnlabeledEchoTOAObservation(
            mic.microphone_id,
            event.event_id,
            false_id,
            TOAReading(direct + float(rng.uniform(0.012, 0.028))),
            provenance="synthetic_audio",
        ))
    observations = CalibratedTOAObservationSet(
        inputs,
        "synthetic",
        direct_paths=adapter.direct_paths,
        unlabeled_echoes=tuple(echo_list),
    )
    return {
        "name": name,
        "seed": seed,
        "dimensions_truth_evaluation_only_m": tuple(dimensions),
        "snr_db": snr_db,
        "reflection_coefficient": reflection,
        "layout": layout,
        "inputs": inputs,
        "observations": observations,
        "truth": truth,
        "false_ids": false_ids,
        "raw_extraction": analysis,
    }


def _truth_map(case):
    """Map extracted echo IDs to simulator paths after estimation for scoring only."""
    echo_by_pair: dict[tuple[str, str], list] = {}
    for echo in case["observations"].unlabeled_echoes:
        if echo.echo_id in case["false_ids"]:
            continue
        echo_by_pair.setdefault((echo.microphone_id, echo.event_id), []).append(echo)
    candidate_truth: dict[str, tuple[str, int]] = {}
    for pair, echoes in echo_by_pair.items():
        paths = case["truth"][pair]
        times = [p["toa_s"] for p in paths if p["order"] in (1, 2)]
        if not echoes or not times:
            continue
        # Assign candidates to all simulator paths for post-run classification;
        # only order-1 labels are used to score association.
        cost = np.abs(np.subtract.outer([e.reading.arrival_time_s for e in echoes], times))
        rows, cols = linear_sum_assignment(cost)
        path_records = [p for p in paths if p["order"] in (1, 2)]
        for row, col in zip(rows, cols):
            if cost[row, col] <= max(2.0 / FS, 7e-5):
                path = path_records[col]
                candidate_truth[echoes[row].echo_id] = (str(path["wall"]), int(path["order"]))
    return candidate_truth


def _score_method(case, result, method_name, candidate_truth):
    assigned = {item.echo_id: item.wall_id for item in result.final_assignments}
    true_first_order = {
        echo_id: wall for echo_id, (wall, order) in candidate_truth.items() if order == 1
    }
    true_nonfirst = set(candidate_truth) - set(true_first_order)
    false_ids = case["false_ids"]
    clutter_ids = true_nonfirst | false_ids
    correctly_associated = sum(assigned.get(echo_id) == wall for echo_id, wall in true_first_order.items())
    associated_truth = sum(echo_id in assigned for echo_id in true_first_order)
    wrong_first_order = sum(
        echo_id in assigned and assigned[echo_id] != wall for echo_id, wall in true_first_order.items()
    )
    rejected_clutter = sum(echo_id not in assigned for echo_id in clutter_ids)
    expected_paths = sum(
        1 for pair_paths in case["truth"].values() for path in pair_paths if path["order"] == 1
    )
    detected_firstorder = len(true_first_order)
    dimensions = result.estimated_dimensions_m
    truth_dims = case["dimensions_truth_evaluation_only_m"]
    abs_errors = [abs(a - b) for a, b in zip(dimensions, truth_dims)] if dimensions else None
    pct_errors = [100.0 * e / d for e, d in zip(abs_errors, truth_dims)] if abs_errors else None
    fit = result.dimension_fit
    return {
        "method": method_name,
        "status": result.status,
        "converged": result.converged,
        "estimated_dimensions_m": dimensions,
        "dimensions_truth_evaluation_only_m": truth_dims,
        "dimension_absolute_errors_m": abs_errors,
        "dimension_percentage_errors": pct_errors,
        "maximum_absolute_dimension_error_m": max(abs_errors) if abs_errors else None,
        "mean_absolute_dimension_percentage_error": float(np.mean(pct_errors)) if pct_errors else None,
        "recovery_pass_predeclared": bool(
            result.status == "converged"
            and abs_errors
            and max(abs_errors) <= RECOVERY_MAX_ABS_M
            and max(pct_errors) <= RECOVERY_MAX_PERCENT
            and fit is not None
            and fit.physical_valid
        ),
        "extracted_first_order_candidate_recall": detected_firstorder / expected_paths if expected_paths else None,
        "wall_association_accuracy_all_detected_first_order": (
            correctly_associated / associated_truth if associated_truth else None
        ),
        "wrong_first_order_associations": wrong_first_order,
        "unassigned_candidate_count": len(result.unassigned_echo_ids),
        "clutter_rejection_rate": rejected_clutter / len(clutter_ids) if clutter_ids else None,
        "injected_false_detections_unassigned": sum(echo_id not in assigned for echo_id in false_ids),
        "missed_first_order_paths": max(0, expected_paths - associated_truth),
        "predicted_wall_paths_missed": len(result.missed_paths),
        "toa_fit_residual_rms_s": (
            fit.residual_statistics.rms_s if fit and fit.residual_statistics else None
        ),
        "jacobian_rank": fit.jacobian_rank if fit else None,
        "jacobian_condition_number": fit.jacobian_condition_number if fit else None,
        "optimizer_success": fit.optimizer_success if fit else None,
        "optimizer_status": fit.optimizer_status if fit else None,
        "optimizer_function_evaluations": fit.function_evaluations if fit else None,
        "physical_valid": fit.physical_valid if fit else None,
        "association_ambiguity_count": len(result.ambiguous_echo_ids),
        "rejected_edge_count": len(getattr(result, "rejected_edges", ())),
        "iterations": len(result.iterations),
        "runtime_s": result.runtime_s,
        "warnings": result.warnings,
    }


def _labeled_ceiling(case, candidate_truth, initial):
    observations = case["observations"]
    labeled = []
    for echo in observations.unlabeled_echoes:
        if echo.echo_id in case["false_ids"]:
            continue
        label = candidate_truth.get(echo.echo_id)
        if label and label[1] == 1:
            labeled.append(FirstOrderReflectionTOAObservation(
                echo.microphone_id,
                echo.event_id,
                label[0],
                echo.reading,
                "synthetic_ground_truth",
            ))
    labeled_data = CalibratedTOAObservationSet(
        observations.inputs,
        "synthetic",
        direct_paths=observations.direct_paths,
        labeled_first_order_reflections=tuple(labeled),
    )
    fit = estimate_shoebox_dimensions(
        labeled_data,
        initial_dimensions_m=initial,
        upper_bounds_m=UPPER,
        max_nfev=400,
    )
    class _Result:
        pass
    result = _Result()
    result.status = fit.status
    result.converged = fit.status == "converged"
    result.estimated_dimensions_m = fit.estimated_dimensions_m
    result.final_assignments = ()
    result.unassigned_echo_ids = ()
    result.missed_paths = ()
    result.ambiguous_echo_ids = ()
    result.dimension_fit = fit
    result.iterations = ()
    result.runtime_s = None
    result.warnings = fit.warnings
    return _score_method(case, result, "phase5d2_labeled_extracted_upper_bound", candidate_truth)


def run_case(case, initial):
    observations = case["observations"]
    candidate_truth = _truth_map(case)
    start = perf_counter()
    baseline = estimate_dimensions_from_unlabeled_echoes(
        observations,
        initial_dimensions_m=initial,
        upper_bounds_m=UPPER,
        association_scale_s=1e-4,
        max_match_error_s=0.006,
        missing_path_penalty=9.0,
        false_detection_penalty=9.0,
        max_iterations=20,
        max_nfev=400,
    )
    baseline_runtime = perf_counter() - start
    robust = estimate_dimensions_clutter_aware(
        observations,
        initial_dimensions_m=initial,
        upper_bounds_m=UPPER,
        association_scale_s=1e-4,
        maximum_match_error_s=0.006,
        consistency_gate_s=5e-4,
        missing_path_penalty=9.0,
        clutter_penalty=9.0,
        ambiguity_cost_gap=1.0,
        strength_weight=0.25,
        max_iterations=20,
        max_nfev=400,
    )
    baseline_record = _score_method(case, baseline, "phase5d3_hungarian_baseline", candidate_truth)
    baseline_record["runtime_s"] = baseline_runtime
    robust_record = _score_method(case, robust, "phase5e2_clutter_aware", candidate_truth)
    labeled = _labeled_ceiling(case, candidate_truth, initial)
    return {
        "case": case["name"],
        "seed": case["seed"],
        "snr_db": case["snr_db"],
        "reflection_coefficient": case["reflection_coefficient"],
        "layout": case["layout"],
        "initial_dimensions_m_not_truth_derived": initial,
        "recording_channels": case["observations"].inputs.microphone_array.microphones.__len__(),
        "source_event_count": len(case["observations"].inputs.source_events),
        "unlabeled_input_echo_count": len(observations.unlabeled_echoes),
        "extraction_candidate_count": len(observations.unlabeled_echoes) - len(case["false_ids"]),
        "ground_truth_label_leakage_to_estimators": False,
        "methods": [labeled, baseline_record, robust_record],
    }


def main():
    cases = []
    specifications = (
        ("room_a_nominal", (4.5, 4.2, 3.6), 0.7, None, "standard"),
        ("room_b_noisy_alternate", (5.4, 4.8, 3.8), 0.7, 30.0, "alternate"),
        ("room_c_weak_reflections", (4.8, 4.4, 3.7), 0.16, 18.0, "standard"),
        ("room_d_symmetric", (4.0, 4.0, 3.0), 0.7, None, "symmetric"),
    )
    for name, dims, reflection, snr, layout in specifications:
        for seed in (17, 29):
            case = _make_case(name, dims, seed=seed, snr_db=snr, reflection=reflection, layout=layout)
            for initial in STARTS:
                cases.append(run_case(case, initial))
    recovery = {}
    for method in ("phase5d2_labeled_extracted_upper_bound", "phase5d3_hungarian_baseline", "phase5e2_clutter_aware"):
        records = [entry for case in cases for entry in case["methods"] if entry["method"] == method]
        recovery[method] = {
            "runs": len(records),
            "recovery_passes": sum(bool(row["recovery_pass_predeclared"]) for row in records),
            "recovery_rate": sum(bool(row["recovery_pass_predeclared"]) for row in records) / len(records),
        }
    output = {
        "title": "Phase 5E.2 clutter-aware audio-to-room synthetic investigation",
        "synthetic_only": True,
        "ground_truth_wall_labels_used_for_scoring_after_estimation_only": True,
        "recovery_criteria_predeclared": {
            "max_absolute_dimension_error_m": RECOVERY_MAX_ABS_M,
            "max_dimension_percentage_error": RECOVERY_MAX_PERCENT,
            "optimizer_status_must_be_converged": True,
            "physical_validity_required": True,
        },
        "association_settings": {
            "maximum_match_error_s": 0.006,
            "consistency_gate_s": 0.0005,
            "missing_path_penalty": 9.0,
            "clutter_penalty": 9.0,
            "optional_strength_weight": 0.25,
            "max_iterations": 20,
        },
        "aggregate_recovery": recovery,
        "runs": cases,
    }
    path = Path(__file__).with_name("shoebox_clutter_aware_recovery_results.json")
    path.write_text(json.dumps(output, indent=2), encoding="utf-8")
    for method, stats in recovery.items():
        print(f"{method}: {stats['recovery_passes']}/{stats['runs']} ({stats['recovery_rate']:.3f})")
    print(f"Wrote {path}")


if __name__ == "__main__":
    main()
