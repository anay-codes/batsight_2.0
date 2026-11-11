"""Bounded estimator for calibrated, labeled first-order shoebox TOAs.

Only the three room dimensions are unknown. This is deliberately separate
from the uncalibrated convex-room research branch.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence

import numpy as np
from numpy.typing import NDArray
from scipy.optimize import least_squares

from batsight.datasets.calibrated import CalibratedTOAObservationSet
from batsight.reconstruction.models import (
    ObservationCounts,
    ResidualStatistics,
    ShoeboxDimensionEstimate,
    WallObservationCount,
)
from batsight.simulation.reflections import predict_first_order_arrivals
from batsight.simulation.shoebox import WALLS, ShoeboxRoom

FloatArray = NDArray[np.float64]
_WALL_AXIS = {wall: index // 2 for index, wall in enumerate(WALLS)}


def estimate_shoebox_dimensions(
    observations: CalibratedTOAObservationSet,
    *,
    initial_dimensions_m: Sequence[float],
    upper_bounds_m: Sequence[float],
    interior_clearance_m: float = 1e-6,
    default_uncertainty_s: float | None = None,
    max_nfev: int = 500,
    rank_tolerance: float = 1e-8,
    bound_tolerance_m: float = 1e-7,
) -> ShoeboxDimensionEstimate:
    """Estimate `(Lx, Ly, Lz)` from calibrated labeled first-order echoes.

    Direct TOAs and unlabeled echoes are retained in exclusion counts but do
    not enter the objective. Each residual is observed minus predicted time;
    if uncertainty standard deviations are complete (or completed by an
    explicit default), residuals are divided by their standard deviations.
    Mixed specified/unspecified uncertainties without a default are rejected.

    Finite upper bounds are required because the data contract supplies no
    universal maximum room size. Each lower bound is the largest known point
    coordinate plus the requested clearance and a floating-point safety gap.
    At least one usable maximum-wall echo on each axis is required: minimum
    wall reflections and direct paths have zero dimension derivative.
    """
    if not isinstance(observations, CalibratedTOAObservationSet):
        raise TypeError("observations must be CalibratedTOAObservationSet")
    if not np.isfinite(interior_clearance_m) or interior_clearance_m < 0.0:
        raise ValueError("interior_clearance_m must be finite and non-negative")
    if not isinstance(max_nfev, int) or max_nfev < 1:
        raise ValueError("max_nfev must be a positive integer")
    if not np.isfinite(rank_tolerance) or rank_tolerance <= 0.0:
        raise ValueError("rank_tolerance must be finite and positive")
    if not np.isfinite(bound_tolerance_m) or bound_tolerance_m < 0.0:
        raise ValueError("bound_tolerance_m must be finite and non-negative")
    if default_uncertainty_s is not None and (
        not np.isfinite(default_uncertainty_s) or default_uncertainty_s <= 0.0
    ):
        raise ValueError("default_uncertainty_s must be finite and positive")

    initial = _triple(initial_dimensions_m, "initial_dimensions_m", positive=True)
    upper = _triple(upper_bounds_m, "upper_bounds_m", positive=True)
    upper_array = np.asarray(upper, dtype=np.float64)
    inputs = observations.inputs
    points = np.asarray(
        [m.position_m for m in inputs.microphone_array.microphones]
        + [e.position_m for e in inputs.source_events],
        dtype=np.float64,
    )
    if np.any(points.min(axis=0) <= interior_clearance_m):
        raise ValueError(
            "known positions must exceed interior_clearance_m from the room origin on every axis"
        )
    maxima = points.max(axis=0)
    scale = np.maximum(1.0, maxima + interior_clearance_m)
    safety = np.maximum(1e-12, 16.0 * np.finfo(np.float64).eps * scale)
    lower = maxima + interior_clearance_m + safety
    if np.any(upper_array <= lower):
        raise ValueError("each upper bound must exceed the derived interior lower bound")
    initial_array = np.asarray(initial, dtype=np.float64)
    if np.any(initial_array <= lower) or np.any(initial_array >= upper_array):
        raise ValueError("initial_dimensions_m must lie strictly inside derived bounds")

    counts = Counter()
    wall_total: Counter[str] = Counter()
    wall_used: Counter[str] = Counter()
    wall_missing: Counter[str] = Counter()
    wall_invalid: Counter[str] = Counter()
    usable = []
    for item in observations.labeled_first_order_reflections:
        wall_total[item.wall_id] += 1
        if item.reading.status == "missing":
            wall_missing[item.wall_id] += 1
            continue
        if item.reading.status == "invalid":
            wall_invalid[item.wall_id] += 1
            continue
        usable.append(item)
        wall_used[item.wall_id] += 1
    counts = ObservationCounts(
        direct_paths_excluded=len(observations.direct_paths),
        unlabeled_echoes_excluded=len(observations.unlabeled_echoes),
        labeled_first_order_total=len(observations.labeled_first_order_reflections),
        labeled_first_order_used=len(usable),
        labeled_first_order_missing=sum(wall_missing.values()),
        labeled_first_order_invalid=sum(wall_invalid.values()),
    )
    per_wall = tuple(
        WallObservationCount(
            wall_id=wall,
            total=wall_total[wall],
            used=wall_used[wall],
            missing=wall_missing[wall],
            invalid=wall_invalid[wall],
        )
        for wall in WALLS
    )
    covered_axes = {
        _WALL_AXIS[item.wall_id]
        for item in usable
        if item.wall_id.endswith("_max")
    }
    missing_axes = ["xyz"[axis] for axis in range(3) if axis not in covered_axes]
    if not usable or missing_axes:
        return _empty_result(
            status="insufficient_information",
            initial=initial,
            lower=lower,
            upper=upper,
            clearance=interior_clearance_m,
            counts=counts,
            per_wall=per_wall,
            reason=(
                "No usable labeled first-order observations."
                if not usable
                else "No usable maximum-wall observations for dimension(s): " + ", ".join(missing_axes)
            ),
        )

    uncertainties = [item.reading.uncertainty_s for item in usable]
    specified = [value is not None for value in uncertainties]
    if any(value == 0.0 for value in uncertainties if value is not None):
        raise ValueError("zero uncertainty is not supported; use a positive standard deviation")
    if any(specified) and not all(specified) and default_uncertainty_s is None:
        raise ValueError("mixed uncertainty values require default_uncertainty_s for unspecified readings")
    weighted = any(specified) or default_uncertainty_s is not None
    sigmas = np.asarray(
        [
            float(item.reading.uncertainty_s)
            if item.reading.uncertainty_s is not None
            else float(default_uncertainty_s)
            for item in usable
        ],
        dtype=np.float64,
    ) if weighted else np.ones(len(usable), dtype=np.float64)
    weighting_mode = "uncertainty_weighted" if weighted else "unweighted_seconds"

    microphones = {item.microphone_id: item for item in inputs.microphone_array.microphones}
    def predict(dimensions: FloatArray):
        room = ShoeboxRoom(tuple(float(value) for value in dimensions), inputs.speed_of_sound_m_s)
        arrivals = predict_first_order_arrivals(
            inputs, room, boundary_tolerance_m=interior_clearance_m
        )
        return {
            (a.microphone_id, a.event_id, a.wall_id): a
            for a in arrivals
            if a.reflection_order == 1
        }

    def residual_and_jacobian(dimensions: FloatArray) -> tuple[FloatArray, FloatArray]:
        predictions = predict(dimensions)
        residual = np.empty(len(usable), dtype=np.float64)
        jacobian = np.zeros((len(usable), 3), dtype=np.float64)
        c = inputs.speed_of_sound_m_s
        for row, item in enumerate(usable):
            key = (item.microphone_id, item.event_id, item.wall_id)
            arrival = predictions[key]
            residual[row] = float(item.reading.arrival_time_s) - arrival.arrival_time_s
            if item.wall_id.endswith("_max"):
                axis = _WALL_AXIS[item.wall_id]
                image = np.asarray(arrival.image_source_position_m)
                mic = np.asarray(microphones[item.microphone_id].position_m)
                distance = arrival.propagation_distance_m
                # d arrival / d L_axis = 2 (image_axis - mic_axis)/(c d).
                jacobian[row, axis] = -2.0 * (image[axis] - mic[axis]) / (c * distance)
        return residual / sigmas, jacobian / sigmas[:, None]

    result = least_squares(
        lambda x: residual_and_jacobian(x)[0],
        np.asarray(initial),
        jac=lambda x: residual_and_jacobian(x)[1],
        bounds=(lower, upper),
        method="trf",
        x_scale="jac",
        max_nfev=max_nfev,
        ftol=1e-12,
        xtol=1e-12,
        gtol=1e-12,
    )
    dimensions = np.asarray(result.x, dtype=np.float64)
    raw_residual, weighted_jacobian = residual_and_jacobian(dimensions)
    raw_residual = raw_residual * sigmas
    singular_values = np.linalg.svd(weighted_jacobian, compute_uv=False)
    threshold = rank_tolerance * singular_values[0] if singular_values.size else 0.0
    rank = int(np.count_nonzero(singular_values > threshold))
    condition = (
        float(singular_values[0] / singular_values[-1])
        if len(singular_values) >= 3 and rank == 3 and singular_values[-1] > 0.0
        else None
    )
    stats = ResidualStatistics(
        count=len(raw_residual),
        mean_signed_s=float(np.mean(raw_residual)),
        mean_absolute_s=float(np.mean(np.abs(raw_residual))),
        rms_s=float(np.sqrt(np.mean(raw_residual**2))),
        maximum_absolute_s=float(np.max(np.abs(raw_residual))),
    )
    mic_clearance = _minimum_clearance([m.position_m for m in inputs.microphone_array.microphones], dimensions)
    source_clearance = _minimum_clearance([e.position_m for e in inputs.source_events], dimensions)
    physical_valid = mic_clearance > interior_clearance_m and source_clearance > interior_clearance_m
    warnings: list[str] = []
    if rank < 3:
        warnings.append(f"dimension Jacobian rank is {rank}, below 3")
    at_bounds = tuple(
        "xyz"[axis]
        for axis in range(3)
        if dimensions[axis] - lower[axis] <= bound_tolerance_m
        or upper[axis] - dimensions[axis] <= bound_tolerance_m
    )
    if at_bounds:
        warnings.append("one or more estimates are within bound_tolerance_m of a configured bound")
    if not physical_valid:
        warnings.append("estimated room does not satisfy the requested strict interior clearance")
    if not physical_valid:
        status = "invalid_physical_solution"
    elif rank < 3:
        status = "insufficient_information"
    elif result.success:
        status = "converged"
    else:
        status = "optimizer_failed"
    return ShoeboxDimensionEstimate(
        status=status,
        estimated_dimensions_m=tuple(float(value) for value in dimensions),
        initial_dimensions_m=initial,
        lower_bounds_m=tuple(float(value) for value in lower),
        upper_bounds_m=upper,
        interior_clearance_m=float(interior_clearance_m),
        observation_counts=counts,
        per_wall_counts=per_wall,
        weighting_mode=weighting_mode,
        objective_value=float(result.cost),
        residual_statistics=stats,
        jacobian_rank=rank,
        jacobian_singular_values=tuple(float(value) for value in singular_values),
        jacobian_condition_number=condition,
        optimizer_success=bool(result.success),
        optimizer_status=int(result.status),
        termination_message=str(result.message),
        function_evaluations=int(result.nfev),
        jacobian_evaluations=int(result.njev or 0),
        physical_valid=physical_valid,
        minimum_microphone_clearance_m=mic_clearance,
        minimum_source_clearance_m=source_clearance,
        dimensions_at_bounds=at_bounds,
        warnings=tuple(warnings),
    )


def _empty_result(*, status, initial, lower, upper, clearance, counts, per_wall, reason):
    return ShoeboxDimensionEstimate(
        status=status,
        estimated_dimensions_m=None,
        initial_dimensions_m=initial,
        lower_bounds_m=tuple(float(value) for value in lower),
        upper_bounds_m=upper,
        interior_clearance_m=float(clearance),
        observation_counts=counts,
        per_wall_counts=per_wall,
        weighting_mode="unweighted_seconds",
        objective_value=None,
        residual_statistics=None,
        jacobian_rank=0,
        jacobian_singular_values=(),
        jacobian_condition_number=None,
        optimizer_success=None,
        optimizer_status=None,
        termination_message=reason,
        function_evaluations=0,
        jacobian_evaluations=0,
        physical_valid=None,
        minimum_microphone_clearance_m=None,
        minimum_source_clearance_m=None,
        dimensions_at_bounds=(),
        warnings=(reason,),
    )


def _triple(values: Sequence[float], name: str, *, positive: bool) -> tuple[float, float, float]:
    try:
        result = tuple(float(value) for value in values)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must contain three finite metres") from exc
    if len(result) != 3 or not all(np.isfinite(value) for value in result):
        raise ValueError(f"{name} must contain three finite metres")
    if positive and any(value <= 0.0 for value in result):
        raise ValueError(f"{name} values must be positive")
    return result  # type: ignore[return-value]


def _minimum_clearance(points: Sequence[Sequence[float]], dimensions: FloatArray) -> float:
    return float(min(min(*point, *(dimensions - np.asarray(point))) for point in points))
