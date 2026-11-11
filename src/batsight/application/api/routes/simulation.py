"""Forward-only geometry path previews for editable shoebox scenes."""

from __future__ import annotations

import numpy as np
from fastapi import APIRouter, HTTPException

from batsight.application.api.schemas.contracts import SimulationPathsRequest, SimulationPathsResponse
from batsight.simulation.shoebox import WALLS, ShoeboxRoom, predict_acoustic_paths

router = APIRouter(prefix="/api/simulation", tags=["simulation"])

_WALL_AXIS_SIDE = {
    "x_min": (0, "min"), "x_max": (0, "max"),
    "y_min": (1, "min"), "y_max": (1, "max"),
    "z_min": (2, "min"), "z_max": (2, "max"),
}


def _first_order_bounce(room: ShoeboxRoom, image: tuple[float, float, float],
                        microphone: tuple[float, float, float], wall: str):
    axis, side = _WALL_AXIS_SIDE[wall]
    plane = 0.0 if side == "min" else room.dimensions_m[axis]
    denominator = microphone[axis] - image[axis]
    if abs(denominator) <= np.finfo(float).eps:
        return None, False
    fraction = (plane - image[axis]) / denominator
    if fraction < 0.0 or fraction > 1.0:
        return None, False
    point = tuple(float(image[i] + fraction * (microphone[i] - image[i])) for i in range(3))
    finite = all(0.0 <= point[i] <= room.dimensions_m[i] for i in range(3))
    return (point if finite else None), bool(finite)


@router.post("/paths", response_model=SimulationPathsResponse,
             summary="Preview simulated image-source paths for an editable shoebox")
def preview_paths(payload: SimulationPathsRequest):
    """Use the existing shoebox predictor; never treats scene data as measurements."""
    if set(payload.wall_reflection_coefficients) - set(WALLS):
        raise HTTPException(422, f"wall coefficient keys must be among {WALLS}")
    try:
        room = ShoeboxRoom(
            payload.room_dimensions_m,
            payload.speed_of_sound_m_s,
            payload.wall_reflection_coefficients,
        )
        room.validate_interior_position(payload.source_position_m, name="source_position_m")
        output = []
        for index, microphone in enumerate(payload.microphone_positions_m):
            predicted = predict_acoustic_paths(
                room,
                payload.source_position_m,
                microphone,
                max_reflection_order=payload.max_reflection_order,
            )
            paths = []
            for path in predicted:
                wall = path.reflection_sequence[0] if path.reflection_order == 1 else None
                bounce, bounce_valid = (
                    _first_order_bounce(room, path.image_source.position_m, microphone, wall)
                    if wall is not None else (None, None)
                )
                paths.append({
                    "reflection_order": path.reflection_order,
                    "reflection_sequence": list(path.reflection_sequence),
                    "image_source_position_m": path.image_source.position_m,
                    "path_length_m": path.propagation_distance_m,
                    "time_of_flight_s": path.time_of_flight_s,
                    "reflection_coefficient": path.image_source.reflection_coefficient,
                    "reflection_point_m": bounce,
                    "finite_wall_bounce_valid": bounce_valid,
                })
            output.append({
                "microphone_index": index,
                "microphone_position_m": microphone,
                "paths": paths,
            })
    except (TypeError, ValueError) as exc:
        raise HTTPException(422, str(exc)) from exc
    return {
        "room_dimensions_m": room.dimensions_m,
        "source_position_m": payload.source_position_m,
        "speed_of_sound_m_s": room.speed_of_sound_m_s,
        "max_reflection_order": payload.max_reflection_order,
        "microphone_paths": output,
        "provenance": "visualization_only_simulated_prediction_from_editable_scene",
        "model_description": (
            "Existing BatSight ideal shoebox image-source model; geometric prediction only, "
            "not measured or estimated room data. First-order bounce points are finite-face checked. "
            "Second-order operator sequences are virtual image-source paths and are not validated bounce trajectories."
        ),
    }
