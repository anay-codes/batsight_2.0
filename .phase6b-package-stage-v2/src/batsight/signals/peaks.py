"""Two-stage local/global threshold peak detection."""

from __future__ import annotations

import numpy as np
from scipy.signal import find_peaks

from .models import DetectedArrivalTime, SamplingFrequency


def detect_peaks(
    values: np.ndarray,
    sampling_frequency: SamplingFrequency,
    *,
    window_length_samples: int,
    thr1: float = 0.9,
    thr2: float = 0.1,
    start_time_seconds: float = 0.0,
) -> tuple[DetectedArrivalTime, ...]:
    """Detect peak samples using a forward sliding threshold then global cutoff.

    Engineering choices made explicit where the paper is underspecified:

    * Magnitude (absolute value) is used for detection, allowing either
      correlation polarity; returned amplitude retains its original sign.
    * Candidate local maxima are extracted with SciPy `find_peaks`; endpoints
      that exceed their sole neighbor are also considered peak candidates.
    * At candidate index i, the local window is the forward, truncated interval
      `[i, i + window_length_samples)`, matching Algorithm 1's forward sliding
      window. The candidate survives stage one if its magnitude is at least
      `thr1 * maximum(window)`.
    * Stage two keeps candidates at least `thr2 * global_maximum`. The global
      maximum is computed over the entire input, as in the paper. Threshold
      comparisons are inclusive.

    Returned `sample_index` is relative to `values[0]`; `start_time_seconds`
    lets callers describe lag arrays (for example full matched-filter output).
    Time units are seconds and sample rate is Hz. This is a peak-picker, not a
    probabilistic false-alarm controller.
    """
    data = np.asarray(values, dtype=np.float64)
    if data.ndim != 1 or data.size == 0:
        raise ValueError("values must be a non-empty 1D array")
    if not np.all(np.isfinite(data)):
        raise ValueError("values must contain only finite values")
    if not isinstance(sampling_frequency, SamplingFrequency):
        raise TypeError("sampling_frequency must be a SamplingFrequency")
    if isinstance(window_length_samples, bool) or not isinstance(window_length_samples, (int, np.integer)):
        raise TypeError("window_length_samples must be an integer")
    if window_length_samples < 1:
        raise ValueError("window_length_samples must be at least 1")
    if not np.isfinite(thr1) or not 0 <= thr1 <= 1:
        raise ValueError("thr1 must be finite and in [0, 1]")
    if not np.isfinite(thr2) or not 0 <= thr2 <= 1:
        raise ValueError("thr2 must be finite and in [0, 1]")
    if not np.isfinite(start_time_seconds):
        raise ValueError("start_time_seconds must be finite")

    magnitude = np.abs(data)
    global_maximum = float(np.max(magnitude))
    if global_maximum == 0.0:
        return ()

    candidates, _ = find_peaks(magnitude)
    endpoint_candidates: list[int] = []
    if magnitude.size == 1:
        endpoint_candidates.append(0)
    else:
        if magnitude[0] > magnitude[1]:
            endpoint_candidates.append(0)
        if magnitude[-1] > magnitude[-2]:
            endpoint_candidates.append(magnitude.size - 1)
    candidates = np.sort(np.concatenate((candidates, np.asarray(endpoint_candidates, dtype=int))))

    accepted: list[DetectedArrivalTime] = []
    for index_value in candidates:
        index = int(index_value)
        window_end = min(data.size, index + int(window_length_samples))
        local_maximum = float(np.max(magnitude[index:window_end]))
        value = float(magnitude[index])
        if value < thr1 * local_maximum:
            continue
        if value < thr2 * global_maximum:
            continue
        accepted.append(
            DetectedArrivalTime(
                sample_index=index,
                time_seconds=float(start_time_seconds) + index / sampling_frequency.hertz,
                amplitude=float(data[index]),
            )
        )
    return tuple(accepted)
