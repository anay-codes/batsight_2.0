"""Forward shoebox-room impulse-response simulation via image sources.

This implements a small geometric-acoustics model, not a complete room
acoustics solver or an inverse room reconstruction method.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal, Mapping, Sequence

import numpy as np
from numpy.typing import NDArray
from scipy.signal import fftconvolve

from batsight.signals.models import AudioSignal, RecordingMetadata, SamplingFrequency

Position3D = tuple[float, float, float]
FloatArray = NDArray[np.float64]
ImpulsePlacement = Literal["linear", "nearest"]

WALLS = (
    "x_min",
    "x_max",
    "y_min",
    "y_max",
    "z_min",
    "z_max",
)
_WALL_AXIS_SIDE = {
    "x_min": (0, "min"),
    "x_max": (0, "max"),
    "y_min": (1, "min"),
    "y_max": (1, "max"),
    "z_min": (2, "min"),
    "z_max": (2, "max"),
}


def _position(value: Sequence[float], name: str) -> Position3D:
    try:
        point = tuple(float(coordinate) for coordinate in value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must contain exactly three finite coordinates") from exc
    if len(point) != 3 or not all(np.isfinite(coordinate) for coordinate in point):
        raise ValueError(f"{name} must contain exactly three finite coordinates")
    return point  # type: ignore[return-value]


@dataclass(frozen=True, slots=True)
class ShoeboxRoom:
    """Axis-aligned convex rectangular room with origin at its minimum corner.

    Coordinates are right-handed Cartesian axes x, y, z with the room interior
    `0 < x < Lx`, `0 < y < Ly`, and `0 < z < Lz`. Dimensions are in metres.
    Wall coefficients are real pressure-amplitude reflection coefficients
    between -1 and 1; omitted walls default to 0.8.
    """

    dimensions_m: Position3D
    speed_of_sound_m_s: float = 343.0
    wall_reflection_coefficients: Mapping[str, float] | None = None

    def __post_init__(self) -> None:
        dimensions = _position(self.dimensions_m, "dimensions_m")
        if any(dimension <= 0 for dimension in dimensions):
            raise ValueError("all room dimensions must be greater than 0 metres")
        if not np.isfinite(self.speed_of_sound_m_s) or self.speed_of_sound_m_s <= 0:
            raise ValueError("speed_of_sound_m_s must be finite and greater than 0")
        coefficients = dict(self.wall_reflection_coefficients or {})
        unknown = set(coefficients) - set(WALLS)
        if unknown:
            raise ValueError(f"unknown wall identifiers: {sorted(unknown)}")
        normalized: dict[str, float] = {}
        for wall in WALLS:
            value = float(coefficients.get(wall, 0.8))
            if not np.isfinite(value) or abs(value) > 1.0:
                raise ValueError("wall reflection coefficients must be finite and in [-1, 1]")
            normalized[wall] = value
        object.__setattr__(self, "dimensions_m", dimensions)
        object.__setattr__(self, "wall_reflection_coefficients", MappingProxyType(normalized))

    def validate_interior_position(self, position: Sequence[float], *, name: str = "position") -> Position3D:
        """Return normalized point or reject points on/outside any wall."""
        point = _position(position, name)
        if any(coordinate <= 0.0 or coordinate >= dimension for coordinate, dimension in zip(point, self.dimensions_m)):
            raise ValueError(f"{name} must be strictly inside the room")
        return point


@dataclass(frozen=True, slots=True)
class ImageSource:
    """A direct or reflected image with its construction labels."""

    position_m: Position3D
    reflection_order: int
    reflection_sequence: tuple[str, ...]
    reflection_coefficient: float


@dataclass(frozen=True, slots=True)
class AcousticPath:
    """Image-source path timing and amplitude for one microphone."""

    image_source: ImageSource
    propagation_distance_m: float
    time_of_flight_s: float

    @property
    def reflection_order(self) -> int:
        return self.image_source.reflection_order

    @property
    def reflection_sequence(self) -> tuple[str, ...]:
        return self.image_source.reflection_sequence


@dataclass(frozen=True, slots=True)
class RIRSimulation:
    """Discrete RIR plus geometric path records used to build it."""

    impulse_response: AudioSignal
    paths: tuple[AcousticPath, ...]
    impulse_placement: ImpulsePlacement


@dataclass(frozen=True, slots=True)
class SimulatedRecordings:
    """Multichannel input-waveform recordings and per-channel RIR details."""

    recordings: AudioSignal
    impulse_responses: tuple[RIRSimulation, ...]
    requested_snr_db: float | None


def _reflect_point(room: ShoeboxRoom, point: Position3D, wall: str) -> Position3D:
    axis, side = _WALL_AXIS_SIDE[wall]
    plane_coordinate = 0.0 if side == "min" else room.dimensions_m[axis]
    reflected = list(point)
    reflected[axis] = 2.0 * plane_coordinate - reflected[axis]
    return tuple(reflected)  # type: ignore[return-value]


def image_sources(
    room: ShoeboxRoom,
    source_position_m: Sequence[float],
    *,
    max_reflection_order: int = 2,
) -> tuple[ImageSource, ...]:
    """Enumerate direct, first-, and optional second-order image sources.

    Reflection operations are applied in tuple order, following the recursive
    image construction `IM(IM(source, wall_1), wall_2)`. Only different walls
    are paired at order two, matching the paper's Eq. 3. Because perpendicular
    mirror operators commute and can produce identical image coordinates, such
    coordinate-identical second-order images are collapsed; the
    lexicographically first wall-operator sequence is retained. Opposite walls
    produce different images and remain distinct. The tuple is deterministic:
    direct first, then single walls in `WALLS` order, then unique pairs in
    lexicographic product order.

    The sequence identifies image-construction operators, not a separately
    validated physical bounce trajectory. All image distances are valid path
    lengths in the ideal shoebox image-source model.
    """
    if not isinstance(room, ShoeboxRoom):
        raise TypeError("room must be a ShoeboxRoom")
    source = room.validate_interior_position(source_position_m, name="source_position_m")
    if (
        isinstance(max_reflection_order, bool)
        or not isinstance(max_reflection_order, (int, np.integer))
        or max_reflection_order not in (0, 1, 2)
    ):
        raise ValueError("max_reflection_order must be 0, 1, or 2")
    coeffs = room.wall_reflection_coefficients
    images: list[ImageSource] = [ImageSource(source, 0, (), 1.0)]
    if max_reflection_order == 0:
        return tuple(images)

    first_order: list[ImageSource] = []
    for wall in WALLS:
        image = _reflect_point(room, source, wall)
        first_order.append(
            ImageSource(image, 1, (wall,), float(coeffs[wall]))
        )
    images.extend(first_order)
    if max_reflection_order == 1:
        return tuple(images)

    seen_coordinates = {item.position_m for item in images}
    for first_wall in WALLS:
        first_image = _reflect_point(room, source, first_wall)
        for second_wall in WALLS:
            if second_wall == first_wall:
                continue
            position = _reflect_point(room, first_image, second_wall)
            key = position
            if key in seen_coordinates:
                continue
            seen_coordinates.add(key)
            images.append(
                ImageSource(
                    position,
                    2,
                    (first_wall, second_wall),
                    float(coeffs[first_wall] * coeffs[second_wall]),
                )
            )
    return tuple(images)


def _paths_for_microphone(
    room: ShoeboxRoom,
    images: tuple[ImageSource, ...],
    microphone_position_m: Position3D,
) -> tuple[AcousticPath, ...]:
    result: list[AcousticPath] = []
    microphone = np.asarray(microphone_position_m, dtype=np.float64)
    for image in images:
        distance = float(np.linalg.norm(np.asarray(image.position_m) - microphone))
        if distance <= np.finfo(np.float64).eps:
            raise ValueError("source and microphone/image source cannot coincide; 1/r spreading is singular")
        result.append(AcousticPath(image, distance, distance / room.speed_of_sound_m_s))
    return tuple(result)


def predict_acoustic_paths(
    room: ShoeboxRoom,
    source_position_m: Sequence[float],
    microphone_position_m: Sequence[float],
    *,
    max_reflection_order: int = 2,
) -> tuple[AcousticPath, ...]:
    """Predict continuous geometric paths without sampling or adding noise.

    This is the shared forward path calculation used by both RIR synthesis
    and calibrated TOA prediction. Ordering and wall labels follow
    :func:`image_sources`; no waveform, impulse placement, or noise is involved.
    """
    if not isinstance(room, ShoeboxRoom):
        raise TypeError("room must be a ShoeboxRoom")
    source = room.validate_interior_position(source_position_m, name="source_position_m")
    microphone = room.validate_interior_position(microphone_position_m, name="microphone_position_m")
    images = image_sources(room, source, max_reflection_order=max_reflection_order)
    return _paths_for_microphone(room, images, microphone)


def _deposit_impulse(
    output: FloatArray,
    sample_position: float,
    amplitude: float,
    placement: ImpulsePlacement,
) -> None:
    if placement == "nearest":
        output[int(np.floor(sample_position + 0.5))] += amplitude
        return
    lower = int(np.floor(sample_position))
    fraction = sample_position - lower
    output[lower] += amplitude * (1.0 - fraction)
    if fraction > 0.0:
        output[lower + 1] += amplitude * fraction


def generate_rir(
    room: ShoeboxRoom,
    source_position_m: Sequence[float],
    microphone_position_m: Sequence[float],
    sampling_frequency: SamplingFrequency,
    *,
    max_reflection_order: int = 2,
    impulse_placement: ImpulsePlacement = "linear",
) -> RIRSimulation:
    """Generate a sparse discrete RIR for one source/microphone pair.

    Each path has amplitude `reflection_coefficient / distance_m`. The `1/r`
    factor is the chosen frequency-independent free-field geometric spreading
    convention; reflection attenuation is the product of the real pressure
    coefficients for that path and is applied separately. Source strength and
    microphone sensitivity are unity, so values are normalized relative
    amplitudes (with a 1/m spreading factor), not calibrated pascals.

    `impulse_placement="linear"` (default) splits fractional delays between
    adjacent samples, preserving each path's discrete impulse sum and temporal
    first moment. It introduces a triangular interpolation response and is not
    an exact bandlimited fractional-delay filter. `"nearest"` deposits at the
    nearest sample, with half-sample ties rounded upward; its timing error is at
    most `0.5 / fs` seconds. RIR length extends through the final deposition
    sample under the selected convention.
    """
    if not isinstance(sampling_frequency, SamplingFrequency):
        raise TypeError("sampling_frequency must be a SamplingFrequency")
    if impulse_placement not in ("linear", "nearest"):
        raise ValueError("impulse_placement must be 'linear' or 'nearest'")
    paths = predict_acoustic_paths(
        room, source_position_m, microphone_position_m, max_reflection_order=max_reflection_order
    )
    sample_positions = [path.time_of_flight_s * sampling_frequency.hertz for path in paths]
    last_sample = max(
        int(np.ceil(position)) if impulse_placement == "linear" else int(np.floor(position + 0.5))
        for position in sample_positions
    )
    rir = np.zeros(last_sample + 1, dtype=np.float64)
    for path, sample_position in zip(paths, sample_positions):
        geometric_attenuation = 1.0 / path.propagation_distance_m
        amplitude = path.image_source.reflection_coefficient * geometric_attenuation
        _deposit_impulse(rir, sample_position, amplitude, impulse_placement)
    return RIRSimulation(AudioSignal(rir, sampling_frequency), paths, impulse_placement)


def simulate_recordings(
    room: ShoeboxRoom,
    source_position_m: Sequence[float],
    microphone_positions_m: Sequence[Sequence[float]],
    excitation: AudioSignal,
    *,
    max_reflection_order: int = 2,
    impulse_placement: ImpulsePlacement = "linear",
    snr_db: float | None = None,
    random_seed: int | None = None,
) -> SimulatedRecordings:
    """Convolve a known mono input with RIRs for multiple mic positions.

    When enabled, zero-mean Gaussian noise is added independently per channel.
    Its variance is set from the noiseless channel's mean-square power and the
    requested SNR. A supplied `random_seed` makes the generated noise
    deterministic. If a channel is silent, its added noise is also zero.
    """
    if not isinstance(excitation, AudioSignal):
        raise TypeError("excitation must be an AudioSignal")
    if excitation.channel_count != 1:
        raise ValueError("excitation must be mono")
    if not isinstance(room, ShoeboxRoom):
        raise TypeError("room must be a ShoeboxRoom")
    if snr_db is not None and not np.isfinite(snr_db):
        raise ValueError("snr_db must be finite or None")
    if random_seed is not None and (isinstance(random_seed, bool) or not isinstance(random_seed, (int, np.integer))):
        raise TypeError("random_seed must be an integer or None")
    microphones = tuple(
        room.validate_interior_position(position, name=f"microphone_positions_m[{index}]")
        for index, position in enumerate(microphone_positions_m)
    )
    if not microphones:
        raise ValueError("at least one microphone position is required")
    source = room.validate_interior_position(source_position_m, name="source_position_m")
    responses = tuple(
        generate_rir(
            room,
            source,
            microphone,
            excitation.sampling_frequency,
            max_reflection_order=max_reflection_order,
            impulse_placement=impulse_placement,
        )
        for microphone in microphones
    )
    rendered = [
        fftconvolve(excitation.samples, response.impulse_response.samples, mode="full")
        for response in responses
    ]
    frame_count = max(values.size for values in rendered)
    channels = np.zeros((frame_count, len(rendered)), dtype=np.float64)
    for channel, values in enumerate(rendered):
        channels[: values.size, channel] = values

    if snr_db is not None:
        rng = np.random.default_rng(random_seed)
        noise = np.zeros_like(channels)
        target_noise_to_signal = 10.0 ** (-float(snr_db) / 10.0)
        for channel in range(channels.shape[1]):
            signal_power = float(np.mean(channels[:, channel] ** 2))
            if signal_power > 0.0:
                noise_std = float(np.sqrt(signal_power * target_noise_to_signal))
                noise[:, channel] = rng.normal(0.0, noise_std, frame_count)
        channels += noise

    recording = AudioSignal(
        channels,
        excitation.sampling_frequency,
        RecordingMetadata(
            notes="Synthetic shoebox-room convolution; no reconstruction performed.",
            attributes={
                "simulator": "batsight.image_source.shoebox",
                "max_reflection_order": max_reflection_order,
                "microphone_count": len(microphones),
                "snr_db": "none" if snr_db is None else float(snr_db),
            },
        ),
    )
    return SimulatedRecordings(recording, responses, snr_db)
