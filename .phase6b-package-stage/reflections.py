"""Deterministic first-order shoebox TOA prediction for calibrated inputs."""

from __future__ import annotations

from dataclasses import dataclass
import numpy as np

from batsight.datasets.calibrated import CalibratedShoeboxInputs
from batsight.geometry.shoebox import WallIdentifier, require_room_interior
from batsight.simulation.shoebox import WALLS, ShoeboxRoom, predict_acoustic_paths

Position3D = tuple[float, float, float]


@dataclass(frozen=True, slots=True)
class PredictedArrival:
    """One noiseless direct or first-order predicted arrival."""

    microphone_id: str
    event_id: str
    source_id: str
    reflection_order: int
    wall_id: WallIdentifier | None
    image_source_position_m: Position3D
    propagation_distance_m: float
    propagation_time_s: float
    emission_time_s: float
    arrival_time_s: float

    def __post_init__(self) -> None:
        identifiers = (self.microphone_id, self.event_id, self.source_id)
        if not all(isinstance(value, str) and value.strip() for value in identifiers):
            raise ValueError("predicted arrival identifiers must be non-empty")
        if self.reflection_order not in (0, 1):
            raise ValueError("first-order predictor result must have order 0 or 1")
        if (self.reflection_order == 0) != (self.wall_id is None):
            raise ValueError("direct paths have no wall_id; first-order paths require one")
        if self.wall_id is not None and self.wall_id not in WALLS:
            raise ValueError(f"wall_id must be one of {WALLS}")
        if len(self.image_source_position_m) != 3 or not all(
            np.isfinite(value) for value in self.image_source_position_m
        ):
            raise ValueError("image source coordinates must be three finite metres")
        if not all(
            np.isfinite(value)
            for value in (
                self.propagation_distance_m,
                self.propagation_time_s,
                self.emission_time_s,
                self.arrival_time_s,
            )
        ):
            raise ValueError("predicted arrival values must be finite")
        if self.propagation_distance_m <= 0.0 or self.propagation_time_s <= 0.0:
            raise ValueError("propagation distance and time must be positive")
        if self.arrival_time_s != self.emission_time_s + self.propagation_time_s:
            raise ValueError("arrival_time_s must equal emission_time_s + propagation_time_s")


def predict_first_order_arrivals(
    inputs: CalibratedShoeboxInputs,
    candidate_room: ShoeboxRoom,
    *,
    boundary_tolerance_m: float = 0.0,
) -> tuple[PredictedArrival, ...]:
    """Predict direct and all six labeled first-order TOAs for each pair.

    ``candidate_room`` supplies the current candidate dimensions and known
    sound speed; room dimensions are not part of ``inputs``. The same
    :func:`predict_acoustic_paths` image-source implementation used by RIR
    synthesis is reused. Output order is event, microphone, direct path, then
    the simulator's canonical ``WALLS`` order. This function is geometric: it
    adds neither measurement noise nor detection/matching decisions.

    Arrival times are ``known emission time + propagation time``. No clock
    offset is introduced because the calibrated profile requires synchronized
    channels.
    """
    if not isinstance(inputs, CalibratedShoeboxInputs):
        raise TypeError("inputs must be CalibratedShoeboxInputs")
    if not isinstance(candidate_room, ShoeboxRoom):
        raise TypeError("candidate_room must be a ShoeboxRoom")
    if candidate_room.speed_of_sound_m_s != inputs.speed_of_sound_m_s:
        raise ValueError("candidate room and calibrated inputs must use the same known sound speed")
    if not np.isfinite(boundary_tolerance_m) or boundary_tolerance_m < 0.0:
        raise ValueError("boundary_tolerance_m must be finite and non-negative")

    microphones = inputs.microphone_array.microphones
    events = inputs.source_events
    for microphone in microphones:
        require_room_interior(
            candidate_room,
            microphone.position_m,
            name=f"microphone {microphone.microphone_id}",
            minimum_clearance_m=boundary_tolerance_m,
        )
    for event in events:
        require_room_interior(
            candidate_room,
            event.position_m,
            name=f"source event {event.event_id}",
            minimum_clearance_m=boundary_tolerance_m,
        )

    predictions: list[PredictedArrival] = []
    for event in events:
        for microphone in microphones:
            paths = predict_acoustic_paths(
                candidate_room,
                event.position_m,
                microphone.position_m,
                max_reflection_order=1,
            )
            for path in paths:
                wall_id = path.reflection_sequence[0] if path.reflection_order == 1 else None
                arrival = event.emission_time_s + path.time_of_flight_s
                predictions.append(
                    PredictedArrival(
                        microphone_id=microphone.microphone_id,
                        event_id=event.event_id,
                        source_id=event.source_id,
                        reflection_order=path.reflection_order,
                        wall_id=wall_id,
                        image_source_position_m=path.image_source.position_m,
                        propagation_distance_m=path.propagation_distance_m,
                        propagation_time_s=path.time_of_flight_s,
                        emission_time_s=event.emission_time_s,
                        arrival_time_s=arrival,
                    )
                )
    return tuple(predictions)
