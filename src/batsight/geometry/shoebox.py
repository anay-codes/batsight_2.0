"""Geometry helpers for the existing axis-aligned :class:`ShoeboxRoom`.

The simulator's room type remains the canonical dimension/room model. This
module adds wall-plane and boundary-classification views without defining a
second room or image-source implementation.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Sequence

import numpy as np

from batsight.simulation.shoebox import ShoeboxRoom

Position3D = tuple[float, float, float]
WallIdentifier = str


class PointLocation(str, Enum):
    """Position of a point relative to a shoebox's closed boundary."""

    INTERIOR = "interior"
    NEAR_BOUNDARY = "near_boundary"
    ON_BOUNDARY = "on_boundary"
    OUTSIDE = "outside"


@dataclass(frozen=True, slots=True)
class ShoeboxWallPlane:
    """One outward-oriented plane in the inequality ``n dot x <= offset``.

    The normal is dimensionless and the offset is metres. Coordinates use the
    room-local, right-handed xyz frame whose origin is the minimum corner.
    """

    wall_id: WallIdentifier
    outward_normal: Position3D
    offset_m: float

    def signed_outside_distance_m(self, point_m: Sequence[float]) -> float:
        """Return ``n dot point - offset``; positive values lie outside."""
        point = _point(point_m)
        return float(np.dot(self.outward_normal, point) - self.offset_m)


def shoebox_wall_planes(room: ShoeboxRoom) -> tuple[ShoeboxWallPlane, ...]:
    """Return the six named, deterministic shoebox face planes.

    For a point inside the box, every returned signed outside distance is
    non-positive. Paired faces have opposite outward normals.
    """
    if not isinstance(room, ShoeboxRoom):
        raise TypeError("room must be a ShoeboxRoom")
    lx, ly, lz = room.dimensions_m
    return (
        ShoeboxWallPlane("x_min", (-1.0, 0.0, 0.0), 0.0),
        ShoeboxWallPlane("x_max", (1.0, 0.0, 0.0), lx),
        ShoeboxWallPlane("y_min", (0.0, -1.0, 0.0), 0.0),
        ShoeboxWallPlane("y_max", (0.0, 1.0, 0.0), ly),
        ShoeboxWallPlane("z_min", (0.0, 0.0, -1.0), 0.0),
        ShoeboxWallPlane("z_max", (0.0, 0.0, 1.0), lz),
    )


def classify_room_point(
    room: ShoeboxRoom,
    point_m: Sequence[float],
    *,
    boundary_tolerance_m: float = 1e-9,
) -> PointLocation:
    """Classify a finite room-frame point using a metric boundary tolerance.

    Points strictly outside the closed box are ``OUTSIDE``. Exact wall points
    are ``ON_BOUNDARY``. Interior points with minimum wall clearance no greater
    than ``boundary_tolerance_m`` are ``NEAR_BOUNDARY``. Remaining points are
    ``INTERIOR``. The tolerance is a classification/validation margin; it does
    not move the modeled walls.
    """
    if not isinstance(room, ShoeboxRoom):
        raise TypeError("room must be a ShoeboxRoom")
    if not np.isfinite(boundary_tolerance_m) or boundary_tolerance_m < 0.0:
        raise ValueError("boundary_tolerance_m must be finite and non-negative")
    point = _point(point_m)
    dimensions = room.dimensions_m
    if any(value < 0.0 or value > limit for value, limit in zip(point, dimensions)):
        return PointLocation.OUTSIDE
    clearances = (*point, *(limit - value for value, limit in zip(point, dimensions)))
    clearance = min(clearances)
    if clearance == 0.0:
        return PointLocation.ON_BOUNDARY
    if clearance <= boundary_tolerance_m:
        return PointLocation.NEAR_BOUNDARY
    return PointLocation.INTERIOR


def require_room_interior(
    room: ShoeboxRoom,
    point_m: Sequence[float],
    *,
    name: str = "position",
    minimum_clearance_m: float = 0.0,
) -> Position3D:
    """Normalize a point or reject it unless it is safely inside the box.

    ``minimum_clearance_m=0`` accepts any strictly interior point, matching
    ``ShoeboxRoom.validate_interior_position``. A positive value rejects
    interior points at or closer than that distance from any face.
    """
    if not np.isfinite(minimum_clearance_m) or minimum_clearance_m < 0.0:
        raise ValueError("minimum_clearance_m must be finite and non-negative")
    point = _point(point_m, name)
    location = classify_room_point(
        room, point, boundary_tolerance_m=minimum_clearance_m
    )
    if location is not PointLocation.INTERIOR:
        if location is PointLocation.OUTSIDE:
            raise ValueError(f"{name} must lie inside the room")
        raise ValueError(f"{name} must be farther than {minimum_clearance_m:g} m from every wall")
    return room.validate_interior_position(point, name=name)


def _point(values: Sequence[float], name: str = "point_m") -> Position3D:
    try:
        point = tuple(float(value) for value in values)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must contain exactly three finite coordinates") from exc
    if len(point) != 3 or not all(np.isfinite(value) for value in point):
        raise ValueError(f"{name} must contain exactly three finite coordinates")
    return point  # type: ignore[return-value]
