"""Generic deterministic waveforms for engineering experiments.

These helpers do not implement or claim to reproduce the unresolved chirp in
Crocco et al. (2016), Eq. 10.
"""

from __future__ import annotations

import numpy as np

from .models import AudioSignal, SamplingFrequency


def _validate_waveform_parameters(
    duration_seconds: float,
    sampling_frequency: SamplingFrequency,
    amplitude: float,
) -> int:
    if not np.isfinite(duration_seconds) or duration_seconds <= 0:
        raise ValueError("duration_seconds must be finite and greater than 0")
    if not isinstance(sampling_frequency, SamplingFrequency):
        raise TypeError("sampling_frequency must be a SamplingFrequency")
    if not np.isfinite(amplitude) or amplitude < 0:
        raise ValueError("amplitude must be finite and non-negative")
    sample_count = int(np.floor(duration_seconds * sampling_frequency.hertz + 0.5))
    if sample_count < 1:
        raise ValueError("duration_seconds is shorter than half a sample interval")
    return sample_count


def _validate_frequency(frequency_hz: float, sampling_frequency: SamplingFrequency, name: str) -> None:
    if not np.isfinite(frequency_hz) or frequency_hz < 0:
        raise ValueError(f"{name} must be finite and non-negative")
    if frequency_hz >= sampling_frequency.hertz / 2:
        raise ValueError(f"{name} must be below the Nyquist frequency")


def generate_sine_wave(
    frequency_hz: float,
    duration_seconds: float,
    sampling_frequency: SamplingFrequency,
    *,
    amplitude: float = 1.0,
    phase_radians: float = 0.0,
) -> AudioSignal:
    """Generate a generic sampled sine wave with time in seconds and Hz input."""
    count = _validate_waveform_parameters(duration_seconds, sampling_frequency, amplitude)
    _validate_frequency(frequency_hz, sampling_frequency, "frequency_hz")
    if not np.isfinite(phase_radians):
        raise ValueError("phase_radians must be finite")
    time = np.arange(count, dtype=np.float64) / sampling_frequency.hertz
    samples = amplitude * np.sin(2.0 * np.pi * frequency_hz * time + phase_radians)
    return AudioSignal(samples, sampling_frequency)


def generate_linear_sweep(
    start_frequency_hz: float,
    end_frequency_hz: float,
    duration_seconds: float,
    sampling_frequency: SamplingFrequency,
    *,
    amplitude: float = 1.0,
    phase_radians: float = 0.0,
) -> AudioSignal:
    """Generate a generic linear instantaneous-frequency sine sweep.

    For the requested duration T, the engineering convention is
    ``phi(t) = 2*pi*(f_start*t + 0.5*((f_end-f_start)/T)*t**2) + phase``.
    Samples occur at ``t = n/fs`` for ``n=0,...,N-1``; the endpoint T itself is
    not sampled. This convention is explicitly independent of the unresolved
    Eq. 10 frequency convention in the research paper.
    """
    count = _validate_waveform_parameters(duration_seconds, sampling_frequency, amplitude)
    _validate_frequency(start_frequency_hz, sampling_frequency, "start_frequency_hz")
    _validate_frequency(end_frequency_hz, sampling_frequency, "end_frequency_hz")
    if not np.isfinite(phase_radians):
        raise ValueError("phase_radians must be finite")
    time = np.arange(count, dtype=np.float64) / sampling_frequency.hertz
    sweep_rate = (end_frequency_hz - start_frequency_hz) / duration_seconds
    phase = 2.0 * np.pi * (start_frequency_hz * time + 0.5 * sweep_rate * time**2)
    samples = amplitude * np.sin(phase + phase_radians)
    return AudioSignal(samples, sampling_frequency)
