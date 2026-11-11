"""Reference-waveform matched filtering with explicit lag conventions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np
from numpy.typing import NDArray
from scipy.signal import correlate, correlation_lags

from .models import AudioSignal, KnownReferenceSignal

FloatArray = NDArray[np.float64]
Normalization = Literal["reference_energy", "none"]
Polarity = Literal["either", "positive"]


@dataclass(frozen=True, slots=True)
class MatchedFilterResult:
    """Full correlation sequence and corresponding signed sample lags.

    Positive lag means the recording contains the reference later than the
    reference's sample-zero position. The normalized correlation values are
    divided by reference energy, not converted to a correlation coefficient.
    """

    correlation: FloatArray
    lags_samples: NDArray[np.int64]
    sampling_frequency_hz: float

    def __post_init__(self) -> None:
        corr = np.asarray(self.correlation, dtype=np.float64)
        lags = np.asarray(self.lags_samples, dtype=np.int64)
        if corr.ndim != 1 or lags.ndim != 1 or corr.size != lags.size or corr.size == 0:
            raise ValueError("correlation and lags_samples must be non-empty 1D arrays of equal length")
        if not np.all(np.isfinite(corr)):
            raise ValueError("correlation values must be finite")
        if not np.isfinite(self.sampling_frequency_hz) or self.sampling_frequency_hz <= 0:
            raise ValueError("sampling_frequency_hz must be finite and greater than 0")
        corr = np.array(corr, copy=True)
        lags = np.array(lags, copy=True)
        corr.setflags(write=False)
        lags.setflags(write=False)
        object.__setattr__(self, "correlation", corr)
        object.__setattr__(self, "lags_samples", lags)

    @property
    def lags_seconds(self) -> FloatArray:
        """Signed lag timestamps in seconds relative to reference sample zero."""
        return self.lags_samples.astype(np.float64) / self.sampling_frequency_hz

    def estimate_arrival_time(self, *, polarity: Polarity = "either") -> tuple[int, float, float]:
        """Return (lag in samples, lag in seconds, signed matched-filter value).

        ``either`` selects the largest absolute correlation and supports an
        inverted recording polarity; ``positive`` selects the largest signed
        correlation and assumes the recorded waveform polarity matches the
        supplied reference. Ties use NumPy's first-occurrence convention.
        """
        if polarity not in ("either", "positive"):
            raise ValueError("polarity must be 'either' or 'positive'")
        criterion = np.abs(self.correlation) if polarity == "either" else self.correlation
        index = int(np.argmax(criterion))
        lag = int(self.lags_samples[index])
        return lag, lag / self.sampling_frequency_hz, float(self.correlation[index])


def matched_filter(
    recording: AudioSignal,
    reference: KnownReferenceSignal | AudioSignal,
    *,
    normalization: Normalization = "reference_energy",
) -> MatchedFilterResult:
    """Correlate a mono recording with an explicitly supplied reference.

    Convention: ``correlate(recording, reference, mode='full')``. With this
    argument order, a copy of the reference delayed by d samples produces a
    peak at lag ``+d``. For additive white noise and a known waveform, this is
    the conventional matched-filter statistic. No generalized
    cross-correlation/PHAT spectrum weighting is applied.

    ``reference_energy`` divides the correlation by ``sum(reference**2)``;
    for a noiseless `gain * reference` this returns the signed gain at the
    correct lag. `none` returns the raw discrete correlation sum. By default,
    arrival selection uses absolute correlation to allow unknown polarity;
    select ``polarity='positive'`` on the result to assume matching polarity.
    A single maximum is an arrival estimate, not a multi-echo detector.
    """
    if not isinstance(recording, AudioSignal):
        raise TypeError("recording must be an AudioSignal")
    if recording.channel_count != 1:
        raise ValueError("matched_filter currently accepts a mono recording")
    if isinstance(reference, KnownReferenceSignal):
        reference_signal = reference.signal
    elif isinstance(reference, AudioSignal):
        reference_signal = reference
    else:
        raise TypeError("reference must be an AudioSignal or KnownReferenceSignal")
    if reference_signal.channel_count != 1:
        raise ValueError("matched-filter reference must be mono")
    if not np.isclose(
        recording.sampling_frequency.hertz,
        reference_signal.sampling_frequency.hertz,
        rtol=0.0,
        atol=0.0,
    ):
        raise ValueError("recording and reference sampling frequencies must match exactly")
    if normalization not in ("reference_energy", "none"):
        raise ValueError("normalization must be 'reference_energy' or 'none'")

    ref = reference_signal.samples
    energy = float(np.dot(ref, ref))
    if not np.isfinite(energy) or energy <= np.finfo(np.float64).tiny:
        raise ValueError("reference signal must have non-zero finite energy")
    corr = correlate(recording.samples, ref, mode="full", method="auto")
    if normalization == "reference_energy":
        corr = corr / energy
    lags = correlation_lags(recording.sample_count, reference_signal.sample_count, mode="full")
    return MatchedFilterResult(corr, lags, recording.sampling_frequency.hertz)
