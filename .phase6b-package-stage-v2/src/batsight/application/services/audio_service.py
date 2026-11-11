"""WAV validation and loading service."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy.io import wavfile

from batsight.application.adapters.audio import read_audio_signal
from batsight.application.config import Settings
from batsight.signals import AudioSignal


@dataclass(frozen=True, slots=True)
class WavMetadata:
    sample_rate_hz: int
    channel_count: int
    sample_count: int
    duration_s: float
    file_size_bytes: int
    sample_dtype: str


class AudioService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def validate_wav(self, path: Path) -> WavMetadata:
        size = path.stat().st_size
        if size <= 0:
            raise ValueError("WAV file is empty")
        if size > self.settings.max_upload_size_bytes:
            raise ValueError("WAV file exceeds the configured upload size limit")
        samples = None
        try:
            try:
                sample_rate, samples = wavfile.read(path, mmap=True)
            except ValueError:
                # SciPy cannot memory-map packed 24-bit PCM; the upload-size
                # limit bounds this fallback allocation.
                sample_rate, samples = wavfile.read(path, mmap=False)
            data = np.asarray(samples)
            if data.ndim == 1:
                channels = 1
            elif data.ndim == 2:
                channels = int(data.shape[1])
            else:
                raise ValueError("WAV samples must be mono or samples-by-channels")
            if data.shape[0] <= 0:
                raise ValueError("WAV contains no samples")
            if not self.settings.min_sample_rate_hz <= int(sample_rate) <= self.settings.max_sample_rate_hz:
                raise ValueError(
                    f"Sample rate must be between {self.settings.min_sample_rate_hz} and "
                    f"{self.settings.max_sample_rate_hz} Hz; files are not resampled"
                )
            if channels < 1 or channels > self.settings.max_channels:
                raise ValueError(f"Channel count must be between 1 and {self.settings.max_channels}")
            if data.dtype.kind not in "iuf":
                raise ValueError("WAV sample encoding must be integer PCM or floating point")
            if data.dtype.kind == "f" and not np.all(np.isfinite(data)):
                raise ValueError("WAV contains non-finite floating-point samples")
            count = int(data.shape[0])
            duration = count / float(sample_rate)
            if duration <= 0 or duration > self.settings.max_recording_duration_s:
                raise ValueError(
                    f"Recording duration must be in (0, {self.settings.max_recording_duration_s}] seconds"
                )
            return WavMetadata(int(sample_rate), channels, count, duration, size, str(data.dtype))
        except (ValueError, OSError, EOFError) as exc:
            if isinstance(exc, ValueError) and str(exc).startswith((
                "WAV", "Sample rate", "Channel count", "Recording duration"
            )):
                raise
            raise ValueError("File is not a supported, complete WAV recording") from exc
        finally:
            mapped_file = getattr(samples, "_mmap", None)
            if mapped_file is not None:
                mapped_file.close()

    def load(self, path: Path, *, recording_id: str | None = None) -> AudioSignal:
        self.validate_wav(path)
        return read_audio_signal(path, recording_id=recording_id)
