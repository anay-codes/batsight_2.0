"""Reproducible forward TOA dataset with 3 microphones and 5 sources.

Run from the repository root with ``python experiments/uncalibrated_toa_example.py``.
The example prints JSON to stdout and performs no localization.
"""

import json

from batsight.datasets import generate_toa_observations
from batsight.simulation import ShoeboxRoom


def main() -> None:
    room = ShoeboxRoom(dimensions_m=(8.0, 6.0, 3.5), speed_of_sound_m_s=343.0)
    sources = [
        (1.0, 1.0, 1.2), (2.0, 4.0, 1.4), (3.5, 2.0, 1.6),
        (5.0, 4.5, 1.1), (6.5, 1.5, 1.8),
    ]
    microphones = [(1.0, 3.0, 1.4), (4.0, 1.0, 1.5), (6.5, 4.0, 1.3)]
    dataset = generate_toa_observations(
        room,
        sources,
        microphones,
        source_emission_times_s=[0.00, 0.17, 0.39, 0.64, 0.92],
        microphone_clock_offsets_s=[0.0012, -0.0007, 0.0021],
        timing_noise_std_seconds=0.0002,
        missing_probability=0.1,
        random_seed=2025,
    )
    print(json.dumps(dataset.to_dict(), indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
