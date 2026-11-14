"""Measurement and echo-detection service using matched filtering and time-of-flight."""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any, Literal

import numpy as np
from scipy.io import wavfile
from scipy.signal import butter, sosfilt
from sqlalchemy.orm import Session

from batsight.application.config import Settings
from batsight.application.models.entities import Recording
from batsight.application.services.audio_service import AudioService
from batsight.application.services.recording_service import RecordingService
from batsight.application.services.signal_service import SignalProcessingService
from batsight.signals import AudioSignal, SamplingFrequency
from batsight.signals.matched_filter import matched_filter
from batsight.signals.peaks import detect_peaks




def apply_bandpass_filter(
    data: np.ndarray,
    sample_rate_hz: float,
    lowcut_hz: float = 1500.0,
    highcut_hz: float = 4500.0,
    order: int = 4,
) -> np.ndarray:
    """Butterworth bandpass filter to isolate chirp frequencies and reject environmental noise."""
    nyquist = 0.5 * sample_rate_hz
    low = max(20.0, lowcut_hz) / nyquist
    high = min(nyquist - 50.0, highcut_hz) / nyquist
    if low >= high or low <= 0 or high >= 1:
        return data
    sos = butter(order, [low, high], btype="bandpass", output="sos")
    return sosfilt(sos, data)

class MeasurementService:
    """Calculates echo arrivals and distances from chirp recordings."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.audio_service = AudioService(settings)
        self.signal_service = SignalProcessingService()

    def process_samples(
        self,
        samples: np.ndarray,
        sample_rate_hz: float,
        *,
        waveform: str = "linear_sweep",
        duration_s: float = 1.0,
        start_frequency_hz: float = 300.0,
        end_frequency_hz: float = 4000.0,
        amplitude: float = 0.9,
        speed_of_sound_m_s: float = 343.0,
        window_length_samples: int | None = None,
        thr1: float = 0.35,
        thr2: float = 0.04,
        normalization: Literal["reference_energy", "none"] = "reference_energy",
        bandpass_filter: bool = True,
        bandpass_lowcut_hz: float | None = None,
        bandpass_highcut_hz: float | None = None,
    ) -> dict[str, Any]:
        """Core signal processing: matched filter, peak detection, distance estimation."""
        data = np.asarray(samples)
        if data.ndim == 2:
            data = data[:, 0]  # default to channel 0
        if data.ndim != 1 or data.size == 0:
            raise ValueError("Audio samples must be non-empty 1D array")

        # Normalize PCM to float64 [-1.0, 1.0] if integer
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

        # Apply noise-rejection bandpass filter
        if bandpass_filter:
            lowcut = bandpass_lowcut_hz or max(50.0, start_frequency_hz * 0.85)
            highcut = bandpass_highcut_hz or min(sample_rate_hz / 2.0 - 100.0, end_frequency_hz * 1.15)
            data = apply_bandpass_filter(data, sample_rate_hz, lowcut, highcut)

        fs = SamplingFrequency(sample_rate_hz)
        mono = AudioSignal(data, fs)

        # Generate matched reference chirp
        reference = self.signal_service.generate_reference(
            waveform=waveform,
            sample_rate_hz=sample_rate_hz,
            duration_s=duration_s,
            start_frequency_hz=start_frequency_hz,
            end_frequency_hz=min(end_frequency_hz, sample_rate_hz / 2.0 - 1.0),
            amplitude=amplitude,
        )

        # Matched filter correlation
        matched = matched_filter(mono, reference, normalization=normalization)
        lags = matched.lags_samples

        # Adaptive window for realistic room echolocation (3-4ms / ~0.5m resolution)
        effective_window = window_length_samples or max(60, int(sample_rate_hz * 0.0035))

        # Detect correlation peaks
        peaks = detect_peaks(
            matched.correlation,
            fs,
            window_length_samples=effective_window,
            thr1=thr1,
            thr2=thr2,
            start_time_seconds=float(lags[0]) / sample_rate_hz,
        )

        # Identify direct path: dominant arrival from co-located speaker into microphone
        positive_peaks = [p for p in peaks if lags[p.sample_index] >= 0]
        if positive_peaks:
            max_pos_amp = max(abs(p.amplitude) for p in positive_peaks)
            # Pick first peak that has dominant energy (>= 50% of maximum peak)
            direct_peak = next(
                (p for p in positive_peaks if abs(p.amplitude) >= 0.50 * max_pos_amp),
                positive_peaks[0],
            )
        else:
            direct_peak = None

        direct_lag_s = (
            float(lags[direct_peak.sample_index]) / sample_rate_hz
            if direct_peak is not None
            else None
        )
        direct_distance_m = (
            direct_lag_s * speed_of_sound_m_s if direct_lag_s is not None else None
        )

        peak_records = []
        echo_distances: list[float] = []
        min_echo_delay_s = 0.0018  # ~31cm minimum distance to separate from direct-path mainlobe

        for p in peaks:
            lag_s = float(lags[p.sample_index]) / sample_rate_hz
            if direct_lag_s is not None and lag_s >= direct_lag_s:
                delay = lag_s - direct_lag_s
                dist = round((delay * speed_of_sound_m_s) / 2.0, 4)
                if p == direct_peak:
                    classification = "direct_path"
                elif delay >= min_echo_delay_s:
                    classification = "echo"
                    if 0.15 <= dist <= 15.0:
                        echo_distances.append(dist)
                else:
                    classification = "direct_sidelobe"
            elif lag_s < 0:
                delay = 0.0
                dist = 0.0
                classification = "pre_trigger"
            else:
                delay = lag_s
                dist = round((delay * speed_of_sound_m_s) / 2.0, 4)
                classification = "echo"
                if 0.15 <= dist <= 15.0:
                    echo_distances.append(dist)

            peak_records.append({
                "correlation_sample_index": int(p.sample_index),
                "lag_samples": int(lags[p.sample_index]),
                "lag_seconds": lag_s,
                "amplitude": float(p.amplitude),
                "delay_from_direct_s": round(delay, 6),
                "distance_m": dist,
                "path_length_m": round(max(0.0, lag_s) * speed_of_sound_m_s, 4),
                "classification": classification,
            })

        duration_s = float(data.size) / sample_rate_hz

        return {
            "sample_rate_hz": sample_rate_hz,
            "duration_s": round(duration_s, 4),
            "speed_of_sound_m_s": speed_of_sound_m_s,
            "direct_lag_s": direct_lag_s,
            "direct_distance_m": round(direct_distance_m, 4) if direct_distance_m is not None else None,
            "peaks": peak_records,
            "echo_count": len(echo_distances),
            "closest_reflector_m": min(echo_distances) if echo_distances else None,
            "farthest_reflector_m": max(echo_distances) if echo_distances else None,
            "provenance": "matched_filter_echo_detection",
        }

    def process_wav_bytes(
        self,
        wav_bytes: bytes,
        *,
        channel_index: int = 0,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Decode WAV bytes in memory and run measurement processing."""
        sample_rate, samples = wavfile.read(io.BytesIO(wav_bytes))
        data = np.asarray(samples)
        if data.ndim == 2:
            ch = min(channel_index, data.shape[1] - 1)
            data = data[:, ch]
        return self.process_samples(data, float(sample_rate), **kwargs)

    def process_recording(
        self,
        session: Session,
        recording_id: int,
        *,
        channel_index: int = 0,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Load an existing managed recording by ID and process it."""
        rec = session.get(Recording, recording_id)
        if rec is None:
            raise LookupError(f"Recording with ID {recording_id} not found")
        path = RecordingService(self.settings).safe_managed_path(rec)
        sample_rate, samples = wavfile.read(path)
        data = np.asarray(samples)
        if data.ndim == 2:
            ch = min(channel_index, data.shape[1] - 1)
            data = data[:, ch]
        return self.process_samples(data, float(sample_rate), **kwargs)


    def estimate_room_geometry(
        self,
        echo_distances: list[float],
        *,
        default_ceiling_height_m: float = 2.8,
        centered_assumption: bool = True,
    ) -> dict[str, Any]:
        """Estimate 2D/3D rectangular room geometry from detected echo distances."""
        valid = sorted([float(d) for d in echo_distances if d is not None and d > 0.05])

        if len(valid) >= 4:
            d1, d2, d3, d4 = valid[:4]
            length_x = round(d1 + d3, 3)
            width_y = round(d2 + d4, 3)
            x_min, x_max = d1, d3
            y_min, y_max = d2, d4
            device_x, device_y = d1, d2
            confidence = "calibrated_4_wall_fit"
        elif len(valid) >= 2:
            d1, d2 = valid[0], valid[1]
            if centered_assumption:
                length_x = round(d2 * 2.0, 3)
                width_y = round(d1 * 2.0, 3)
                device_x = round(length_x / 2.0, 3)
                device_y = round(width_y / 2.0, 3)
                x_min, x_max = d2, d2
                y_min, y_max = d1, d1
            else:
                length_x = round(d2 * 1.6, 3)
                width_y = round(d1 * 1.6, 3)
                device_x = d1
                device_y = d2
                x_min, x_max = d1, round(length_x - d1, 3)
                y_min, y_max = d2, round(width_y - d2, 3)
            confidence = "calibrated_2_wall_fit"
        elif len(valid) == 1:
            d1 = valid[0]
            length_x = round(d1 * 2.0, 3)
            width_y = round(d1 * 1.5, 3)
            device_x = round(length_x / 2.0, 3)
            device_y = round(width_y / 2.0, 3)
            x_min, x_max = d1, d1
            y_min, y_max = round(width_y / 2.0, 3), round(width_y / 2.0, 3)
            confidence = "single_echo_estimate"
        else:
            length_x = 5.0
            width_y = 4.0
            device_x = 2.5
            device_y = 2.0
            x_min, x_max = 2.5, 2.5
            y_min, y_max = 2.0, 2.0
            confidence = "default_fallback"

        length_x = max(1.0, length_x)
        width_y = max(1.0, width_y)
        height_z = round(default_ceiling_height_m, 3)
        device_z = round(min(1.2, height_z / 2.0), 3)

        area = round(length_x * width_y, 2)
        volume = round(length_x * width_y * height_z, 2)

        return {
            "estimated_dimensions_m": (length_x, width_y, height_z),
            "length_x_m": length_x,
            "width_y_m": width_y,
            "height_z_m": height_z,
            "floor_area_m2": area,
            "room_volume_m3": volume,
            "device_position_m": (device_x, device_y, device_z),
            "wall_distances": {
                "x_min": x_min,
                "x_max": x_max,
                "y_min": y_min,
                "y_max": y_max,
                "z_min": device_z,
                "z_max": round(height_z - device_z, 3),
            },
            "echo_distances_used": valid,
            "method": "calibrated_rectangular_bounding_box",
            "confidence": confidence,
        }
