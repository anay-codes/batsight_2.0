"""Small fixed-seed forward-experiment examples; no inverse reconstruction."""

from __future__ import annotations

import json

from batsight.experiments import run_experiment
from batsight.signals import SamplingFrequency, generate_linear_sweep
from batsight.simulation import ShoeboxRoom


def build_examples():
    fs = SamplingFrequency(16_000.0)
    # Generic engineering test sweep; it does not claim to reproduce paper Eq. 10.
    probe = generate_linear_sweep(1_000.0, 6_000.0, 0.03, fs, amplitude=0.5)
    room = ShoeboxRoom(
        (6.0, 5.0, 3.0),
        speed_of_sound_m_s=343.0,
        wall_reflection_coefficients={
            "x_min": 0.8,
            "x_max": 0.75,
            "y_min": 0.7,
            "y_max": 0.65,
            "z_min": 0.85,
            "z_max": 0.8,
        },
    )
    source = (1.2, 1.4, 1.0)
    microphones = ((3.0, 2.0, 1.4), (4.2, 3.5, 1.2))
    base = {
        "room": room,
        "source_position_m": source,
        "microphone_positions_m": microphones,
        "excitation": probe,
        "peak_window_length_samples": 12,
        "thr1": 0.9,
        "thr2": 0.12,
        "matching_tolerance_seconds": 1.5 / fs.hertz,
    }
    cases = {
        "direct_only_noiseless": dict(max_reflection_order=0, snr_db=None, random_seed=101),
        "direct_first_order_noiseless": dict(max_reflection_order=1, snr_db=None, random_seed=102),
        "first_second_order_20db": dict(max_reflection_order=2, snr_db=20.0, random_seed=103),
        "first_second_order_10db": dict(max_reflection_order=2, snr_db=10.0, random_seed=104),
        "first_second_order_0db": dict(max_reflection_order=2, snr_db=0.0, random_seed=105),
    }
    return {name: run_experiment(**base, **settings) for name, settings in cases.items()}


if __name__ == "__main__":
    experiments = build_examples()
    report = {
        name: {
            "configuration": result.configuration.to_dict(),
            "overall_metrics": result.overall_metrics.to_dict(),
            "per_microphone_metrics": [
                microphone.toa_comparison.metrics.to_dict() for microphone in result.microphone_results
            ],
        }
        for name, result in experiments.items()
    }
    print(json.dumps(report, indent=2))
