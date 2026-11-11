"""Synthetic multichannel waveform-to-TOA extraction tests."""

from pathlib import Path

import numpy as np
import pytest
from scipy.io import wavfile

from batsight.datasets import (
    CalibratedMicrophone,
    CalibratedMicrophoneArray,
    CalibratedShoeboxInputs,
    CalibratedSourceEvent,
)
from batsight.datasets.audio_toa import recording_analysis_to_observations
from batsight.signals import AudioSignal, KnownReferenceSignal, RecordingMetadata, SamplingFrequency, generate_linear_sweep
from batsight.signals.recording_analysis import (
    RecordingAnalysisConfig,
    analyze_multichannel_recording,
    load_multichannel_wav,
)
from batsight.simulation import ShoeboxRoom, predict_acoustic_paths, simulate_recordings


def synthetic_fixture(*, snr_db=None, seed=7, coefficient=0.7, events_count=2):
    fs = SamplingFrequency(48_000.0)
    reference = generate_linear_sweep(900.0, 11_000.0, 0.01, fs, amplitude=0.8)
    known = KnownReferenceSignal(reference, "synthetic engineering sweep")
    room = ShoeboxRoom(
        (4.5, 4.1, 3.4),
        343.0,
        {wall: coefficient for wall in ("x_min", "x_max", "y_min", "y_max", "z_min", "z_max")},
    )
    microphones = (
        CalibratedMicrophone("m0", (2.0, 1.7, 1.2)),
        CalibratedMicrophone("m1", (3.2, 2.3, 1.4)),
        CalibratedMicrophone("m2", (1.3, 2.8, 2.1)),
    )
    positions = ((1.1, 1.0, 1.6), (2.2, 1.2, 2.4))[:events_count]
    emissions = (0.02, 0.14)[:events_count]
    events = tuple(
        CalibratedSourceEvent(f"e{idx}", f"s{idx}", position, emission, known)
        for idx, (position, emission) in enumerate(zip(positions, emissions))
    )
    inputs = CalibratedShoeboxInputs(
        CalibratedMicrophoneArray(microphones, fs, clocks_synchronized=True), events, 343.0
    )
    frame_count = int(0.27 * fs.hertz)
    combined = np.zeros((frame_count, len(microphones)), dtype=np.float64)
    paths = {}
    for event in events:
        start = fs.time_to_sample_index(event.emission_time_s)
        padded = np.pad(reference.samples, (start, 0))
        excitation = AudioSignal(padded, fs)
        simulation = simulate_recordings(
            room,
            event.position_m,
            [mic.position_m for mic in microphones],
            excitation,
            max_reflection_order=2,
            impulse_placement="linear",
        )
        length = min(frame_count, simulation.recordings.sample_count)
        combined[:length] += simulation.recordings.samples[:length]
        for channel, mic in enumerate(microphones):
            paths[(mic.microphone_id, event.event_id)] = tuple(
                (path.reflection_order, path.reflection_sequence[0] if path.reflection_sequence else None,
                 event.emission_time_s + path.time_of_flight_s)
                for path in simulation.impulse_responses[channel].paths
            )
    if snr_db is not None:
        rng = np.random.default_rng(seed)
        signal_power = float(np.mean(combined**2))
        noise_std = np.sqrt(signal_power * 10.0 ** (-snr_db / 10.0))
        combined += rng.normal(0.0, noise_std, combined.shape)
    recording = AudioSignal(
        combined,
        fs,
        RecordingMetadata(
            recording_id=f"synthetic-{seed}",
            attributes={"sample_rate_hz": int(fs.hertz), "channel_count": len(microphones)},
        ),
    )
    return room, reference, inputs, recording, paths


def analyze(fixture, **config_kwargs):
    _, reference, inputs, recording, _ = fixture
    options = {
        "maximum_echo_excess_delay_s": 0.035,
        "minimum_peak_separation_s": 0.00012,
        "window_length_samples": 12,
        "thr1": 0.9,
        "thr2": 0.008,
    }
    options.update(config_kwargs)
    return analyze_multichannel_recording(
        recording,
        reference,
        inputs,
        config=RecordingAnalysisConfig(**options),
    )


def test_noiseless_multichannel_direct_and_first_order_timing_recovery():
    fixture = synthetic_fixture()
    result = analyze(fixture)
    assert len(result.pair_results) == 6
    assert all(pair.direct_arrival is not None for pair in result.pair_results)
    assert all(abs(pair.direct_arrival.arrival_time_s - pair.expected_direct_time_s) < 1.0 / 48_000
               for pair in result.pair_results)
    assert all(item.classification == "unclassified_echo_candidate"
               for pair in result.pair_results for item in pair.echo_candidates)
    assert all(item.echo_id for pair in result.pair_results for item in pair.echo_candidates)


def test_extracted_observations_keep_provenance_confidence_and_no_wall_labels():
    result = analyze(synthetic_fixture())
    observations = recording_analysis_to_observations(result, origin="synthetic")
    assert len(observations.direct_paths) == 6
    assert observations.unlabeled_echoes
    assert not observations.labeled_first_order_reflections
    assert all(item.provenance == "synthetic_audio" for item in observations.unlabeled_echoes)
    assert all(item.detection_strength is not None for item in observations.unlabeled_echoes)
    assert all(item.reflection_order_hint is None for item in observations.unlabeled_echoes)
    assert all(item.candidate_classification == "unclassified_echo_candidate" for item in observations.unlabeled_echoes)
    assert all(item.reading.uncertainty_s is None for item in observations.unlabeled_echoes)


@pytest.mark.parametrize("snr_db", [40.0, 25.0, 15.0])
def test_seeded_noise_is_reproducible_and_records_noise_diagnostics(snr_db):
    fixture1 = synthetic_fixture(snr_db=snr_db, seed=123)
    fixture2 = synthetic_fixture(snr_db=snr_db, seed=123)
    result1, result2 = analyze(fixture1), analyze(fixture2)
    assert result1.recording.samples == pytest.approx(result2.recording.samples)
    times1 = [p.direct_arrival.arrival_time_s if p.direct_arrival else np.nan for p in result1.pair_results]
    times2 = [p.direct_arrival.arrival_time_s if p.direct_arrival else np.nan for p in result2.pair_results]
    assert times1 == pytest.approx(times2, nan_ok=True)
    for pair1, pair2 in zip(result1.pair_results, result2.pair_results):
        assert [x.arrival_time_s for x in pair1.echo_candidates] == pytest.approx(
            [x.arrival_time_s for x in pair2.echo_candidates]
        )
    assert all(pair.robust_noise_scale > 0.0 for pair in result1.pair_results)


def test_fractional_sample_estimates_and_configured_uncertainty_are_explicit():
    fixture = synthetic_fixture(events_count=1)
    result = analyze(fixture, timing_uncertainty_s=0.75 / 48_000)
    arrivals = [pair.direct_arrival for pair in result.pair_results]
    assert all(item is not None for item in arrivals)
    assert any(abs(item.fractional_sample_index - round(item.fractional_sample_index)) > 1e-3 for item in arrivals)
    assert all(item.uncertainty_s == pytest.approx(0.75 / 48_000) for item in arrivals)
    assert result.config.timing_uncertainty_s == pytest.approx(0.75 / 48_000)


def test_weak_reflections_are_audited_instead_of_claimed_as_missing_truth():
    fixture = synthetic_fixture(coefficient=0.06, events_count=1)
    result = analyze(fixture, thr2=0.002, minimum_peak_prominence=1e-4)
    assert any(pair.rejected_peaks for pair in result.pair_results)
    assert all(rejection.reason for pair in result.pair_results for rejection in pair.rejected_peaks)
    assert any(rejection.reason == "suppressed_duplicate"
               for pair in result.pair_results for rejection in pair.rejected_peaks)


def test_recording_duration_and_channel_sample_rate_are_validated():
    _, reference, inputs, recording, _ = synthetic_fixture()
    short = AudioSignal(recording.samples[:100], recording.sampling_frequency)
    result = analyze_multichannel_recording(short, reference, inputs)
    assert any("does not fully cover" in warning for warning in result.warnings)
    with pytest.raises(ValueError, match="channel count"):
        analyze_multichannel_recording(AudioSignal(recording.samples[:, :2], recording.sampling_frequency), reference, inputs)
    wrong_rate = AudioSignal(recording.samples, SamplingFrequency(44_100))
    with pytest.raises(ValueError, match="sampling frequencies"):
        analyze_multichannel_recording(wrong_rate, reference, inputs)


def test_wav_input_does_not_resample_and_preserves_pcm_metadata(tmp_path: Path):
    path = tmp_path / "stereo.wav"
    pcm = np.asarray([[0, 32767], [-32768, 0]], dtype=np.int16)
    wavfile.write(path, 48_000, pcm)
    loaded = load_multichannel_wav(path, expected_sampling_frequency_hz=48_000)
    assert loaded.channel_count == 2
    assert loaded.samples[0, 1] == pytest.approx(32767 / 32768)
    assert loaded.metadata.attributes["channel_count"] == 2
    with pytest.raises(ValueError, match="resampling is not implicit"):
        load_multichannel_wav(path, expected_sampling_frequency_hz=44_100)


def test_invalid_configs_and_reference_mismatch_are_rejected():
    with pytest.raises(ValueError, match="echo delay limits"):
        RecordingAnalysisConfig(minimum_echo_excess_delay_s=0.1, maximum_echo_excess_delay_s=0.1)
    _, reference, inputs, recording, _ = synthetic_fixture()
    wrong = AudioSignal(np.ones(10), SamplingFrequency(44_100))
    with pytest.raises(ValueError, match="sampling frequencies"):
        analyze_multichannel_recording(recording, wrong, inputs)


def test_simulator_ground_truth_is_only_used_after_extraction_for_recall_and_toa_error():
    fixture = synthetic_fixture()
    result = analyze(fixture)
    _, _, inputs, _, path_truth = fixture
    detected_direct = 0
    expected_direct = 0
    echo_errors = []
    echo_matched = 0
    expected_first_order = 0
    for pair in result.pair_results:
        expected_direct += 1
        detected_direct += pair.direct_arrival is not None
        paths = path_truth[(pair.microphone_id, pair.event_id)]
        first_order = [time for order, _, time in paths if order == 1]
        expected_first_order += len(first_order)
        candidates = list(pair.echo_candidates)
        used = set()
        for toa in first_order:
            eligible = [(abs(item.arrival_time_s - toa), idx) for idx, item in enumerate(candidates) if idx not in used]
            if eligible:
                error, idx = min(eligible)
                if error < 2.0 / inputs.microphone_array.sampling_frequency.hertz:
                    used.add(idx)
                    echo_matched += 1
                    echo_errors.append(error)
    assert detected_direct / expected_direct == 1.0
    assert echo_matched / expected_first_order > 0.9
    assert sum(len(pair.echo_candidates) for pair in result.pair_results) > echo_matched
    assert max(echo_errors) < 2.0 / 48_000


def test_close_first_order_arrivals_below_the_separation_setting_are_not_forced_as_two_echoes():
    fixture = synthetic_fixture(events_count=1)
    truth = fixture[4]
    gaps = []
    for paths in truth.values():
        times = [toa for order, _, toa in paths if order == 1]
        gaps.extend(abs(times[i] - times[j]) for i in range(len(times)) for j in range(i + 1, len(times)))
    assert min(gaps) < 0.00012
    result = analyze(fixture)
    assert any(
        peak.reason == "suppressed_duplicate"
        for pair in result.pair_results
        for peak in pair.rejected_peaks
    )
