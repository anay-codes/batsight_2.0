"""Generate downloadable WAVs through existing BatSight waveform functions."""

from __future__ import annotations

from io import BytesIO

import numpy as np
from scipy.io import wavfile

from batsight.application.services.signal_service import SignalProcessingService


class WaveformService:
    def __init__(self) -> None:
        self.signal_service = SignalProcessingService()

    def generate_pcm16_wav(
        self, *, waveform: str, sample_rate_hz: int, duration_s: float,
        start_frequency_hz: float, end_frequency_hz: float, amplitude: float,
    ) -> tuple[bytes, int, float]:
        reference = self.signal_service.generate_reference(
            waveform=waveform,
            sample_rate_hz=sample_rate_hz,
            duration_s=duration_s,
            start_frequency_hz=start_frequency_hz,
            end_frequency_hz=end_frequency_hz,
            amplitude=amplitude,
        )
        samples = np.rint(np.clip(reference.signal.samples, -1.0, 1.0) * 32767.0).astype(np.int16)
        output = BytesIO()
        wavfile.write(output, int(round(sample_rate_hz)), samples)
        duration = samples.size / float(sample_rate_hz)
        return output.getvalue(), int(samples.size), duration
