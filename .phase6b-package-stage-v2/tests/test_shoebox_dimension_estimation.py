"""Synthetic tests for calibrated shoebox dimension estimation."""

import numpy as np
import pytest

from batsight.datasets import (
    CalibratedMicrophone,
    CalibratedMicrophoneArray,
    CalibratedShoeboxInputs,
    CalibratedSourceEvent,
    CalibratedTOAObservationSet,
    DirectPathTOAObservation,
    FirstOrderReflectionTOAObservation,
    TOAReading,
    UnlabeledEchoTOAObservation,
)
from batsight.reconstruction import estimate_shoebox_dimensions
from batsight.signals import SamplingFrequency
from batsight.simulation import ShoeboxRoom, predict_first_order_arrivals


MICROPHONES = (
    CalibratedMicrophone("m0", (0.7, 1.1, 0.8)),
    CalibratedMicrophone("m1", (1.8, 0.9, 1.5)),
    CalibratedMicrophone("m2", (1.2, 2.2, 1.0)),
)
EVENTS = (
    CalibratedSourceEvent("e0", "s0", (2.1, 1.7, 2.0), 0.011),
    CalibratedSourceEvent("e1", "s1", (3.0, 2.5, 1.8), 0.037),
)


def make_data(dimensions=(4.0, 3.6, 3.2), *, noise_s=0.0, seed=9, missing=(), invalid=(), uncertain=False):
    inputs = CalibratedShoeboxInputs(
        CalibratedMicrophoneArray(MICROPHONES, SamplingFrequency(48_000.0)),
        EVENTS,
        340.0,
    )
    room = ShoeboxRoom(dimensions, inputs.speed_of_sound_m_s)
    rng = np.random.default_rng(seed)
    reflections = []
    for arrival in predict_first_order_arrivals(inputs, room):
        if arrival.reflection_order != 1:
            continue
        key = (arrival.microphone_id, arrival.event_id, arrival.wall_id)
        if key in missing:
            reading = TOAReading(None, status="missing")
        elif key in invalid:
            reading = TOAReading(None, status="invalid", reason="synthetic invalid record")
        else:
            sigma = (1e-5 if arrival.wall_id.endswith("_max") else 2e-5) if uncertain else None
            time = arrival.arrival_time_s + (rng.normal(0.0, noise_s) if noise_s else 0.0)
            reading = TOAReading(time, uncertainty_s=sigma)
        reflections.append(FirstOrderReflectionTOAObservation(
            arrival.microphone_id, arrival.event_id, arrival.wall_id, reading, "synthetic_ground_truth"
        ))
    direct = tuple(
        DirectPathTOAObservation(m.microphone_id, e.event_id, TOAReading(0.0))
        for m in MICROPHONES for e in EVENTS
    )
    unlabeled = (UnlabeledEchoTOAObservation("m0", "e0", "echo0", TOAReading(0.2)),)
    return CalibratedTOAObservationSet(inputs, "synthetic", direct, tuple(reflections), unlabeled), inputs


def estimate(data, initial=(5.0, 4.5, 4.0), upper=(9.0, 8.0, 7.0), **kwargs):
    return estimate_shoebox_dimensions(
        data, initial_dimensions_m=initial, upper_bounds_m=upper, **kwargs
    )


@pytest.mark.parametrize("dimensions,speed", [((4.0, 3.6, 3.2), 340.0), ((6.2, 4.7, 3.9), 343.0), ((8.0, 6.0, 4.2), 330.0)])
def test_noiseless_recovery_multiple_rooms_and_sound_speeds(dimensions, speed):
    data, _ = make_data(dimensions)
    # Rebind the same observations to a known alternate speed only in this fixture's generator.
    if speed != 340.0:
        inputs = CalibratedShoeboxInputs(data.inputs.microphone_array, data.inputs.source_events, speed)
        room = ShoeboxRoom(dimensions, speed)
        records = []
        for arrival in predict_first_order_arrivals(inputs, room):
            if arrival.reflection_order:
                records.append(FirstOrderReflectionTOAObservation(
                    arrival.microphone_id, arrival.event_id, arrival.wall_id,
                    TOAReading(arrival.arrival_time_s), "synthetic_ground_truth"
                ))
        data = CalibratedTOAObservationSet(inputs, "synthetic", labeled_first_order_reflections=tuple(records))
    result = estimate(data)
    assert result.status == "converged"
    assert result.estimated_dimensions_m == pytest.approx(dimensions, abs=2e-8)
    assert result.jacobian_rank == 3
    assert result.physical_valid


def test_labeled_reflection_coverage_counts_and_direct_unlabeled_exclusions():
    missing = {("m0", "e0", "x_min")}
    invalid = {("m1", "e1", "y_min")}
    data, _ = make_data(missing=missing, invalid=invalid)
    result = estimate(data)
    assert result.observation_counts.direct_paths_excluded == len(MICROPHONES) * len(EVENTS)
    assert result.observation_counts.unlabeled_echoes_excluded == 1
    assert result.observation_counts.labeled_first_order_used == 34
    assert result.observation_counts.labeled_first_order_missing == 1
    assert result.observation_counts.labeled_first_order_invalid == 1
    assert result.per_wall_counts[0].missing == 1
    assert result.per_wall_counts[2].invalid == 1
    assert result.estimated_dimensions_m == pytest.approx((4.0, 3.6, 3.2), abs=2e-8)


def test_missing_a_max_wall_axis_returns_insufficient_information_without_optimization():
    missing = {("m0", "e0", "z_max"), ("m1", "e0", "z_max"), ("m2", "e0", "z_max"),
               ("m0", "e1", "z_max"), ("m1", "e1", "z_max"), ("m2", "e1", "z_max")}
    data, _ = make_data(missing=missing)
    result = estimate(data)
    assert result.status == "insufficient_information"
    assert result.optimizer_success is None
    assert result.estimated_dimensions_m is None
    assert "z" in result.termination_message


def test_maximum_wall_observations_alone_are_sufficient_for_three_scalar_dimensions():
    data, inputs = make_data()
    reflections = tuple(
        item for item in data.labeled_first_order_reflections if item.wall_id.endswith("_max")
    )
    max_only = CalibratedTOAObservationSet(inputs, "synthetic", labeled_first_order_reflections=reflections)
    result = estimate(max_only)
    assert result.status == "converged"
    assert result.estimated_dimensions_m == pytest.approx((4.0, 3.6, 3.2), abs=2e-8)


def test_seeded_noise_and_uncertainty_weighting_are_finite_and_reproducible():
    first, _ = make_data(noise_s=8e-6, uncertain=True, seed=42)
    second, _ = make_data(noise_s=8e-6, uncertain=True, seed=42)
    a, b = estimate(first), estimate(second)
    assert a == b
    assert a.status == "converged"
    assert a.weighting_mode == "uncertainty_weighted"
    assert all(np.isfinite(a.estimated_dimensions_m))
    assert a.residual_statistics.rms_s > 0.0


def test_unweighted_mode_and_explicit_default_for_mixed_uncertainties():
    data, inputs = make_data()
    rows = list(data.labeled_first_order_reflections)
    first = rows[0]
    rows[0] = FirstOrderReflectionTOAObservation(
        first.microphone_id, first.event_id, first.wall_id,
        TOAReading(first.reading.arrival_time_s, 1e-5), "synthetic_ground_truth"
    )
    mixed = CalibratedTOAObservationSet(inputs, "synthetic", labeled_first_order_reflections=tuple(rows))
    with pytest.raises(ValueError, match="mixed uncertainty"):
        estimate(mixed)
    result = estimate(mixed, default_uncertainty_s=2e-5)
    assert result.weighting_mode == "uncertainty_weighted"
    assert estimate(data).weighting_mode == "unweighted_seconds"


def test_invalid_configuration_and_unsupported_zero_uncertainty_are_rejected():
    data, inputs = make_data()
    with pytest.raises(ValueError, match="upper bound"):
        estimate(data, upper=(0.9, 0.8, 0.7))
    with pytest.raises(ValueError, match="strictly inside"):
        estimate(data, initial=(9.0, 4.5, 4.0))
    item = data.labeled_first_order_reflections[0]
    zero = FirstOrderReflectionTOAObservation(
        item.microphone_id, item.event_id, item.wall_id,
        TOAReading(item.reading.arrival_time_s, 0.0), "synthetic_ground_truth"
    )
    altered = CalibratedTOAObservationSet(
        inputs, "synthetic", labeled_first_order_reflections=(zero, *data.labeled_first_order_reflections[1:])
    )
    with pytest.raises(ValueError, match="zero uncertainty"):
        estimate(altered)


def test_poor_but_feasible_initialization_and_custom_clearance():
    data, _ = make_data()
    result = estimate(data, initial=(7.5, 7.0, 6.0), interior_clearance_m=1e-3)
    assert result.status == "converged"
    assert result.estimated_dimensions_m == pytest.approx((4.0, 3.6, 3.2), abs=2e-8)
    assert result.minimum_microphone_clearance_m > 1e-3


def test_max_wall_analytic_derivative_matches_central_difference():
    dimensions = np.asarray((4.0, 3.6, 3.2), dtype=np.float64)
    inputs = CalibratedShoeboxInputs(
        CalibratedMicrophoneArray(MICROPHONES, SamplingFrequency(48_000.0)), EVENTS, 340.0
    )
    room = ShoeboxRoom(tuple(dimensions), 340.0)
    predictions = predict_first_order_arrivals(inputs, room)
    arrival = next(p for p in predictions if p.microphone_id == "m0" and p.event_id == "e0" and p.wall_id == "x_max")
    image_x = arrival.image_source_position_m[0]
    mic_x = MICROPHONES[0].position_m[0]
    analytic = 2.0 * (image_x - mic_x) / (340.0 * arrival.propagation_distance_m)
    step = 1e-5
    plus = dimensions.copy(); plus[0] += step
    minus = dimensions.copy(); minus[0] -= step
    t_plus = next(p.arrival_time_s for p in predict_first_order_arrivals(inputs, ShoeboxRoom(tuple(plus), 340.0))
                  if p.microphone_id == "m0" and p.event_id == "e0" and p.wall_id == "x_max")
    t_minus = next(p.arrival_time_s for p in predict_first_order_arrivals(inputs, ShoeboxRoom(tuple(minus), 340.0))
                   if p.microphone_id == "m0" and p.event_id == "e0" and p.wall_id == "x_max")
    assert (t_plus - t_minus) / (2.0 * step) == pytest.approx(analytic, rel=1e-9)


def test_positions_too_close_to_origin_for_requested_clearance_are_rejected():
    microphones = (CalibratedMicrophone("near", (1e-4, 1.0, 1.0)),)
    inputs = CalibratedShoeboxInputs(
        CalibratedMicrophoneArray(microphones, SamplingFrequency(48_000.0)), EVENTS, 340.0
    )
    # Construct a valid dataset contract; estimation must reject incompatible clearance.
    observations = CalibratedTOAObservationSet(inputs, "synthetic")
    with pytest.raises(ValueError, match="exceed interior_clearance"):
        estimate_shoebox_dimensions(
            observations,
            initial_dimensions_m=(5.0, 5.0, 5.0),
            upper_bounds_m=(8.0, 8.0, 8.0),
            interior_clearance_m=1e-3,
        )
