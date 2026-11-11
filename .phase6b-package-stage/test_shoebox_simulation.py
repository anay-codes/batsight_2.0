import numpy as np
import pytest

from batsight.signals import AudioSignal, SamplingFrequency, generate_sine_wave
from batsight.simulation import ShoeboxRoom, generate_rir, image_sources, simulate_recordings


def room(**kwargs) -> ShoeboxRoom:
    return ShoeboxRoom((4.0, 5.0, 3.0), **kwargs)


def test_direct_distance_and_tof_match_hand_calculation() -> None:
    box = room(speed_of_sound_m_s=340.0)
    result = generate_rir(box, (1.0, 1.0, 1.0), (2.0, 2.0, 1.0), SamplingFrequency(8_000.0), max_reflection_order=0)
    path = result.paths[0]
    assert path.reflection_order == 0
    assert path.reflection_sequence == ()
    assert path.propagation_distance_m == pytest.approx(np.sqrt(2.0))
    assert path.time_of_flight_s == pytest.approx(np.sqrt(2.0) / 340.0)


def test_first_order_x_min_distance_matches_hand_calculation() -> None:
    result = generate_rir(room(), (1.0, 1.0, 1.0), (2.0, 2.0, 1.0), SamplingFrequency(8_000.0), max_reflection_order=1)
    x_min = next(path for path in result.paths if path.reflection_sequence == ("x_min",))
    assert x_min.image_source.position_m == pytest.approx((-1.0, 1.0, 1.0))
    assert x_min.propagation_distance_m == pytest.approx(np.sqrt(10.0))
    assert x_min.time_of_flight_s == pytest.approx(np.sqrt(10.0) / 343.0)


def test_second_order_path_and_image_coordinates() -> None:
    images = image_sources(room(), (1.0, 1.0, 1.0), max_reflection_order=2)
    # x_min then y_min is canonical for the coordinate shared with y_min,x_min.
    image = next(item for item in images if item.reflection_sequence == ("x_min", "y_min"))
    assert image.position_m == pytest.approx((-1.0, -1.0, 1.0))
    assert image.reflection_order == 2
    assert len([item for item in images if item.reflection_order == 2]) == 18

    result = generate_rir(room(), (1.0, 1.0, 1.0), (2.0, 2.0, 1.0), SamplingFrequency(8_000.0))
    path = next(path for path in result.paths if path.reflection_sequence == ("x_min", "y_min"))
    assert path.propagation_distance_m == pytest.approx(np.sqrt(18.0))


def test_perpendicular_reflection_orders_are_deduplicated_and_order_is_stable() -> None:
    first = image_sources(room(), (1.25, 2.0, 1.0), max_reflection_order=2)
    second = image_sources(room(), (1.25, 2.0, 1.0), max_reflection_order=2)
    assert first == second
    coordinate_keys = [tuple(np.round(item.position_m, 12)) for item in first]
    assert len(coordinate_keys) == len(set(coordinate_keys))
    assert len(first) == 25  # direct + 6 first-order + 18 unique second-order


def test_symmetric_room_configuration_has_equal_opposite_wall_distances() -> None:
    box = ShoeboxRoom((4.0, 4.0, 4.0))
    result = generate_rir(box, (2.0, 1.0, 1.0), (2.0, 2.0, 2.0), SamplingFrequency(4_000.0), max_reflection_order=1)
    x_min = next(path for path in result.paths if path.reflection_sequence == ("x_min",))
    x_max = next(path for path in result.paths if path.reflection_sequence == ("x_max",))
    assert x_min.propagation_distance_m == pytest.approx(x_max.propagation_distance_m)


@pytest.mark.parametrize(
    "position",
    [(-0.1, 1.0, 1.0), (0.0, 1.0, 1.0), (4.0, 1.0, 1.0), (1.0, 5.0, 1.0), (1.0, 1.0, 3.0)],
)
def test_source_and_microphone_must_be_strictly_inside(position) -> None:
    box = room()
    with pytest.raises(ValueError, match="strictly inside"):
        generate_rir(box, position, (2.0, 2.0, 1.5), SamplingFrequency(8_000.0))
    with pytest.raises(ValueError, match="strictly inside"):
        generate_rir(box, (1.0, 1.0, 1.0), position, SamplingFrequency(8_000.0))


def test_fractional_arrival_is_split_and_has_exact_first_moment() -> None:
    box = ShoeboxRoom((10.0, 10.0, 10.0), speed_of_sound_m_s=1.0, wall_reflection_coefficients={wall: 0.0 for wall in ("x_min", "x_max", "y_min", "y_max", "z_min", "z_max")})
    fs = SamplingFrequency(10.0)
    # Direct path length sqrt(0.5^2 + 0.5^2) = sqrt(0.5); fs/c makes u fractional.
    source = (1.0, 1.0, 1.0)
    microphone = (1.5, 1.5, 1.0)
    result = generate_rir(box, source, microphone, fs, max_reflection_order=0)
    path = result.paths[0]
    sample_position = path.time_of_flight_s * fs.hertz
    lower = int(np.floor(sample_position))
    fraction = sample_position - lower
    expected_amplitude = 1.0 / path.propagation_distance_m
    assert result.impulse_response.samples[lower] == pytest.approx(expected_amplitude * (1.0 - fraction))
    assert result.impulse_response.samples[lower + 1] == pytest.approx(expected_amplitude * fraction)
    observed_moment = np.dot(np.arange(result.impulse_response.sample_count), result.impulse_response.samples) / np.sum(result.impulse_response.samples)
    assert observed_moment == pytest.approx(sample_position)


def test_nearest_impulse_placement_is_configurable_and_reports_quantization() -> None:
    zero_reflections = {wall: 0.0 for wall in ("x_min", "x_max", "y_min", "y_max", "z_min", "z_max")}
    box = ShoeboxRoom((10.0, 10.0, 10.0), speed_of_sound_m_s=1.0, wall_reflection_coefficients=zero_reflections)
    fs = SamplingFrequency(10.0)
    # Distance 0.55 m gives a 5.5-sample delay; nearest ties round upward.
    source, microphone = (1.0, 1.0, 1.0), (1.55, 1.0, 1.0)
    linear = generate_rir(box, source, microphone, fs, max_reflection_order=0)
    nearest = generate_rir(box, source, microphone, fs, max_reflection_order=0, impulse_placement="nearest")
    assert linear.impulse_placement == "linear"
    assert nearest.impulse_placement == "nearest"
    assert linear.impulse_response.samples[5] == pytest.approx(linear.impulse_response.samples[6])
    assert nearest.impulse_response.samples[5] == 0.0
    assert nearest.impulse_response.samples[6] == pytest.approx(1.0 / 0.55)
    assert abs(6 - nearest.paths[0].time_of_flight_s * fs.hertz) == pytest.approx(0.5)


def test_reflection_coefficients_are_separate_from_geometric_spreading() -> None:
    coeffs = {wall: 0.0 for wall in ("x_min", "x_max", "y_min", "y_max", "z_min", "z_max")}
    coeffs["x_min"] = 0.5
    box = ShoeboxRoom((4.0, 5.0, 3.0), wall_reflection_coefficients=coeffs)
    result = generate_rir(box, (1.0, 1.0, 1.0), (2.0, 2.0, 1.0), SamplingFrequency(1_000.0), max_reflection_order=1)
    direct, reflected = result.paths[0], next(p for p in result.paths if p.reflection_sequence == ("x_min",))
    assert direct.image_source.reflection_coefficient == 1.0
    assert reflected.image_source.reflection_coefficient == 0.5
    sample_position = reflected.time_of_flight_s * 1_000.0
    lower = int(np.floor(sample_position))
    fraction = sample_position - lower
    expected_path_amplitude = 0.5 / reflected.propagation_distance_m
    assert result.impulse_response.samples[lower] == pytest.approx(expected_path_amplitude * (1.0 - fraction))
    assert result.impulse_response.samples[lower + 1] == pytest.approx(expected_path_amplitude * fraction)


def test_rir_tof_to_sample_positions_is_explicit_and_no_nearest_rounding() -> None:
    box = ShoeboxRoom((10.0, 10.0, 10.0), speed_of_sound_m_s=100.0, wall_reflection_coefficients={wall: 0.0 for wall in ("x_min", "x_max", "y_min", "y_max", "z_min", "z_max")})
    result = generate_rir(box, (1.0, 1.0, 1.0), (1.5, 1.0, 1.0), SamplingFrequency(1_000.0), max_reflection_order=0)
    assert result.paths[0].time_of_flight_s == pytest.approx(0.005)
    assert result.paths[0].time_of_flight_s * 1_000.0 == pytest.approx(5.0)
    # A 5.5-sample case is tested through fractional split above; no TOF is rounded to one index.


def test_wall_coefficients_and_room_dimensions_are_validated() -> None:
    with pytest.raises(ValueError, match="dimensions"):
        ShoeboxRoom((1.0, 0.0, 2.0))
    with pytest.raises(ValueError, match="speed_of_sound"):
        ShoeboxRoom((1.0, 2.0, 3.0), speed_of_sound_m_s=0)
    with pytest.raises(ValueError, match="coefficients"):
        ShoeboxRoom((1.0, 2.0, 3.0), wall_reflection_coefficients={"x_min": 1.2})
    with pytest.raises(ValueError, match="unknown wall"):
        ShoeboxRoom((1.0, 2.0, 3.0), wall_reflection_coefficients={"left": 0.5})


def test_multimicrophone_recordings_and_noiseless_convolution() -> None:
    box = room()
    fs = SamplingFrequency(8_000.0)
    excitation = generate_sine_wave(440.0, 0.02, fs, amplitude=0.2)
    microphones = ((2.0, 2.0, 1.0), (3.0, 2.0, 1.0))
    simulated = simulate_recordings(box, (1.0, 1.0, 1.0), microphones, excitation, max_reflection_order=1)
    assert simulated.recordings.channel_count == 2
    assert simulated.recordings.samples.shape[0] == max(
        excitation.sample_count + rir.impulse_response.sample_count - 1
        for rir in simulated.impulse_responses
    )
    assert simulated.requested_snr_db is None
    assert all(np.any(simulated.recordings.samples[:, channel] != 0) for channel in range(2))


def test_seeded_noise_is_deterministic_and_noisy_output_differs() -> None:
    box = room()
    fs = SamplingFrequency(8_000.0)
    excitation = generate_sine_wave(600.0, 0.01, fs, amplitude=0.3)
    microphones = ((2.0, 2.0, 1.0), (3.0, 2.0, 1.0))
    clean = simulate_recordings(box, (1.0, 1.0, 1.0), microphones, excitation, max_reflection_order=0)
    noisy_a = simulate_recordings(box, (1.0, 1.0, 1.0), microphones, excitation, max_reflection_order=0, snr_db=12.0, random_seed=19)
    noisy_b = simulate_recordings(box, (1.0, 1.0, 1.0), microphones, excitation, max_reflection_order=0, snr_db=12.0, random_seed=19)
    assert np.array_equal(noisy_a.recordings.samples, noisy_b.recordings.samples)
    assert not np.array_equal(clean.recordings.samples, noisy_a.recordings.samples)
    noise = noisy_a.recordings.samples - clean.recordings.samples
    for channel in range(2):
        actual_snr = 10 * np.log10(np.mean(clean.recordings.samples[:, channel] ** 2) / np.mean(noise[:, channel] ** 2))
        assert actual_snr == pytest.approx(12.0, abs=3.0)


def test_invalid_simulation_inputs_are_rejected() -> None:
    box = room()
    fs = SamplingFrequency(8_000.0)
    excitation = generate_sine_wave(440.0, 0.01, fs)
    with pytest.raises(ValueError, match="at least one microphone"):
        simulate_recordings(box, (1.0, 1.0, 1.0), (), excitation)
    with pytest.raises(ValueError, match="snr_db"):
        simulate_recordings(box, (1.0, 1.0, 1.0), ((2.0, 2.0, 1.0),), excitation, snr_db=float("nan"))
    with pytest.raises(ValueError, match="0, 1, or 2"):
        image_sources(box, (1.0, 1.0, 1.0), max_reflection_order=3)
    with pytest.raises(ValueError, match="coincide"):
        generate_rir(box, (1.0, 1.0, 1.0), (1.0, 1.0, 1.0), fs, max_reflection_order=0)
