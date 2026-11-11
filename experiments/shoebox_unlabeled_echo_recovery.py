"""Deterministic unlabeled first-order echo association experiments.

Run from the repository root with ``python experiments/shoebox_unlabeled_echo_recovery.py``.
Ground-truth wall identities are retained in this runner only for scoring;
they are never inserted into the observation set passed to the estimator.
"""

from __future__ import annotations

import json
from pathlib import Path
from time import perf_counter

import numpy as np

from batsight.datasets import (
    CalibratedMicrophone,
    CalibratedMicrophoneArray,
    CalibratedShoeboxInputs,
    CalibratedSourceEvent,
    CalibratedTOAObservationSet,
    FirstOrderReflectionTOAObservation,
    FirstOrderReflectionTOAObservation,
    TOAReading,
    UnlabeledEchoTOAObservation,
)
from batsight.reconstruction import (
    estimate_dimensions_from_unlabeled_echoes,
    estimate_shoebox_dimensions,
)
from batsight.signals import SamplingFrequency
from batsight.simulation import ShoeboxRoom, predict_first_order_arrivals


def _make_case(name, dimensions, *, seed, noise_s=0.0, missing_rate=0.0, false_count=0,
               alternate_layout=False, symmetric_layout=False):
    if symmetric_layout:
        microphones = (CalibratedMicrophone("center-mic", (2.0, 2.0, 1.5)),)
        source_positions = ((2.3, 1.7, 1.8),)
    elif alternate_layout:
        microphones = (
            CalibratedMicrophone("a-mic", (0.9, 0.7, 0.8)),
            CalibratedMicrophone("b-mic", (2.2, 1.4, 1.1)),
            CalibratedMicrophone("c-mic", (1.3, 2.7, 1.8)),
            CalibratedMicrophone("d-mic", (3.0, 1.8, 2.4)),
        )
        source_positions = ((3.5, 3.4, 2.9), (2.8, 1.2, 2.7), (4.1, 2.3, 1.6))
    else:
        microphones = (
            CalibratedMicrophone("m0", (0.6, 0.8, 0.7)),
            CalibratedMicrophone("m1", (1.8, 1.0, 1.4)),
            CalibratedMicrophone("m2", (1.2, 2.2, 1.0)),
            CalibratedMicrophone("m3", (2.5, 1.7, 2.0)),
        )
        source_positions = ((3.1, 2.6, 2.2), (2.7, 2.8, 1.5), (3.4, 1.9, 2.5))
    events = tuple(
        CalibratedSourceEvent(f"event-{index}", f"source-{index}", position, 0.012 + index * 0.023)
        for index, position in enumerate(source_positions)
    )
    speed = 343.0
    inputs = CalibratedShoeboxInputs(
        CalibratedMicrophoneArray(microphones, SamplingFrequency(48_000.0)), events, speed
    )
    truth_dimensions = tuple(float(value) for value in dimensions)
    prediction_room = ShoeboxRoom(truth_dimensions, speed)
    rng = np.random.default_rng(seed)
    echoes = []
    truth_wall_by_echo = {}
    omitted_truth_echoes = []
    candidates = [p for p in predict_first_order_arrivals(inputs, prediction_room) if p.reflection_order == 1]
    for index, arrival in enumerate(candidates):
        echo_id = f"{arrival.microphone_id}/{arrival.event_id}/echo-{index:03d}"
        if rng.random() < missing_rate:
            omitted_truth_echoes.append({"microphone_id": arrival.microphone_id, "event_id": arrival.event_id,
                                         "wall_id": arrival.wall_id})
            continue
        measured = arrival.arrival_time_s + (float(rng.normal(0.0, noise_s)) if noise_s else 0.0)
        echoes.append(UnlabeledEchoTOAObservation(
            arrival.microphone_id,
            arrival.event_id,
            echo_id,
            TOAReading(measured, uncertainty_s=2e-5 if noise_s else None),
            reflection_order_hint=1,
        ))
        truth_wall_by_echo[echo_id] = arrival.wall_id
    false_ids = []
    for index in range(false_count):
        microphone = microphones[index % len(microphones)]
        event = events[(index * 2) % len(events)]
        echo_id = f"{microphone.microphone_id}/{event.event_id}/false-{index:02d}"
        # Explicit false detections are part of the experiment, not fabricated missing arrivals.
        time_s = 0.35 + 0.017 * index
        echoes.append(UnlabeledEchoTOAObservation(
            microphone.microphone_id, event.event_id, echo_id, TOAReading(time_s), reflection_order_hint=1
        ))
        false_ids.append(echo_id)
    rng.shuffle(echoes)
    dataset = CalibratedTOAObservationSet(inputs, "synthetic", unlabeled_echoes=tuple(echoes))
    return {
        "name": name,
        "truth_dimensions_m": truth_dimensions,
        "dataset": dataset,
        "truth_wall_by_echo": truth_wall_by_echo,
        "false_ids": set(false_ids),
        "omitted_truth_echoes": omitted_truth_echoes,
        "possible_first_order_paths": len(candidates),
        "seed": seed,
        "noise_s": noise_s,
        "missing_rate_requested": missing_rate,
        "alternate_layout": alternate_layout,
    }


def _run(case, initial):
    started = perf_counter()
    result = estimate_dimensions_from_unlabeled_echoes(
        case["dataset"],
        initial_dimensions_m=initial,
        upper_bounds_m=(9.0, 8.0, 7.0),
        association_scale_s=2e-5,
        max_match_error_s=4e-3,
        missing_path_penalty=9.0,
        false_detection_penalty=9.0,
        ambiguity_cost_gap=1.0,
        max_iterations=20,
        max_nfev=500,
    )
    runtime = perf_counter() - started
    assigned = {item.echo_id: item.wall_id for item in result.final_assignments}
    truth = case["truth_wall_by_echo"]
    ambiguous = set(result.ambiguous_echo_ids)
    evaluable = {key: wall for key, wall in truth.items() if key not in ambiguous}
    correct = sum(assigned.get(key) == wall for key, wall in evaluable.items())
    association_accuracy = correct / len(evaluable) if evaluable else None
    all_correct = sum(assigned.get(key) == wall for key, wall in truth.items())
    all_accuracy = all_correct / len(truth) if truth else None
    false_assigned = sum(echo_id in assigned for echo_id in case["false_ids"])
    wrong_true = sum(echo_id in assigned and assigned[echo_id] != wall for echo_id, wall in truth.items())
    false_association_count = false_assigned + wrong_true
    missed_true = sum(echo_id not in assigned for echo_id in truth)
    assignment_count = len(result.final_assignments)
    dimensions = result.estimated_dimensions_m
    errors = [abs(a - b) for a, b in zip(dimensions, case["truth_dimensions_m"])] if dimensions else None
    dimfit = result.dimension_fit
    return {
        "case": case["name"],
        "seed": case["seed"],
        "noise_standard_deviation_s": case["noise_s"],
        "requested_missing_rate": case["missing_rate_requested"],
        "possible_first_order_paths": case["possible_first_order_paths"],
        "input_echoes": result.input_echo_count,
        "usable_echoes": result.usable_echo_count,
        "dimensions_truth_evaluation_only_m": case["truth_dimensions_m"],
        "estimated_dimensions_m": dimensions,
        "absolute_dimension_error_m": errors,
        "max_absolute_dimension_error_m": max(errors) if errors else None,
        "association_accuracy_excluding_reported_ambiguous_pairs": association_accuracy,
        "association_accuracy_all_detected_true_echoes": all_accuracy,
        "ambiguous_echo_count": len(result.ambiguous_echo_ids),
        "ambiguous_echo_ids": result.ambiguous_echo_ids,
        "unassigned_echo_ids": result.unassigned_echo_ids,
        "false_detection_count": len(case["false_ids"]),
        "false_detections_assigned_to_walls": false_assigned,
        "wrongly_assigned_true_echoes": wrong_true,
        "false_association_count": false_association_count,
        "false_association_rate_among_assignments": (
            false_association_count / assignment_count if assignment_count else None
        ),
        "omitted_true_echoes": case["omitted_truth_echoes"],
        "unmatched_detected_true_echo_count": missed_true,
        "unassigned_detected_false_echo_count": sum(echo_id not in assigned for echo_id in case["false_ids"]),
        "missed_predicted_path_count": result.missed_path_count,
        "missed_predicted_paths": result.missed_paths,
        "inferred_associations": [
            {
                "microphone_id": item.microphone_id,
                "event_id": item.event_id,
                "echo_id": item.echo_id,
                "inferred_wall_id": item.wall_id,
                "observed_time_s": item.observed_time_s,
                "predicted_time_s": item.predicted_time_s,
                "residual_s": item.residual_s,
                "assignment_cost": item.assignment_cost,
            }
            for item in result.final_assignments
        ],
        "dimension_fit_status": dimfit.status if dimfit else None,
        "dimension_optimizer_success": dimfit.optimizer_success if dimfit else None,
        "dimension_optimizer_status": dimfit.optimizer_status if dimfit else None,
        "dimension_optimizer_message": dimfit.termination_message if dimfit else None,
        "dimension_function_evaluations": dimfit.function_evaluations if dimfit else None,
        "dimension_fit_objective": dimfit.objective_value if dimfit else None,
        "toa_residual_statistics_s": ({
            "mean_signed": dimfit.residual_statistics.mean_signed_s,
            "mean_absolute": dimfit.residual_statistics.mean_absolute_s,
            "rms": dimfit.residual_statistics.rms_s,
            "maximum_absolute": dimfit.residual_statistics.maximum_absolute_s,
        } if dimfit and dimfit.residual_statistics else None),
        "jacobian_rank": dimfit.jacobian_rank if dimfit else None,
        "jacobian_singular_values": dimfit.jacobian_singular_values if dimfit else None,
        "jacobian_condition_number": dimfit.jacobian_condition_number if dimfit else None,
        "physical_valid": dimfit.physical_valid if dimfit else None,
        "converged": result.converged,
        "association_status": result.status,
        "iteration_count": len(result.iterations),
        "runtime_s_external_wallclock": runtime,
        "runtime_s_reported": result.runtime_s,
        "warnings": result.warnings,
        "iterations": [
            {
                "iteration": step.iteration,
                "dimensions_before_m": step.dimensions_before_m,
                "dimensions_after_m": step.dimensions_after_m,
                "matched_count": len(step.assignments),
                "unassigned_count": len(step.unassigned_echo_ids),
                "missed_path_count": step.missed_wall_paths,
                "ambiguous_count": len(step.ambiguous_echo_ids),
                "changed_assignments": step.changed_assignments,
                "association_objective": step.association_objective,
                "dimension_fit_status": step.dimension_fit.status if step.dimension_fit else None,
            }
            for step in result.iterations
        ],
    }


def _labeled_baseline(case, initial):
    inputs = case["dataset"].inputs
    labeled = []
    for echo in case["dataset"].unlabeled_echoes:
        wall = case["truth_wall_by_echo"].get(echo.echo_id)
        if wall is None:
            continue
        labeled.append(FirstOrderReflectionTOAObservation(
            echo.microphone_id, echo.event_id, wall, echo.reading, "synthetic_ground_truth"
        ))
    baseline_set = CalibratedTOAObservationSet(
        inputs, "synthetic", labeled_first_order_reflections=tuple(labeled)
    )
    result = estimate_shoebox_dimensions(
        baseline_set, initial_dimensions_m=initial, upper_bounds_m=(9.0, 8.0, 7.0), max_nfev=500
    )
    return {
        "status": result.status,
        "estimated_dimensions_m": result.estimated_dimensions_m,
        "absolute_dimension_error_m": (
            [abs(a - b) for a, b in zip(result.estimated_dimensions_m, case["truth_dimensions_m"])]
            if result.estimated_dimensions_m else None
        ),
        "residual_rms_s": result.residual_statistics.rms_s if result.residual_statistics else None,
        "jacobian_rank": result.jacobian_rank,
        "condition_number": result.jacobian_condition_number,
        "used_observations": result.observation_counts.labeled_first_order_used,
    }


def main():
    cases = [
        _make_case("complete_room_a", (4.0, 3.8, 3.3), seed=21),
        _make_case("complete_room_b", (5.6, 4.5, 3.7), seed=22),
        _make_case("noisy_missing_false_room_a", (4.0, 3.8, 3.3), seed=32,
                   noise_s=5e-6, missing_rate=0.18, false_count=3),
        _make_case("alternate_spatial_layout", (6.2, 5.1, 4.3), seed=44,
                   noise_s=2e-6, alternate_layout=True),
        _make_case("symmetric_ambiguous_pair", (4.0, 4.0, 3.0), seed=55, symmetric_layout=True),
    ]
    results = []
    for case in cases:
        initial = (5.2, 4.8, 4.1)
        if case["name"] == "symmetric_ambiguous_pair":
            initial = (4.1, 4.1, 3.1)
        entry = _run(case, initial)
        entry["labeled_phase5d2_baseline"] = _labeled_baseline(case, initial)
        results.append(entry)
    report = {
        "title": "Phase 5D.3 deterministic unlabeled first-order echo association",
        "synthetic_only": True,
        "ground_truth_labels_passed_to_estimator": False,
        "association_method": "per-microphone/event augmented Hungarian matching alternating with the unchanged Phase 5D.2 bounded dimension fit",
        "cases": results,
    }
    path = Path(__file__).with_name("shoebox_unlabeled_echo_recovery_results.json")
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    for item in results:
        print(
            f"{item['case']}: status={item['association_status']} dimensions={item['estimated_dimensions_m']} "
            f"max_dim_error={item['max_absolute_dimension_error_m']} "
            f"association_accuracy={item['association_accuracy_excluding_reported_ambiguous_pairs']} "
            f"false_assigned={item['false_detections_assigned_to_walls']} "
            f"ambiguous={item['ambiguous_echo_count']} runtime_s={item['runtime_s_external_wallclock']:.3f}"
        )
    print(f"Wrote {path}")


if __name__ == "__main__":
    main()
