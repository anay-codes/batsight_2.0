"""Tests for the reusable shoebox wall-plane and boundary view."""

import numpy as np
import pytest

from batsight.geometry import (
    PointLocation,
    classify_room_point,
    require_room_interior,
    shoebox_wall_planes,
)
from batsight.simulation import ShoeboxRoom


def test_six_planes_follow_named_wall_order_and_inside_halfspaces():
    room = ShoeboxRoom((4.0, 5.0, 3.0))
    planes = shoebox_wall_planes(room)
    assert tuple(plane.wall_id for plane in planes) == (
        "x_min", "x_max", "y_min", "y_max", "z_min", "z_max"
    )
    assert [plane.offset_m for plane in planes] == [0.0, 4.0, 0.0, 5.0, 0.0, 3.0]
    assert [plane.outward_normal for plane in planes] == [
        (-1.0, 0.0, 0.0), (1.0, 0.0, 0.0),
        (0.0, -1.0, 0.0), (0.0, 1.0, 0.0),
        (0.0, 0.0, -1.0), (0.0, 0.0, 1.0),
    ]
    assert all(plane.signed_outside_distance_m((1.0, 2.0, 1.0)) < 0.0 for plane in planes)
    assert planes[0].signed_outside_distance_m((-0.1, 1.0, 1.0)) > 0.0


@pytest.mark.parametrize(
    ("point", "tolerance", "expected"),
    [
        ((1.0, 1.0, 1.0), 0.0, PointLocation.INTERIOR),
        ((0.0, 1.0, 1.0), 1e-3, PointLocation.ON_BOUNDARY),
        ((5e-4, 1.0, 1.0), 1e-3, PointLocation.NEAR_BOUNDARY),
        ((-1e-6, 1.0, 1.0), 1e-3, PointLocation.OUTSIDE),
        ((4.0, 1.0, 1.0), 0.0, PointLocation.ON_BOUNDARY),
    ],
)
def test_point_boundary_classification(point, tolerance, expected):
    room = ShoeboxRoom((4.0, 5.0, 3.0))
    assert classify_room_point(room, point, boundary_tolerance_m=tolerance) is expected


def test_require_interior_applies_clearance_without_moving_walls():
    room = ShoeboxRoom((4.0, 5.0, 3.0))
    assert require_room_interior(room, (0.1, 1.0, 1.0)) == (0.1, 1.0, 1.0)
    with pytest.raises(ValueError, match="farther"):
        require_room_interior(room, (0.1, 1.0, 1.0), minimum_clearance_m=0.1)
    with pytest.raises(ValueError, match="inside"):
        require_room_interior(room, (4.1, 1.0, 1.0))


@pytest.mark.parametrize("tolerance", [-1.0, np.nan, np.inf])
def test_boundary_tolerance_must_be_finite_nonnegative(tolerance):
    room = ShoeboxRoom((4.0, 5.0, 3.0))
    with pytest.raises(ValueError):
        classify_room_point(room, (1.0, 1.0, 1.0), boundary_tolerance_m=tolerance)


def test_invalid_geometry_points_are_rejected():
    room = ShoeboxRoom((4.0, 5.0, 3.0))
    for point in ((1.0, 2.0), (1.0, np.nan, 1.0), ("a", 1.0, 1.0)):
        with pytest.raises(ValueError):
            classify_room_point(room, point)
    with pytest.raises(ValueError):
        ShoeboxRoom((4.0, 0.0, 3.0))
