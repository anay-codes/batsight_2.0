"""Typed signal containers with explicit SI units and sample conversions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

import numpy as np
from numpy.typing import NDArray

FloatArray = NDArray[np.float64]


@dataclass(frozen=True, slots=True)
class SamplingFrequency:
    """Sampling frequency expressed in samples per second (hertz)."""

    hertz: float

    def __post_init__(self) -> None:
        if not np.isfinite(self.hertz) or self.hertz <= 0:
            raise ValueError("sampling frequency must be a finite value greater than 0 Hz")

    def sample_index_to_time(self, sample_index: int) -> float:
        """Convert a zero-based sample index to seconds relative to sample 0."""
        if isinstance(sample_index, bool) or not isinstance(sample_index, (int, np.integer)):
            raise TypeError("sample_index must be an integer")
        if sample_index < 0:
            raise ValueError("sample_index must be non-negative")
        return int(sample_index) / self.hertz

    def time_to_sample_index(self, time_seconds: float) -> int:
        """Round a non-negative time to its nearest sample (ties round upward)."""
        if not np.isfinite(time_seconds) or time_seconds < 0:
            raise ValueError("time_seconds must be finite and non-negative")
        return int(np.floor(float(time_seconds) * self.hertz + 0.5))


@dataclass(frozen=True, slots=True)
class RecordingMetadata:
    """Optional provenance and acquisition information for an audio signal."""

    recording_id: str | None = None
    source_id: str | None = None
    device: str | None = None
    notes: str | None = None
    attributes: Mapping[str, str | int | float | bool] | None = None


@dataclass(frozen=True, slots=True)
class AudioSignal:
    """Floating-point audio samples and their sampling frequency.

    Samples use shape ``(samples,)`` for mono or ``(samples, channels)`` for
    multichannel data. Amplitude units are caller-defined (typically normalized
    full scale); sample rate is always in Hz. The samples are copied and made
    read-only so that stored metadata and derived results cannot be invalidated
    by mutating the original input array.
    """

    samples: FloatArray
    sampling_frequency: SamplingFrequency
    metadata: RecordingMetadata | None = None

    def __post_init__(self) -> None:
        data = np.asarray(self.samples, dtype=np.float64)
        if data.ndim not in (1, 2):
            raise ValueError("audio samples must be a 1D mono or 2D samples-by-channels array")
        if data.shape[0] == 0 or (data.ndim == 2 and data.shape[1] == 0):
            raise ValueError("audio samples must contain at least one sample and one channel")
        if not np.all(np.isfinite(data)):
            raise ValueError("audio samples must contain only finite values")
        if not isinstance(self.sampling_frequency, SamplingFrequency):
            raise TypeError("sampling_frequency must be a SamplingFrequency")
        if self.metadata is not None and not isinstance(self.metadata, RecordingMetadata):
            raise TypeError("metadata must be RecordingMetadata or None")
        data = np.array(data, copy=True)
        data.setflags(write=False)
        object.__setattr__(self, "samples", data)

    @property
    def sample_count(self) -> int:
        """Number of samples per channel."""
        return int(self.samples.shape[0])

    @property
    def channel_count(self) -> int:
        """Number of channels represented by this signal."""
        return 1 if self.samples.ndim == 1 else int(self.samples.shape[1])

    @property
    def duration_seconds(self) -> float:
        """Sample-frame duration, equal to sample_count / sampling frequency."""
        return self.sample_count / self.sampling_frequency.hertz

    def sample_index_to_time(self, sample_index: int) -> float:
        """Convert a sample index to seconds relative to the start of this signal."""
        return self.sampling_frequency.sample_index_to_time(sample_index)

    def time_to_sample_index(self, time_seconds: float) -> int:
        """Convert seconds to the nearest zero-based sample index."""
        return self.sampling_frequency.time_to_sample_index(time_seconds)


@dataclass(frozen=True, slots=True)
class KnownReferenceSignal:
    """A supplied, known transmitted waveform used as a matched-filter reference."""

    signal: AudioSignal
    description: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.signal, AudioSignal):
            raise TypeError("signal must be an AudioSignal")
        if self.signal.channel_count != 1:
            raise ValueError("known reference signal must be mono")


@dataclass(frozen=True, slots=True)
class DetectedArrivalTime:
    """One detected peak with index, time coordinate, and signed amplitude.

    Time is in seconds relative to the caller's chosen origin. It may be
    negative when describing signed correlation lags rather than a physical
    arrival after time zero.
    """

    sample_index: int
    time_seconds: float
    amplitude: float

    def __post_init__(self) -> None:
        if isinstance(self.sample_index, bool) or not isinstance(self.sample_index, (int, np.integer)):
            raise TypeError("sample_index must be an integer")
        if self.sample_index < 0:
            raise ValueError("sample_index must be non-negative")
        if not np.isfinite(self.time_seconds):
            raise ValueError("time_seconds must be finite")
        if not np.isfinite(self.amplitude):
            raise ValueError("amplitude must be finite")
