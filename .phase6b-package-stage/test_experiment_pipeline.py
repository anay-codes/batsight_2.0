import csv
import io

import numpy as np
import pytest

from batsight.experiments import ExpectedArrival, match_arrivals, run_experiment
from batsight.signals import AudioSignal, DetectedArrivalTime, SamplingFrequency
from batsight.simulation import ShoeboxRoom


def excitation(seed: int = 10, count: int = 96, sample_rate: float = 1_000.0) -> AudioSignal:
    rng = np.random.default_rng(seed)
    samples = rng.normal(size=count)
    return AudioSignal(samples, SamplingFrequency(sample_rate))


def direct_room() -> ShoeboxRoom:
    return ShoeboxRoom(
        (4.0, 4.0, 4.0),
        speed_of_sound_m_s=100.0,
        wall_reflection_coefficients={wall: 0.0 for wall in ("x_min", "x_max", "y_min", "y_max", "z_min", "z_max")},
    )


def test_complete_noiseless_direct_path_experiment() -> None:
    result = run_experiment(
        direct_room(),
        (1.0, 1.0, 1.0),
        ((2.0, 1.0, 1.0),),
        excitation(),
        max_reflection_order=0,
        peak_window_length_samples=8,
        thr1=0.9,
        thr2=0.2,
        matching_tolerance_seconds=0.001,
    )
    mic = result.microphone_results[0]
    assert len(mic.toa_comparison.expected_arrivals) == 1
    assert mic.toa_comparison.expected_arrivals[0].time_of_flight_s == pytest.approx(0.01)
    assert len(mic.toa_comparison.matches) == 1
    assert mic.toa_comparison.matches[0].detected.time_seconds == pytest.approx(0.01)
    assert mic.toa_comparison.metrics.mean_absolute_error_seconds == pytest.approx(0.0)
    assert mic.toa_comparison.metrics.root_mean_square_error_seconds == pytest.approx(0.0)
    assert mic.toa_comparison.missed_expected == ()


def test_multiple_microphones_have_separate_positions_paths_and_comparisons() -> None:
    result = run_experiment(
        direct_room(),
        (1.0, 1.0, 1.0),
        ((2.0, 1.0, 1.0), (1.0, 3.0, 1.0)),
        excitation(),
        max_reflection_order=0,
        peak_window_length_samples=8,
        matching_tolerance_seconds=0.001,
    )
    assert result.simulated_recordings.recordings.channel_count == 2
    assert [item.microphone_position_m for item in result.microphone_results] == [(2.0, 1.0, 1.0), (1.0, 3.0, 1.0)]
    assert [item.toa_comparison.expected_arrivals[0].time_of_flight_s for item in result.microphone_results] == pytest.approx([0.01, 0.02])
    assert all(item.toa_comparison.metrics.matched_count == 1 for item in result.microphone_results)


def test_first_order_reflection_is_detected_and_path_truth_is_retained() -> None:
    coefficients = {wall: 0.0 for wall in ("x_min", "x_max", "y_min", "y_max", "z_min", "z_max")}
    coefficients["x_min"] = 0.8
    room = ShoeboxRoom((4.0, 5.0, 6.0), speed_of_sound_m_s=100.0, wall_reflection_coefficients=coefficients)
    result = run_experiment(
        room,
        (1.0, 1.0, 2.0),
        ((2.0, 1.0, 2.0),),
        excitation(seed=31, count=127),
        max_reflection_order=1,
        peak_window_length_samples=8,
        thr2=0.12,
        matching_tolerance_seconds=0.001,
    )
    comparison = result.microphone_results[0].toa_comparison
    matched_sequences = {match.expected.reflection_sequence for match in comparison.matches}
    assert () in matched_sequences
    assert ("x_min",) in matched_sequences
    # Zero-coefficient wall paths remain in simulator ground truth, and may be
    # reported as missed; they are not removed to make detections look complete.
    assert len(comparison.expected_arrivals) == 7
    assert any(arrival.reflection_coefficient == 0 for arrival in comparison.missed_expected)


def test_second_order_paths_are_present_in_experiment_ground_truth() -> None:
    box = ShoeboxRoom((4.0, 5.0, 6.0), speed_of_sound_m_s=100.0)
    result = run_experiment(
        box,
        (1.0, 1.5, 2.0),
        ((2.0, 2.0, 3.0),),
        excitation(seed=8),
        max_reflection_order=2,
        peak_window_length_samples=8,
        thr2=0.2,
        matching_tolerance_seconds=0.001,
    )
    expected = result.microphone_results[0].toa_comparison.expected_arrivals
    assert {item.reflection_order for item in expected} == {0, 1, 2}
    assert len([item for item in expected if item.reflection_order == 2]) == 18


def test_arrival_matching_does_not_force_missed_or_false_peaks() -> None:
    expected = tuple(
        ExpectedArrival(index, 0, (), (0.0, 0.0, 0.0), time, time, 1.0)
        for index, time in enumerate((1.0, 2.0, 3.0))
    )
    detected = (
        DetectedArrivalTime(10, 0.9, 0.5),
        DetectedArrivalTime(20, 2.1, 0.4),
        DetectedArrivalTime(40, 4.0, 0.2),
    )
    comparison = match_arrivals(expected, detected, tolerance_seconds=0.11)
    assert [match.expected.path_index for match in comparison.matches] == [0, 1]
    assert [arrival.path_index for arrival in comparison.missed_expected] == [2]
    assert [arrival.sample_index for arrival in comparison.unmatched_detected] == [40]
    assert comparison.metrics.matched_count == 2


def test_matching_metrics_match_hand_calculation() -> None:
    expected = tuple(
        ExpectedArrival(index, 0, (), (0.0, 0.0, 0.0), time, time, 1.0)
        for index, time in enumerate((0.0, 1.0, 2.0))
    )
    detected = (
        DetectedArrivalTime(1, 0.1, 1.0),
        DetectedArrivalTime(10, 1.2, 1.0),
    )
    comparison = match_arrivals(expected, detected, tolerance_seconds=0.25)
    assert comparison.metrics.matched_count == 2
    assert comparison.metrics.missed_expected_count == 1
    assert comparison.metrics.unmatched_detected_count == 0
    assert comparison.metrics.mean_absolute_error_seconds == pytest.approx((0.1 + 0.2) / 2)
    assert comparison.metrics.root_mean_square_error_seconds == pytest.approx(np.sqrt((0.1**2 + 0.2**2) / 2))


@pytest.mark.parametrize("seed", [2, 19, 2026])
def test_direct_arrival_survives_fixed_high_snr_noise_seeds(seed: int) -> None:
    result = run_experiment(
        direct_room(),
        (1.0, 1.0, 1.0),
        ((2.0, 1.0, 1.0),),
        excitation(seed=5, count=256),
        max_reflection_order=0,
        snr_db=20.0,
        random_seed=seed,
        peak_window_length_samples=8,
        thr2=0.2,
        matching_tolerance_seconds=0.002,
    )
    assert result.microphone_results[0].toa_comparison.metrics.matched_count == 1
    assert result.configuration.random_seed == seed


def test_multiple_noise_levels_are_reproducible_and_distinct() -> None:
    common = dict(
        room=direct_room(),
        source_position_m=(1.0, 1.0, 1.0),
        microphone_positions_m=((2.0, 1.0, 1.0),),
        excitation=excitation(seed=16, count=128),
        max_reflection_order=0,
        random_seed=73,
        peak_window_length_samples=8,
    )
    at_20_db = run_experiment(**common, snr_db=20.0)
    at_5_db = run_experiment(**common, snr_db=5.0)
    repeat_5_db = run_experiment(**common, snr_db=5.0)
    assert np.array_equal(at_5_db.simulated_recordings.recordings.samples, repeat_5_db.simulated_recordings.recordings.samples)
    assert not np.array_equal(at_20_db.simulated_recordings.recordings.samples, at_5_db.simulated_recordings.recordings.samples)


def test_csv_export_includes_matched_missed_and_unmatched_rows() -> None:
    result = run_experiment(
        direct_room(),
        (1.0, 1.0, 1.0),
        ((2.0, 1.0, 1.0),),
        excitation(),
        max_reflection_order=1,
        peak_window_length_samples=8,
        matching_tolerance_seconds=0.001,
    )
    output = io.StringIO()
    result.write_csv(output)
    output.seek(0)
    rows = list(csv.DictReader(output))
    assert rows
    assert {row["status"] for row in rows} >= {"matched", "missed_expected", "unmatched_detected"}
    assert any(row["expected_time_s"] for row in rows)
    assert "reflection_sequence" in rows[0]


def test_structured_result_contains_configuration_paths_detections_and_trace() -> None:
    result = run_experiment(
        direct_room(),
        (1.0, 1.0, 1.0),
        ((2.0, 1.0, 1.0),),
        excitation(),
        max_reflection_order=0,
    )
    payload = result.to_dict(include_waveforms=True, include_correlations=True)
    assert payload["configuration"]["excitation_sha256"] == result.configuration.excitation_sha256
    assert payload["microphone_results"][0]["paths"][0]["reflection_order"] == 0
    assert "detected_arrivals" in payload["microphone_results"][0]["toa_comparison"]
    assert "matched_filter_trace" in payload["microphone_results"][0]
    assert len(payload["recordings"]["samples_by_microphone"]) == result.simulated_recordings.recordings.sample_count


def test_configuration_and_outputs_reproduce_with_fixed_seed() -> None:
    args = dict(
        room=direct_room(),
        source_position_m=(1.0, 1.0, 1.0),
        microphone_positions_m=((2.0, 1.0, 1.0),),
        excitation=excitation(seed=45),
        max_reflection_order=0,
        snr_db=15.0,
        random_seed=77,
    )
    first = run_experiment(**args)
    second = run_experiment(**args)
    assert first.configuration == second.configuration
    assert first.to_dict() == second.to_dict()
    assert np.array_equal(first.simulated_recordings.recordings.samples, second.simulated_recordings.recordings.samples)


def test_invalid_pipeline_settings_are_rejected() -> None:
    with pytest.raises(ValueError, match="must match"):
        run_experiment(direct_room(), (1, 1, 1), ((2, 1, 1),), excitation(), sampling_frequency=SamplingFrequency(2_000))
    with pytest.raises(ValueError, match="matching_tolerance"):
        run_experiment(direct_room(), (1, 1, 1), ((2, 1, 1),), excitation(), matching_tolerance_seconds=-1)
