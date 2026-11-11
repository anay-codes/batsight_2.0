"""Phase 5C.10: competing-endpoint unknown-wall solver investigation.

Exploratory only. Uses the corrected C9 predictor/objective and archived C8
observations. No true wall geometry is used for initialization, constraints,
or scoring in competing-endpoint runs.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
from time import perf_counter

import numpy as np
from scipy.optimize import least_squares
from scipy.spatial.transform import Rotation

HERE = Path(__file__).resolve().parent
OUT = HERE / "phase5c10_results.json"
SEEDS = (101, 202, 303, 404, 505)
MAX_NFEV = 200
FACE_WEIGHT = 10.0
TOL = 1e-11


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, HERE / file)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


P59 = load("phase5c9_c10", "phase5c9_unknown_wall_solver_validation.py")
P58 = P59.P58


def fixed_endpoint_observations():
    result = json.loads((HERE / "phase5c9_results.json").read_text(encoding="utf-8"))
    target = np.asarray(json.loads((HERE / "phase5c8_results.json").read_text(encoding="utf-8"))
                        ["observations"]["observed_echo_TOAs_s_sorted_within_each_group"], dtype=np.float64)
    endpoints = P59.unpack_endpoint_vectors()
    # Verify we use the exact validated observation array and archived endpoint.
    _, _, _, _, _, regenerated, _, _ = P58.make_observations()
    if not np.array_equal(target, regenerated):
        raise RuntimeError("C8 observation matrix does not match deterministic seed-11 generation")
    return endpoints, target, result


def plane_from_normal_gaps(normals, points, gaps):
    span = max(float(np.ptp(points, axis=0).max()), 1.0)
    floor = 1e-4 * span
    offsets = -np.max(points @ normals.T, axis=0) - gaps
    encoded_gap = gaps - floor
    if np.any(encoded_gap <= 0):
        raise ValueError("initialization gap must exceed the parameterization floor")
    az = np.arctan2(normals[:, 1], normals[:, 0])
    el = np.arcsin(np.clip(normals[:, 2], -1, 1))
    return np.r_[np.column_stack((az, el)).ravel(), np.log(encoded_gap)], offsets


def pca_frame(points):
    centered = points - points.mean(axis=0)
    _, _, vt = np.linalg.svd(centered, full_matrices=False)
    frame = vt[:3].T
    if np.linalg.det(frame) < 0:
        frame[:, -1] *= -1
    return frame


def data_derived_starts(endpoint):
    points = np.vstack((endpoint["mics"], endpoint["sources"]))
    span = max(float(np.ptp(points, axis=0).max()), 1.0)
    base = pca_frame(points)
    starts = []
    # PCA and deterministic SO(3) perturbations of that data-derived frame.
    rotations = [("pca_0deg", np.eye(3))]
    for seed, degrees in zip(SEEDS, (10.0, 20.0, 35.0, 55.0, 80.0)):
        rng = np.random.default_rng(seed)
        axis = rng.normal(size=3); axis /= np.linalg.norm(axis)
        rotations.append((f"pca_rot_{degrees:g}deg_seed_{seed}", Rotation.from_rotvec(axis * np.deg2rad(degrees)).as_matrix()))
    for label, rotation in rotations:
        frame = base @ rotation
        normals = np.vstack((frame.T, -frame.T))
        for fraction in (0.03, 0.08, 0.16):
            gaps = np.full(6, fraction * span)
            x, _ = plane_from_normal_gaps(normals, points, gaps)
            starts.append({"name": f"{label}_gap_{fraction:g}span", "x": x, "frame_label": label, "gap_fraction_span": fraction})
    # C9 PCA baseline included verbatim as a regression-comparable start.
    starts.append({"name": "C9_PCA_start", "x": P58.initial_start(-1, points), "frame_label": "C9_PCA", "gap_fraction_span": 0.12})
    return starts


def residual_parts(x, endpoint, target, points, face_weight=FACE_WEIGHT, fixed_rank=None):
    normals, offsets, gaps = P58.plane_parameters(x, points)
    pred, order, _, distances = P59.corrected_echoes_with_associations(endpoint, normals, offsets)
    if fixed_rank is not None:
        # Fixed-rank diagnostic: map each plane's oracle-start rank to that
        # observed rank. This is used only in the assignment-aware block method.
        unsorted = np.take_along_axis(pred, np.argsort(order, axis=2), axis=2)
        assigned_target = np.take_along_axis(target, fixed_rank, axis=2)
        echo_residual = unsorted - assigned_target
    else:
        echo_residual = pred - target
    face = P58.face_penetration_residuals(endpoint["mics"], endpoint["sources"], normals, offsets)
    return normals, offsets, gaps, pred, order, distances, echo_residual, face


def objective_residual(x, endpoint, target, points, face_weight=FACE_WEIGHT, fixed_rank=None):
    *_, echo, face = residual_parts(x, endpoint, target, points, face_weight, fixed_rank)
    return np.r_[(P58.C * echo).ravel(), (face_weight * P58.C * face).ravel()]


def diagnostics(x, endpoint, target, points, optimizer=None, *, name=None, start=None, runtime=0.0, face_weight=FACE_WEIGHT, fixed_rank=None):
    normals, offsets, gaps, pred, order, distances, echo, face = residual_parts(x, endpoint, target, points, face_weight, fixed_rank)
    enclosure = P58.feasible_geometry(normals, offsets, points, gaps)
    finite_face = P58.reflection_face_validity(endpoint["mics"], endpoint["sources"], normals, offsets)
    # Continuous diagnostics on the current sorted assignment branch.
    fun = lambda z: objective_residual(z, endpoint, target, points, face_weight, fixed_rank)
    jac = P59.central_jac(fun, x, 1e-6)
    sv = np.linalg.svd(jac, compute_uv=False)
    rank = int(np.count_nonzero(sv > sv[0] * 1e-8))
    init_order = None
    initial_echo_norm = None
    if start is not None:
        init_parts = residual_parts(start, endpoint, target, points, face_weight, fixed_rank)
        init_order = init_parts[4]
        initial_echo_norm = float(np.linalg.norm(init_parts[6]))
    min_gap = float(np.min(np.diff(pred, axis=2)))
    echo_obj = float(0.5 * np.sum((P58.C * echo) ** 2))
    face_obj = float(0.5 * np.sum((face_weight * P58.C * face) ** 2))
    return {
        "name": name,
        "initial_reflection_residual_norm_s": initial_echo_norm,
        "reflection_residual_norm_s": float(np.linalg.norm(echo)),
        "reflection_max_abs_residual_s": float(np.max(np.abs(echo))),
        "reflection_residual_by_microphone_s": np.linalg.norm(echo, axis=(1, 2)).tolist(),
        "reflection_residual_by_source_s": np.linalg.norm(echo, axis=(0, 2)).tolist(),
        "reflection_residual_by_arrival_rank_s": np.linalg.norm(echo, axis=(0, 1)).tolist(),
        "echo_objective_half_squared_m2": echo_obj,
        "face_penalty_half_squared_m2": face_obj,
        "face_penalty_weight": face_weight,
        "convex_enclosure": enclosure,
        "positive_paths": bool(np.all(np.isfinite(distances)) and np.all(distances > 0) and np.all(pred > 0)),
        "minimum_path_length_m": float(np.min(distances)),
        "minimum_arrival_s": float(np.min(pred)),
        "finite_face_bounce_validity": finite_face,
        "all_physical_checks_pass": bool(enclosure["valid_enclosure"] and np.all(distances > 0) and np.all(pred > 0) and finite_face["all_bounces_on_finite_faces"]),
        "minimum_adjacent_sorted_echo_gap_s": min_gap,
        "assignment_changed_groups_from_start": None if init_order is None else int(np.count_nonzero(np.any(order != init_order, axis=2))),
        "plane_normal_matrix_condition": enclosure["normal_matrix_condition"],
        "scaled_plane_design_condition": enclosure["scaled_plane_design_condition"],
        "jacobian_rank_relative_1e-8": rank,
        "jacobian_singular_values": sv.tolist(),
        "jacobian_condition": float(sv[0] / sv[-1]) if sv[-1] else float("inf"),
        "optimizer_success": None if optimizer is None else bool(optimizer.success),
        "optimizer_status": None if optimizer is None else int(optimizer.status),
        "optimizer_message": None if optimizer is None else str(optimizer.message),
        "nfev": None if optimizer is None else int(optimizer.nfev),
        "runtime_s": float(runtime),
        "parameters": np.asarray(x).tolist(),
        "normals": normals.tolist(),
        "offsets_m": offsets.tolist(),
        "support_gaps_m": gaps.tolist(),
    }


def fit(endpoint, target, x0, *, max_nfev=MAX_NFEV, face_weight=FACE_WEIGHT, x_scale="jac", fixed_rank=None, name=None):
    points = np.vstack((endpoint["mics"], endpoint["sources"]))
    fun = lambda x: objective_residual(x, endpoint, target, points, face_weight, fixed_rank)
    begin = perf_counter()
    opt = least_squares(fun, x0, method="trf", x_scale=x_scale, max_nfev=max_nfev, ftol=TOL, xtol=TOL, gtol=TOL)
    runtime = perf_counter() - begin
    return diagnostics(opt.x, endpoint, target, points, opt, name=name, start=x0, runtime=runtime, face_weight=face_weight, fixed_rank=fixed_rank)


def fixed_assignment_refinement(endpoint, target, x0, rounds=4, inner_nfev=120):
    """Block-coordinate solve: freeze current optimal assignment, refit, repeat."""
    points = np.vstack((endpoint["mics"], endpoint["sources"]))
    x = x0.copy(); history=[]; total_time=0.0; total_nfev=0
    for r in range(rounds):
        normals, offsets, _, pred, order, _, _, _ = residual_parts(x, endpoint, target, points)
        rank = np.argsort(order, axis=2)
        begin = perf_counter()
        row = fit(endpoint, target, x, max_nfev=inner_nfev, face_weight=FACE_WEIGHT, fixed_rank=rank, name=f"fixed_assignment_round_{r}")
        total_time += row["runtime_s"]; total_nfev += row["nfev"] or 0
        x = np.asarray(row["parameters"])
        # Re-score against the true sorted minimum-assignment objective.
        rescored = diagnostics(x, endpoint, target, points, name=f"reassigned_round_{r}", start=None)
        history.append({"round": r, "fixed_rank_objective_echo_norm_s": row["reflection_residual_norm_s"], "reassigned_sorted_echo_norm_s": rescored["reflection_residual_norm_s"], "all_physical_checks_pass": rescored["all_physical_checks_pass"], "optimizer_success": row["optimizer_success"], "optimizer_status": row["optimizer_status"], "optimizer_message": row["optimizer_message"], "nfev": row["nfev"], "runtime_s": row["runtime_s"]})
    final = diagnostics(x, endpoint, target, points, name="assignment_aware_final", runtime=total_time)
    final.update({"rounds": rounds, "total_nfev": total_nfev, "round_history": history, "assignment_strategy": "recompute exact sorted one-dimensional optimal matching between least-squares blocks"})
    return final


def main():
    endpoints, target, c9 = fixed_endpoint_observations()
    competing = endpoints["competing"]
    generating = endpoints["generating"]
    points_c = np.vstack((competing["mics"], competing["sources"]))
    points_g = np.vstack((generating["mics"], generating["sources"]))

    starts = data_derived_starts(competing)
    # Score starts by the baseline objective before spending optimization effort.
    ranked=[]
    for s in starts:
        normals, offsets, gaps = P58.plane_parameters(s["x"], points_c)
        pred, order, _, _ = P59.corrected_echoes_with_associations(competing, normals, offsets)
        face = P58.face_penetration_residuals(competing["mics"], competing["sources"], normals, offsets)
        echo = pred-target
        init_cost=float(np.dot((P58.C*echo).ravel(),(P58.C*echo).ravel()) + np.dot((FACE_WEIGHT*P58.C*face).ravel(),(FACE_WEIGHT*P58.C*face).ravel()))
        ranked.append({**s,"initial_cost":init_cost})
    starts_results=[]
    for s in ranked:
        row=fit(competing,target,s["x"],max_nfev=MAX_NFEV,name=s["name"])
        row["frame_label"]=s["frame_label"];row["gap_fraction_span"]=s["gap_fraction_span"];row["initial_total_cost_m2"]=s["initial_cost"]
        starts_results.append(row)

    best = min(starts_results, key=lambda x: x["echo_objective_half_squared_m2"]+x["face_penalty_half_squared_m2"])
    best_x=np.asarray(best["parameters"])
    baseline_c9=next(r for r in c9["blind_start_investigation"]["runs_by_endpoint"]["competing"] if r["seed"]==-1)
    baseline_start=np.asarray(P58.initial_start(-1,points_c))

    # Solver variants start from baseline PCA or best data-derived candidate.
    continuation=[]
    x=baseline_start.copy()
    for weight in (0.0,0.1,1.0,FACE_WEIGHT):
        row=fit(competing,target,x,max_nfev=250,face_weight=weight,name=f"continuation_weight_{weight:g}")
        continuation.append(row);x=np.asarray(row["parameters"])

    explicit_scale=np.r_[np.full(12,0.25),np.ones(6)]
    scaled=fit(competing,target,baseline_start,max_nfev=400,x_scale=explicit_scale,name="PCA_explicit_parameter_scaling")
    assignment_fit=fixed_assignment_refinement(competing,target,baseline_start,rounds=4,inner_nfev=120)

    # Generating endpoint PCA positive-control regression, run with the exact C9
    # start and corrected C9 objective; this never initializes competing fits.
    gen_start=P58.initial_start(-1,points_g)
    gen_regression=fit(generating,target,gen_start,max_nfev=400,name="generating_C9_PCA_regression")

    output={
        "phase":"5C.10 competing endpoint reflection-fit investigation",
        "preservation":{"C8_and_C9_archives_unchanged":True,"endpoint_vectors_from_phase5c6_verbatim":True,"C8_echoes_exactly_verified_against_seed11":True},
        "observations":{"shape":list(target.shape),"count":int(target.size),"observation_source":"exact phase5c8_results.json sorted echo matrix","true_wall_data_passed_to_inverse":False,"known_face_count":6,"wall_labels_passed":False},
        "baseline":{"corrected_predictor_objective":"C9 corrected source-plane dot product and C8 finite-face hinge; sorted TOA matching; weight 10", "C9_competing_PCA_result":baseline_c9,"baseline_start_parameters":baseline_start.tolist()},
        "competing_data_derived_multistart":starts_results,
        "competing_solver_variants":{"face_penalty_continuation":continuation,"explicit_parameter_scaling":scaled,"assignment_aware_fixed_correspondence_blocks":assignment_fit},
        "generating_regression_positive_control":gen_regression,
        "analysis":{"fit_endpoint_coordinates_and_timing_fixed":True,"true_walls_used_in_any_initialization_or_objective":False,"ground_truth_wall_error_scoring_used":False,"interpretation":"All candidates are numerical fits only; finite-run failure does not prove metric incompatibility."},
        "settings":{"data_derived_orientation_starts":len(starts),"orientation_rotations_degrees":[0,10,20,35,55,80],"gap_fractions_of_candidate_span":[0.03,0.08,0.16],"seed_set":list(SEEDS),"baseline_max_nfev":MAX_NFEV,"face_weight_continuation":[0,0.1,1,10],"jacobian_condition_threshold":1e-8,"optimizer_tolerances":TOL},
    }
    OUT.write_text(json.dumps(output,indent=2),encoding="utf-8")
    print("generating regression",gen_regression["reflection_residual_norm_s"],gen_regression["finite_face_bounce_validity"]["valid_first_order_bounce_count"],gen_regression["optimizer_success"],gen_regression["nfev"])
    print("competing starts")
    for r in sorted(starts_results,key=lambda z:z["reflection_residual_norm_s"]):
        print(r["name"],"res",r["reflection_residual_norm_s"],"max",r["reflection_max_abs_residual_s"],"physical",r["all_physical_checks_pass"],"bounces",r["finite_face_bounce_validity"]["valid_first_order_bounce_count"],"status",r["optimizer_status"],"nfev",r["nfev"],"time",r["runtime_s"])
    print("continuation",[(r["name"],r["reflection_residual_norm_s"],r["all_physical_checks_pass"],r["optimizer_status"],r["nfev"]) for r in continuation])
    print("scaling",scaled["reflection_residual_norm_s"],scaled["all_physical_checks_pass"],scaled["optimizer_status"],scaled["nfev"])
    print("assignment aware",assignment_fit["reflection_residual_norm_s"],assignment_fit["all_physical_checks_pass"],assignment_fit["total_nfev"])
    print("results_json",OUT)


if __name__=="__main__":
    main()
