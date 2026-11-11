"""Alternating unlabeled first-order echo assignment and shoebox fitting.

Associations are inferred from predicted TOAs at a shared candidate room.
This is a BatSight engineering method, not an algorithm attributed to the
2016 paper. It uses the Phase 5D.2 dimension objective unchanged after each
assignment step.
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
from batsight.reconstruction.models import ShoeboxDimensionEstimate
from batsight.reconstruction.shoebox_dimensions import estimate_shoebox_dimensions
from batsight.simulation.reflections import predict_first_order_arrivals
from batsight.simulation.shoebox import WALLS, ShoeboxRoom


@dataclass(frozen=True, slots=True)
class EchoAssignment:
    """One observed echo matched to a predicted first-order wall path."""

    microphone_id: str
    event_id: str
    echo_id: str
    wall_id: str
    observed_time_s: float
    predicted_time_s: float
    residual_s: float
    assignment_cost: float


@dataclass(frozen=True, slots=True)
class EchoAssociationIteration:
    """Snapshot of one assignment and dimension-fit iteration."""

    iteration: int
    dimensions_before_m: tuple[float, float, float]
    dimensions_after_m: tuple[float, float, float] | None
    assignments: tuple[EchoAssignment, ...]
    unassigned_echo_ids: tuple[str, ...]
    missed_paths: tuple[tuple[str, str, str], ...]
    missed_wall_paths: int
    ambiguous_echo_ids: tuple[str, ...]
    association_objective: float
    dimension_fit: ShoeboxDimensionEstimate | None
    changed_assignments: int
    runtime_s: float


@dataclass(frozen=True, slots=True)
class UnlabeledEchoDimensionResult:
    """Final output and diagnostics for alternating echo association."""

    status: Literal["converged", "max_iterations", "dimension_fit_failed"]
    estimated_dimensions_m: tuple[float, float, float] | None
    iterations: tuple[EchoAssociationIteration, ...]
    final_assignments: tuple[EchoAssignment, ...]
    unassigned_echo_ids: tuple[str, ...]
    ambiguous_echo_ids: tuple[str, ...]
    missed_paths: tuple[tuple[str, str, str], ...]
    input_echo_count: int
    usable_echo_count: int
    excluded_nonobserved_echo_count: int
    unassigned_detection_count: int
    missed_path_count: int
    association_accuracy: float | None
    dimension_fit: ShoeboxDimensionEstimate | None
    converged: bool
    runtime_s: float
    warnings: tuple[str, ...]


def estimate_dimensions_from_unlabeled_echoes(
    observations: CalibratedTOAObservationSet,
    *,
    initial_dimensions_m: tuple[float, float, float],
    upper_bounds_m: tuple[float, float, float],
    association_scale_s: float = 1e-4,
    max_match_error_s: float = 2e-3,
    missing_path_penalty: float = 9.0,
    false_detection_penalty: float = 9.0,
    ambiguity_cost_gap: float = 1.0,
    max_iterations: int = 20,
    dimension_tolerance_m: float = 1e-8,
    interior_clearance_m: float = 1e-6,
    dimension_default_uncertainty_s: float | None = None,
    max_nfev: int = 500,
) -> UnlabeledEchoDimensionResult:
    """Alternate one-to-one echo assignment and the Phase 5D.2 dimension fit.

    Each microphone/event pair is assigned independently at the current room
    dimensions using a square-augmented Hungarian problem. Its six predicted
    wall paths and the pair's detected echoes form a bipartite matching.
    Matching cost is squared timing residual divided by `association_scale_s`
    or the observation's positive uncertainty. Unmatched predicted paths and
    unmatched detections incur separate configurable penalties. A hard time
    gate disallows implausible matches. The six room dimensions are shared
    across all pairs through the subsequent Phase 5D.2 fit.

    Assignment is not based on global arrival order. Repeated assignment and
    dimension fitting is a non-convex alternating procedure; starts matter,
    ties can remain ambiguous, and convergence is not a correctness claim.
    No wall labels are read from the observation records.
    """
    _validate_options(
        association_scale_s,
        max_match_error_s,
        missing_path_penalty,
        false_detection_penalty,
        ambiguity_cost_gap,
        max_iterations,
        dimension_tolerance_m,
    )
    if dimension_default_uncertainty_s is not None and (
        not np.isfinite(dimension_default_uncertainty_s) or dimension_default_uncertainty_s <= 0.0
    ):
        raise ValueError("dimension_default_uncertainty_s must be finite and positive")
    if not isinstance(observations, CalibratedTOAObservationSet):
        raise TypeError("observations must be CalibratedTOAObservationSet")
    if observations.labeled_first_order_reflections:
        raise ValueError("unlabeled association accepts observations without labeled reflections")
    started_all = perf_counter()
    usable = [item for item in observations.unlabeled_echoes if item.reading.status == "observed"]
    excluded = len(observations.unlabeled_echoes) - len(usable)
    inputs = observations.inputs
    groups: dict[tuple[str, str], list] = defaultdict(list)
    for echo in usable:
        groups[(echo.microphone_id, echo.event_id)].append(echo)
    pair_keys = [
        (microphone.microphone_id, event.event_id)
        for event in inputs.source_events
        for microphone in inputs.microphone_array.microphones
    ]
    current = np.asarray(initial_dimensions_m, dtype=np.float64)
    if current.shape != (3,) or not np.all(np.isfinite(current)) or np.any(current <= 0.0):
        raise ValueError("initial_dimensions_m must contain three positive finite dimensions")
    upper = np.asarray(upper_bounds_m, dtype=np.float64)
    if upper.shape != (3,) or not np.all(np.isfinite(upper)) or np.any(upper <= current):
        raise ValueError("upper_bounds_m must contain three finite values greater than the initial dimensions")

    history: list[EchoAssociationIteration] = []
    prior_signature = None
    fit: ShoeboxDimensionEstimate | None = None
    final_assignments: tuple[EchoAssignment, ...] = ()
    final_unassigned: tuple[str, ...] = ()
    final_ambiguous: tuple[str, ...] = ()
    final_missed_paths: tuple[tuple[str, str, str], ...] = ()
    final_missed = 0
    converged = False
    warnings: list[str] = []

    for iteration in range(max_iterations):
        step_started = perf_counter()
        room = ShoeboxRoom(tuple(float(v) for v in current), inputs.speed_of_sound_m_s)
        predicted = predict_first_order_arrivals(inputs, room, boundary_tolerance_m=interior_clearance_m)
        by_pair: dict[tuple[str, str], dict[str, float]] = defaultdict(dict)
        for arrival in predicted:
            if arrival.reflection_order == 1:
                by_pair[(arrival.microphone_id, arrival.event_id)][arrival.wall_id] = arrival.arrival_time_s

        step_assignments: list[EchoAssignment] = []
        step_unassigned: list[str] = []
        step_ambiguous: list[str] = []
        association_objective = 0.0
        assigned_by_pair: dict[tuple[str, str], dict[str, object]] = {}
        for pair in pair_keys:
            echoes = groups.get(pair, [])
            wall_times = by_pair[pair]
            matches, unmatched, _, ambiguous, objective = _assign_pair(
                pair,
                echoes,
                wall_times,
                association_scale_s=association_scale_s,
                max_match_error_s=max_match_error_s,
                missing_path_penalty=missing_path_penalty,
                false_detection_penalty=false_detection_penalty,
                ambiguity_cost_gap=ambiguity_cost_gap,
            )
            step_assignments.extend(matches)
            step_unassigned.extend(unmatched)
            step_ambiguous.extend(ambiguous)
            association_objective += objective
            assigned_by_pair[pair] = {m.wall_id: m for m in matches}

        missed_paths = tuple(
            (pair[0], pair[1], wall)
            for pair in pair_keys
            for wall in WALLS
            if wall not in assigned_by_pair[pair]
        )

        signature = tuple(sorted((a.microphone_id, a.event_id, a.echo_id, a.wall_id) for a in step_assignments))
        changed = len(set(signature).symmetric_difference(set(prior_signature or ())))
        labeled = []
        for pair in pair_keys:
            matches = assigned_by_pair[pair]
            echo_lookup = {item.echo_id: item for item in groups.get(pair, [])}
            for wall in WALLS:
                match = matches.get(wall)
                if match is None:
                    reading = TOAReading(None, status="missing")
                else:
                    reading = echo_lookup[match.echo_id].reading
                labeled.append(FirstOrderReflectionTOAObservation(
                    pair[0], pair[1], wall, reading, "estimated_association"
                ))
        associated_data = CalibratedTOAObservationSet(
            observations.inputs,
            observations.origin,
            direct_paths=observations.direct_paths,
            labeled_first_order_reflections=tuple(labeled),
        )
        used_sigmas = [
            item.reading.uncertainty_s
            for item in labeled
            if item.reading.status == "observed"
        ]
        has_sigma = any(value is not None for value in used_sigmas)
        has_missing_sigma = any(value is None for value in used_sigmas)
        if has_sigma and has_missing_sigma and dimension_default_uncertainty_s is None:
            raise ValueError(
                "mixed matched-echo uncertainties require dimension_default_uncertainty_s"
            )
        fit = estimate_shoebox_dimensions(
            associated_data,
            initial_dimensions_m=tuple(float(v) for v in current),
            upper_bounds_m=tuple(float(v) for v in upper),
            interior_clearance_m=interior_clearance_m,
            default_uncertainty_s=dimension_default_uncertainty_s,
            max_nfev=max_nfev,
        )
        final_assignments = tuple(sorted(step_assignments, key=lambda a: (a.microphone_id, a.event_id, a.echo_id)))
        final_unassigned = tuple(sorted(step_unassigned))
        final_ambiguous = tuple(sorted(step_ambiguous))
        final_missed_paths = missed_paths
        final_missed = len(missed_paths)
        next_dimensions = fit.estimated_dimensions_m
        history.append(EchoAssociationIteration(
            iteration=iteration,
            dimensions_before_m=tuple(float(v) for v in current),
            dimensions_after_m=next_dimensions,
            assignments=final_assignments,
            unassigned_echo_ids=final_unassigned,
            missed_paths=missed_paths,
            missed_wall_paths=len(missed_paths),
            ambiguous_echo_ids=final_ambiguous,
            association_objective=association_objective,
            dimension_fit=fit,
            changed_assignments=changed,
            runtime_s=perf_counter() - step_started,
        ))
        if fit.status != "converged" or next_dimensions is None:
            warnings.append(f"dimension fit did not converge: {fit.status}: {fit.termination_message}")
            break
        dimension_change = float(np.max(np.abs(np.asarray(next_dimensions) - current)))
        if prior_signature == signature and dimension_change <= dimension_tolerance_m:
            converged = True
            current = np.asarray(next_dimensions)
            break
        prior_signature = signature
        current = np.asarray(next_dimensions)
        if np.any(current >= upper) or np.any(current <= fit.lower_bounds_m):
            warnings.append("dimension update reached a configured or derived bound; another iteration cannot start")
            break

    if not converged and len(history) == max_iterations:
        warnings.append("alternating procedure reached max_iterations before assignments and dimensions stabilized")
    total_echoes = len(usable)
    unassigned_detection_count = len(final_unassigned)
    accuracy = None
    status = "converged" if converged else ("dimension_fit_failed" if fit is not None and fit.status != "converged" else "max_iterations")
    if not usable:
        warnings.append("no observed unlabeled echoes were available")
    return UnlabeledEchoDimensionResult(
        status=status,
        estimated_dimensions_m=fit.estimated_dimensions_m if fit is not None else None,
        iterations=tuple(history),
        final_assignments=final_assignments,
        unassigned_echo_ids=final_unassigned,
        ambiguous_echo_ids=final_ambiguous,
        missed_paths=final_missed_paths,
        input_echo_count=len(observations.unlabeled_echoes),
        usable_echo_count=total_echoes,
        excluded_nonobserved_echo_count=excluded,
        unassigned_detection_count=unassigned_detection_count,
        missed_path_count=final_missed,
        association_accuracy=accuracy,
        dimension_fit=fit,
        converged=converged,
        runtime_s=perf_counter() - started_all,
        warnings=tuple(warnings),
    )


def _assign_pair(
    pair,
    echoes,
    wall_times,
    *,
    association_scale_s,
    max_match_error_s,
    missing_path_penalty,
    false_detection_penalty,
    ambiguity_cost_gap,
):
    echo_count = len(echoes)
    wall_count = len(WALLS)
    size = wall_count + echo_count
    if not echo_count:
        return (), (), wall_count, (), wall_count * missing_path_penalty
    times = np.asarray([wall_times[wall] for wall in WALLS], dtype=np.float64)
    observed = np.asarray([item.reading.arrival_time_s for item in echoes], dtype=np.float64)
    # Keep early assignment costs broad enough for the configured hard gate.
    # The dimension fit itself still uses the original measurement
    # uncertainties through the unchanged Phase 5D.2 objective.
    assignment_floor = max(association_scale_s, max_match_error_s / 3.0)
    scales = np.asarray([
        max(
            item.reading.uncertainty_s
            if item.reading.uncertainty_s is not None
            else association_scale_s,
            assignment_floor,
        )
        for item in echoes
    ], dtype=np.float64)
    if np.any(scales <= 0.0):
        raise ValueError("observed echo uncertainty must be positive")
    delta = times[:, None] - observed[None, :]
    costs = (delta / scales[None, :]) ** 2
    valid = np.abs(delta) <= max_match_error_s
    costs[~valid] = missing_path_penalty + false_detection_penalty + 1e12
    matrix = np.full((size, size), 0.0, dtype=np.float64)
    matrix[:wall_count, :echo_count] = costs
    matrix[:wall_count, echo_count:] = missing_path_penalty
    matrix[wall_count:, :echo_count] = false_detection_penalty
    matrix[wall_count:, echo_count:] = 0.0
    rows, columns = linear_sum_assignment(matrix)
    assignments = []
    matched_walls = set()
    matched_echoes = set()
    objective = 0.0
    for row, column in zip(rows, columns):
        objective += float(matrix[row, column])
        if row < wall_count and column < echo_count and valid[row, column]:
            echo = echoes[column]
            wall = WALLS[row]
            assignments.append(EchoAssignment(
                pair[0], pair[1], echo.echo_id, wall,
                float(observed[column]), float(times[row]),
                float(observed[column] - times[row]), float(costs[row, column]),
            ))
            matched_walls.add(row)
            matched_echoes.add(column)
    unassigned = tuple(echoes[index].echo_id for index in range(echo_count) if index not in matched_echoes)
    missed = wall_count - len(matched_walls)
    ambiguous = []
    # Compare the selected global one-to-one assignment against alternatives
    # with each chosen edge forbidden. This detects assignment-level ties that
    # nearest-arrival comparisons alone can miss.
    for row, column in zip(rows, columns):
        if row >= wall_count or column >= echo_count or not valid[row, column]:
            continue
        alternative = matrix.copy()
        alternative[row, column] = 1e15
        alt_rows, alt_columns = linear_sum_assignment(alternative)
        alternative_objective = float(alternative[alt_rows, alt_columns].sum())
        if alternative_objective - objective <= ambiguity_cost_gap:
            ambiguous.append(echoes[column].echo_id)
    return tuple(assignments), unassigned, missed, tuple(ambiguous), objective


def _validate_options(scale, gate, missing, false, ambiguity, iterations, dimension_tolerance):
    values = (scale, gate, missing, false, ambiguity, dimension_tolerance)
    if not all(np.isfinite(value) for value in values):
        raise ValueError("association options must be finite")
    if scale <= 0.0 or gate <= 0.0:
        raise ValueError("association_scale_s and max_match_error_s must be positive")
    if missing <= 0.0 or false <= 0.0 or ambiguity < 0.0 or dimension_tolerance < 0.0:
        raise ValueError("assignment penalties must be positive and tolerances non-negative")
    if not isinstance(iterations, int) or iterations < 1:
        raise ValueError("max_iterations must be a positive integer")
