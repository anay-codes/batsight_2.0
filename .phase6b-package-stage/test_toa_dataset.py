import json
from io import StringIO

import numpy as np
import pytest

from batsight.datasets import TOAObservationDataset, generate_toa_observations
from batsight.simulation import ShoeboxRoom


def example_inputs():
    room = ShoeboxRoom(dimensions_m=(8.0, 7.0, 5.0), speed_of_sound_m_s=2.0)
    sources = [(1.0, 1.0, 1.0), (2.0, 2.0, 1.0)]
    microphones = [(3.0, 1.0, 1.0), (1.0, 4.0, 1.0)]
    return room, sources, microphones


def test_hand_calculated_distances_and_toas():
    room, sources, microphones = example_inputs()
    data = generate_toa_observations(
        room, sources, microphones, [0.25, 0.75], [0.1, -0.2]
    )
    expected_distances = np.array([[2.0, np.sqrt(2.0)], [3.0, np.sqrt(5.0)]])
    np.testing.assert_allclose(data.true_distances_m, expected_distances)
    np.testing.assert_allclose(data.propagation_times_s, expected_distances / 2.0)
    np.testing.assert_allclose(
        data.ideal_toas_s,
        expected_distances / 2.0 + np.array([0.25, 0.75])[None, :] + np.array([0.1, -0.2])[:, None],
    )


def test_multiple_sources_and_microphones_shape_is_microphone_by_source():
    room = ShoeboxRoom((10.0, 10.0, 10.0))
    sources = [(1 + i, 2.0, 3.0) for i in range(5)]
    microphones = [(2.0, 2.0, 2.0), (4.0, 3.0, 2.0), (6.0, 5.0, 4.0)]
    data = generate_toa_observations(room, sources, microphones, [0] * 5, [0] * 3)
    assert data.true_distances_m.shape == (3, 5)
    assert data.microphone_count == 3
    assert data.source_count == 5


def test_zero_noise_matches_ideal_and_preserves_components():
    room, sources, microphones = example_inputs()
    data = generate_toa_observations(room, sources, microphones, [1.2, 2.4], [0.3, 0.5])
    np.testing.assert_array_equal(data.timing_noise_s, np.zeros((2, 2)))
    np.testing.assert_allclose(data.measured_toas_s, data.ideal_toas_s)


def test_noise_is_seeded_and_configurable():
    room, sources, microphones = example_inputs()
    args = (room, sources, microphones, [0, 0], [0, 0])
    a = generate_toa_observations(*args, timing_noise_std_seconds=0.01, random_seed=123)
    b = generate_toa_observations(*args, timing_noise_std_seconds=0.01, random_seed=123)
    c = generate_toa_observations(*args, timing_noise_std_seconds=0.01, random_seed=124)
    np.testing.assert_array_equal(a.timing_noise_s, b.timing_noise_s)
    assert not np.array_equal(a.timing_noise_s, c.timing_noise_s)
    assert np.any(a.timing_noise_s != 0)


def test_missingness_can_be_seeded_or_explicit():
    room, sources, microphones = example_inputs()
    args = (room, sources, microphones, [0, 0], [0, 0])
    a = generate_toa_observations(*args, missing_probability=0.4, random_seed=21)
    b = generate_toa_observations(*args, missing_probability=0.4, random_seed=21)
    np.testing.assert_array_equal(a.missing_mask, b.missing_mask)
    assert np.all(np.isnan(a.measured_toas_s[a.missing_mask]))
    assert np.all(np.isfinite(a.ideal_toas_s))
    mask = [[True, False], [False, True]]
    explicit = generate_toa_observations(*args, missing_mask=mask)
    np.testing.assert_array_equal(explicit.missing_mask, mask)
    assert np.isnan(explicit.measured_toas_s[0, 0])
    assert np.isfinite(explicit.measured_toas_s[0, 1])


@pytest.mark.parametrize("point", [(0, 1, 1), (8, 1, 1), (-1, 1, 1)])
def test_rejects_source_positions_not_strictly_inside(point):
    room = ShoeboxRoom((8.0, 7.0, 5.0))
    with pytest.raises(ValueError):
        generate_toa_observations(room, [point], [(2, 2, 2)], [0], [0])


def test_rejects_bad_counts_times_and_generation_parameters():
    room, sources, microphones = example_inputs()
    with pytest.raises(ValueError):
        generate_toa_observations(room, sources, microphones, [0], [0, 0])
    with pytest.raises(ValueError):
        generate_toa_observations(room, sources, microphones, [0, np.nan], [0, 0])
    with pytest.raises(ValueError):
        generate_toa_observations(room, sources, microphones, [0, 0], [0, 0], timing_noise_std_seconds=-1)
    with pytest.raises(ValueError):
        generate_toa_observations(room, sources, microphones, [0, 0], [0, 0], missing_probability=1.1)
    with pytest.raises(ValueError):
        generate_toa_observations(room, sources, microphones, [0, 0], [0, 0], missing_mask=[[False]])
    with pytest.raises(ValueError):
        generate_toa_observations(room, sources, microphones, [0, 0], [0, 0], missing_mask=[[False] * 2] * 2, missing_probability=0.2)


def test_json_serialization_round_trip(tmp_path):
    room, sources, microphones = example_inputs()
    original = generate_toa_observations(
        room, sources, microphones, [0.2, 0.4], [0.01, -0.02],
        timing_noise_std_seconds=0.001, missing_probability=0.25, random_seed=55,
    )
    encoded = json.dumps(original.to_dict(), allow_nan=False)
    from_text = TOAObservationDataset.from_json(StringIO(encoded))
    path = tmp_path / "observations.json"
    original.to_json(path)
    from_path = TOAObservationDataset.from_json(path)
    for restored in (from_text, from_path):
        assert restored.room_dimensions_m == original.room_dimensions_m
        assert restored.metadata == original.metadata
        for field in (
            "source_emission_times_s", "microphone_clock_offsets_s", "true_distances_m",
            "propagation_times_s", "ideal_toas_s", "measured_toas_s", "missing_mask", "timing_noise_s",
        ):
            np.testing.assert_equal(getattr(restored, field), getattr(original, field))


def test_metadata_has_no_sampling_rate_and_seed_reproduces_entire_dataset():
    room, sources, microphones = example_inputs()
    args = (room, sources, microphones, [0.1, 0.2], [0.03, 0.04])
    a = generate_toa_observations(*args, timing_noise_std_seconds=0.002, missing_probability=0.2, random_seed=9)
    b = generate_toa_observations(*args, timing_noise_std_seconds=0.002, missing_probability=0.2, random_seed=9)
    assert "sample_rate" not in json.dumps(a.metadata.to_dict()).lower()
    for field in ("timing_noise_s", "missing_mask", "measured_toas_s"):
        np.testing.assert_equal(getattr(a, field), getattr(b, field))
