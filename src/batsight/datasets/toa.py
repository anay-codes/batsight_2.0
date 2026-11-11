"""Forward direct-path TOA observation dataset; no localization is performed."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import IO, Any, Sequence

import numpy as np
from numpy.typing import NDArray

from batsight.simulation import ShoeboxRoom

FloatArray = NDArray[np.float64]
BoolArray = NDArray[np.bool_]


@dataclass(frozen=True, slots=True)
class ObservationMetadata:
    """Sampling-independent provenance and stochastic generation settings."""

    schema_version: str = "1.0"
    observation_model: str = "uncalibrated_direct_path_toa"
    noise_model: str = "independent_zero_mean_gaussian"
    missingness_model: str = "independent_bernoulli"
    timing_noise_std_seconds: float = 0.0
    missing_probability: float = 0.0
    random_seed: int | None = None
    length_unit: str = "metre"
    time_unit: str = "second"
    speed_unit: str = "metre_per_second"

    def __post_init__(self) -> None:
        if not np.isfinite(self.timing_noise_std_seconds) or self.timing_noise_std_seconds < 0:
            raise ValueError("metadata timing_noise_std_seconds must be finite and non-negative")
        if not np.isfinite(self.missing_probability) or not 0 <= self.missing_probability <= 1:
            raise ValueError("metadata missing_probability must be in [0, 1]")
        if self.random_seed is not None and (
            isinstance(self.random_seed, bool) or not isinstance(self.random_seed, (int, np.integer))
        ):
            raise TypeError("metadata random_seed must be an integer or None")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "observation_model": self.observation_model,
            "noise_model": self.noise_model,
            "missingness_model": self.missingness_model,
            "timing_noise_std_seconds": self.timing_noise_std_seconds,
            "missing_probability": self.missing_probability,
            "random_seed": self.random_seed,
            "length_unit": self.length_unit,
            "time_unit": self.time_unit,
            "speed_unit": self.speed_unit,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ObservationMetadata:
        return cls(**data)


@dataclass(frozen=True, slots=True)
class TOAObservationDataset:
    """Ground-truth positions and direct-path TOA observation components.

    Matrix convention is `[microphone_index, source_index]`. Missing
    measurements have `missing_mask=True` and `measured_toas_s=NaN`; the
    geometric distances, ideal TOAs, and generated timing-noise values remain
    available for analysis of the observation process.
    """

    room_dimensions_m: tuple[float, float, float]
    speed_of_sound_m_s: float
    source_positions_m: tuple[tuple[float, float, float], ...]
    microphone_positions_m: tuple[tuple[float, float, float], ...]
    source_emission_times_s: FloatArray
    microphone_clock_offsets_s: FloatArray
    true_distances_m: FloatArray
    propagation_times_s: FloatArray
    ideal_toas_s: FloatArray
    measured_toas_s: FloatArray
    missing_mask: BoolArray
    timing_noise_s: FloatArray
    metadata: ObservationMetadata

    def __post_init__(self) -> None:
        dimensions = _triple(self.room_dimensions_m, "room_dimensions_m")
        if any(value <= 0 for value in dimensions):
            raise ValueError("room_dimensions_m values must be greater than 0")
        if not np.isfinite(self.speed_of_sound_m_s) or self.speed_of_sound_m_s <= 0:
            raise ValueError("speed_of_sound_m_s must be finite and greater than 0")
        sources = tuple(_triple(point, "source position") for point in self.source_positions_m)
        microphones = tuple(_triple(point, "microphone position") for point in self.microphone_positions_m)
        if not sources or not microphones:
            raise ValueError("at least one source and one microphone are required")
        _validate_inside(sources, dimensions, "source")
        _validate_inside(microphones, dimensions, "microphone")

        source_count, microphone_count = len(sources), len(microphones)
        emission = _vector(self.source_emission_times_s, source_count, "source_emission_times_s")
        offsets = _vector(self.microphone_clock_offsets_s, microphone_count, "microphone_clock_offsets_s")
        shape = (microphone_count, source_count)
        distances = _matrix(self.true_distances_m, shape, "true_distances_m")
        propagation = _matrix(self.propagation_times_s, shape, "propagation_times_s")
        ideal = _matrix(self.ideal_toas_s, shape, "ideal_toas_s")
        noise = _matrix(self.timing_noise_s, shape, "timing_noise_s")
        missing = np.asarray(self.missing_mask, dtype=np.bool_)
        if missing.shape != shape:
            raise ValueError(f"missing_mask must have shape {shape}")
        measured = np.asarray(self.measured_toas_s, dtype=np.float64)
        if measured.shape != shape:
            raise ValueError(f"measured_toas_s must have shape {shape}")
        if not np.all(np.isfinite(measured[~missing])):
            raise ValueError("observed measured_toas_s values must be finite")
        if not np.all(np.isnan(measured[missing])):
            raise ValueError("missing measured_toas_s entries must be NaN")
        if np.any(distances < 0):
            raise ValueError("true source/microphone distances cannot be negative")

        expected_distances = _distance_matrix(sources, microphones)
        expected_propagation = expected_distances / self.speed_of_sound_m_s
        expected_ideal = (
            expected_propagation
            + emission[np.newaxis, :]
            + offsets[:, np.newaxis]
        )
        if not np.allclose(distances, expected_distances, rtol=1e-12, atol=1e-12):
            raise ValueError("true_distances_m does not agree with ground-truth positions")
        if not np.allclose(propagation, expected_propagation, rtol=1e-12, atol=1e-12):
            raise ValueError("propagation_times_s does not agree with distance / speed")
        if not np.allclose(ideal, expected_ideal, rtol=1e-12, atol=1e-12):
            raise ValueError("ideal_toas_s does not agree with the documented TOA equation")
        if not np.allclose(measured[~missing], (ideal + noise)[~missing], rtol=1e-12, atol=1e-12):
            raise ValueError("observed measured_toas_s values must equal ideal_toas_s + timing_noise_s")
        if not isinstance(self.metadata, ObservationMetadata):
            raise TypeError("metadata must be ObservationMetadata")

        for name, value in (
            ("room_dimensions_m", dimensions),
            ("source_positions_m", sources),
            ("microphone_positions_m", microphones),
        ):
            object.__setattr__(self, name, value)
        for name, array in (
            ("source_emission_times_s", emission),
            ("microphone_clock_offsets_s", offsets),
            ("true_distances_m", distances),
            ("propagation_times_s", propagation),
            ("ideal_toas_s", ideal),
            ("measured_toas_s", measured),
            ("missing_mask", missing),
            ("timing_noise_s", noise),
        ):
            array = np.array(array, copy=True)
            array.setflags(write=False)
            object.__setattr__(self, name, array)

    @property
    def microphone_count(self) -> int:
        return len(self.microphone_positions_m)

    @property
    def source_count(self) -> int:
        return len(self.source_positions_m)

    def to_dict(self) -> dict[str, Any]:
        """Return JSON-safe values; missing measured entries serialize as null."""
        measured: list[list[float | None]] = []
        for row, mask_row in zip(self.measured_toas_s, self.missing_mask):
            measured.append([None if bool(is_missing) else float(value) for value, is_missing in zip(row, mask_row)])
        return {
            "schema": "batsight.toa_observation_dataset",
            "metadata": self.metadata.to_dict(),
            "room": {
                "dimensions_m": list(self.room_dimensions_m),
                "speed_of_sound_m_s": float(self.speed_of_sound_m_s),
            },
            "axis_convention": "right-handed Cartesian xyz; room origin at minimum corner",
            "matrix_axis_order": "[microphone_index, source_index]",
            "source_positions_m": [list(point) for point in self.source_positions_m],
            "microphone_positions_m": [list(point) for point in self.microphone_positions_m],
            "source_emission_times_s": self.source_emission_times_s.tolist(),
            "microphone_clock_offsets_s": self.microphone_clock_offsets_s.tolist(),
            "true_distances_m": self.true_distances_m.tolist(),
            "propagation_times_s": self.propagation_times_s.tolist(),
            "ideal_toas_s": self.ideal_toas_s.tolist(),
            "measured_toas_s": measured,
            "missing_mask": self.missing_mask.tolist(),
            "timing_noise_s": self.timing_noise_s.tolist(),
        }

    def to_json(self, destination: str | Path | IO[str], *, indent: int = 2) -> None:
        """Serialize this dataset as JSON to a path or text stream."""
        should_close = not hasattr(destination, "write")
        stream = open(destination, "w", encoding="utf-8") if should_close else destination
        try:
            json.dump(self.to_dict(), stream, indent=indent, allow_nan=False)
        finally:
            if should_close:
                stream.close()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TOAObservationDataset:
        if data.get("schema") != "batsight.toa_observation_dataset":
            raise ValueError("unrecognized TOA dataset schema")
        measured_values = [
            [np.nan if value is None else float(value) for value in row]
            for row in data["measured_toas_s"]
        ]
        return cls(
            room_dimensions_m=tuple(data["room"]["dimensions_m"]),
            speed_of_sound_m_s=float(data["room"]["speed_of_sound_m_s"]),
            source_positions_m=tuple(tuple(row) for row in data["source_positions_m"]),
            microphone_positions_m=tuple(tuple(row) for row in data["microphone_positions_m"]),
            source_emission_times_s=np.asarray(data["source_emission_times_s"], dtype=np.float64),
            microphone_clock_offsets_s=np.asarray(data["microphone_clock_offsets_s"], dtype=np.float64),
            true_distances_m=np.asarray(data["true_distances_m"], dtype=np.float64),
            propagation_times_s=np.asarray(data["propagation_times_s"], dtype=np.float64),
            ideal_toas_s=np.asarray(data["ideal_toas_s"], dtype=np.float64),
            measured_toas_s=np.asarray(measured_values, dtype=np.float64),
            missing_mask=np.asarray(data["missing_mask"], dtype=np.bool_),
            timing_noise_s=np.asarray(data["timing_noise_s"], dtype=np.float64),
            metadata=ObservationMetadata.from_dict(data["metadata"]),
        )

    @classmethod
    def from_json(cls, source: str | Path | IO[str]) -> TOAObservationDataset:
        """Load a dataset from a JSON path or text stream."""
        should_close = not hasattr(source, "read")
        stream = open(source, "r", encoding="utf-8") if should_close else source
        try:
            return cls.from_dict(json.load(stream))
        finally:
            if should_close:
                stream.close()


def generate_toa_observations(
    room: ShoeboxRoom,
    source_positions_m: Sequence[Sequence[float]],
    microphone_positions_m: Sequence[Sequence[float]],
    source_emission_times_s: Sequence[float],
    microphone_clock_offsets_s: Sequence[float],
    *,
    timing_noise_std_seconds: float = 0.0,
    missing_probability: float = 0.0,
    random_seed: int | None = None,
    missing_mask: Sequence[Sequence[bool]] | None = None,
) -> TOAObservationDataset:
    """Generate uncalibrated direct-path TOA observations from known geometry.

    Noise and missingness use a single seeded NumPy generator. If an explicit
    `missing_mask` is supplied, random missingness must remain at its default
    probability of zero. The explicit mask is copied and used as given.
    """
    if not isinstance(room, ShoeboxRoom):
        raise TypeError("room must be a ShoeboxRoom")
    if not np.isfinite(timing_noise_std_seconds) or timing_noise_std_seconds < 0:
        raise ValueError("timing_noise_std_seconds must be finite and non-negative")
    if not np.isfinite(missing_probability) or not 0 <= missing_probability <= 1:
        raise ValueError("missing_probability must be finite and in [0, 1]")
    if random_seed is not None and (isinstance(random_seed, bool) or not isinstance(random_seed, (int, np.integer))):
        raise TypeError("random_seed must be an integer or None")
    if missing_mask is not None and missing_probability != 0:
        raise ValueError("provide either explicit missing_mask or non-zero missing_probability, not both")

    sources = tuple(room.validate_interior_position(point, name=f"source_positions_m[{i}]") for i, point in enumerate(source_positions_m))
    microphones = tuple(
        room.validate_interior_position(point, name=f"microphone_positions_m[{i}]")
        for i, point in enumerate(microphone_positions_m)
    )
    if not sources or not microphones:
        raise ValueError("at least one source and one microphone are required")
    emissions = _vector(source_emission_times_s, len(sources), "source_emission_times_s")
    offsets = _vector(microphone_clock_offsets_s, len(microphones), "microphone_clock_offsets_s")
    distances = _distance_matrix(sources, microphones)
    propagation = distances / room.speed_of_sound_m_s
    ideal = propagation + emissions[np.newaxis, :] + offsets[:, np.newaxis]

    rng = np.random.default_rng(random_seed)
    noise = rng.normal(0.0, timing_noise_std_seconds, size=ideal.shape)
    measured = ideal + noise
    if missing_mask is not None:
        mask = np.asarray(missing_mask, dtype=np.bool_)
        if mask.shape != ideal.shape:
            raise ValueError(f"missing_mask must have shape {ideal.shape}")
    elif missing_probability == 0:
        mask = np.zeros(ideal.shape, dtype=np.bool_)
    else:
        mask = rng.random(ideal.shape) < missing_probability
    measured[mask] = np.nan

    metadata = ObservationMetadata(
        timing_noise_std_seconds=float(timing_noise_std_seconds),
        missing_probability=float(missing_probability),
        random_seed=None if random_seed is None else int(random_seed),
    )
    return TOAObservationDataset(
        room_dimensions_m=room.dimensions_m,
        speed_of_sound_m_s=room.speed_of_sound_m_s,
        source_positions_m=sources,
        microphone_positions_m=microphones,
        source_emission_times_s=emissions,
        microphone_clock_offsets_s=offsets,
        true_distances_m=distances,
        propagation_times_s=propagation,
        ideal_toas_s=ideal,
        measured_toas_s=measured,
        missing_mask=mask,
        timing_noise_s=noise,
        metadata=metadata,
    )


def _triple(values: Sequence[float], name: str) -> tuple[float, float, float]:
    try:
        output = tuple(float(value) for value in values)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must contain exactly three finite values") from exc
    if len(output) != 3 or not all(np.isfinite(value) for value in output):
        raise ValueError(f"{name} must contain exactly three finite values")
    return output  # type: ignore[return-value]


def _validate_inside(
    points: Sequence[tuple[float, float, float]],
    dimensions: tuple[float, float, float],
    name: str,
) -> None:
    for index, point in enumerate(points):
        if any(value <= 0 or value >= limit for value, limit in zip(point, dimensions)):
            raise ValueError(f"{name}_positions_m[{index}] must be strictly inside the room")


def _vector(values: Sequence[float], expected_size: int, name: str) -> FloatArray:
    output = np.asarray(values, dtype=np.float64)
    if output.shape != (expected_size,):
        raise ValueError(f"{name} must have shape ({expected_size},)")
    if not np.all(np.isfinite(output)):
        raise ValueError(f"{name} values must be finite seconds")
    return np.array(output, copy=True)


def _matrix(values: NDArray[Any], expected_shape: tuple[int, int], name: str) -> FloatArray:
    output = np.asarray(values, dtype=np.float64)
    if output.shape != expected_shape:
        raise ValueError(f"{name} must have shape {expected_shape}")
    if not np.all(np.isfinite(output)):
        raise ValueError(f"{name} values must be finite")
    return np.array(output, copy=True)


def _distance_matrix(
    sources: Sequence[tuple[float, float, float]],
    microphones: Sequence[tuple[float, float, float]],
) -> FloatArray:
    source_array = np.asarray(sources, dtype=np.float64)
    microphone_array = np.asarray(microphones, dtype=np.float64)
    return np.linalg.norm(microphone_array[:, np.newaxis, :] - source_array[np.newaxis, :, :], axis=2)
