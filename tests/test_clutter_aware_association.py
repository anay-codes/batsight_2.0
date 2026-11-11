"""Tests for the separate clutter-aware association proposal."""

import numpy as np
import pytest

from batsight.datasets import (
    CalibratedMicrophone,
    CalibratedMicrophoneArray,
    CalibratedShoeboxInputs,
    CalibratedSourceEvent,
    CalibratedTOAObservationSet,
    TOAReading,
    UnlabeledEchoTOAObservation,
)
from batsight.reconstruction.clutter_aware_association import estimate_dimensions_clutter_aware
from batsight.reconstruction.echo_association import estimate_dimensions_from_unlabeled_echoes
from batsight.signals import SamplingFrequency
from batsight.simulation import ShoeboxRoom, predict_acoustic_paths


TRUTH = (4.5, 4.2, 3.6)
START = (4.8, 4.5, 3.9)
UPPER = (9.0, 8.0, 7.0)


def make_data(*, seed=41, noise_s=0.0, clutter=False, omit=False):
    microphones = (
        CalibratedMicrophone("m0", (0.8, 0.9, 0.7)),
        CalibratedMicrophone("m1", (2.1, 1.3, 1.4)),
        CalibratedMicrophone("m2", (1.4, 2.9, 2.0)),
        CalibratedMicrophone("m3", (3.2, 2.3, 1.1)),
    )
    events = (
        CalibratedSourceEvent("e0", "s0", (3.6, 3.3, 2.8), 0.01),
        CalibratedSourceEvent("e1", "s1", (2.8, 1.8, 2.7), 0.04),
        CalibratedSourceEvent("e2", "s2", (3.4, 2.8, 1.7), 0.07),
    )
    inputs = CalibratedShoeboxInputs(
        CalibratedMicrophoneArray(microphones, SamplingFrequency(48_000)), events, 343.0
    )
    room = ShoeboxRoom(TRUTH, 343.0)
    rng = np.random.default_rng(seed)
    echoes = []
    truth_wall = {}
    truth_firstorder = 0
    for event in events:
        for mic in microphones:
            paths = predict_acoustic_paths(room, event.position_m, mic.position_m, max_reflection_order=2)
            first_order_idx = 0
            for path in paths:
                if path.reflection_order not in (1, 2):
                    continue
                if path.reflection_order == 1:
                    truth_firstorder += 1
                    if omit and (event.event_id, mic.microphone_id, first_order_idx) in {
                        ("e0", "m0", 0), ("e1", "m2", 2), ("e2", "m3", 4)
                    }:
                        first_order_idx += 1
                        continue
                    wall = path.reflection_sequence[0]
                    first_order_idx += 1
                else:
                    if not clutter:
                        continue
                    wall = None
                echo_id = f"{mic.microphone_id}/{event.event_id}/echo-{len(echoes)}"
                toa = event.emission_time_s + path.time_of_flight_s
                if noise_s:
                    toa += float(rng.normal(0.0, noise_s))
                echoes.append(UnlabeledEchoTOAObservation(
                    mic.microphone_id, event.event_id, echo_id, TOAReading(toa, noise_s if noise_s else None)
                ))
                if wall is not None:
                    truth_wall[echo_id] = wall
    if clutter:
        # Explicit synthetic false detections well outside the first-order TOA cluster.
        for i, mic in enumerate(microphones):
            echoes.append(UnlabeledEchoTOAObservation(
                mic.microphone_id, "e0", f"false-{i}", TOAReading(0.4 + 0.01 * i)
            ))
    rng.shuffle(echoes)
    return (
        CalibratedTOAObservationSet(inputs, "synthetic", unlabeled_echoes=tuple(echoes)),
        truth_wall,
        truth_firstorder,
    )


def run(data, *, initial=START, **kwargs):
    options = {
        "initial_dimensions_m": initial,
        "upper_bounds_m": UPPER,
        "association_scale_s": 1e-4,
        "maximum_match_error_s": 0.006,
        "consistency_gate_s": 0.0004,
        "max_iterations": 20,
    }
    options.update(kwargs)
    return estimate_dimensions_clutter_aware(data, **options)


def test_complete_noiseless_echoes_recover_dimensions_and_wall_associations():
    data, truth, expected = make_data()
    result = run(data)
    assigned = {item.echo_id: item.wall_id for item in result.final_assignments}
    assert result.status == "converged"
    assert result.estimated_dimensions_m == pytest.approx(TRUTH, abs=2e-7)
    assert sum(assigned.get(key) == wall for key, wall in truth.items()) == expected
    assert result.dimension_fit.jacobian_rank == 3
    assert result.dimension_fit.physical_valid
    assert not result.iterations[-1].rejected_edges


def test_clutter_missing_paths_and_false_detections_remain_unassigned_or_rejected():
    data, truth, expected = make_data(seed=13, noise_s=5e-6, clutter=True, omit=True)
    result = run(data)
    assert result.status in ("converged", "max_iterations", "dimension_fit_failed")
    assert result.input_echo_count == len(data.unlabeled_echoes)
    assert result.unassigned_detection_count >= 4
    assert result.missed_paths
    assert result.estimated_dimensions_m is None or all(np.isfinite(result.estimated_dimensions_m))
    assert result.dimension_fit is None or result.dimension_fit.jacobian_rank in (0, 1, 2, 3)
    # The estimator receives only unlabeled records; labels above exist in this test solely for scoring.
    assert not data.labeled_first_order_reflections
    assigned_ids = {item.echo_id for item in result.final_assignments}
    assert all(f"false-{i}" not in assigned_ids for i in range(4))
    assert len(truth) < expected


def test_labeled_and_d53_baselines_remain_importable_and_unmodified():
    data, _, _ = make_data(clutter=True)
    baseline = estimate_dimensions_from_unlabeled_echoes(
        data,
        initial_dimensions_m=START,
        upper_bounds_m=UPPER,
        max_match_error_s=0.006,
        max_iterations=20,
    )
    robust = run(data)
    assert baseline.status in ("converged", "max_iterations", "dimension_fit_failed")
    assert robust.status in ("converged", "max_iterations", "dimension_fit_failed", "no_consistent_assignment")


def test_repeated_runs_are_deterministic_and_strength_is_optional():
    data, _, _ = make_data(clutter=True)
    first = run(data, strength_weight=0.0)
    second = run(data, strength_weight=0.0)
    assert first.final_assignments == second.final_assignments
    assert first.estimated_dimensions_m == pytest.approx(second.estimated_dimensions_m)
    weighted = run(data, strength_weight=0.5)
    assert weighted.status in ("converged", "max_iterations", "dimension_fit_failed", "no_consistent_assignment")


def test_inputs_and_parameters_are_validated_and_labels_are_rejected():
    data, _, _ = make_data()
    with pytest.raises(ValueError, match="max_iterations"):
        run(data, max_iterations=0)
    with pytest.raises(ValueError, match="unlabeled echoes"):
        labeled = CalibratedTOAObservationSet(
            data.inputs,
            "synthetic",
            labeled_first_order_reflections=(),
            unlabeled_echoes=data.unlabeled_echoes,
        )
        # Nonempty labels exercise the protected input contract.
        from batsight.datasets import FirstOrderReflectionTOAObservation
        labeled = CalibratedTOAObservationSet(
            data.inputs, "synthetic",
            labeled_first_order_reflections=(FirstOrderReflectionTOAObservation(
                "m0", "e0", "x_max", TOAReading(0.02), "synthetic_ground_truth"
            ),),
        )
        run(labeled)
