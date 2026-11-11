"""Multichannel matched-filter analysis and conservative unlabeled TOA extraction."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import numpy as np
from numpy.typing import NDArray
from scipy.io import wavfile
from scipy.signal import find_peaks, peak_prominences

from batsight.datasets.calibrated import CalibratedShoeboxInputs
from batsight.signals.matched_filter import matched_filter
from batsight.signals.models import AudioSignal, KnownReferenceSignal, RecordingMetadata, SamplingFrequency
from batsight.signals.peaks import detect_peaks

FloatArray = NDArray[np.float64]
PeakDisposition = Literal[
    "below_local_threshold",
    "below_global_threshold",
    "below_prominence",
    "selected_direct",
    "inside_direct_window_not_selected",
    "unclassified_echo_candidate",
    "outside_candidate_window",
    "suppressed_duplicate",
]


@dataclass(frozen=True, slots=True)
class RecordingAnalysisConfig:
    """Explicit peak and timing windows for recording analysis.

    Delay windows are excess times after the geometrically predicted direct
    TOA. They do not classify an echo as first or higher order.
    """

    direct_tolerance_s: float = 2e-3
    minimum_echo_excess_delay_s: float = 2e-4
    maximum_echo_excess_delay_s: float = 5e-2
    minimum_peak_separation_s: float = 1.5e-4
    window_length_samples: int = 8
    thr1: float = 0.9
    thr2: float = 0.02
    minimum_peak_prominence: float = 0.0
    polarity: Literal["either", "positive"] = "either"
    timing_uncertainty_s: float | None = None

    def __post_init__(self) -> None:
        if not np.isfinite(self.direct_tolerance_s) or self.direct_tolerance_s <= 0.0:
            raise ValueError("direct_tolerance_s must be finite and positive")
        if (
            not np.isfinite(self.minimum_echo_excess_delay_s)
            or self.minimum_echo_excess_delay_s < 0.0
            or not np.isfinite(self.maximum_echo_excess_delay_s)
            or self.maximum_echo_excess_delay_s <= self.minimum_echo_excess_delay_s
        ):
            raise ValueError("echo delay limits must be finite, non-negative, and increasing")
        if not np.isfinite(self.minimum_peak_separation_s) or self.minimum_peak_separation_s < 0.0:
            raise ValueError("minimum_peak_separation_s must be finite and non-negative")
        if isinstance(self.window_length_samples, bool) or not isinstance(self.window_length_samples, int) or self.window_length_samples < 1:
            raise ValueError("window_length_samples must be a positive integer")
        if not np.isfinite(self.thr1) or not 0.0 <= self.thr1 <= 1.0:
            raise ValueError("thr1 must be in [0, 1]")
        if not np.isfinite(self.thr2) or not 0.0 <= self.thr2 <= 1.0:
            raise ValueError("thr2 must be in [0, 1]")
        if not np.isfinite(self.minimum_peak_prominence) or self.minimum_peak_prominence < 0.0:
            raise ValueError("minimum_peak_prominence must be finite and non-negative")
        if self.polarity not in ("either", "positive"):
            raise ValueError("polarity must be either or positive")
        if self.timing_uncertainty_s is not None and (
            not np.isfinite(self.timing_uncertainty_s) or self.timing_uncertainty_s <= 0.0
        ):
            raise ValueError("timing_uncertainty_s must be finite and positive when supplied")


@dataclass(frozen=True, slots=True)
class ExtractedArrival:
    """A direct arrival or an unclassified echo candidate from one channel."""

    microphone_id: str
    event_id: str
    echo_id: str | None
    kind: Literal["direct", "echo_candidate"]
    arrival_time_s: float
    fractional_sample_index: float
    integer_peak_index: int
    matched_filter_amplitude: float
    prominence: float
    robust_noise_scale: float
    peak_to_noise_ratio: float
    uncertainty_s: float | None
    classification: Literal["direct_path_candidate", "unclassified_echo_candidate"]


@dataclass(frozen=True, slots=True)
class RejectedPeak:
    """A peak candidate retained with the reason it was not emitted."""

    microphone_id: str
    event_id: str
    integer_peak_index: int
    fractional_sample_index: float
    arrival_time_s: float
    matched_filter_amplitude: float
    prominence: float
    reason: PeakDisposition


@dataclass(frozen=True, slots=True)
class PairRecordingAnalysis:
    """Matched-filter outcomes for one microphone and source event."""

    microphone_id: str
    event_id: str
    expected_direct_time_s: float
    direct_arrival: ExtractedArrival | None
    echo_candidates: tuple[ExtractedArrival, ...]
    rejected_peaks: tuple[RejectedPeak, ...]
    robust_noise_scale: float
    warnings: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RecordingAnalysisResult:
    """Complete multichannel analysis, including accepted and rejected peaks."""

    inputs: CalibratedShoeboxInputs
    recording: AudioSignal
    reference: AudioSignal
    recording_start_time_s: float
    config: RecordingAnalysisConfig
    pair_results: tuple[PairRecordingAnalysis, ...]
    warnings: tuple[str, ...]


def load_multichannel_wav(
    path: str | Path,
    *,
    expected_sampling_frequency_hz: float | None = None,
) -> AudioSignal:
    """Load PCM/float WAV without resampling; integer PCM is normalized to FS.

    Signed integer PCM is divided by the larger absolute dtype endpoint;
    unsigned PCM is centered at its midpoint and scaled by half its range.
    Floating WAV samples are passed through as dimensionless amplitudes.
    Other sample encodings are rejected rather than silently transformed.
    """
    file_path = Path(path)
    sample_rate, raw = wavfile.read(file_path)
    if expected_sampling_frequency_hz is not None and (
        not np.isfinite(expected_sampling_frequency_hz)
        or float(sample_rate) != float(expected_sampling_frequency_hz)
    ):
        raise ValueError("WAV sampling frequency differs from the expected calibrated rate; resampling is not implicit")
    if raw.dtype.kind == "i":
        limits = np.iinfo(raw.dtype)
        scale = float(max(abs(int(limits.min)), abs(int(limits.max))))
        samples = raw.astype(np.float64) / scale
    elif raw.dtype.kind == "u":
        limits = np.iinfo(raw.dtype)
        midpoint = (float(limits.max) + 1.0) / 2.0
        samples = (raw.astype(np.float64) - midpoint) / midpoint
    elif raw.dtype.kind == "f":
        samples = raw.astype(np.float64)
    else:
        raise ValueError(f"unsupported WAV sample dtype: {raw.dtype}")
    audio_metadata = RecordingMetadata(
        recording_id=file_path.name,
        device="WAV file",
        attributes={
            "sample_rate_hz": int(sample_rate),
            "channel_count": 1 if samples.ndim == 1 else int(samples.shape[1]),
            "source_dtype": str(raw.dtype),
            "integer_pcm_normalized_to_full_scale": raw.dtype.kind in ("i", "u"),
        },
    )
    return AudioSignal(
        samples,
        SamplingFrequency(float(sample_rate)),
        metadata=audio_metadata,
    )


def analyze_multichannel_recording(
    recording: AudioSignal,
    reference: KnownReferenceSignal | AudioSignal,
    inputs: CalibratedShoeboxInputs,
    *,
    recording_start_time_s: float = 0.0,
    config: RecordingAnalysisConfig = RecordingAnalysisConfig(),
) -> RecordingAnalysisResult:
    """Extract direct-path candidates and unlabeled echo TOAs from a recording.

    Channel order is the order of ``inputs.microphone_array.microphones``.
    Each event's geometrically expected direct time is known from calibrated
    positions, known emission time, and sound speed. The nearest accepted
    matched-filter peak inside ``direct_tolerance_s`` is the direct candidate.
    Remaining peaks in the configured excess-delay window are emitted as
    *unclassified* echoes; higher-order paths and spurious peaks may remain.
    No wall identity or first-order guarantee is assigned.
    """
    if not isinstance(recording, AudioSignal):
        raise TypeError("recording must be AudioSignal")
    if not isinstance(inputs, CalibratedShoeboxInputs):
        raise TypeError("inputs must be CalibratedShoeboxInputs")
    if not isinstance(config, RecordingAnalysisConfig):
        raise TypeError("config must be RecordingAnalysisConfig")
    if not np.isfinite(recording_start_time_s):
        raise ValueError("recording_start_time_s must be finite seconds")
    if recording.channel_count != len(inputs.microphone_array.microphones):
        raise ValueError("recording channel count must equal calibrated microphone count")
    fs = recording.sampling_frequency.hertz
    calibrated_fs = inputs.microphone_array.sampling_frequency.hertz
    if fs != calibrated_fs:
        raise ValueError("recording and calibrated microphone sampling frequencies must match exactly")
    if recording.metadata is not None and recording.metadata.attributes is not None:
        attributes = recording.metadata.attributes
        declared_rate = attributes.get("sample_rate_hz")
        declared_channels = attributes.get("channel_count")
        if declared_rate is not None and float(declared_rate) != fs:
            raise ValueError("recording metadata sample_rate_hz disagrees with AudioSignal")
        if declared_channels is not None and int(declared_channels) != recording.channel_count:
            raise ValueError("recording metadata channel_count disagrees with AudioSignal")
    if isinstance(reference, KnownReferenceSignal):
        reference_signal = reference.signal
    elif isinstance(reference, AudioSignal):
        reference_signal = reference
    else:
        raise TypeError("reference must be AudioSignal or KnownReferenceSignal")
    if reference_signal.channel_count != 1:
        raise ValueError("transmitted reference must be mono")
    if reference_signal.sampling_frequency.hertz != fs:
        raise ValueError("reference and recording sampling frequencies must match exactly")
    for event in inputs.source_events:
        if event.reference_signal is not None and not np.array_equal(
            event.reference_signal.signal.samples, reference_signal.samples
        ):
            raise ValueError(f"event {event.event_id} carries a different known reference signal")

    samples = recording.samples if recording.samples.ndim == 2 else recording.samples[:, None]
    pair_results: list[PairRecordingAnalysis] = []
    overall_warnings: list[str] = []
    microphones = inputs.microphone_array.microphones
    for event in inputs.source_events:
        for channel, microphone in enumerate(microphones):
            expected_direct = (
                event.emission_time_s
                + float(np.linalg.norm(np.asarray(event.position_m) - np.asarray(microphone.position_m)))
                / inputs.speed_of_sound_m_s
            )
            expected_relative = expected_direct - recording_start_time_s
            channel_signal = AudioSignal(samples[:, channel], recording.sampling_frequency, recording.metadata)
            mf = matched_filter(channel_signal, reference_signal, normalization="reference_energy")
            correlations = mf.correlation
            absolute = np.abs(correlations)
            median = float(np.median(correlations))
            robust_noise = float(1.4826 * np.median(np.abs(correlations - median)))
            robust_noise = max(robust_noise, np.finfo(np.float64).eps)
            accepted = detect_peaks(
                correlations,
                recording.sampling_frequency,
                window_length_samples=config.window_length_samples,
                thr1=config.thr1,
                thr2=config.thr2,
                start_time_seconds=float(mf.lags_samples[0]) / fs,
            )
            accepted_indices = {peak.sample_index for peak in accepted}
            local_indices = _all_local_maxima(absolute)
            prominence_by_index: dict[int, float] = {}
            interior = [index for index in local_indices if 0 < index < absolute.size - 1]
            if interior:
                values, _, _ = peak_prominences(absolute, np.asarray(interior, dtype=int))
                prominence_by_index.update({index: float(value) for index, value in zip(interior, values)})
            for index in local_indices:
                prominence_by_index.setdefault(index, float(absolute[index]))

            rejected: list[RejectedPeak] = []
            detections: list[ExtractedArrival] = []
            for index in local_indices:
                if index in accepted_indices:
                    continue
                local_end = min(absolute.size, index + config.window_length_samples)
                reason: PeakDisposition = (
                    "below_local_threshold"
                    if absolute[index] < config.thr1 * float(np.max(absolute[index:local_end]))
                    else "below_global_threshold"
                )
                lag_samples = float(mf.lags_samples[index])
                frac = lag_samples + _parabolic_peak_offset(absolute, index)
                rejected.append(_rejected(microphone.microphone_id, event.event_id, int(mf.lags_samples[index]), frac,
                                          recording_start_time_s + frac / fs,
                                          float(correlations[index]), prominence_by_index[index], reason))
            for peak in accepted:
                index = peak.sample_index
                prominence = prominence_by_index[index]
                lag_samples = float(mf.lags_samples[index])
                frac = lag_samples + _parabolic_peak_offset(absolute, index)
                if prominence < config.minimum_peak_prominence:
                    rejected.append(_rejected(microphone.microphone_id, event.event_id, index, frac,
                                              recording_start_time_s + frac / fs,
                                              peak.amplitude, prominence, "below_prominence"))
                    continue
                toa = recording_start_time_s + frac / fs
                detections.append(ExtractedArrival(
                    microphone_id=microphone.microphone_id,
                    event_id=event.event_id,
                    echo_id=f"{microphone.microphone_id}/{event.event_id}/sample-{int(mf.lags_samples[index])}",
                    kind="echo_candidate",
                    arrival_time_s=toa,
                    fractional_sample_index=frac,
                    integer_peak_index=int(mf.lags_samples[index]),
                    matched_filter_amplitude=float(peak.amplitude),
                    prominence=prominence,
                    robust_noise_scale=robust_noise,
                    peak_to_noise_ratio=float(abs(peak.amplitude) / robust_noise),
                    uncertainty_s=config.timing_uncertainty_s,
                    classification="unclassified_echo_candidate",
                ))

            direct_candidates = [
                item for item in detections
                if abs(item.arrival_time_s - expected_direct) <= config.direct_tolerance_s
            ]
            direct = None
            if direct_candidates:
                direct = min(
                    direct_candidates,
                    key=lambda item: (abs(item.arrival_time_s - expected_direct), -abs(item.matched_filter_amplitude)),
                )
                direct = ExtractedArrival(
                    microphone_id=direct.microphone_id,
                    event_id=direct.event_id,
                    echo_id=None,
                    kind="direct",
                    arrival_time_s=direct.arrival_time_s,
                    fractional_sample_index=direct.fractional_sample_index,
                    integer_peak_index=direct.integer_peak_index,
                    matched_filter_amplitude=direct.matched_filter_amplitude,
                    prominence=direct.prominence,
                    robust_noise_scale=direct.robust_noise_scale,
                    peak_to_noise_ratio=direct.peak_to_noise_ratio,
                    uncertainty_s=direct.uncertainty_s,
                    classification="direct_path_candidate",
                )
                selected = next(item for item in detections if item.fractional_sample_index == direct.fractional_sample_index)
                detections.remove(selected)
                rejected.append(_rejected(microphone.microphone_id, event.event_id, direct.integer_peak_index,
                                          direct.fractional_sample_index, direct.arrival_time_s,
                                          direct.matched_filter_amplitude, direct.prominence, "selected_direct"))
                for item in tuple(detections):
                    if abs(item.arrival_time_s - expected_direct) <= config.direct_tolerance_s:
                        detections.remove(item)
                        rejected.append(_rejected(
                            item.microphone_id, item.event_id, item.integer_peak_index,
                            item.fractional_sample_index, item.arrival_time_s,
                            item.matched_filter_amplitude, item.prominence,
                            "inside_direct_window_not_selected",
                        ))

            lower_time = expected_direct + config.minimum_echo_excess_delay_s
            upper_time = expected_direct + config.maximum_echo_excess_delay_s
            echo_window: list[ExtractedArrival] = []
            for item in detections:
                if lower_time <= item.arrival_time_s <= upper_time:
                    echo_window.append(item)
                else:
                    rejected.append(_rejected(
                        microphone.microphone_id, event.event_id, item.integer_peak_index,
                        item.fractional_sample_index, item.arrival_time_s, item.matched_filter_amplitude,
                        item.prominence, "outside_candidate_window"
                    ))
            echo_candidates, duplicate_rejections = _suppress_duplicates(
                echo_window,
                config.minimum_peak_separation_s,
                fs,
            )
            rejected.extend(duplicate_rejections)
            pair_warnings = []
            duration = recording.duration_seconds
            expected_last = expected_relative + config.maximum_echo_excess_delay_s + reference_signal.duration_seconds
            if expected_relative < 0.0 or expected_last > duration:
                pair_warnings.append("recording does not fully cover the configured event/echo analysis interval")
            if direct is None:
                pair_warnings.append("no direct-path peak passed thresholds inside the known-geometry timing gate")
            pair_results.append(PairRecordingAnalysis(
                microphone_id=microphone.microphone_id,
                event_id=event.event_id,
                expected_direct_time_s=expected_direct,
                direct_arrival=direct,
                echo_candidates=tuple(sorted(echo_candidates, key=lambda item: item.arrival_time_s)),
                rejected_peaks=tuple(sorted(rejected, key=lambda item: item.fractional_sample_index)),
                robust_noise_scale=robust_noise,
                warnings=tuple(pair_warnings),
            ))
            overall_warnings.extend(pair_warnings)

    return RecordingAnalysisResult(
        inputs=inputs,
        recording=recording,
        reference=reference_signal,
        recording_start_time_s=float(recording_start_time_s),
        config=config,
        pair_results=tuple(pair_results),
        warnings=tuple(overall_warnings),
    )


def _all_local_maxima(values: FloatArray) -> list[int]:
    peaks, _ = find_peaks(values)
    result = [int(value) for value in peaks]
    if values.size == 1:
        result.append(0)
    elif values.size > 1:
        if values[0] > values[1]:
            result.append(0)
        if values[-1] > values[-2]:
            result.append(values.size - 1)
    return sorted(set(result))


def _parabolic_peak_offset(values: FloatArray, index: int) -> float:
    if index <= 0 or index >= values.size - 1:
        return 0.0
    left, center, right = (float(values[index - 1]), float(values[index]), float(values[index + 1]))
    denominator = left - 2.0 * center + right
    if denominator >= 0.0 or abs(denominator) <= np.finfo(np.float64).eps:
        return 0.0
    return float(np.clip(0.5 * (left - right) / denominator, -0.5, 0.5))


def _rejected(microphone_id, event_id, index, frac, toa, amplitude, prominence, reason):
    return RejectedPeak(
        microphone_id, event_id, int(index), float(frac), float(toa),
        float(amplitude), float(prominence), reason
    )


def _suppress_duplicates(candidates, separation_s, fs):
    if not candidates:
        return (), ()
    ordered = sorted(candidates, key=lambda item: item.arrival_time_s)
    clusters: list[list[ExtractedArrival]] = [[ordered[0]]]
    for item in ordered[1:]:
        if item.arrival_time_s - clusters[-1][-1].arrival_time_s < separation_s:
            clusters[-1].append(item)
        else:
            clusters.append([item])
    kept = []
    rejected = []
    for cluster in clusters:
        winner = max(cluster, key=lambda item: (item.prominence, abs(item.matched_filter_amplitude)))
        kept.append(winner)
        for item in cluster:
            if item is not winner:
                rejected.append(_rejected(
                    item.microphone_id, item.event_id, item.integer_peak_index,
                    item.fractional_sample_index, item.arrival_time_s, item.matched_filter_amplitude,
                    item.prominence, "suppressed_duplicate"
                ))
    return tuple(kept), tuple(rejected)
