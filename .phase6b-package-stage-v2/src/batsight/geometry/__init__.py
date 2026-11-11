"""Geometry views and validation utilities."""

from .shoebox import (
    PointLocation,
    ShoeboxWallPlane,
    classify_room_point,
    require_room_interior,
    shoebox_wall_planes,
)

__all__ = [
    "PointLocation",
    "ShoeboxWallPlane",
    "classify_room_point",
    "require_room_interior",
    "shoebox_wall_planes",
]
