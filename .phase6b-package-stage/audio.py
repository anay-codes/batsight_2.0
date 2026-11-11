"""WAV-to-domain-object adapter; no resampling or channel mixing."""

from pathlib import Path

import numpy as np
from scipy.io import wavfile

from batsight.signals import AudioSignal, RecordingMetadata, SamplingFrequency


def read_audio_signal(path: Path, *, recording_id: str | None = None) -> AudioSignal:
    sample_rate, samples = wavfile.read(path)
    data = np.asarray(samples)
    if data.dtype.kind == "u":
        info = np.iinfo(data.dtype)
        midpoint = float(info.max + 1) / 2.0
        data = (data.astype(np.float64) - midpoint) / midpoint
    elif data.dtype.kind == "i":
        info = np.iinfo(data.dtype)
        scale = float(max(abs(int(info.min)), abs(int(info.max))))
        data = data.astype(np.float64) / scale
    else:
        data = data.astype(np.float64)
    metadata = RecordingMetadata(
        recording_id=recording_id,
        attributes={"original_dtype": str(samples.dtype), "source_path_name": path.name},
    )
    return AudioSignal(data, SamplingFrequency(float(sample_rate)), metadata)
