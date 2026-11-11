"""Phase 5C.12 exploratory joint-solver basin and echo-Jacobian study.

This study imports the frozen C11 model, reads C11 artifacts, and writes only
phase5c12_* files. It does not add production localization or wall fitting.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
from time import perf_counter

import numpy as np
from scipy.optimize import least_squares

HERE = Path(__file__).resolve().parent
OUT = HERE / "phase5c12_results.json"
STEPS = (1e-4, 1e-5, 1e-6, 1e-7, 1e-8)
LEVELS = (1e-8, 1e-7, 1e-6, 1e-5, 1e-4, 1e-3)
DIRECTIONS = (1201, 1202, 1203)
MAX_NFEV = 80
TOL = 1e-11


def load(name: str, file: str):
    spec = importlib.util.spec_from_file_location(name, HERE / file)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {file}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


C11 = load("phase5c12_c11", "phase5c11_joint_direct_reflection_fit.py")


def coordinate_parameter_derivatives(x, model):
    """Return d(all microphone/source coordinates)/d(scaled direct params)."""
    m, n, ls = model.m, model.n, model.ls
    result = np.zeros((m + n, 3, model.size))
    # Gauge-fixed microphone chart.
    result[1, 0, 0] = ls * np.exp(x[0])
    result[2, 0, 1] = ls
    result[2, 1, 2] = ls * np.exp(x[2])
    for i in range(3, m):
        start = 3 + 3 * (i - 3)
        result[i, :, start:start + 3] = np.eye(3) * ls
    src_start = 3 * m - 6
    for j in range(n):
        start = src_start + 3 * j
        result[m + j, :, start:start + 3] = np.eye(3) * ls
    return result


def analytic_echo_jacobian(x, model, q, echo_observations):
    """Analytic Jacobian of sorted echo residuals in distance units.

    The derivative is valid within a region with fixed predicted arrival order,
    unique support extrema, and a fixed active coordinate-span axis. At ties the
    implemented model is nonsmooth; the central-difference diagnostics report
    such crossings separately.
    """
    state = C11.split_and_residuals(x, model, q, echo_observations)
    mics, sources = state["microphones"], state["sources"]
    normals, offsets = state["normals"], state["offsets"]
    m, n, nd = model.m, model.n, model.size
    nw = 18
    total = nd + nw
    points = np.vstack((mics, sources))
    dpoints = coordinate_parameter_derivatives(x[:nd], model)
    span_axis = int(np.argmax(np.ptp(points, axis=0)))
    span = float(np.ptp(points, axis=0)[span_axis])
    if span > 1.0:
        max_idx = int(np.argmax(points[:, span_axis]))
        min_idx = int(np.argmin(points[:, span_axis]))
        dfloor = 1e-4 * (dpoints[max_idx, span_axis] - dpoints[min_idx, span_axis])
    else:
        dfloor = np.zeros(nd)
    # Plane-normal derivatives wrt azimuth and elevation.
    angles = state["wall_x"][:12].reshape(6, 2)
    az, el = angles[:, 0], angles[:, 1]
    dn = np.zeros((6, 3, nw))
    for k in range(6):
        dn[k, :, 2 * k] = (-np.cos(el[k]) * np.sin(az[k]), np.cos(el[k]) * np.cos(az[k]), 0.0)
        dn[k, :, 2 * k + 1] = (-np.sin(el[k]) * np.cos(az[k]), -np.sin(el[k]) * np.sin(az[k]), np.cos(el[k]))
    # Differentiate support-derived offsets. np.argmax is the active support
    # point; active-point changes are nonsmooth boundaries in this chart.
    doffset = np.zeros((6, total))
    support_active = np.argmax(points @ normals.T, axis=0)
    for k in range(6):
        pidx = int(support_active[k])
        doffset[k, :nd] = -(normals[k] @ dpoints[pidx]) - dfloor
        angle_start = nd + 2 * k
        doffset[k, angle_start:angle_start + 2] += -(points[pidx] @ dn[k, :, 2 * k:2 * k + 2])
        loggap = state["wall_x"][12 + k]
        gap_derivative = np.exp(np.clip(loggap, -30.0, 20.0)) if -30.0 < loggap < 20.0 else 0.0
        doffset[k, nd + 12 + k] = -gap_derivative

    # Output is flattened in (microphone, source, sorted-arrival-rank) order.
    jac = np.zeros((m * n * 6, total))
    _, order, images, distances = C11.P59.corrected_echoes_with_associations(
        {"mics": mics, "sources": sources,
         "emissions": state["emissions"], "clocks": state["clocks"]},
        normals, offsets,
    )
    dist = distances  # (M,N,6), indexed by wall ID
    # Direct coordinate and timing derivatives are assembled per wall path,
    # then selected through the currently sorted wall association.
    for i in range(m):
        for j in range(n):
            for rank, kraw in enumerate(order[i, j]):
                k = int(kraw)
                image = images[j, k]
                delta = image - mics[i]
                rho = float(dist[i, j, k])
                unit = delta / rho
                z = float(np.dot(normals[k], sources[j]) + offsets[k])
                # d(image)=ds-2[(dn.s+n.ds+dd)n+z dn]
                dimage = np.zeros((3, total))
                dimage[:, :nd] = dpoints[m + j]
                dimage[:, :nd] -= 2.0 * np.outer(normals[k], normals[k] @ dpoints[m + j] + doffset[k, :nd])
                dimage[:, nd:] = -2.0 * np.outer(normals[k], doffset[k, nd:])
                for p in range(total):
                    if p >= nd:
                        dnk = dn[k, :, p - nd]
                        dimage[:, p] -= 2.0 * ((float(dnk @ sources[j])) * normals[k] + z * dnk)
                dmic = np.zeros((3, total))
                dmic[:, :nd] = dpoints[i]
                d_range = unit @ (dimage - dmic)
                # TOA terms are stored in seconds; residuals are c*seconds.
                dtime = np.zeros(total)
                clock_idx = model.clock_start + i
                dtime[clock_idx] = model.ts * model.c
                if j > 0:
                    dtime[model.emission_start + j - 1] = model.ts * model.c
                jac[(i * n + j) * 6 + rank] = d_range + dtime
    return jac


def finite_echo_jacobian(x, model, q, echoes, h=1e-6, central=True, fixed_order=None):
    def evaluate(v):
        st = C11.split_and_residuals(v, model, q, echoes)
        if fixed_order is None:
            pred = st["predicted_echoes"]
        else:
            _, _, _, raw_distances = C11.P59.corrected_echoes_with_associations(
                {"mics": st["microphones"], "sources": st["sources"],
                 "emissions": st["emissions"], "clocks": st["clocks"]},
                st["normals"], st["offsets"])
            raw = st["emissions"][None, :, None] + st["clocks"][:, None, None] + raw_distances / model.c
            pred = np.take_along_axis(raw, fixed_order, axis=2)
        return (pred - echoes).ravel() * model.c
    base = evaluate(x)
    jac = np.empty((base.size, x.size))
    for k in range(x.size):
        step = h * max(1.0, abs(float(x[k])))
        plus, minus = x.copy(), x.copy()
        plus[k] += step
        minus[k] -= step
        fp = evaluate(plus)
        if central:
            fm = evaluate(minus)
            jac[:, k] = (fp - fm) / (2 * step)
        else:
            jac[:, k] = (fp - base) / step
    return jac


def derivative_report(x, model, problem, echoes, label):
    analytic = analytic_echo_jacobian(x, model, problem.q, echoes)
    rows = []
    for step in STEPS:
        numeric = finite_echo_jacobian(x, model, problem.q, echoes, step, True)
        diff = analytic - numeric
        denom = np.linalg.norm(numeric)
        base_order = C11.split_and_residuals(x, model, problem.q, echoes)["echo_order"]
        fixed_numeric = finite_echo_jacobian(x, model, problem.q, echoes, step, True, base_order)
        fixed_diff = analytic - fixed_numeric
        sv = np.linalg.svd(analytic, compute_uv=False)
        rows.append({
            "step": step,
            "relative_frobenius_discrepancy": float(np.linalg.norm(diff) / denom) if denom else 0.0,
            "maximum_absolute_discrepancy": float(np.max(np.abs(diff))),
            "fixed_association_relative_frobenius_discrepancy": float(np.linalg.norm(fixed_diff) / np.linalg.norm(fixed_numeric)),
            "fixed_association_maximum_absolute_discrepancy": float(np.max(np.abs(fixed_diff))),
            "finite_difference_singular_values": np.linalg.svd(numeric, compute_uv=False).tolist(),
            "analytic_singular_values": sv.tolist(),
            "analytic_rank_rel_1e-8": int(np.sum(sv > sv[0] * 1e-8)),
            "finite_difference_rank_rel_1e-8": int(np.sum(np.linalg.svd(numeric, compute_uv=False) > np.linalg.svd(numeric, compute_uv=False)[0] * 1e-8)),
        })
    return {"label": label, "steps": rows}


def full_jacobian(x, model, q, echoes, mode):
    base = C11.split_and_residuals(x, model, q, echoes)
    jac = np.zeros((model.m * model.n + echoes.size, x.size))
    jac[:model.m * model.n, :model.size] = base["direct_jacobian_m"]
    if mode == "analytic":
        ej = analytic_echo_jacobian(x, model, q, echoes)
    elif mode == "forward_fd":
        ej = finite_echo_jacobian(x, model, q, echoes, 1e-6, False)
    else:
        raise ValueError(mode)
    jac[model.m * model.n:] = ej
    return jac


def run_solver(name, start, mode, model, problem, echoes, truth, true_normals, true_offsets):
    fun = lambda v: C11.split_and_residuals(v, model, problem.q, echoes)["residual_m"]
    jac = lambda v: full_jacobian(v, model, problem.q, echoes, mode)
    before = C11.split_and_residuals(start, model, problem.q, echoes)
    t0 = perf_counter()
    opt = least_squares(fun, start.copy(), jac=jac, method="trf", x_scale="jac", max_nfev=MAX_NFEV,
                        ftol=TOL, xtol=TOL, gtol=TOL)
    elapsed = perf_counter() - t0
    final = C11.split_and_residuals(opt.x, model, problem.q, echoes)
    singular = np.linalg.svd(opt.jac, compute_uv=False)
    rank = int(np.sum(singular > singular[0] * 1e-8))
    enclosure = C11.P58.feasible_geometry(final["normals"], final["offsets"], final["points"], final["gaps"])
    faces = C11.P58.reflection_face_validity(final["microphones"], final["sources"], final["normals"], final["offsets"])
    direct_lengths = np.linalg.norm(final["sources"][None, :, :] - final["microphones"][:, None, :], axis=2)
    corrected_direct = problem.q - final["emissions"][None, :] - final["clocks"][:, None]
    direct_physical = bool(np.all(np.isfinite(direct_lengths)) and np.all(direct_lengths > 0)
                           and np.all(np.isfinite(corrected_direct)) and np.all(corrected_direct > 0))
    geo = C11.P56.aligned_metrics(final["microphones"], final["sources"], truth)
    timing = C11.P56.timing_metrics(final["emissions"], final["clocks"], truth)
    aligned, rotation, ce, ct = C11.align_transform(final["microphones"], final["sources"], truth.microphones_truth, truth.sources_truth)
    walls = C11.wall_errors_after_alignment(final["normals"], final["offsets"], rotation, ce, ct, true_normals, true_offsets)
    echo_order0 = before["echo_order"]
    echo_changes = int(np.count_nonzero(np.any(final["echo_order"] != echo_order0, axis=2)))
    exact = bool(np.linalg.norm(final["direct_residual_s"]) < 1e-9 and np.linalg.norm(final["echo_residual_s"]) < 1e-9
                 and geo[2] < 1e-6 and direct_physical and enclosure["valid_enclosure"]
                 and faces["all_bounces_on_finite_faces"])
    return {
        "name": name, "jacobian": mode,
        "initial_direct_residual_norm_s": float(np.linalg.norm(before["direct_residual_s"])),
        "initial_reflection_residual_norm_s": float(np.linalg.norm(before["echo_residual_s"])),
        "final_direct_residual_norm_s": float(np.linalg.norm(final["direct_residual_s"])),
        "final_direct_max_abs_residual_s": float(np.max(np.abs(final["direct_residual_s"]))),
        "final_reflection_residual_norm_s": float(np.linalg.norm(final["echo_residual_s"])),
        "final_reflection_max_abs_residual_s": float(np.max(np.abs(final["echo_residual_s"]))),
        "coordinate_rmse_after_alignment_m": geo[2], "timing_errors": timing,
        "wall_plane_errors_evaluation_only": walls,
        "positive_direct_path_lengths_and_corrected_TOAs": direct_physical,
        "convex_enclosure": enclosure, "finite_face_bounce_validity": faces,
        "all_physical_checks_pass": bool(direct_physical and enclosure["valid_enclosure"] and faces["all_bounces_on_finite_faces"]
                                             and np.all(final["path_lengths"] > 0)
                                             and np.all(final["predicted_echoes"] > 0)),
        "echo_groups_with_order_change": echo_changes,
        "joint_jacobian_rank_rel_1e-8": rank, "joint_jacobian_singular_values": singular.tolist(),
        "joint_jacobian_condition": float(singular[0] / singular[-1]) if singular[-1] else float("inf"),
        "optimizer_success": bool(opt.success), "optimizer_status": int(opt.status),
        "optimizer_message": str(opt.message), "nfev": int(opt.nfev), "njev": int(opt.njev or 0),
        "runtime_s": elapsed, "exact_solution_recovered": exact,
        "final_parameters_83": opt.x.tolist(),
    }


def main():
    problem, model, echoes, endpoints = C11.load_exact_inputs()
    c11 = json.loads((HERE / "phase5c11_results.json").read_text(encoding="utf-8"))
    staged_row = next(r for r in c11["runs"] if r["name"] == "generating_endpoint_staged_data_derived_walls")
    reference = np.asarray(staged_row["final_complete_parameters_83"], dtype=float)
    if reference.size != 83:
        raise RuntimeError("C11 staged positive control is not the expected 83-vector")
    # Plane truth is imported only for scoring/diagnostics, as in C11.
    room, raw_m, _, _, _, _, _, _ = C11.P58.make_observations()
    true_normals, true_offsets, _, _ = C11.P59.true_planes_in_canonical_gauge(room, raw_m)
    ref_state = C11.split_and_residuals(reference, model, problem.q, echoes)
    ref_jac = full_jacobian(reference, model, problem.q, echoes, "analytic")
    ref_s = np.linalg.svd(ref_jac, compute_uv=False)
    ref_faces = C11.P58.reflection_face_validity(ref_state["microphones"], ref_state["sources"], ref_state["normals"], ref_state["offsets"])
    ref_enclosure = C11.P58.feasible_geometry(ref_state["normals"], ref_state["offsets"], ref_state["points"], ref_state["gaps"])
    derivative_starts = {
        "exact_staged_reference": reference,
        "generating_PCA_wall_endpoint": np.asarray(next(r for r in c11["runs"] if r["name"] == "generating_endpoint_PCA_wall_start")["initial_complete_parameters_83"]),
        "competing_PCA_wall_endpoint": np.asarray(next(r for r in c11["runs"] if r["name"] == "competing_endpoint_PCA_wall_start")["initial_complete_parameters_83"]),
    }
    rng = np.random.default_rng(1204)
    derivative_starts["small_perturbed_solution"] = reference + rng.normal(0, 1e-5, 83)
    derivative_checks = [derivative_report(v, model, problem, echoes, k) for k, v in derivative_starts.items()]
    # Explicitly probe predicted echo ordering near a crossing by approaching
    # the closest pair along the projected gradient of their TOA difference.
    crossing = crossing_diagnostic(reference, model, problem, echoes)

    basin_runs = []
    for magnitude in LEVELS:
        for seed in DIRECTIONS:
            direction = np.random.default_rng(seed).normal(size=83)
            direction /= np.linalg.norm(direction)
            start = reference + magnitude * np.sqrt(83.0) * direction
            for mode in ("forward_fd", "analytic"):
                basin_runs.append(run_solver(f"basin_{magnitude:g}_seed_{seed}", start, mode, model, problem, echoes, problem, true_normals, true_offsets))
    comparison_starts = {"exact_reference": reference,
                         "generating_PCA_wall": derivative_starts["generating_PCA_wall_endpoint"],
                         "competing_PCA_wall": derivative_starts["competing_PCA_wall_endpoint"]}
    # Same deterministic perturbation per solver.
    for level, seed in ((1e-8, 1301), (1e-6, 1302), (1e-4, 1303), (1e-3, 1304)):
        direction = np.random.default_rng(seed).normal(size=83)
        direction /= np.linalg.norm(direction)
        comparison_starts[f"perturb_{level:g}_seed_{seed}"] = reference + level * np.sqrt(83.0) * direction
    comparisons = []
    for label, start in comparison_starts.items():
        for mode in ("forward_fd", "analytic"):
            comparisons.append(run_solver(label, start, mode, model, problem, echoes, problem, true_normals, true_offsets))
    output = {
        "phase": "5C.12 joint solver basin and Jacobian investigation",
        "preservation": {"C11_files_read_only": True, "endpoint_vectors_and_echo_data_loaded_from_C11_sources": True},
        "reference": {"source": "C11 staged generating data-derived-wall positive control final 83-vector",
            "parameters_83": reference.tolist(),
            "direct_residual_norm_s": float(np.linalg.norm(ref_state["direct_residual_s"])),
            "reflection_residual_norm_s": float(np.linalg.norm(ref_state["echo_residual_s"])),
            "coordinate_rmse_m": C11.P56.aligned_metrics(ref_state["microphones"], ref_state["sources"], problem)[2],
            "timing_errors": C11.P56.timing_metrics(ref_state["emissions"], ref_state["clocks"], problem),
            "wall_errors_evaluation_only": C11.wall_errors_after_alignment(ref_state["normals"], ref_state["offsets"], *C11.align_transform(ref_state["microphones"], ref_state["sources"], problem.microphones_truth, problem.sources_truth)[1:], true_normals, true_offsets),
            "gauges": "m1 origin, m2 positive x, m3 xy positive y, e1=0; wall points contained via support gap chart",
            "convex_enclosure": ref_enclosure, "finite_face_bounces": ref_faces,
            "joint_jacobian_rank_rel_1e-8": int(np.sum(ref_s > ref_s[0] * 1e-8)),
            "joint_jacobian_singular_values": ref_s.tolist(),
            "joint_jacobian_condition": float(ref_s[0] / ref_s[-1])},
        "derivative_validation": derivative_checks,
        "arrival_crossing_diagnostic": crossing,
        "basin_runs": basin_runs,
        "optimizer_comparison_runs": comparisons,
        "settings": {"noise_model": "none; exact seed-11 observations", "optimizer": "SciPy least_squares TRF",
            "max_nfev": MAX_NFEV, "ftol_xtol_gtol": TOL, "x_scale": "jac",
            "objective_and_scaling": "unchanged C11 455 residuals, seconds multiplied by c, unit observation weights, no regularization",
            "echo_assignment": "re-sort predicted arrivals within each mic/source group at every evaluation",
            "perturbations": "83-dimensional scaled parameter chart; three normalized deterministic Gaussian directions per magnitude; amplitude magnitude*sqrt(83) gives per-coordinate RMS magnitude",
            "exact_recovery_criterion": "direct and echo norm <1e-9 s, aligned coordinate RMSE <1e-6 m, convex and all finite-face checks pass"}
    }
    OUT.write_text(json.dumps(output, indent=2), encoding="utf-8")
    with (HERE / "phase5c12_run.log").open("w", encoding="utf-8") as f:
        for row in comparisons:
            f.write(f"{row['name']} {row['jacobian']} direct={row['final_direct_residual_norm_s']:.6g} echo={row['final_reflection_residual_norm_s']:.6g} coord={row['coordinate_rmse_after_alignment_m']:.6g} rank={row['joint_jacobian_rank_rel_1e-8']} cond={row['joint_jacobian_condition']:.4g} status={row['optimizer_status']} nfev={row['nfev']} sec={row['runtime_s']:.4g} exact={row['exact_solution_recovered']}\n")
        f.write(f"basin runs={len(basin_runs)}; derivative cases={len(derivative_checks)}; output={OUT}\n")
    print(f"wrote {OUT}; {len(basin_runs)} basin runs, {len(comparisons)} optimizer comparisons")


def crossing_diagnostic(reference, model, problem, echoes):
    """Probe the nearest predicted-arrival order boundary in scaled coordinates."""
    state = C11.split_and_residuals(reference, model, problem.q, echoes)
    pred = state["predicted_echoes"]
    jac = analytic_echo_jacobian(reference, model, problem.q, echoes).reshape(model.m, model.n, 6, -1)
    gaps = np.diff(pred, axis=2)
    i, j, rank = np.unravel_index(np.argmin(gaps), gaps.shape)
    # Adjacent sorted gap derivative; step along its steepest descending unit direction.
    grad = jac[i, j, rank + 1] - jac[i, j, rank]
    norm = float(np.linalg.norm(grad))
    if norm == 0:
        return {"minimum_gap_s": float(gaps[i, j, rank]), "crossing_found": False}
    direction = -grad / norm
    records = []
    for distance in (1e-6, 1e-5, 1e-4, 2e-4, 3e-4, 5e-4, 1e-3):
        x = reference + distance * direction
        sp = C11.split_and_residuals(x, model, problem.q, echoes)
        order_changed = int(np.count_nonzero(np.any(sp["echo_order"] != state["echo_order"], axis=2)))
        gap = np.diff(sp["predicted_echoes"], axis=2)
        records.append({"scaled_parameter_step_norm": distance,
                        "target_pair_gap_s": float(gap[i, j, rank]),
                        "order_changed_groups": order_changed,
                        "minimum_gap_s": float(np.min(gap))})
    return {"group_i_j": [int(i), int(j)], "adjacent_rank": int(rank),
            "minimum_gap_s": float(gaps[i, j, rank]), "gradient_norm_s_per_scaled_unit": norm / model.c,
            "directional_probes": records,
            "note": "The sorted residual is smooth while order is fixed and generally kinked at ties; finite probes can cross ordering cells."}


if __name__ == "__main__":
    main()
