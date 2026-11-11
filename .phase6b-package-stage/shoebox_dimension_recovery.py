"""Reproducible synthetic demonstration of the calibrated shoebox estimator.

Run with ``python experiments/shoebox_dimension_recovery.py`` from the repo.
All starts and observations are generated without passing dimensions to the
estimator; truth is used only afterward to calculate evaluation errors.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from time import perf_counter

import numpy as np

from batsight.datasets import (
    CalibratedMicrophone,
    CalibratedMicrophoneArray,
    CalibratedShoeboxInputs,
    CalibratedSourceEvent,
    CalibratedTOAObservationSet,
    FirstOrderReflectionTOAObservation,
    TOAReading,
)
from batsight.reconstruction import estimate_shoebox_dimensions
from batsight.signals import SamplingFrequency
from batsight.simulation import ShoeboxRoom, predict_first_order_arrivals


def _case(dimensions, seed: int, noise_s: float) -> dict:
    microphones = (
        CalibratedMicrophone("mic-a", (0.6, 0.8, 0.7)),
        CalibratedMicrophone("mic-b", (1.9, 1.0, 1.4)),
        CalibratedMicrophone("mic-c", (1.1, 2.2, 1.0)),
        CalibratedMicrophone("mic-d", (2.4, 1.8, 2.1)),
    )
    events = tuple(
        CalibratedSourceEvent(f"event-{idx}", f"source-{idx}", pos, 0.013 + idx * 0.021)
        for idx, pos in enumerate(((2.8, 2.5, 1.9), (3.4, 1.2, 2.5), (1.8, 3.0, 1.4), (3.1, 3.2, 2.7)))
    )
    speed = 343.0
    inputs = CalibratedShoeboxInputs(
        CalibratedMicrophoneArray(microphones, SamplingFrequency(48_000.0)), events, speed
    )
    truth = tuple(float(v) for v in dimensions)
    rng = np.random.default_rng(seed)
    observations = []
    for arrival in predict_first_order_arrivals(inputs, ShoeboxRoom(truth, speed)):
        if arrival.reflection_order != 1:
            continue
        measured = arrival.arrival_time_s + (float(rng.normal(0.0, noise_s)) if noise_s else 0.0)
        observations.append(FirstOrderReflectionTOAObservation(
            arrival.microphone_id,
            arrival.event_id,
            arrival.wall_id,
            TOAReading(measured, uncertainty_s=2e-5 if noise_s else None),
            "synthetic_ground_truth",
        ))
    data = CalibratedTOAObservationSet(
        inputs, "synthetic", labeled_first_order_reflections=tuple(observations)
    )
    # Fixed starts are selected from known coordinate bounds, not room truth.
    started = perf_counter()
    result = estimate_shoebox_dimensions(
        data,
        initial_dimensions_m=(5.0, 5.0, 5.0),
        upper_bounds_m=(8.0, 8.0, 8.0),
        default_uncertainty_s=2e-5 if noise_s else None,
    )
    runtime_s = perf_counter() - started
    return {
        "seed": seed,
        "noise_standard_deviation_s": noise_s,
        "ground_truth_dimensions_m_for_evaluation_only": truth,
        "estimate": asdict(result),
        "runtime_s": runtime_s,
        "absolute_dimension_error_m": (
            [abs(a - b) for a, b in zip(result.estimated_dimensions_m, truth)]
            if result.estimated_dimensions_m is not None else None
        ),
    }


def main() -> None:
    report = {
        "experiment": "synthetic calibrated shoebox dimension recovery",
        "not_real_world_accuracy_or_paper_reproduction": True,
        "cases": [
            _case((4.0, 4.2, 3.6), seed=101, noise_s=0.0),
            _case((5.5, 4.8, 3.9), seed=202, noise_s=0.0),
            _case((6.1, 5.2, 4.0), seed=303, noise_s=8e-6),
        ],
    }
    output = Path(__file__).with_name("shoebox_dimension_recovery_results.json")
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    for case in report["cases"]:
        result = case["estimate"]
        print(
            f"seed={case['seed']} status={result['status']} "
            f"estimate_m={result['estimated_dimensions_m']} "
            f"error_m={case['absolute_dimension_error_m']} "
            f"rms_s={result['residual_statistics']['rms_s'] if result['residual_statistics'] else None} "
            f"rank={result['jacobian_rank']} cond={result['jacobian_condition_number']} "
            f"runtime_s={case['runtime_s']:.6f} nfev={result['function_evaluations']}"
        )
    print(f"Wrote {output}")


if __name__ == "__main__":
    main()
