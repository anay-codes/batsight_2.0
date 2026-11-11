"""Forward simulation -> matched filter -> peak detection -> TOA comparison."""

from __future__ import annotations

import csv
import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import IO, Any, Sequence

import numpy as np

from batsight.signals import AudioSignal, DetectedArrivalTime, SamplingFrequency, detect_peaks, matched_filter
from batsight.simulation import AcousticPath, RIRSimulation, ShoeboxRoom, SimulatedRecordings, simulate_recordings
from batsight.signals.matched_filter import MatchedFilterResult


@dataclass(frozen=True, slots=True)
class ExpectedArrival:
    """Simulator-derived expected path and continuous TOF."""

    path_index: int
    reflection_order: int
    reflection_sequence: tuple[str, ...]
    image_source_position_m: tuple[float, float, float]
    distance_m: float
    time_of_flight_s: float
    reflection_coefficient: float

    @classmethod
    def from_path(cls, index: int, path: AcousticPath) -> ExpectedArrival:
        return cls(
            path_index=index,
            reflection_order=path.reflection_order,
            reflection_sequence=path.reflection_sequence,
            image_source_position_m=path.image_source.position_m,
            distance_m=path.propagation_distance_m,
            time_of_flight_s=path.time_of_flight_s,
            reflection_coefficient=path.image_source.reflection_coefficient,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "path_index": self.path_index,
            "reflection_order": self.reflection_order,
            "reflection_sequence": list(self.reflection_sequence),
            "image_source_position_m": list(self.image_source_position_m),
            "distance_m": self.distance_m,
            "time_of_flight_s": self.time_of_flight_s,
            "reflection_coefficient": self.reflection_coefficient,
        }


@dataclass(frozen=True, slots=True)
class ArrivalMatch:
    """One expected path paired with one detected matched-filter peak."""

    expected: ExpectedArrival
    detected: DetectedArrivalTime
    absolute_error_seconds: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "expected": self.expected.to_dict(),
            "detected": _detected_to_dict(self.detected),
            "absolute_error_seconds": self.absolute_error_seconds,
        }


@dataclass(frozen=True, slots=True)
class ArrivalMetrics:
    """Error/count metrics computed only over accepted one-to-one matches."""

    matched_count: int
    missed_expected_count: int
    unmatched_detected_count: int
    mean_absolute_error_seconds: float | None
    root_mean_square_error_seconds: float | None

    @classmethod
    def from_matches(
        cls,
        matches: Sequence[ArrivalMatch],
        missed_count: int,
        unmatched_count: int,
    ) -> ArrivalMetrics:
        if matches:
            errors = np.asarray([match.absolute_error_seconds for match in matches], dtype=np.float64)
            mae: float | None = float(np.mean(np.abs(errors)))
            rmse: float | None = float(np.sqrt(np.mean(errors**2)))
        else:
            mae = None
            rmse = None
        return cls(len(matches), missed_count, unmatched_count, mae, rmse)

    def to_dict(self) -> dict[str, int | float | None]:
        return {
            "matched_count": self.matched_count,
            "missed_expected_count": self.missed_expected_count,
            "unmatched_detected_count": self.unmatched_detected_count,
            "mean_absolute_error_seconds": self.mean_absolute_error_seconds,
            "root_mean_square_error_seconds": self.root_mean_square_error_seconds,
        }


@dataclass(frozen=True, slots=True)
class TOAComparison:
    """Complete expected/detected sets, accepted matches, and errors."""

    expected_arrivals: tuple[ExpectedArrival, ...]
    detected_arrivals: tuple[DetectedArrivalTime, ...]
    matches: tuple[ArrivalMatch, ...]
    missed_expected: tuple[ExpectedArrival, ...]
    unmatched_detected: tuple[DetectedArrivalTime, ...]
    tolerance_seconds: float
    metrics: ArrivalMetrics

    def to_dict(self) -> dict[str, Any]:
        return {
            "tolerance_seconds": self.tolerance_seconds,
            "expected_arrivals": [item.to_dict() for item in self.expected_arrivals],
            "detected_arrivals": [_detected_to_dict(item) for item in self.detected_arrivals],
            "matched_arrivals": [item.to_dict() for item in self.matches],
            "missed_expected_arrivals": [item.to_dict() for item in self.missed_expected],
            "unmatched_detected_peaks": [_detected_to_dict(item) for item in self.unmatched_detected],
            "metrics": self.metrics.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class ExperimentConfiguration:
    """Fully recorded scalar/geometry settings for one forward experiment."""

    room_dimensions_m: tuple[float, float, float]
    speed_of_sound_m_s: float
    wall_reflection_coefficients: tuple[tuple[str, float], ...]
    source_position_m: tuple[float, float, float]
    microphone_positions_m: tuple[tuple[float, float, float], ...]
    max_reflection_order: int
    sampling_frequency_hz: float
    excitation_sample_count: int
    excitation_sha256: str
    requested_snr_db: float | None
    random_seed: int | None
    impulse_placement: str
    peak_window_length_samples: int
    thr1: float
    thr2: float
    matching_tolerance_seconds: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "room_dimensions_m": list(self.room_dimensions_m),
            "speed_of_sound_m_s": self.speed_of_sound_m_s,
            "wall_reflection_coefficients": dict(self.wall_reflection_coefficients),
            "source_position_m": list(self.source_position_m),
            "microphone_positions_m": [list(position) for position in self.microphone_positions_m],
            "max_reflection_order": self.max_reflection_order,
            "sampling_frequency_hz": self.sampling_frequency_hz,
            "excitation_sample_count": self.excitation_sample_count,
            "excitation_sha256": self.excitation_sha256,
            "requested_snr_db": self.requested_snr_db,
            "random_seed": self.random_seed,
            "impulse_placement": self.impulse_placement,
            "peak_window_length_samples": self.peak_window_length_samples,
            "thr1": self.thr1,
            "thr2": self.thr2,
            "matching_tolerance_seconds": self.matching_tolerance_seconds,
        }


@dataclass(frozen=True, slots=True)
class MicrophoneExperimentResult:
    """Per-microphone waveform, matched-filter trace, peaks, and TOA metrics."""

    microphone_index: int
    microphone_position_m: tuple[float, float, float]
    rir_simulation: RIRSimulation
    matched_filter_result: MatchedFilterResult
    toa_comparison: TOAComparison

    def to_dict(self, *, include_correlation: bool = False) -> dict[str, Any]:
        result: dict[str, Any] = {
            "microphone_index": self.microphone_index,
            "microphone_position_m": list(self.microphone_position_m),
            "paths": [_path_to_dict(path) for path in self.rir_simulation.paths],
            "toa_comparison": self.toa_comparison.to_dict(),
        }
        if include_correlation:
            result["matched_filter_trace"] = {
                "lags_samples": self.matched_filter_result.lags_samples.tolist(),
                "lags_seconds": self.matched_filter_result.lags_seconds.tolist(),
                "correlation": self.matched_filter_result.correlation.tolist(),
            }
        return result


@dataclass(frozen=True, slots=True)
class ExperimentResult:
    """Frontend-friendly structured result plus underlying simulated audio."""

    configuration: ExperimentConfiguration
    excitation: AudioSignal
    simulated_recordings: SimulatedRecordings
    microphone_results: tuple[MicrophoneExperimentResult, ...]

    @property
    def overall_metrics(self) -> ArrivalMetrics:
        matches = tuple(match for result in self.microphone_results for match in result.toa_comparison.matches)
        missed = sum(len(result.toa_comparison.missed_expected) for result in self.microphone_results)
        unmatched = sum(len(result.toa_comparison.unmatched_detected) for result in self.microphone_results)
        return ArrivalMetrics.from_matches(matches, missed, unmatched)

    def to_dict(
        self,
        *,
        include_waveforms: bool = False,
        include_correlations: bool = False,
    ) -> dict[str, Any]:
        result: dict[str, Any] = {
            "configuration": self.configuration.to_dict(),
            "room": {
                "dimensions_m": list(self.configuration.room_dimensions_m),
                "speed_of_sound_m_s": self.configuration.speed_of_sound_m_s,
                "wall_reflection_coefficients": dict(self.configuration.wall_reflection_coefficients),
            },
            "microphones": [
                {
                    "index": item.microphone_index,
                    "position_m": list(item.microphone_position_m),
                    "channel_count": 1,
                }
                for item in self.microphone_results
            ],
            "microphone_results": [
                item.to_dict(include_correlation=include_correlations) for item in self.microphone_results
            ],
            "overall_metrics": self.overall_metrics.to_dict(),
        }
        if include_waveforms:
            result["recordings"] = {
                "sampling_frequency_hz": self.simulated_recordings.recordings.sampling_frequency.hertz,
                "samples_by_microphone": self.simulated_recordings.recordings.samples.tolist(),
            }
            result["excitation"] = {
                "sampling_frequency_hz": self.excitation.sampling_frequency.hertz,
                "samples": self.excitation.samples.tolist(),
            }
            result["rir_samples"] = [
                item.rir_simulation.impulse_response.samples.tolist() for item in self.microphone_results
            ]
        return result

    def write_csv(self, destination: str | Path | IO[str]) -> None:
        """Write one row per matched, missed, or unmatched arrival.

        A missed expected arrival and an unmatched detection each get their own
        row; no synthetic pairing is created to make the table rectangular.
        """
        fieldnames = (
            "microphone_index",
            "microphone_x_m",
            "microphone_y_m",
            "microphone_z_m",
            "status",
            "expected_path_index",
            "reflection_order",
            "reflection_sequence",
            "expected_time_s",
            "detected_sample_index",
            "detected_time_s",
            "detected_amplitude",
            "absolute_error_s",
        )
        should_close = not hasattr(destination, "write")
        stream = open(destination, "w", newline="", encoding="utf-8") if should_close else destination
        try:
            writer = csv.DictWriter(stream, fieldnames=fieldnames)
            writer.writeheader()
            for microphone in self.microphone_results:
                comparison = microphone.toa_comparison
                for match in comparison.matches:
                    writer.writerow(
                        _csv_row(
                            microphone,
                            "matched",
                            match.expected,
                            match.detected,
                            match.absolute_error_seconds,
                        )
                    )
                for expected in comparison.missed_expected:
                    writer.writerow(_csv_row(microphone, "missed_expected", expected, None, None))
                for detected in comparison.unmatched_detected:
                    writer.writerow(_csv_row(microphone, "unmatched_detected", None, detected, None))
        finally:
            if should_close:
                stream.close()


def match_arrivals(
    expected: Sequence[ExpectedArrival],
    detected: Sequence[DetectedArrivalTime],
    *,
    tolerance_seconds: float,
) -> TOAComparison:
    """Greedily match chronological arrivals one-to-one within a tolerance.

    Inputs are sorted by time with original order as a stable tie-breaker. The
    two-pointer matcher pairs the earliest expected and detected arrivals when
    their absolute difference is within tolerance; otherwise it advances the
    earlier one as missed/unmatched. Thus every item is used at most once and
    no out-of-tolerance match is forced. This deterministic chronological rule
    is appropriate for scalar TOAs; it does not infer path labels from geometry.
    """
    if not np.isfinite(tolerance_seconds) or tolerance_seconds < 0:
        raise ValueError("tolerance_seconds must be finite and non-negative")
    expected_ordered = tuple(sorted(expected, key=lambda item: item.time_of_flight_s))
    detected_ordered = tuple(sorted(detected, key=lambda item: item.time_seconds))
    matches: list[ArrivalMatch] = []
    missed: list[ExpectedArrival] = []
    unmatched: list[DetectedArrivalTime] = []
    expected_index = detected_index = 0
    while expected_index < len(expected_ordered) and detected_index < len(detected_ordered):
        exp = expected_ordered[expected_index]
        det = detected_ordered[detected_index]
        delta = det.time_seconds - exp.time_of_flight_s
        if abs(delta) <= tolerance_seconds:
            matches.append(ArrivalMatch(exp, det, abs(delta)))
            expected_index += 1
            detected_index += 1
        elif det.time_seconds < exp.time_of_flight_s:
            unmatched.append(det)
            detected_index += 1
        else:
            missed.append(exp)
            expected_index += 1
    missed.extend(expected_ordered[expected_index:])
    unmatched.extend(detected_ordered[detected_index:])
    match_tuple = tuple(matches)
    missed_tuple = tuple(missed)
    unmatched_tuple = tuple(unmatched)
    metrics = ArrivalMetrics.from_matches(match_tuple, len(missed_tuple), len(unmatched_tuple))
    return TOAComparison(
        expected_ordered,
        detected_ordered,
        match_tuple,
        missed_tuple,
        unmatched_tuple,
        float(tolerance_seconds),
        metrics,
    )


def run_experiment(
    room: ShoeboxRoom,
    source_position_m: Sequence[float],
    microphone_positions_m: Sequence[Sequence[float]],
    excitation: AudioSignal,
    *,
    max_reflection_order: int = 2,
    sampling_frequency: SamplingFrequency | None = None,
    snr_db: float | None = None,
    random_seed: int | None = None,
    impulse_placement: str = "linear",
    peak_window_length_samples: int | None = None,
    thr1: float = 0.9,
    thr2: float = 0.1,
    matching_tolerance_seconds: float | None = None,
) -> ExperimentResult:
    """Run forward simulation, existing matched filter/peak detector, and TOA evaluation."""
    if not isinstance(excitation, AudioSignal):
        raise TypeError("excitation must be an AudioSignal")
    fs = excitation.sampling_frequency if sampling_frequency is None else sampling_frequency
    if not isinstance(fs, SamplingFrequency):
        raise TypeError("sampling_frequency must be a SamplingFrequency or None")
    if fs.hertz != excitation.sampling_frequency.hertz:
        raise ValueError("sampling_frequency must match the excitation; resampling is not performed")
    window = max(1, int(np.floor(0.001 * fs.hertz + 0.5))) if peak_window_length_samples is None else peak_window_length_samples
    if isinstance(window, bool) or not isinstance(window, (int, np.integer)) or window < 1:
        raise ValueError("peak_window_length_samples must be a positive integer")
    tolerance = (1.0 / fs.hertz) if matching_tolerance_seconds is None else float(matching_tolerance_seconds)
    if not np.isfinite(tolerance) or tolerance < 0:
        raise ValueError("matching_tolerance_seconds must be finite and non-negative")

    source = room.validate_interior_position(source_position_m, name="source_position_m")
    microphones = tuple(
        room.validate_interior_position(position, name=f"microphone_positions_m[{index}]")
        for index, position in enumerate(microphone_positions_m)
    )
    if not microphones:
        raise ValueError("at least one microphone position is required")
    simulation = simulate_recordings(
        room,
        source,
        microphones,
        excitation,
        max_reflection_order=max_reflection_order,
        impulse_placement=impulse_placement,  # type: ignore[arg-type]
        snr_db=snr_db,
        random_seed=random_seed,
    )
    reference_energy = float(np.dot(excitation.samples, excitation.samples))
    if reference_energy <= np.finfo(np.float64).tiny:
        raise ValueError("excitation reference must have non-zero energy for matched filtering")

    mic_results: list[MicrophoneExperimentResult] = []
    for microphone_index, microphone_position in enumerate(microphones):
        recording_channel = AudioSignal(
            simulation.recordings.samples[:, microphone_index],
            fs,
            simulation.recordings.metadata,
        )
        filtered = matched_filter(recording_channel, excitation)
        detected = detect_peaks(
            filtered.correlation,
            fs,
            window_length_samples=int(window),
            thr1=thr1,
            thr2=thr2,
            start_time_seconds=float(filtered.lags_samples[0]) / fs.hertz,
        )
        rir_result = simulation.impulse_responses[microphone_index]
        expected = tuple(ExpectedArrival.from_path(index, path) for index, path in enumerate(rir_result.paths))
        comparison = match_arrivals(expected, detected, tolerance_seconds=tolerance)
        mic_results.append(
            MicrophoneExperimentResult(
                microphone_index,
                microphone_position,
                rir_result,
                filtered,
                comparison,
            )
        )

    waveform_hash = hashlib.sha256(np.asarray(excitation.samples, dtype="<f8").tobytes()).hexdigest()
    configuration = ExperimentConfiguration(
        room_dimensions_m=room.dimensions_m,
        speed_of_sound_m_s=room.speed_of_sound_m_s,
        wall_reflection_coefficients=tuple(
            (wall, float(room.wall_reflection_coefficients[wall])) for wall in sorted(room.wall_reflection_coefficients)
        ),
        source_position_m=source,
        microphone_positions_m=microphones,
        max_reflection_order=max_reflection_order,
        sampling_frequency_hz=fs.hertz,
        excitation_sample_count=excitation.sample_count,
        excitation_sha256=waveform_hash,
        requested_snr_db=snr_db,
        random_seed=random_seed,
        impulse_placement=impulse_placement,
        peak_window_length_samples=int(window),
        thr1=float(thr1),
        thr2=float(thr2),
        matching_tolerance_seconds=tolerance,
    )
    return ExperimentResult(configuration, excitation, simulation, tuple(mic_results))


def _detected_to_dict(item: DetectedArrivalTime) -> dict[str, int | float]:
    return {
        "sample_index": int(item.sample_index),
        "time_seconds": float(item.time_seconds),
        "amplitude": float(item.amplitude),
    }


def _path_to_dict(path: AcousticPath) -> dict[str, Any]:
    return {
        "reflection_order": path.reflection_order,
        "reflection_sequence": list(path.reflection_sequence),
        "image_source_position_m": list(path.image_source.position_m),
        "reflection_coefficient": path.image_source.reflection_coefficient,
        "distance_m": path.propagation_distance_m,
        "time_of_flight_s": path.time_of_flight_s,
    }


def _csv_row(
    microphone: MicrophoneExperimentResult,
    status: str,
    expected: ExpectedArrival | None,
    detected: DetectedArrivalTime | None,
    error: float | None,
) -> dict[str, Any]:
    position = microphone.microphone_position_m
    return {
        "microphone_index": microphone.microphone_index,
        "microphone_x_m": position[0],
        "microphone_y_m": position[1],
        "microphone_z_m": position[2],
        "status": status,
        "expected_path_index": "" if expected is None else expected.path_index,
        "reflection_order": "" if expected is None else expected.reflection_order,
        "reflection_sequence": "" if expected is None else ">".join(expected.reflection_sequence),
        "expected_time_s": "" if expected is None else expected.time_of_flight_s,
        "detected_sample_index": "" if detected is None else detected.sample_index,
        "detected_time_s": "" if detected is None else detected.time_seconds,
        "detected_amplitude": "" if detected is None else detected.amplitude,
        "absolute_error_s": "" if error is None else error,
    }
