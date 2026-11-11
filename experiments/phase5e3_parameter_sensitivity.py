"""Phase 5E.3 deterministic diagnostics; never changes estimator modules."""

from __future__ import annotations

import json
import math
from pathlib import Path
from time import perf_counter

import numpy as np
try:
    from .shoebox_clutter_aware_recovery import STARTS, UPPER, _make_case, _truth_map
except ImportError:  # Direct script execution with experiments/ on sys.path.
    from shoebox_clutter_aware_recovery import STARTS, UPPER, _make_case, _truth_map
from batsight.datasets import CalibratedTOAObservationSet, FirstOrderReflectionTOAObservation
from batsight.reconstruction.clutter_aware_association import estimate_dimensions_clutter_aware
from batsight.reconstruction.echo_association import estimate_dimensions_from_unlabeled_echoes
from batsight.reconstruction.shoebox_dimensions import estimate_shoebox_dimensions


GATES_S = (0.002, 0.006, 0.012, 0.025)
DUMMY_PAIRS = ((1.0, 1.0), (3.0, 3.0), (9.0, 9.0), (25.0, 25.0), (1.0, 9.0), (9.0, 1.0))
STRENGTH_WEIGHTS = (0.0, 0.25, 1.0)
INITIAL = STARTS[0]
SCALE_S = 1e-4
CONSISTENCY_GATE_S = 5e-4
RECOVERY_MAX_ABS_M = 0.05
RECOVERY_MAX_PERCENT = 2.0


def match_preferred_to_unmatched(match_cost: float, missing_cost: float, clutter_cost: float) -> bool:
    """Return whether one match beats leaving both endpoints unmatched.

    In the augmented one-to-one assignment, matching one wall/detection avoids
    one missing-wall dummy and one clutter-detection dummy. Equality is a tie.
    This helper audits the isolated local cost comparison, not all global
    assignment interactions.
    """
    return match_cost < missing_cost + clutter_cost


def _score(case, result, method: str, candidate_truth: dict[str, tuple[str, int]],
           settings: dict[str, float]) -> dict:
    assigned = {item.echo_id: item.wall_id for item in result.final_assignments}
    first = {key: wall for key, (wall, order) in candidate_truth.items() if order == 1}
    nonfirst = {key for key, (_, order) in candidate_truth.items() if order != 1}
    known = set(candidate_truth) | set(case["false_ids"])
    clutter = nonfirst | set(case["false_ids"])
    tp = sum(assigned.get(echo_id) == wall for echo_id, wall in first.items())
    wrong_first = sum(echo_id in assigned and assigned[echo_id] != wall for echo_id, wall in first.items())
    assigned_known_clutter = sum(echo_id in assigned for echo_id in clutter)
    known_assigned = sum(echo_id in assigned for echo_id in known)
    unassigned_clutter = sum(echo_id not in assigned for echo_id in clutter)
    classified_correct = tp + unassigned_clutter
    expected_first = sum(path["order"] == 1 for paths in case["truth"].values() for path in paths)
    detected_first = len(first)
    dimensions = result.estimated_dimensions_m
    truth_dimensions = case["dimensions_truth_evaluation_only_m"]
    abs_error = [abs(a-b) for a,b in zip(dimensions, truth_dimensions)] if dimensions else None
    pct_error = [100*e/d for e,d in zip(abs_error,truth_dimensions)] if abs_error else None
    fit = result.dimension_fit
    pair_count = len(case["observations"].inputs.microphone_array.microphones) * len(case["observations"].inputs.source_events)
    physical = bool(fit and fit.physical_valid)
    return {
        "method": method,
        "settings": settings,
        "status": result.status,
        "optimizer_success": bool(fit.optimizer_success) if fit else False,
        "optimizer_status": fit.optimizer_status if fit else None,
        "function_evaluations": fit.function_evaluations if fit else None,
        "physical_valid": physical,
        "estimated_dimensions_m": dimensions,
        "dimension_absolute_error_m": abs_error,
        "dimension_percentage_error": pct_error,
        "mean_dimension_error_m": sum(abs_error)/3 if abs_error else None,
        "maximum_dimension_error_m": max(abs_error) if abs_error else None,
        "maximum_dimension_error_percent": max(pct_error) if pct_error else None,
        "recovery_pass": bool(result.status == "converged" and physical and abs_error and max(abs_error) <= RECOVERY_MAX_ABS_M and max(pct_error) <= RECOVERY_MAX_PERCENT),
        "toa_residual_rms_s": fit.residual_statistics.rms_s if fit and fit.residual_statistics else None,
        "jacobian_rank": fit.jacobian_rank if fit else None,
        "jacobian_condition_number": fit.jacobian_condition_number if fit else None,
        "runtime_s": result.runtime_s,
        "first_order_detection_recall": detected_first/expected_first if expected_first else None,
        "association_precision": tp/len(result.final_assignments) if result.final_assignments else 0.0,
        "association_recall_on_detected_first_order": tp/detected_first if detected_first else None,
        "association_accuracy_on_classified_detections": classified_correct/len(known) if known else None,
        "classification_coverage": len(known)/len(case["observations"].unlabeled_echoes) if case["observations"].unlabeled_echoes else None,
        "false_assignment_rate": (len(result.final_assignments)-tp)/len(result.final_assignments) if result.final_assignments else 0.0,
        "wrong_first_order_assignments": wrong_first,
        "assigned_known_clutter_count": assigned_known_clutter,
        "unassigned_detection_count": len(result.unassigned_echo_ids),
        "missed_first_order_path_count": max(0, expected_first-tp),
        "unmatched_predicted_wall_path_count": len(result.missed_paths) if hasattr(result, "missed_paths") else result.missed_path_count,
        "unassigned_injected_false_count": sum(echo_id not in assigned for echo_id in case["false_ids"]),
        "ambiguous_echo_count": len(result.ambiguous_echo_ids),
        "rejected_edge_count": len(getattr(result, "rejected_edges", ())),
        "iteration_count": len(result.iterations),
        "extraction_candidate_count": len(case["observations"].unlabeled_echoes),
        "truth_path_label_coverage": len(candidate_truth)/max(1, len(case["observations"].unlabeled_echoes)-len(case["false_ids"])),
    }


def _run_method(case, candidate_truth, method, *, sweep, gate, missing, clutter, strength=0.0):
    start = perf_counter()
    if method == "phase5d3_hungarian":
        result = estimate_dimensions_from_unlabeled_echoes(
            case["observations"], initial_dimensions_m=INITIAL, upper_bounds_m=UPPER,
            association_scale_s=SCALE_S, max_match_error_s=gate,
            missing_path_penalty=missing, false_detection_penalty=clutter,
            max_iterations=20, max_nfev=400,
        )
    else:
        result = estimate_dimensions_clutter_aware(
            case["observations"], initial_dimensions_m=INITIAL, upper_bounds_m=UPPER,
            association_scale_s=SCALE_S, maximum_match_error_s=gate,
            consistency_gate_s=CONSISTENCY_GATE_S,
            missing_path_penalty=missing, clutter_penalty=clutter,
            ambiguity_cost_gap=1.0, strength_weight=strength,
            max_iterations=20, max_nfev=400,
        )
    # Include orchestration overhead consistently for D5.3; E2 exposes total runtime.
    elapsed = perf_counter() - start
    record = _score(case, result, method, candidate_truth, {
        "sweep": sweep,
        "gate_s": gate, "missing_path_penalty": missing,
        "clutter_penalty": clutter, "strength_weight": strength,
        "consistency_gate_s": CONSISTENCY_GATE_S if method == "phase5e2_clutter_aware" else None,
    })
    record["runtime_s"] = elapsed
    return record


def _oracle_fit(case, candidate_truth):
    """Fit extracted candidates with post-hoc simulator labels, diagnostic only."""
    labels=[]
    for echo in case["observations"].unlabeled_echoes:
        truth=candidate_truth.get(echo.echo_id)
        if truth and truth[1] == 1:
            labels.append(FirstOrderReflectionTOAObservation(
                echo.microphone_id, echo.event_id, truth[0], echo.reading,
                "synthetic_ground_truth",
            ))
    oracle=CalibratedTOAObservationSet(
        case["observations"].inputs, "synthetic",
        direct_paths=case["observations"].direct_paths,
        labeled_first_order_reflections=tuple(labels),
    )
    start=perf_counter()
    fit=estimate_shoebox_dimensions(oracle, initial_dimensions_m=INITIAL,
                                    upper_bounds_m=UPPER, max_nfev=400)
    elapsed=perf_counter()-start
    errors=[abs(a-b) for a,b in zip(fit.estimated_dimensions_m,case["dimensions_truth_evaluation_only_m"])] if fit.estimated_dimensions_m else None
    return {
        "method":"oracle_detected_first_order_labels_diagnostic_only",
        "status":fit.status,"optimizer_success":fit.optimizer_success,
        "estimated_dimensions_m":fit.estimated_dimensions_m,
        "dimension_absolute_error_m":errors,
        "maximum_dimension_error_m":max(errors) if errors else None,
        "physical_valid":fit.physical_valid,
        "toa_residual_rms_s":fit.residual_statistics.rms_s if fit.residual_statistics else None,
        "jacobian_rank":fit.jacobian_rank,
        "jacobian_condition_number":fit.jacobian_condition_number,
        "function_evaluations":fit.function_evaluations,"runtime_s":elapsed,
        "labeled_observation_count":len(labels),
        "labels_entered_unlabeled_estimators":False,
        "limitations":"Uses post-hoc simulator labels only to isolate dimension fitting on extracted detections.",
    }


def _strength_summary(case, candidate_truth):
    """Post-hoc strength/path-order audit; never passed to an estimator."""
    grouped={"first_order":[],"higher_order":[],"injected_false":[],"unclassified":[]}
    by_wall={wall:[] for wall in ("x_min","x_max","y_min","y_max","z_min","z_max")}
    for echo in case["observations"].unlabeled_echoes:
        value=echo.detection_strength
        if value is None or not math.isfinite(float(value)):
            continue
        if echo.echo_id in case["false_ids"]:
            grouped["injected_false"].append(float(value)); continue
        label=candidate_truth.get(echo.echo_id)
        if label is None:
            grouped["unclassified"].append(float(value)); continue
        if label[1] == 1:
            grouped["first_order"].append(float(value)); by_wall[label[0]].append(float(value))
        else:
            grouped["higher_order"].append(float(value))
    def summary(values):
        return {"count":len(values),"mean":sum(values)/len(values) if values else None,
                "median":float(np.median(values)) if values else None,
                "q25":float(np.quantile(values,0.25)) if values else None,
                "q75":float(np.quantile(values,0.75)) if values else None}
    return {"posthoc_label_use_only":True,"strength_is_uncalibrated":True,
            "class_strength_statistics":{key:summary(vals) for key,vals in grouped.items()},
            "first_order_by_wall":{wall:summary(vals) for wall,vals in by_wall.items()}}


def main() -> None:
    specs=(
        ("nominal_asymmetric",(4.5,4.2,3.6),0.7,None,"standard"),
        ("noisy_asymmetric",(5.4,4.8,3.8),0.7,30.0,"alternate"),
        ("weak_reflections",(4.8,4.4,3.7),0.16,18.0,"standard"),
        ("close_arrival_symmetric",(4.0,4.0,3.0),0.7,None,"symmetric"),
    )
    cases=[]
    for name,dims,reflection,snr,layout in specs:
        case=_make_case(name,dims,seed=17,snr_db=snr,reflection=reflection,layout=layout)
        truth=_truth_map(case)
        rows=[]
        # Timing gate sensitivity for both unchanged baselines.
        for method in ("phase5d3_hungarian","phase5e2_clutter_aware"):
            for gate in GATES_S:
                rows.append(_run_method(case,truth,method,sweep="gate",gate=gate,missing=9.0,clutter=9.0))
        # Dummy cost sensitivity, including unequal miss/clutter costs.
        for method in ("phase5d3_hungarian","phase5e2_clutter_aware"):
            for missing,clutter in DUMMY_PAIRS:
                rows.append(_run_method(case,truth,method,sweep="dummy_cost",gate=0.006,missing=missing,clutter=clutter))
        # Strength is a separate 5E.2-only ablation, same observations and settings.
        for strength in STRENGTH_WEIGHTS:
            rows.append(_run_method(case,truth,"phase5e2_clutter_aware",sweep="strength",gate=0.006,
                                    missing=9.0,clutter=9.0,strength=strength))
        # D5.2 upper-bound/oracle labels isolate extraction + dimension fit.
        oracle=_oracle_fit(case,truth)
        first_detected=sum(1 for _,(_,order) in truth.items() if order==1)
        first_expected=sum(path["order"]==1 for paths in case["truth"].values() for path in paths)
        cases.append({
            "case":name,"seed":17,"dimensions_truth_evaluation_only_m":dims,
            "snr_db":snr,"reflection_coefficient":reflection,"layout":layout,
            "initial_dimensions_m_not_truth_derived":INITIAL,
            "audio_candidate_count":len(case["observations"].unlabeled_echoes),
            "injected_false_detection_count":len(case["false_ids"]),
            "extracted_first_order_detection_recall":first_detected/first_expected if first_expected else None,
            "oracle_dimension_fit_diagnostic":oracle,
            "reflection_strength_posthoc_audit":_strength_summary(case,truth),
            "estimators_received_truth_labels":False,
            "sensitivity_runs":rows,
        })
    output={
        "title":"Phase 5E.3 assignment failure analysis and parameter sensitivity",
        "synthetic_only":True,"seed_policy":"one fixed seed (17) per frozen 5E.2 scenario; each parameter comparison reuses the exact same generated audio/TOA observations",
        "estimators_modified":False,"ground_truth_used_only_for_post_run_scoring_and_explicit_oracle_fit":True,
        "recovery_criteria_predeclared":{"max_absolute_dimension_error_m":RECOVERY_MAX_ABS_M,"max_axis_percentage_error":RECOVERY_MAX_PERCENT,"converged_status_required":True,"physical_validity_required":True},
        "fixed_settings":{"initial_dimensions_m":INITIAL,"upper_bounds_m":UPPER,"association_scale_s":SCALE_S,"consistency_gate_s":CONSISTENCY_GATE_S,"max_association_iterations":20,"dimension_fit_max_nfev":400,"maximum_dimension_tolerance_m":1e-7},
        "sweeps":{"timing_gates_s":GATES_S,"dummy_cost_pairs_missing_then_clutter":DUMMY_PAIRS,"strength_weights":STRENGTH_WEIGHTS},
        "metric_definitions":{
            "first_order_detection_recall":"extracted candidate mapped post hoc to a first-order simulator path / all simulated first-order paths",
            "association_precision":"correct first-order wall assignments / all assigned detection-wall pairs",
            "association_recall_on_detected_first_order":"correct assigned first-order candidates / extracted candidates mapped post hoc to first-order paths",
            "association_accuracy_on_classified_detections":"correct first-order wall assignments plus known clutter left unassigned / detections mapped post hoc to first-/higher-order paths or injected false set",
            "false_assignment_rate":"wrong-wall first-order assignments plus assigned higher-order/injected detections / all assignments",
            "missed_first_order_path_count":"all simulated first-order paths minus correctly associated detected first-order paths; includes extraction misses",
            "unmatched_predicted_wall_path_count":"six times microphone/event pairs minus assigned wall predictions (or estimator's equivalent count)",
            "dimension_error":"estimated minus simulator dimensions, used only after fitting; strict pass requires status converged, physical validity, max absolute error <=0.05 m and max per-axis percent <=2%",
        },
        "cases":cases,
    }
    path=Path(__file__).with_name("phase5e3_parameter_sensitivity_results.json")
    path.write_text(json.dumps(output,indent=2),encoding="utf-8")
    print(f"Wrote {path} with {sum(len(c['sensitivity_runs']) for c in cases)} estimator fits and {len(cases)} oracle diagnostics")


if __name__ == "__main__":
    main()
