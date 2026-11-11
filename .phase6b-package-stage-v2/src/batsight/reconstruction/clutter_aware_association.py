"""Exploratory clutter-aware unlabeled echo association and box fitting.

This module preserves the Phase 5D.3 baseline. It alternates candidate/wall
assignment with the unchanged Phase 5D.2 dimension objective, then forbids
candidate-to-wall edges whose residual is inconsistent with the shared fitted
box. It does not claim a global optimum or exact paper reproduction.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from time import perf_counter
from typing import Literal

import numpy as np
from scipy.optimize import linear_sum_assignment

from batsight.datasets.calibrated import (
    CalibratedTOAObservationSet,
    FirstOrderReflectionTOAObservation,
    TOAReading,
)
from batsight.reconstruction.echo_association import EchoAssignment
from batsight.reconstruction.models import ShoeboxDimensionEstimate
from batsight.reconstruction.shoebox_dimensions import estimate_shoebox_dimensions
from batsight.simulation.reflections import predict_first_order_arrivals
from batsight.simulation.shoebox import WALLS, ShoeboxRoom


@dataclass(frozen=True, slots=True)
class RejectedAssociation:
    """Candidate/wall edge rejected by post-fit shared-geometry checking."""

    microphone_id: str
    event_id: str
    echo_id: str
    wall_id: str
    residual_s: float
    rejection_threshold_s: float
    iteration: int


@dataclass(frozen=True, slots=True)
class ClutterAwareIteration:
    """Diagnostics for one assignment, dimension fit, and consistency pass."""

    iteration: int
    dimensions_before_m: tuple[float, float, float]
    dimensions_after_m: tuple[float, float, float] | None
    assignments: tuple[EchoAssignment, ...]
    rejected_edges: tuple[RejectedAssociation, ...]
    unassigned_echo_ids: tuple[str, ...]
    missed_paths: tuple[tuple[str, str, str], ...]
    ambiguous_echo_ids: tuple[str, ...]
    assignment_objective: float
    dimension_fit: ShoeboxDimensionEstimate
    maximum_assignment_residual_s: float | None
    changed_assignments: int
    runtime_s: float


@dataclass(frozen=True, slots=True)
class ClutterAwareResult:
    """Final clutter-aware estimate, data association, and diagnostics."""

    status: Literal[
        "converged", "max_iterations", "dimension_fit_failed", "no_consistent_assignment"
    ]
    converged: bool
    estimated_dimensions_m: tuple[float, float, float] | None
    iterations: tuple[ClutterAwareIteration, ...]
    final_assignments: tuple[EchoAssignment, ...]
    rejected_edges: tuple[RejectedAssociation, ...]
    unassigned_echo_ids: tuple[str, ...]
    missed_paths: tuple[tuple[str, str, str], ...]
    ambiguous_echo_ids: tuple[str, ...]
    input_echo_count: int
    usable_echo_count: int
    unassigned_detection_count: int
    dimension_fit: ShoeboxDimensionEstimate | None
    runtime_s: float
    warnings: tuple[str, ...]


def estimate_dimensions_clutter_aware(
    observations: CalibratedTOAObservationSet,
    *,
    initial_dimensions_m: tuple[float, float, float],
    upper_bounds_m: tuple[float, float, float],
    association_scale_s: float = 1e-4,
    maximum_match_error_s: float = 5e-3,
    consistency_gate_s: float = 5e-4,
    missing_path_penalty: float = 9.0,
    clutter_penalty: float = 9.0,
    ambiguity_cost_gap: float = 1.0,
    strength_weight: float = 0.0,
    max_iterations: int = 20,
    dimension_tolerance_m: float = 1e-7,
    interior_clearance_m: float = 1e-6,
    dimension_default_uncertainty_s: float | None = None,
    max_nfev: int = 500,
) -> ClutterAwareResult:
    """Estimate dimensions while permitting missed paths and clutter.

    At each iteration, a per-pair augmented Hungarian problem matches zero to
    six wall predictions to detections. Unmatched predictions and observations
    have explicit penalties. A dimension fit then uses only the selected
    observations and the exact Phase 5D.2 objective. Matched edges whose
    post-fit TOA residual exceeds ``max(consistency_gate_s, 3*sigma)`` are
    forbidden in later assignment steps. A rejected edge is not a rejected
    echo: it may still match a different wall if the shared model supports it.

    ``strength_weight`` optionally adds a weak-evidence penalty based on
    within-pair log-strength ranks. This is an engineering tie-breaker, not a
    calibrated probability or a change to the Phase 5D.2 measurement objective.
    The default is zero. The hard match gate, edge-consistency gate, and dummy
    costs are explicit engineering settings.
    """
    _validate(
        association_scale_s,
        maximum_match_error_s,
        consistency_gate_s,
        missing_path_penalty,
        clutter_penalty,
        ambiguity_cost_gap,
        strength_weight,
        max_iterations,
        dimension_tolerance_m,
        interior_clearance_m,
        dimension_default_uncertainty_s,
    )
    if not isinstance(observations, CalibratedTOAObservationSet):
        raise TypeError("observations must be CalibratedTOAObservationSet")
    if observations.labeled_first_order_reflections:
        raise ValueError("clutter-aware association requires unlabeled echoes only")
    current = np.asarray(initial_dimensions_m, dtype=np.float64)
    upper = np.asarray(upper_bounds_m, dtype=np.float64)
    if current.shape != (3,) or not np.all(np.isfinite(current)) or np.any(current <= 0.0):
        raise ValueError("initial_dimensions_m must contain three positive finite values")
    if upper.shape != (3,) or not np.all(np.isfinite(upper)) or np.any(upper <= current):
        raise ValueError("upper_bounds_m must be finite and strictly greater than initial dimensions")

    started = perf_counter()
    inputs = observations.inputs
    usable = [item for item in observations.unlabeled_echoes if item.reading.status == "observed"]
    groups: dict[tuple[str, str], list] = defaultdict(list)
    for item in usable:
        groups[(item.microphone_id, item.event_id)].append(item)
    pairs = [
        (mic.microphone_id, event.event_id)
        for event in inputs.source_events
        for mic in inputs.microphone_array.microphones
    ]
    forbidden_edges: set[tuple[str, str, str, str]] = set()
    history: list[ClutterAwareIteration] = []
    all_rejected: list[RejectedAssociation] = []
    previous_signature: tuple | None = None
    fit: ShoeboxDimensionEstimate | None = None
    final_assignments: tuple[EchoAssignment, ...] = ()
    final_unassigned: tuple[str, ...] = ()
    final_missed: tuple[tuple[str, str, str], ...] = ()
    final_ambiguous: tuple[str, ...] = ()
    warnings: list[str] = []
    converged = False

    for iteration in range(max_iterations):
        iteration_started = perf_counter()
        room = ShoeboxRoom(tuple(float(x) for x in current), inputs.speed_of_sound_m_s)
        predicted = predict_first_order_arrivals(inputs, room, boundary_tolerance_m=interior_clearance_m)
        predicted_by_pair: dict[tuple[str, str], dict[str, object]] = defaultdict(dict)
        for arrival in predicted:
            if arrival.reflection_order == 1:
                predicted_by_pair[(arrival.microphone_id, arrival.event_id)][arrival.wall_id] = arrival

        assignments: list[EchoAssignment] = []
        unassigned: list[str] = []
        ambiguous: list[str] = []
        objective = 0.0
        by_pair_assignment: dict[tuple[str, str], dict[str, EchoAssignment]] = {}
        for pair in pairs:
            matches, left_out, pair_ambiguous, pair_objective = _assign_pair(
                pair,
                groups.get(pair, []),
                predicted_by_pair[pair],
                forbidden_edges,
                association_scale_s=association_scale_s,
                gate_s=maximum_match_error_s,
                miss_cost=missing_path_penalty,
                clutter_cost=clutter_penalty,
                ambiguity_gap=ambiguity_cost_gap,
                strength_weight=strength_weight,
            )
            assignments.extend(matches)
            unassigned.extend(left_out)
            ambiguous.extend(pair_ambiguous)
            objective += pair_objective
            by_pair_assignment[pair] = {item.wall_id: item for item in matches}

        missed_paths = tuple(
            (mic_id, event_id, wall)
            for mic_id, event_id in pairs
            for wall in WALLS
            if wall not in by_pair_assignment[(mic_id, event_id)]
        )
        signature = tuple(sorted(
            (item.microphone_id, item.event_id, item.echo_id, item.wall_id)
            for item in assignments
        ))
        changed = len(set(signature).symmetric_difference(set(previous_signature or ())))
        labeled = []
        for pair in pairs:
            echo_by_id = {item.echo_id: item for item in groups.get(pair, [])}
            assigned = by_pair_assignment[pair]
            for wall in WALLS:
                match = assigned.get(wall)
                reading = echo_by_id[match.echo_id].reading if match else TOAReading(None, status="missing")
                labeled.append(FirstOrderReflectionTOAObservation(
                    pair[0], pair[1], wall, reading, "estimated_association"
                ))
        associated = CalibratedTOAObservationSet(
            observations.inputs,
            observations.origin,
            direct_paths=observations.direct_paths,
            labeled_first_order_reflections=tuple(labeled),
        )
        sigmas = [row.reading.uncertainty_s for row in labeled if row.reading.status == "observed"]
        if any(value is not None for value in sigmas) and any(value is None for value in sigmas):
            if dimension_default_uncertainty_s is None:
                raise ValueError("mixed matched-echo uncertainties require dimension_default_uncertainty_s")
        fit = estimate_shoebox_dimensions(
            associated,
            initial_dimensions_m=tuple(float(x) for x in current),
            upper_bounds_m=tuple(float(x) for x in upper),
            interior_clearance_m=interior_clearance_m,
            default_uncertainty_s=dimension_default_uncertainty_s,
            max_nfev=max_nfev,
        )
        iteration_rejections: list[RejectedAssociation] = []
        max_residual = None
        if fit.status == "converged" and fit.estimated_dimensions_m is not None:
            fitted_room = ShoeboxRoom(fit.estimated_dimensions_m, inputs.speed_of_sound_m_s)
            fitted_arrivals = predict_first_order_arrivals(
                inputs, fitted_room, boundary_tolerance_m=interior_clearance_m
            )
            fitted_lookup = {
                (item.microphone_id, item.event_id, item.wall_id): item
                for item in fitted_arrivals
                if item.reflection_order == 1
            }
            echo_lookup = {
                (item.microphone_id, item.event_id, item.echo_id): item
                for item in usable
            }
            residuals = []
            for assignment in assignments:
                observed = echo_lookup[(assignment.microphone_id, assignment.event_id, assignment.echo_id)]
                prediction = fitted_lookup[(assignment.microphone_id, assignment.event_id, assignment.wall_id)]
                residual_s = float(observed.reading.arrival_time_s - prediction.arrival_time_s)
                residuals.append(abs(residual_s))
                threshold = max(
                    consistency_gate_s,
                    3.0 * observed.reading.uncertainty_s
                    if observed.reading.uncertainty_s is not None
                    else 0.0,
                )
                if abs(residual_s) > threshold:
                    rejected = RejectedAssociation(
                        assignment.microphone_id,
                        assignment.event_id,
                        assignment.echo_id,
                        assignment.wall_id,
                        residual_s,
                        threshold,
                        iteration,
                    )
                    iteration_rejections.append(rejected)
                    forbidden_edges.add((assignment.microphone_id, assignment.event_id,
                                          assignment.echo_id, assignment.wall_id))
            max_residual = max(residuals) if residuals else None

        ordered_assignments = tuple(sorted(
            assignments, key=lambda item: (item.microphone_id, item.event_id, item.echo_id)
        ))
        ordered_unassigned = tuple(sorted(unassigned))
        ordered_ambiguous = tuple(sorted(ambiguous))
        all_rejected.extend(iteration_rejections)
        history.append(ClutterAwareIteration(
            iteration=iteration,
            dimensions_before_m=tuple(float(x) for x in current),
            dimensions_after_m=fit.estimated_dimensions_m,
            assignments=ordered_assignments,
            rejected_edges=tuple(iteration_rejections),
            unassigned_echo_ids=ordered_unassigned,
            missed_paths=missed_paths,
            ambiguous_echo_ids=ordered_ambiguous,
            assignment_objective=float(objective),
            dimension_fit=fit,
            maximum_assignment_residual_s=max_residual,
            changed_assignments=changed,
            runtime_s=perf_counter() - iteration_started,
        ))
        final_assignments = ordered_assignments
        final_unassigned = ordered_unassigned
        final_ambiguous = ordered_ambiguous
        final_missed = missed_paths
        if fit.status != "converged" or fit.estimated_dimensions_m is None:
            warnings.append(f"dimension fit failed: {fit.status}: {fit.termination_message}")
            break
        if iteration_rejections:
            previous_signature = signature
            current = np.asarray(fit.estimated_dimensions_m, dtype=np.float64)
            if np.any(current >= upper) or np.any(current <= fit.lower_bounds_m):
                warnings.append("dimension fit reached a configured/derived bound after edge rejection")
                break
            continue
        dimension_change = float(np.max(np.abs(np.asarray(fit.estimated_dimensions_m) - current)))
        if previous_signature == signature and dimension_change <= dimension_tolerance_m:
            converged = True
            break
        previous_signature = signature
        current = np.asarray(fit.estimated_dimensions_m, dtype=np.float64)
        if np.any(current >= upper) or np.any(current <= fit.lower_bounds_m):
            warnings.append("dimension update reached a configured/derived bound")
            break

    if not converged and len(history) == max_iterations:
        warnings.append("alternating robust assignment reached max_iterations")
    if not usable:
        warnings.append("no observed echo candidates were available")
    if fit is not None and fit.status == "converged" and not final_assignments:
        status = "no_consistent_assignment"
    elif fit is not None and fit.status != "converged":
        status = "dimension_fit_failed"
    elif converged:
        status = "converged"
    else:
        status = "max_iterations"
    return ClutterAwareResult(
        status=status,
        converged=converged,
        estimated_dimensions_m=fit.estimated_dimensions_m if fit else None,
        iterations=tuple(history),
        final_assignments=final_assignments,
        rejected_edges=tuple(all_rejected),
        unassigned_echo_ids=final_unassigned,
        missed_paths=final_missed,
        ambiguous_echo_ids=final_ambiguous,
        input_echo_count=len(observations.unlabeled_echoes),
        usable_echo_count=len(usable),
        unassigned_detection_count=len(final_unassigned),
        dimension_fit=fit,
        runtime_s=perf_counter() - started,
        warnings=tuple(warnings),
    )


def _assign_pair(
    pair,
    echoes,
    wall_predictions,
    forbidden_edges,
    *,
    association_scale_s,
    gate_s,
    miss_cost,
    clutter_cost,
    ambiguity_gap,
    strength_weight,
):
    wall_count = len(WALLS)
    echo_count = len(echoes)
    if echo_count == 0:
        return (), (), (), wall_count * miss_cost
    size = wall_count + echo_count
    predicted_times = np.asarray([wall_predictions[wall].arrival_time_s for wall in WALLS])
    observed_times = np.asarray([item.reading.arrival_time_s for item in echoes])
    sigma = np.asarray([
        item.reading.uncertainty_s if item.reading.uncertainty_s is not None else association_scale_s
        for item in echoes
    ], dtype=np.float64)
    if np.any(sigma <= 0.0):
        raise ValueError("observed echo uncertainties must be positive")
    effective_scale = np.maximum(sigma, gate_s / 3.0)
    delta = predicted_times[:, None] - observed_times[None, :]
    valid = np.abs(delta) <= gate_s
    edge_cost = (delta / effective_scale[None, :]) ** 2
    edge_cost[~valid] = 1e12
    for row, wall in enumerate(WALLS):
        for col, echo in enumerate(echoes):
            key = (pair[0], pair[1], echo.echo_id, wall)
            if key in forbidden_edges:
                valid[row, col] = False
                edge_cost[row, col] = 1e12

    if strength_weight > 0.0:
        strengths = np.asarray([
            float(item.detection_strength)
            if item.detection_strength is not None and np.isfinite(item.detection_strength)
            else np.nan
            for item in echoes
        ])
        finite = np.isfinite(strengths)
        penalty = np.zeros(echo_count, dtype=np.float64)
        if np.any(finite):
            logs = np.log1p(np.maximum(strengths[finite], 0.0))
            lo, hi = float(np.min(logs)), float(np.max(logs))
            quality = np.full(echo_count, 0.5)
            if hi > lo:
                quality[finite] = (logs - lo) / (hi - lo)
            else:
                quality[finite] = 1.0
            penalty = strength_weight * (1.0 - quality)
        edge_cost += penalty[None, :]

    matrix = np.zeros((size, size), dtype=np.float64)
    matrix[:wall_count, :echo_count] = edge_cost
    matrix[:wall_count, echo_count:] = miss_cost
    matrix[wall_count:, :echo_count] = clutter_cost
    rows, cols = linear_sum_assignment(matrix)
    baseline_cost = float(matrix[rows, cols].sum())
    assignments = []
    matched_echoes = set()
    matched_walls = set()
    for row, col in zip(rows, cols):
        if row < wall_count and col < echo_count and valid[row, col]:
            echo = echoes[col]
            wall = WALLS[row]
            pred = wall_predictions[wall]
            assignments.append(EchoAssignment(
                pair[0], pair[1], echo.echo_id, wall,
                float(observed_times[col]), float(pred.arrival_time_s),
                float(observed_times[col] - pred.arrival_time_s), float(edge_cost[row, col]),
            ))
            matched_echoes.add(col)
            matched_walls.add(row)
    unassigned = tuple(echoes[index].echo_id for index in range(echo_count) if index not in matched_echoes)
    ambiguous = []
    for row, col in zip(rows, cols):
        if row >= wall_count or col >= echo_count or not valid[row, col]:
            continue
        alternative = matrix.copy()
        alternative[row, col] = 1e15
        alt_rows, alt_cols = linear_sum_assignment(alternative)
        if float(alternative[alt_rows, alt_cols].sum()) - baseline_cost <= ambiguity_gap:
            ambiguous.append(echoes[col].echo_id)
    missed = wall_count - len(matched_walls)
    return tuple(assignments), unassigned, tuple(ambiguous), baseline_cost


def _validate(
    scale, gate, residual_gate, miss, clutter, ambiguity, strength_weight,
    iterations, dimension_tolerance, clearance, default_uncertainty,
):
    values = (scale, gate, residual_gate, miss, clutter, ambiguity, strength_weight,
              dimension_tolerance, clearance)
    if not all(np.isfinite(value) for value in values):
        raise ValueError("clutter-aware options must be finite")
    if scale <= 0 or gate <= 0 or residual_gate <= 0:
        raise ValueError("association scales and gates must be positive")
    if miss <= 0 or clutter <= 0 or ambiguity < 0 or strength_weight < 0:
        raise ValueError("assignment costs must be positive and weights non-negative")
    if dimension_tolerance < 0 or clearance < 0:
        raise ValueError("dimension tolerance and clearance must be non-negative")
    if not isinstance(iterations, int) or iterations < 1:
        raise ValueError("max_iterations must be a positive integer")
    if default_uncertainty is not None and (
        not np.isfinite(default_uncertainty) or default_uncertainty <= 0
    ):
        raise ValueError("dimension_default_uncertainty_s must be finite and positive")
