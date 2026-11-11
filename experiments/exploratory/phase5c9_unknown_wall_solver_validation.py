"""Phase 5C.9: validate C8 unknown-wall model and optimizer locally.

All true-wall calculations are explicitly oracle diagnostics. Blind trials are
conditional on passing oracle and perturbed-wall recovery checks.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
from time import perf_counter

import numpy as np
from scipy.optimize import linear_sum_assignment, least_squares

HERE = Path(__file__).resolve().parent
OUT = HERE / "phase5c9_results.json"
SEED11_ARCHIVE = HERE / "phase5c6_results.json"
P56_SPEC = importlib.util.spec_from_file_location("p56_c9", HERE / "phase5c6_blind_initialization.py")
P56 = importlib.util.module_from_spec(P56_SPEC)
sys.modules[P56_SPEC.name] = P56
P56_SPEC.loader.exec_module(P56)
P57_SPEC = importlib.util.spec_from_file_location("p57_c9", HERE / "phase5c7_competing_solution_disambiguation.py")
P57 = importlib.util.module_from_spec(P57_SPEC)
sys.modules[P57_SPEC.name] = P57
P57_SPEC.loader.exec_module(P57)
P58_SPEC = importlib.util.spec_from_file_location("p58_c9", HERE / "phase5c8_unknown_wall_reflection_fit.py")
P58 = importlib.util.module_from_spec(P58_SPEC)
sys.modules[P58_SPEC.name] = P58
P58_SPEC.loader.exec_module(P58)

CENTRAL_STEPS = (1e-4, 1e-5, 1e-6)
PERTURB_LEVELS = (0.005, 0.02, 0.05, 0.10)
SEED = 9209


def corrected_echoes_with_associations(endpoint, normals, offsets):
    """Independent corrected image predictor: source signed distance is n·s+d."""
    signed_source = endpoint["sources"] @ normals.T + offsets[None, :]
    images = endpoint["sources"][:, None, :] - 2.0 * signed_source[:, :, None] * normals[None, :, :]
    distances = np.linalg.norm(images[None, :, :, :] - endpoint["mics"][:, None, None, :], axis=3)
    if not np.all(np.isfinite(distances)) or np.any(distances <= 0):
        raise FloatingPointError("invalid image-source distance")
    arrivals = endpoint["emissions"][None, :, None] + endpoint["clocks"][:, None, None] + distances / P58.C
    order = np.argsort(arrivals, axis=2)
    return np.take_along_axis(arrivals, order, axis=2), order, images, distances


def true_planes_in_canonical_gauge(room, raw_mics):
    origin = raw_mics[0].copy()
    ex = raw_mics[1] - origin
    ex /= np.linalg.norm(ex)
    ey = raw_mics[2] - origin
    ey -= np.dot(ey, ex) * ex
    ey /= np.linalg.norm(ey)
    ez = np.cross(ex, ey)
    basis = np.column_stack((ex, ey, ez))
    dims = room.dimensions_m
    raw = [
        ([-1, 0, 0], 0), ([1, 0, 0], -dims[0]),
        ([0, -1, 0], 0), ([0, 1, 0], -dims[1]),
        ([0, 0, -1], 0), ([0, 0, 1], -dims[2]),
    ]
    normals, offsets = [], []
    for n, d in raw:
        nr = np.asarray(n, dtype=np.float64)
        normals.append(basis.T @ nr)
        offsets.append(float(nr @ origin + d))
    return np.asarray(normals), np.asarray(offsets), origin, basis


def encode_planes(normals, offsets, points):
    az = np.arctan2(normals[:, 1], normals[:, 0])
    el = np.arcsin(np.clip(normals[:, 2], -1, 1))
    span = max(float(np.ptp(points, axis=0).max()), 1.0)
    clearance_floor = 1e-4 * span
    gaps = -(np.max(points @ normals.T, axis=0) + offsets)
    if np.any(gaps <= clearance_floor):
        raise ValueError("oracle wall has insufficient margin for C8 parameterization floor")
    return np.r_[np.column_stack((az, el)).ravel(), np.log(gaps - clearance_floor)]


def unpack_endpoint_vectors():
    archived = json.loads(SEED11_ARCHIVE.read_text(encoding="utf-8"))
    runs = archived["problems"]["seed11_noise_0s"]["runs"]
    out = {}
    problem = P56.seed11_problem()
    length, time = P56.characteristic_scales(problem.q, problem.c)
    for name, label in (("generating", "oracle_positive_control"), ("competing", "Gaubitch100_plus_Crocco")):
        row = next(r for r in runs if r["initializer"] == label)
        model = P56.DirectFit(problem.q, problem.c, length, time)
        x = np.asarray(row["final_parameters_scaled"], dtype=np.float64)
        mics, sources, emissions, clocks = model.unpack(x)
        out[name] = {"archive_initializer": label, "parameters": x, "mics": mics, "sources": sources, "emissions": emissions, "clocks": clocks, "archive_row": row}
    return out


def oracle_residual_components(x, endpoint, target, points):
    normals, offsets, gaps = P58.plane_parameters(x, points)
    pred, order, _, _ = corrected_echoes_with_associations(endpoint, normals, offsets)
    echo_residual_s = pred - target
    face_violation_m = P58.face_penetration_residuals(endpoint["mics"], endpoint["sources"], normals, offsets)
    residual = np.r_[(echo_residual_s * P58.C).ravel(), (10.0 * P58.C * face_violation_m).ravel()]
    return residual, echo_residual_s, face_violation_m, normals, offsets, gaps, order


def residual_function(endpoint, target, points):
    return lambda x: oracle_residual_components(x, endpoint, target, points)[0]


def central_jac(fun, x, h):
    base = np.asarray(x, dtype=np.float64)
    cols = []
    for k in range(base.size):
        delta = np.zeros_like(base)
        delta[k] = h
        cols.append((fun(base + delta) - fun(base - delta)) / (2.0 * h))
    return np.column_stack(cols)


def scalar_objective(res):
    return 0.5 * float(np.dot(res, res))


def plane_errors(normals, offsets, true_normals, true_offsets):
    # Plane IDs are exchangeable. Match the unordered oriented-plane sets only
    # for evaluation; this assignment is never provided to the fit.
    angle_cost = np.arccos(np.clip(normals @ true_normals.T, -1.0, 1.0))
    scale = max(float(np.ptp(true_offsets)), 1.0)
    offset_cost = (offsets[:, None] - true_offsets[None, :]) / scale
    cost = angle_cost**2 + offset_cost**2
    rows, cols = linear_sum_assignment(cost)
    angle = angle_cost[rows, cols]
    doff = offsets[rows] - true_offsets[cols]
    return {
        "normal_angle_rmse_deg": float(np.rad2deg(np.sqrt(np.mean(angle**2)))),
        "normal_angle_max_deg": float(np.rad2deg(np.max(angle))),
        "offset_rmse_m": float(np.sqrt(np.mean(doff**2))),
        "offset_max_abs_m": float(np.max(np.abs(doff))),
        "evaluation_plane_assignment": cols.tolist(),
    }


def optimize_start(x0, endpoint, target, points, true_normals, true_offsets):
    fun = residual_function(endpoint, target, points)
    start_eval = oracle_residual_components(x0, endpoint, target, points)
    start_n, start_d, _ = start_eval[3], start_eval[4], start_eval[5]
    start_errors = plane_errors(start_n, start_d, true_normals, true_offsets)
    begin = perf_counter()
    opt = least_squares(fun, x0, method="trf", x_scale="jac", max_nfev=P58.MAX_NFEV, ftol=1e-11, xtol=1e-11, gtol=1e-11)
    runtime = perf_counter() - begin
    residual, echo, face, n, d, gaps, order = oracle_residual_components(opt.x, endpoint, target, points)
    pred, _, _, lengths = corrected_echoes_with_associations(endpoint, n, d)
    jac = np.asarray(opt.jac)
    sv = np.linalg.svd(jac, compute_uv=False)
    rank = int(np.count_nonzero(sv > sv[0] * 1e-8))
    enclosure = P58.feasible_geometry(n, d, points, gaps)
    face_valid = P58.reflection_face_validity(endpoint["mics"], endpoint["sources"], n, d)
    return {
        "initial_plane_errors": start_errors,
        "final_plane_errors": plane_errors(n, d, true_normals, true_offsets),
        "initial_reflection_residual_norm_s": float(np.linalg.norm(start_eval[1])),
        "initial_reflection_max_abs_residual_s": float(np.max(np.abs(start_eval[1]))),
        "final_reflection_residual_norm_s": float(np.linalg.norm(echo)),
        "final_reflection_max_abs_residual_s": float(np.max(np.abs(echo))),
        "final_face_penalty_norm_distance_equivalent_m": float(np.linalg.norm(10.0 * P58.C * face)),
        "final_reflection_residual_components_s": echo.tolist(),
        "final_face_penetration_components_m": face.tolist(),
        "convex_enclosure": enclosure,
        "finite_face_bounce_validity": face_valid,
        "minimum_image_path_length_m": float(np.min(lengths)),
        "minimum_reflection_arrival_s": float(np.min(pred)),
        "all_paths_positive": bool(np.all(np.isfinite(lengths)) and np.all(lengths > 0) and np.all(np.isfinite(pred)) and np.all(pred > 0)),
        "jacobian_rank": rank,
        "jacobian_singular_values": sv.tolist(),
        "jacobian_condition": float(sv[0] / sv[-1]) if sv[-1] > 0 else float("inf"),
        "optimizer_success": bool(opt.success),
        "optimizer_status": int(opt.status),
        "optimizer_message": str(opt.message),
        "nfev": int(opt.nfev),
        "njev": int(opt.njev or 0),
        "runtime_s": float(runtime),
        "final_parameters": opt.x.tolist(),
        "final_normals": n.tolist(),
        "final_offsets_m": d.tolist(),
    }


def perturb_start(x_true, true_normals, true_offsets, points, mode, magnitude, seed):
    rng = np.random.default_rng(seed)
    x = np.asarray(x_true, dtype=np.float64).copy()
    if mode == "normal_orientation_rad":
        x[:12] += rng.normal(0.0, magnitude, 12)
    elif mode == "wall_offset_m":
        # Perturb offsets geometrically, then encode them in the same gap chart.
        normals, offsets, _ = P58.plane_parameters(x, points)
        proposed = offsets + rng.normal(0.0, magnitude, 6)
        span = max(float(np.ptp(points, axis=0).max()), 1.0)
        floor = 1e-4 * span
        gap = -(np.max(points @ normals.T, axis=0) + proposed)
        gap = np.maximum(gap, floor + 1e-5)
        x[12:] = np.log(gap - floor)
    elif mode == "all_parameter_coordinates":
        x[:12] += rng.normal(0.0, magnitude, 12)
        x[12:] += rng.normal(0.0, magnitude, 6)
    else:
        raise ValueError(mode)
    return x


def objective_assignment_diagnostics(x_true, endpoint, target, points, true_normals, true_offsets, true_order):
    rows = []
    x0 = x_true.copy()
    rng = np.random.default_rng(991)
    for scale in (0.0, 0.001, 0.01, 0.05, 0.10):
        x = x0.copy()
        x[:12] += rng.normal(0.0, scale, 12)
        _, echo_res, face, n, d, _, order = oracle_residual_components(x, endpoint, target, points)
        pred, _, _, _ = corrected_echoes_with_associations(endpoint, n, d)
        # Per-group Hungarian assignment on squared scalar residuals.
        hungarian_cost = 0.0
        for i in range(target.shape[0]):
            for j in range(target.shape[1]):
                # `pred` is sorted; sorting is the exact scalar assignment solution.
                cost = (pred[i, j, :, None] - target[i, j, None, :]) ** 2
                rr, cc = linear_sum_assignment(cost)
                hungarian_cost += float(cost[rr, cc].sum())
        sorted_cost = float(np.sum(echo_res**2))
        crossings = int(np.count_nonzero(np.any(order != true_order, axis=2)))
        min_gap = float(np.min(np.diff(pred, axis=2)))
        # Fixed oracle correspondences only: for each plane, retain its rank at truth.
        true_rank = np.argsort(true_order, axis=2)
        unsorted = np.take_along_axis(pred, np.argsort(order, axis=2), axis=2)
        fixed_target = np.take_along_axis(target, true_rank, axis=2)
        fixed_cost = float(np.sum((unsorted - fixed_target) ** 2))
        rows.append({
            "orientation_perturbation_std_rad": scale,
            "sorted_assignment_TOA_squared_cost_s2": sorted_cost,
            "Hungarian_assignment_TOA_squared_cost_s2": hungarian_cost,
            "sorted_vs_Hungarian_abs_difference_s2": abs(sorted_cost - hungarian_cost),
            "fixed_oracle_correspondence_TOA_squared_cost_s2": fixed_cost,
            "groups_with_any_arrival_order_crossing_vs_oracle": crossings,
            "total_groups": int(target.shape[0] * target.shape[1]),
            "minimum_adjacent_predicted_arrival_gap_s": min_gap,
            "face_penalty_norm_m": float(np.linalg.norm(10.0 * P58.C * face)),
        })
    return rows


def oracle_diagnostics(endpoint, target, points, true_normals, true_offsets):
    x = encode_planes(true_normals, true_offsets, points)
    fun = residual_function(endpoint, target, points)
    res, echo, face, n, d, gaps, order = oracle_residual_components(x, endpoint, target, points)
    pred, _, _, path_lengths = corrected_echoes_with_associations(endpoint, n, d)
    central = {}
    jacobians = {}
    for h in CENTRAL_STEPS:
        jacobians[h] = central_jac(fun, x, h)
    j_ref = jacobians[CENTRAL_STEPS[-1]]
    rel_step = {}
    for h in CENTRAL_STEPS[:-1]:
        delta = j_ref - jacobians[h]
        rel_step[str(h)] = {
            "relative_frobenius_difference_from_h_1e-6": float(np.linalg.norm(delta) / max(np.linalg.norm(j_ref), 1e-30)),
            "maximum_absolute_difference": float(np.max(np.abs(delta))),
        }
    # Compare SciPy's forward difference at the selected step to central differences.
    forward = np.column_stack([(fun(x + np.eye(x.size)[k] * 1e-6) - fun(x)) / 1e-6 for k in range(x.size)])
    central["forward_vs_central_relative_frobenius"] = float(np.linalg.norm(forward - j_ref) / max(np.linalg.norm(j_ref), 1e-30))
    central["forward_vs_central_max_abs"] = float(np.max(np.abs(forward - j_ref)))
    sv = np.linalg.svd(j_ref, compute_uv=False)
    grad = {}
    for h in CENTRAL_STEPS:
        vals = []
        for k in range(x.size):
            unit = np.zeros_like(x); unit[k] = h
            vals.append((scalar_objective(fun(x + unit)) - scalar_objective(fun(x - unit))) / (2 * h))
        grad[str(h)] = {"gradient_norm": float(np.linalg.norm(vals)), "gradient_max_abs": float(np.max(np.abs(vals))), "gradient": vals}
    en = P58.feasible_geometry(n, d, points, gaps)
    fv = P58.reflection_face_validity(endpoint["mics"], endpoint["sources"], n, d)
    old_pred, _ = P58.predicted_echoes_with_associations(endpoint["mics"], endpoint["sources"], endpoint["emissions"], endpoint["clocks"], true_normals, true_offsets)
    old_res = old_pred - target
    return x, order, {
        "label": "ORACLE ONLY — true simulator planes used to validate forward/inverse consistency; excluded from blind results",
        "wall_parameter_vector": x.tolist(),
        "wall_normal_max_abs_error": float(np.max(np.abs(n - true_normals))),
        "wall_offset_max_abs_error_m": float(np.max(np.abs(d - true_offsets))),
        "reflection_residual_norm_s": float(np.linalg.norm(echo)),
        "reflection_max_abs_residual_s": float(np.max(np.abs(echo))),
        "preserved_C8_predictor_bug_diagnostic": {
            "C8_predictor_residual_norm_s_at_true_planes": float(np.linalg.norm(old_res)),
            "C8_predictor_max_abs_residual_s_at_true_planes": float(np.max(np.abs(old_res))),
            "corrected_C9_predictor_residual_norm_s_at_true_planes": float(np.linalg.norm(echo)),
            "diagnosis": "C8 formed sum_d (s_d*n_d)*n_d = sum_d s_d*n_d^2 instead of n dot s. C9 computes signed_source = sources @ normals.T + offsets.",
        },
        "all_390_echo_residual_components_s": echo.tolist(),
        "all_390_face_penalty_components_m": face.tolist(),
        "objective_half_squared_distance_residual_m2": scalar_objective(res),
        "convex_enclosure": en,
        "finite_face_bounce_validity": fv,
        "positive_image_path_lengths_and_arrivals": True,
        "minimum_image_path_length_m": float(np.min(path_lengths)),
        "minimum_reflection_arrival_s": float(np.min(pred)),
        "central_difference_jacobian_step_results": rel_step,
        "forward_jacobian_comparison": central,
        "central_jacobian_singular_values_h_1e-6": sv.tolist(),
        "central_jacobian_rank_relative_1e-8": int(np.sum(sv > sv[0] * 1e-8)),
        "central_jacobian_condition": float(sv[0] / sv[-1]) if sv[-1] else float("inf"),
        "objective_gradient_at_true_walls": grad,
    }


def main():
    room, raw_mics, raw_sources, emissions, clocks, target, mic_truth, src_truth = P58.make_observations()
    endpoints = unpack_endpoint_vectors()
    points = np.vstack((mic_truth, src_truth))
    true_normals, true_offsets, origin, basis = true_planes_in_canonical_gauge(room, raw_mics)
    # Preserve exact Phase 5C.8 input observations and assert equality.
    c8_results = json.loads((HERE / "phase5c8_results.json").read_text(encoding="utf-8"))
    archived_echoes = np.asarray(c8_results["observations"]["observed_echo_TOAs_s_sorted_within_each_group"])
    if not np.array_equal(archived_echoes, target):
        raise RuntimeError("Phase 5C.8 echo observations differ from regenerated seed-11 observations")

    output = {
        "phase": "5C.9 unknown-wall solver validation; exploratory only",
        "preservation": {
            "phase5c8_script_results_log_not_modified": True,
            "historical_phase5c6_endpoint_vectors_loaded_verbatim": True,
            "phase5c8_observations_loaded_and_exactly_verified": True,
        },
        "configuration": {
            "observations_shape": list(target.shape), "echo_count": int(target.size), "sound_speed_m_s": P58.C,
            "optimizer": "same Phase 5C.8 least_squares objective: TRF, numerical Jacobian, x_scale=jac, ftol=xtol=gtol=1e-11, max_nfev=400",
            "residual": "c times sorted unlabeled TOA residuals concatenated with 10*c times finite-face hinge violations",
            "perturbation_levels": list(PERTURB_LEVELS), "perturbation_seed": SEED,
        },
    }

    truth = endpoints["generating"]
    x_true, true_order, oracle = oracle_diagnostics(truth, target, points, true_normals, true_offsets)
    output["oracle_wall_positive_control"] = oracle
    output["assignment_objective_diagnostics"] = objective_assignment_diagnostics(x_true, truth, target, points, true_normals, true_offsets, true_order)

    perturbations = {}
    for mode in ("normal_orientation_rad", "wall_offset_m", "all_parameter_coordinates"):
        perturbations[mode] = []
        for idx, magnitude in enumerate(PERTURB_LEVELS):
            start = perturb_start(x_true, true_normals, true_offsets, points, mode, magnitude, SEED + idx + (100 if mode == "wall_offset_m" else 200 if mode == "all_parameter_coordinates" else 0))
            run = optimize_start(start, truth, target, points, true_normals, true_offsets)
            run["perturbation_mode"] = mode
            run["perturbation_magnitude"] = magnitude
            perturbations[mode].append(run)
    output["perturbed_wall_recovery"] = perturbations

    local_pass = bool(
        oracle["reflection_residual_norm_s"] < 1e-10
        and oracle["finite_face_bounce_validity"]["all_bounces_on_finite_faces"]
        and all(
            run["optimizer_success"]
            and run["finite_face_bounce_validity"]["all_bounces_on_finite_faces"]
            and run["convex_enclosure"]["valid_enclosure"]
            and run["final_reflection_residual_norm_s"] < 1e-8
            and run["final_plane_errors"]["normal_angle_max_deg"] < 0.1
            and run["final_plane_errors"]["offset_max_abs_m"] < 1e-3
            for entries in perturbations.values() for run in entries
        )
    )
    blind_results = {}
    if local_pass:
        for endpoint_name, endpoint in endpoints.items():
            blind_results[endpoint_name] = []
            for seed in (-1, 7, 11, 23, 37, 41, 53):
                start = P58.initial_start(seed, np.vstack((endpoint["mics"], endpoint["sources"])))
                run = optimize_start(start, endpoint, target, np.vstack((endpoint["mics"], endpoint["sources"])), true_normals, true_offsets)
                run["start_type"] = "candidate-coordinate PCA" if seed == -1 else "seeded generic orientations/gaps"
                run["seed"] = seed
                run["uses_true_wall_parameters_for_start"] = False
                blind_results[endpoint_name].append(run)
    output["blind_start_investigation"] = {
        "run": bool(local_pass),
        "reason": "ran only because oracle and every prescribed perturbation passed" if local_pass else "oracle/perturbation acceptance gate failed",
        "local_recovery_acceptance_gate_passed": local_pass,
        "runs_by_endpoint": blind_results,
    }
    output["interpretation"] = {
        "forward_model": "verified only if oracle metrics satisfy the documented thresholds",
        "oracle_inverse_consistency": "reported separately and uses true simulator planes by design",
        "local_wall_recovery": "perturbed starts use true walls and are not blind recovery",
        "blind_wall_recovery": "conditional results are reported separately; they do not use true wall parameters in their initial states",
        "competing_endpoint_disambiguation": "not attempted in this validation phase",
    }
    OUT.write_text(json.dumps(output, indent=2), encoding="utf-8")
    print("oracle", oracle["reflection_residual_norm_s"], oracle["reflection_max_abs_residual_s"], oracle["finite_face_bounce_validity"]["valid_first_order_bounce_count"], oracle["central_jacobian_rank_relative_1e-8"])
    for mode, entries in perturbations.items():
        print(mode)
        for row in entries:
            print(row["perturbation_magnitude"], row["initial_reflection_residual_norm_s"], row["final_reflection_residual_norm_s"], row["final_plane_errors"]["normal_angle_max_deg"], row["final_plane_errors"]["offset_max_abs_m"], row["finite_face_bounce_validity"]["valid_first_order_bounce_count"], row["optimizer_success"], row["nfev"], row["runtime_s"])
    print("local_acceptance", local_pass, "blind_started", output["blind_start_investigation"]["run"])
    print("results_json", OUT)


if __name__ == "__main__":
    main()
