import numpy as np
import pytest

from batsight.signals import (
    AudioSignal,
    DetectedArrivalTime,
    KnownReferenceSignal,
    SamplingFrequency,
    detect_peaks,
    generate_linear_sweep,
    generate_sine_wave,
    matched_filter,
)


def make_signal(samples: np.ndarray, sample_rate: float = 8_000.0) -> AudioSignal:
    return AudioSignal(np.asarray(samples, dtype=np.float64), SamplingFrequency(sample_rate))


def test_sample_time_conversion_rounding_and_duration() -> None:
    fs = SamplingFrequency(10.0)
    assert fs.sample_index_to_time(7) == pytest.approx(0.7)
    assert fs.time_to_sample_index(0.74) == 7
    assert fs.time_to_sample_index(0.75) == 8
    audio = AudioSignal(np.zeros(10), fs)
    assert audio.duration_seconds == pytest.approx(1.0)
    assert audio.sample_index_to_time(9) == pytest.approx(0.9)


@pytest.mark.parametrize("frequency", [0.0, 1_000.0, 3_999.0])
def test_sine_wave_count_and_finite_values(frequency: float) -> None:
    fs = SamplingFrequency(8_000.0)
    signal = generate_sine_wave(frequency, 0.25, fs, amplitude=0.4, phase_radians=0.2)
    assert signal.sample_count == 2_000
    assert signal.channel_count == 1
    assert signal.duration_seconds == pytest.approx(0.25)
    assert np.max(np.abs(signal.samples)) <= 0.4 + 1e-12
    assert np.all(np.isfinite(signal.samples))


def test_linear_sweep_has_requested_sample_frame_duration_and_generic_behavior() -> None:
    fs = SamplingFrequency(8_000.0)
    duration = 0.5
    sweep = generate_linear_sweep(500.0, 2_500.0, duration, fs)
    assert sweep.sample_count == 4_000
    assert sweep.duration_seconds == pytest.approx(duration)
    # For the declared engineering phase law, the phase-derived frequency
    # increases across the sweep; this does not test paper Eq. 10.
    times = (np.array([0.1, 0.4]))
    rate = (2_500.0 - 500.0) / duration
    instantaneous_frequencies = 500.0 + rate * times
    assert instantaneous_frequencies[1] > instantaneous_frequencies[0]


def test_generated_waveform_length_rounds_to_nearest_frame() -> None:
    signal = generate_sine_wave(100.0, 0.0106, SamplingFrequency(1_000.0))
    assert signal.sample_count == 11


def test_matched_filter_recovers_known_positive_delay_and_gain() -> None:
    rng = np.random.default_rng(41)
    reference_values = rng.normal(size=127)
    delay = 233
    gain = 0.65
    recorded = np.zeros(delay + reference_values.size + 80)
    recorded[delay : delay + reference_values.size] = gain * reference_values

    result = matched_filter(make_signal(recorded), KnownReferenceSignal(make_signal(reference_values)))
    estimated_lag, estimated_time, score = result.estimate_arrival_time()

    assert estimated_lag == delay
    assert estimated_time == pytest.approx(delay / 8_000.0)
    assert score == pytest.approx(gain)
    assert result.correlation.size == recorded.size + reference_values.size - 1
    assert result.lags_samples[np.argmax(np.abs(result.correlation))] == delay


def test_matched_filter_is_robust_to_deterministic_additive_white_noise() -> None:
    rng = np.random.default_rng(2025)
    reference_values = rng.normal(size=255)
    delay = 417
    recording = np.zeros(1_000)
    recording[delay : delay + reference_values.size] = reference_values
    recording += rng.normal(scale=0.15, size=recording.size)
    result = matched_filter(make_signal(recording), make_signal(reference_values))
    assert result.estimate_arrival_time()[0] == delay


def test_matched_filter_allows_inverted_polarity_and_signed_score() -> None:
    reference_values = np.array([0.0, 1.0, -0.5, 0.25, 0.0])
    delay = 9
    recording = np.zeros(30)
    recording[delay : delay + reference_values.size] = -2.0 * reference_values
    result = matched_filter(make_signal(recording), make_signal(reference_values))
    assert result.estimate_arrival_time(polarity="either")[0] == delay
    assert result.estimate_arrival_time(polarity="either")[2] == pytest.approx(-2.0)
    assert result.estimate_arrival_time(polarity="positive")[0] != delay


def test_matched_filter_multiple_arrivals_returns_strongest_and_full_output() -> None:
    reference_values = np.array([1.0, -0.5, 0.25, 0.0])
    recording = np.zeros(80)
    recording[10:14] += 0.4 * reference_values
    recording[50:54] += 1.1 * reference_values
    result = matched_filter(make_signal(recording), make_signal(reference_values))
    assert result.estimate_arrival_time()[0] == 50
    detections = detect_peaks(
        result.correlation,
        SamplingFrequency(8_000),
        window_length_samples=5,
        thr1=0.8,
        thr2=0.2,
        start_time_seconds=int(result.lags_samples[0]) / 8_000,
    )
    assert {item.sample_index + int(result.lags_samples[0]) for item in detections} >= {10, 50}


def test_peak_detector_filters_weak_peaks_by_global_threshold() -> None:
    values = np.zeros(40)
    values[5] = 1.0
    values[20] = 0.25
    values[35] = -0.08
    peaks = detect_peaks(values, SamplingFrequency(100.0), window_length_samples=3, thr1=0.9, thr2=0.1)
    assert [peak.sample_index for peak in peaks] == [5, 20]
    assert [peak.amplitude for peak in peaks] == [1.0, 0.25]
    assert [peak.time_seconds for peak in peaks] == pytest.approx([0.05, 0.2])


def test_peak_detector_rejects_noise_false_peaks_with_global_cutoff() -> None:
    rng = np.random.default_rng(88)
    values = rng.normal(scale=0.01, size=300)
    values[173] = 1.0
    peaks = detect_peaks(
        values,
        SamplingFrequency(16_000.0),
        window_length_samples=12,
        thr1=0.9,
        thr2=0.15,
    )
    assert [peak.sample_index for peak in peaks] == [173]


def test_peak_detector_suppresses_smaller_peak_in_forward_local_window() -> None:
    values = np.zeros(20)
    values[3] = 0.5
    values[6] = 1.0
    values[15] = 0.4
    peaks = detect_peaks(values, SamplingFrequency(10.0), window_length_samples=5, thr1=0.9, thr2=0.1)
    assert [peak.sample_index for peak in peaks] == [6, 15]


def test_peak_detector_endpoints_and_shifted_signed_time_origin() -> None:
    values = np.array([2.0, 0.0, -1.0])
    peaks = detect_peaks(
        values,
        SamplingFrequency(2.0),
        window_length_samples=1,
        thr1=1.0,
        thr2=0.5,
        start_time_seconds=-1.0,
    )
    assert [(p.sample_index, p.time_seconds, p.amplitude) for p in peaks] == [
        (0, -1.0, 2.0),
        (2, 0.0, -1.0),
    ]
    assert DetectedArrivalTime(0, -0.25, -1.0).amplitude == -1.0


def test_peak_detector_zero_and_single_sample_inputs() -> None:
    fs = SamplingFrequency(44_100.0)
    assert detect_peaks(np.zeros(5), fs, window_length_samples=3) == ()
    peak = detect_peaks(np.array([-0.5]), fs, window_length_samples=1)
    assert len(peak) == 1
    assert peak[0].sample_index == 0
    assert peak[0].amplitude == -0.5


@pytest.mark.parametrize(
    "factory",
    [
        lambda: SamplingFrequency(0.0),
        lambda: SamplingFrequency(float("nan")),
        lambda: make_signal(np.array([1.0, np.inf])),
        lambda: generate_sine_wave(4_000.0, 1.0, SamplingFrequency(8_000.0)),
        lambda: generate_linear_sweep(100.0, 4_000.0, 1.0, SamplingFrequency(8_000.0)),
        lambda: generate_sine_wave(100.0, 0.0, SamplingFrequency(8_000.0)),
        lambda: generate_linear_sweep(100.0, 200.0, 0.0, SamplingFrequency(8_000.0)),
        lambda: SamplingFrequency(1_000.0).time_to_sample_index(float("inf")),
        lambda: SamplingFrequency(1_000.0).sample_index_to_time(-1),
        lambda: detect_peaks(np.array([1.0]), SamplingFrequency(1_000.0), window_length_samples=0),
        lambda: detect_peaks(np.array([1.0]), SamplingFrequency(1_000.0), window_length_samples=1, thr1=1.1),
        lambda: detect_peaks(np.array([np.nan]), SamplingFrequency(1_000.0), window_length_samples=1),
    ],
)
def test_invalid_inputs_are_rejected(factory) -> None:
    with pytest.raises((TypeError, ValueError)):
        factory()


def test_matched_filter_rejects_invalid_reference_and_incompatible_channels() -> None:
    fs = SamplingFrequency(8_000.0)
    recording = AudioSignal(np.zeros((30, 2)), fs)
    reference = AudioSignal(np.ones(4), fs)
    with pytest.raises(ValueError, match="mono recording"):
        matched_filter(recording, reference)
    with pytest.raises(ValueError, match="non-zero"):
        matched_filter(make_signal(np.ones(10)), make_signal(np.zeros(3)))
    with pytest.raises(ValueError, match="must match"):
        matched_filter(make_signal(np.ones(10), 8_000), make_signal(np.ones(3), 16_000))


def test_reference_energy_normalization_is_stable_for_scaled_reference() -> None:
    reference_values = np.array([1e-5, -2e-5, 3e-5, 0.5e-5])
    recording = np.zeros(20)
    recording[7:11] = 3.0 * reference_values
    result = matched_filter(make_signal(recording), make_signal(reference_values))
    assert result.estimate_arrival_time()[0] == 7
    assert result.estimate_arrival_time()[2] == pytest.approx(3.0)
