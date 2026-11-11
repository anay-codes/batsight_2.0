"""Deterministic tests for unordered echo association and dimension fitting."""

import numpy as np
import pytest

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
from batsight.reconstruction import (
    estimate_dimensions_from_unlabeled_echoes,
    estimate_shoebox_dimensions,
)
from batsight.signals import SamplingFrequency
from batsight.simulation import ShoeboxRoom, predict_first_order_arrivals


ROOMS = ((4.0, 3.8, 3.3), (5.6, 4.5, 3.7), (6.2, 5.1, 4.3))


def make_observations(dimensions, *, seed=11, noise_s=0.0, missing_rate=0.0, false_count=0):
    microphones = (
        CalibratedMicrophone("m0", (0.6, 0.8, 0.7)),
        CalibratedMicrophone("m1", (1.8, 1.0, 1.4)),
        CalibratedMicrophone("m2", (1.2, 2.2, 1.0)),
        CalibratedMicrophone("m3", (2.5, 1.7, 2.0)),
    )
    events = (
        CalibratedSourceEvent("e0", "s0", (3.1, 2.6, 2.2), 0.01),
        CalibratedSourceEvent("e1", "s1", (2.7, 2.8, 1.5), 0.037),
        CalibratedSourceEvent("e2", "s2", (3.4, 1.9, 2.5), 0.062),
    )
    inputs = CalibratedShoeboxInputs(
        CalibratedMicrophoneArray(microphones, SamplingFrequency(48_000)), events, 343.0
    )
    truth_room = ShoeboxRoom(dimensions, 343.0)
    predictions = [p for p in predict_first_order_arrivals(inputs, truth_room) if p.reflection_order == 1]
    rng = np.random.default_rng(seed)
    raw = []
    truth = {}
    for index, p in enumerate(predictions):
        if rng.random() < missing_rate:
            continue
        echo_id = f"{p.microphone_id}-{p.event_id}-echo-{index}"
        time = p.arrival_time_s + (float(rng.normal(0.0, noise_s)) if noise_s else 0.0)
        raw.append(UnlabeledEchoTOAObservation(
            p.microphone_id, p.event_id, echo_id, TOAReading(time, 2e-5 if noise_s else None), 1
        ))
        truth[echo_id] = p.wall_id
    for false_index in range(false_count):
        # Explicit synthetic false detections: times are chosen outside the true first-order cluster.
        pair = (microphones[false_index % len(microphones)].microphone_id,
                events[false_index % len(events)].event_id)
        echo_id = f"false-{false_index}"
        raw.append(UnlabeledEchoTOAObservation(
            pair[0], pair[1], echo_id, TOAReading(0.5 + 0.01 * false_index), 1
        ))
    rng.shuffle(raw)
    return CalibratedTOAObservationSet(inputs, "synthetic", unlabeled_echoes=tuple(raw)), truth, inputs


def run(data, *, initial=(5.2, 4.8, 4.1), upper=(9.0, 8.0, 7.0), **kwargs):
    return estimate_dimensions_from_unlabeled_echoes(
        data,
        initial_dimensions_m=initial,
        upper_bounds_m=upper,
        max_match_error_s=0.004,
        association_scale_s=2e-5,
        **kwargs,
    )


def scoring(result, truth):
    matched = {item.echo_id: item.wall_id for item in result.final_assignments}
    ambiguous = set(result.ambiguous_echo_ids)
    evaluable = {echo_id: wall for echo_id, wall in truth.items() if echo_id not in ambiguous}
    correct = sum(matched.get(echo_id) == wall for echo_id, wall in evaluable.items())
    return correct / len(evaluable) if evaluable else 1.0


@pytest.mark.parametrize("dimensions", ROOMS)
def test_complete_unordered_echoes_recover_association_and_dimensions(dimensions):
    data, truth, _ = make_observations(dimensions, seed=21)
    result = run(data)
    assert result.status == "converged"
    assert result.estimated_dimensions_m == pytest.approx(dimensions, abs=2e-7)
    assert scoring(result, truth) == 1.0
    assert result.unassigned_detection_count == 0
    assert result.missed_path_count == 0
    assert result.dimension_fit.jacobian_rank == 3
    assert result.dimension_fit.physical_valid


def test_randomized_input_order_does_not_drive_arrival_order_assignment():
    a, truth_a, _ = make_observations((4.0, 3.8, 3.3), seed=4)
    b, truth_b, _ = make_observations((4.0, 3.8, 3.3), seed=19)
    result_a, result_b = run(a), run(b)
    assert result_a.estimated_dimensions_m == pytest.approx(result_b.estimated_dimensions_m)
    assert truth_a == truth_b
    assert scoring(result_a, truth_a) == 1.0
    mapping_a = {item.echo_id: item.wall_id for item in result_a.final_assignments}
    mapping_b = {item.echo_id: item.wall_id for item in result_b.final_assignments}
    ambiguous = set(result_a.ambiguous_echo_ids) | set(result_b.ambiguous_echo_ids)
    shared_unambiguous = (mapping_a.keys() & mapping_b.keys()) - ambiguous
    assert all(mapping_a[key] == mapping_b[key] for key in shared_unambiguous)


def test_missing_echoes_noise_and_false_detections_are_counted_separately():
    data, truth, _ = make_observations(
        (4.0, 3.8, 3.3), seed=32, noise_s=5e-6, missing_rate=0.18, false_count=3
    )
    result = run(data)
    assert result.input_echo_count == len(data.unlabeled_echoes)
    assert result.unassigned_detection_count == 3
    assert result.missed_path_count > 0
    assert result.estimated_dimensions_m is not None
    assert result.dimension_fit.physical_valid
    assert result.dimension_fit.jacobian_rank == 3
    # Association metrics are post-run only; no truth label reaches the estimator.
    assert scoring(result, truth) > 0.9
    assert max(abs(a - b) for a, b in zip(result.estimated_dimensions_m, (4.0, 3.8, 3.3))) < 0.02


def test_nonobserved_echo_records_are_excluded_without_fabricating_arrivals():
    data, _, inputs = make_observations((4.0, 3.8, 3.3))
    rows = list(data.unlabeled_echoes)
    rows.append(UnlabeledEchoTOAObservation("m0", "e0", "miss-state", TOAReading(None, status="missing"), 1))
    rows.append(UnlabeledEchoTOAObservation("m0", "e0", "invalid-state", TOAReading(None, status="invalid", reason="clipped"), 1))
    altered = CalibratedTOAObservationSet(inputs, "synthetic", unlabeled_echoes=tuple(rows))
    result = run(altered)
    assert result.excluded_nonobserved_echo_count == 2
    assert result.usable_echo_count == len(data.unlabeled_echoes)
    assert result.estimated_dimensions_m == pytest.approx((4.0, 3.8, 3.3), abs=2e-7)


def test_labeled_phase5d2_baseline_and_unlabeled_fit_agree():
    dimensions = (5.6, 4.5, 3.7)
    unlabeled, truth, inputs = make_observations(dimensions, seed=8)
    # These labels are created only for the explicit labeled baseline, not passed to unlabeled association.
    arrivals = [p for p in predict_first_order_arrivals(inputs, ShoeboxRoom(dimensions, 343.0)) if p.reflection_order]
    labeled = CalibratedTOAObservationSet(
        inputs,
        "synthetic",
        labeled_first_order_reflections=tuple(
            FirstOrderReflectionTOAObservation(
                p.microphone_id, p.event_id, p.wall_id, TOAReading(p.arrival_time_s), "synthetic_ground_truth"
            ) for p in arrivals
        ),
    )
    baseline = estimate_shoebox_dimensions(
        labeled, initial_dimensions_m=(5.2, 4.8, 4.1), upper_bounds_m=(9.0, 8.0, 7.0)
    )
    associated = run(unlabeled)
    assert baseline.estimated_dimensions_m == pytest.approx(dimensions, abs=2e-7)
    assert associated.estimated_dimensions_m == pytest.approx(baseline.estimated_dimensions_m, abs=2e-7)
    assert scoring(associated, truth) == 1.0


def test_ambiguous_arrival_ties_are_reported_not_resolved_by_global_order():
    # Symmetric microphone/source placement makes some wall arrival times tie or nearly tie.
    mics = (CalibratedMicrophone("center", (2.0, 2.0, 1.5)),)
    events = (CalibratedSourceEvent("center-event", "s", (2.3, 1.7, 1.8), 0.0),)
    inputs = CalibratedShoeboxInputs(CalibratedMicrophoneArray(mics, SamplingFrequency(48_000)), events, 343.0)
    dims = (4.0, 4.0, 3.0)
    preds = [p for p in predict_first_order_arrivals(inputs, ShoeboxRoom(dims, 343.0)) if p.reflection_order]
    echoes = tuple(
        UnlabeledEchoTOAObservation("center", "center-event", f"e{i}", TOAReading(p.arrival_time_s), 1)
        for i, p in enumerate(preds)
    )
    data = CalibratedTOAObservationSet(inputs, "synthetic", unlabeled_echoes=echoes)
    result = estimate_dimensions_from_unlabeled_echoes(
        data,
        initial_dimensions_m=(4.1, 4.1, 3.1),
        upper_bounds_m=(8.0, 8.0, 7.0),
        association_scale_s=1e-4,
        max_match_error_s=0.01,
    )
    assert result.ambiguous_echo_ids
    assert result.status in ("converged", "max_iterations", "dimension_fit_failed")


def test_invalid_controls_and_no_echo_failure_are_explicit():
    data, _, _ = make_observations((4.0, 3.8, 3.3))
    with pytest.raises(ValueError, match="max_iterations"):
        run(data, max_iterations=0)
    with pytest.raises(ValueError, match="labeled reflections"):
        labeled = CalibratedTOAObservationSet(
            data.inputs, "synthetic", labeled_first_order_reflections=(
                FirstOrderReflectionTOAObservation("m0", "e0", "x_max", TOAReading(0.03), "synthetic_ground_truth"),
            )
        )
        run(labeled)
    empty = CalibratedTOAObservationSet(data.inputs, "synthetic")
    result = run(empty)
    assert result.status == "dimension_fit_failed"
    assert result.usable_echo_count == 0


def test_estimated_association_provenance_is_not_mislabeled_as_ground_truth():
    data, _, inputs = make_observations((4.0, 3.8, 3.3))
    echo = data.unlabeled_echoes[0]
    inferred = FirstOrderReflectionTOAObservation(
        echo.microphone_id, echo.event_id, "x_min", echo.reading, "estimated_association"
    )
    dataset = CalibratedTOAObservationSet(inputs, "synthetic", labeled_first_order_reflections=(inferred,))
    assert dataset.labeled_first_order_reflections[0].label_source == "estimated_association"
