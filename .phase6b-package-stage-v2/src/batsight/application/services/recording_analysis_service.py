"""Application adapter for the existing matched-filter and peak detector."""

from __future__ import annotations

from typing import Any, Literal

import numpy as np
from scipy.signal import spectrogram

from batsight.application.config import Settings
from batsight.application.services.audio_service import AudioService
from batsight.application.services.signal_service import SignalProcessingService
from batsight.signals import AudioSignal, KnownReferenceSignal


class RecordingAnalysisService:
    """Analyze one selected recording channel with no direct/echo labels."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.audio_service = AudioService(settings)
        self.signal_service = SignalProcessingService()

    def analyze(
        self,
        path,
        *,
        recording_id: str,
        channel_index: int,
        reference: KnownReferenceSignal,
        normalization: Literal["reference_energy", "none"],
        window_length_samples: int,
        thr1: float,
        thr2: float,
        spectrogram_nperseg: int,
    ) -> dict[str, Any]:
        recording = self.audio_service.load(path, recording_id=recording_id)
        if recording.sample_count > self.settings.max_analysis_samples:
            raise ValueError(
                f"Recording contains {recording.sample_count} samples; this analysis endpoint "
                f"is limited to {self.settings.max_analysis_samples} samples per channel"
            )
        if channel_index < 0 or channel_index >= recording.channel_count:
            raise IndexError(f"channel_index must be in [0, {recording.channel_count - 1}]")
        channel_samples = (
            recording.samples if recording.samples.ndim == 1
            else recording.samples[:, channel_index]
        )
        mono = AudioSignal(channel_samples, recording.sampling_frequency, recording.metadata)
        matched = self.signal_service.matched_filter(mono, reference, normalization=normalization)
        lags = matched.lags_samples
        peaks = self.signal_service.detect_peaks(
            matched.correlation,
            recording.sampling_frequency,
            window_length_samples=window_length_samples,
            thr1=thr1,
            thr2=thr2,
            start_time_seconds=float(lags[0]) / recording.sampling_frequency.hertz,
        )
        peak_records = [
            {
                "correlation_sample_index": int(peak.sample_index),
                "lag_samples": int(lags[peak.sample_index]),
                "lag_seconds": float(lags[peak.sample_index]) / recording.sampling_frequency.hertz,
                "amplitude": float(peak.amplitude),
                "classification": "unclassified_correlation_peak",
            }
            for peak in peaks
        ]
        envelope = _minmax_envelope(matched.lags_seconds, matched.correlation, maximum_points=4096)
        nperseg = min(spectrogram_nperseg, int(channel_samples.size))
        noverlap = min(nperseg - 1, int(0.75 * nperseg))
        frequencies, times, magnitude = spectrogram(
            channel_samples,
            fs=recording.sampling_frequency.hertz,
            window="hann",
            nperseg=nperseg,
            noverlap=noverlap,
            detrend=False,
            scaling="spectrum",
            mode="magnitude",
        )
        magnitude_db = 20.0 * np.log10(np.maximum(magnitude, np.finfo(np.float64).tiny))
        frequencies, times, magnitude_db = _thin_spectrogram(frequencies, times, magnitude_db)
        return {
            "recording_id": recording_id,
            "channel_index": channel_index,
            "sample_rate_hz": recording.sampling_frequency.hertz,
            "channel_count": recording.channel_count,
            "sample_count": recording.sample_count,
            "duration_s": recording.duration_seconds,
            "amplitude_statistics": {
                "minimum": float(np.min(channel_samples)),
                "maximum": float(np.max(channel_samples)),
                "mean": float(np.mean(channel_samples)),
                "rms": float(np.sqrt(np.mean(np.square(channel_samples)))),
                "amplitude_units": "normalized sample amplitude for integer PCM; source-defined for float WAV",
            },
            "matched_filter": {
                "correlation_convention": "full correlate(recording_channel, reference); positive lag means delayed reference",
                "normalization": normalization,
                "reference_sample_count": reference.signal.sample_count,
                "curve": envelope,
                "peak_detection": {
                    "window_length_samples": window_length_samples,
                    "thr1": thr1,
                    "thr2": thr2,
                    "accepted_peak_count": len(peak_records),
                    "threshold_rejection_reasons_available": False,
                },
                "peaks": peak_records,
                "direct_or_echo_classification_available": False,
            },
            "spectrogram": {
                "frequencies_hz": frequencies.tolist(),
                "times_s": times.tolist(),
                "magnitude_db_re_1_sample_amplitude": magnitude_db.tolist(),
                "window": "hann",
                "nperseg": nperseg,
                "noverlap": noverlap,
                "time_bin_count_is_decimated": times.size < magnitude.shape[1],
            },
            "provenance": "real_or_user_supplied_recording; calibrated synchronization and geometry are not inferred",
        }


def _minmax_envelope(times: np.ndarray, values: np.ndarray, *, maximum_points: int) -> list[dict[str, float]]:
    if values.size <= maximum_points:
        return [{"time_s": float(t), "value": float(v)} for t, v in zip(times, values)]
    block_size = int(np.ceil(values.size / (maximum_points / 2)))
    points: list[dict[str, float]] = []
    for start in range(0, values.size, block_size):
        stop = min(values.size, start + block_size)
        block = values[start:stop]
        local_indices = {start + int(np.argmin(block)), start + int(np.argmax(block))}
        for index in sorted(local_indices):
            points.append({"time_s": float(times[index]), "value": float(values[index])})
    return points


def _thin_spectrogram(frequencies: np.ndarray, times: np.ndarray, values: np.ndarray):
    frequency_step = max(1, int(np.ceil(frequencies.size / 256)))
    time_step = max(1, int(np.ceil(times.size / 512)))
    return frequencies[::frequency_step], times[::time_step], values[::frequency_step, ::time_step]
