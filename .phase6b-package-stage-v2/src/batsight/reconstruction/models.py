"""Typed result models for calibrated shoebox dimension estimation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np

DimensionStatus = Literal[
    "converged",
    "optimizer_failed",
    "insufficient_information",
    "invalid_physical_solution",
]
WeightingMode = Literal["unweighted_seconds", "uncertainty_weighted"]


@dataclass(frozen=True, slots=True)
class WallObservationCount:
    """Labeled first-order observation counts for one wall."""

    wall_id: str
    total: int
    used: int
    missing: int
    invalid: int


@dataclass(frozen=True, slots=True)
class ObservationCounts:
    """Used and excluded TOA counts, separated by information type."""

    direct_paths_excluded: int
    unlabeled_echoes_excluded: int
    labeled_first_order_total: int
    labeled_first_order_used: int
    labeled_first_order_missing: int
    labeled_first_order_invalid: int


@dataclass(frozen=True, slots=True)
class ResidualStatistics:
    """Raw arrival-time residual summary in seconds."""

    count: int
    mean_signed_s: float
    mean_absolute_s: float
    rms_s: float
    maximum_absolute_s: float


@dataclass(frozen=True, slots=True)
class ShoeboxDimensionEstimate:
    """Optimizer and physical diagnostics for an estimated `(Lx,Ly,Lz)`.

    ``optimizer_success`` describes numerical termination only. It does not
    mean room dimensions are correct; assess geometric recovery against
    independently held-out ground truth during validation.
    """

    status: DimensionStatus
    estimated_dimensions_m: tuple[float, float, float] | None
    initial_dimensions_m: tuple[float, float, float]
    lower_bounds_m: tuple[float, float, float]
    upper_bounds_m: tuple[float, float, float]
    interior_clearance_m: float
    observation_counts: ObservationCounts
    per_wall_counts: tuple[WallObservationCount, ...]
    weighting_mode: WeightingMode
    objective_value: float | None
    residual_statistics: ResidualStatistics | None
    jacobian_rank: int
    jacobian_singular_values: tuple[float, ...]
    jacobian_condition_number: float | None
    optimizer_success: bool | None
    optimizer_status: int | None
    termination_message: str
    function_evaluations: int
    jacobian_evaluations: int
    physical_valid: bool | None
    minimum_microphone_clearance_m: float | None
    minimum_source_clearance_m: float | None
    dimensions_at_bounds: tuple[str, ...]
    warnings: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.jacobian_rank < 0 or self.function_evaluations < 0 or self.jacobian_evaluations < 0:
            raise ValueError("diagnostic counts must be non-negative")
        if self.estimated_dimensions_m is not None and (
            len(self.estimated_dimensions_m) != 3
            or not all(np.isfinite(value) and value > 0.0 for value in self.estimated_dimensions_m)
        ):
            raise ValueError("estimated_dimensions_m must contain three positive finite metres")
