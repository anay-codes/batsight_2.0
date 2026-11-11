"""Phase 5C.13 exploratory entropic echo-assignment and continuation study.

Imports the frozen C11/C12 research models; writes only phase5c13 artifacts.
No production reconstruction or wall-estimation code is added.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
from time import perf_counter
from types import SimpleNamespace

import numpy as np
from scipy.optimize import least_squares, linear_sum_assignment
from scipy.special import logsumexp

HERE = Path(__file__).resolve().parent
OUT = HERE / "phase5c13_results.json"
MAX_NFEV_EXACT = 80
MAX_NFEV_PER_TEMPERATURE = 16
TOL = 1e-11
TEMPERATURE_FRACTIONS = (0.5, 0.3, 0.2, 0.1)
SINKHORN_TOL = 1e-12
SINKHORN_MAX_ITER = 2000


def load(name: str, file: str):
    spec = importlib.util.spec_from_file_location(name, HERE / file)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {file}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


C12 = load("phase5c13_c12", "phase5c12_joint_basin_jacobian.py")
C11 = C12.C11


def raw_echoes_and_jacobian(x, model, q, observations, include_jac=True):
    """Raw plane-indexed predicted TOAs and distance-unit Jacobian (M,N,6,83)."""
    state = C11.split_and_residuals(x, model, q, observations)
    if include_jac:
        sorted_jac = C12.analytic_echo_jacobian(x, model, q, observations).reshape(model.m, model.n, 6, -1)
        raw_jac = np.empty_like(sorted_jac)
        for i in range(model.m):
            for j in range(model.n):
                raw_jac[i, j, state["echo_order"][i, j], :] = sorted_jac[i, j]
    else:
        raw_jac = None
    raw_toas = np.empty_like(state["predicted_echoes"])
    # The predictor's returned distances remain in physical wall-ID order.
    _, order, _, distances = C11.P59.corrected_echoes_with_associations(
        {"mics": state["microphones"], "sources": state["sources"],
         "emissions": state["emissions"], "clocks": state["clocks"]},
        state["normals"], state["offsets"])
    raw_toas = state["emissions"][None, :, None] + state["clocks"][:, None, None] + distances / model.c
    return raw_toas, raw_jac, order, state


def sinkhorn_plan(cost, temperature):
    """Balanced entropy-regularized plan with uniform 1/6 marginals.

    A short log-Sinkhorn warm start is followed by a damped Newton solve of the
    11 independent marginal equations (one column dual is fixed as gauge).
    This avoids thousands of slowly converging scaling iterations on nearly
    decomposable costs while solving the same entropic OT problem.
    """
    n = cost.shape[-1]
    leading = cost.shape[:-2]
    # Adding row or column constants changes <P,C> by a constant under fixed
    # marginals and therefore leaves the optimal plan unchanged. Double
    # centering removes large separable squared-distance terms and improves
    # log-kernel conditioning without changing the transport problem.
    centered_cost = (cost - cost.mean(axis=-1, keepdims=True)
                     - cost.mean(axis=-2, keepdims=True)
                     + cost.mean(axis=(-1, -2), keepdims=True))
    log_marginal = -np.log(float(n))
    log_kernel = -centered_cost / temperature
    log_u = np.zeros((*leading, n))
    log_v = np.zeros((*leading, n))
    warm_iterations = min(32, SINKHORN_MAX_ITER)
    for _ in range(warm_iterations):
        log_u = log_marginal - logsumexp(log_kernel + log_v[..., None, :], axis=-1)
        log_v = log_marginal - logsumexp(log_kernel + log_u[..., :, None], axis=-2)
    # Convert scaling potentials to cost-unit dual variables. Remove the
    # additive dual gauge by fixing the last column potential to zero.
    f = temperature * log_u
    g = temperature * log_v
    gauge = g[..., -1, None]
    f = f + gauge
    g = g - gauge
    z = np.concatenate((f, g[..., :-1]), axis=-1)

    def equations(values):
        left = values[..., :n]
        right = np.concatenate((values[..., n:], np.zeros((*leading, 1)),), axis=-1)
        log_plan = (left[..., :, None] + right[..., None, :] - centered_cost) / temperature
        plan = np.exp(np.clip(log_plan, -745.0, 50.0))
        row_sum, col_sum = plan.sum(axis=-1), plan.sum(axis=-2)
        residual = np.concatenate((row_sum - 1/n, (col_sum - 1/n)[..., :-1]), axis=-1)
        hessian = np.zeros((*leading, 2*n-1, 2*n-1))
        hessian[..., :n, :n] = np.eye(n) * row_sum[..., :, None] / temperature
        hessian[..., :n, n:] = plan[..., :, :-1] / temperature
        hessian[..., n:, :n] = np.swapaxes(plan[..., :, :-1], -1, -2) / temperature
        hessian[..., n:, n:] = np.eye(n-1) * col_sum[..., :-1, None] / temperature
        return plan, residual, hessian

    newton_iterations = 0
    for newton_iterations in range(1, 61):
        plan, residual, hessian = equations(z)
        active = np.max(np.abs(residual), axis=-1) >= SINKHORN_TOL
        if not np.any(active):
            break
        diagonal = np.diagonal(hessian, axis1=-2, axis2=-1)
        damping = np.maximum(1e-14, 1e-12 * np.max(diagonal, axis=-1))
        try:
            delta = np.linalg.solve(hessian + damping[..., None, None] * np.eye(2*n-1), -residual[..., None])[..., 0]
        except np.linalg.LinAlgError:
            # Batch least-squares is used only for singular near-permutation
            # Hessians. The dual gauge remains fixed in the last column.
            flat_h = (hessian + damping[..., None, None] * np.eye(2*n-1)).reshape(-1,2*n-1,2*n-1)
            flat_r = (-residual).reshape(-1,2*n-1)
            delta = np.stack([np.linalg.lstsq(hh, rr, rcond=None)[0] for hh,rr in zip(flat_h,flat_r)]).reshape(*leading,2*n-1)
        old_norm = np.linalg.norm(residual, axis=-1)
        pending = active.copy()
        alpha = np.ones(leading, dtype=float)
        for _ in range(32):
            candidate = z + alpha[..., None] * delta
            _, candidate_residual, _ = equations(candidate)
            improved = pending & (np.linalg.norm(candidate_residual, axis=-1) < old_norm)
            z = np.where(improved[..., None], candidate, z)
            pending &= ~improved
            if not np.any(pending):
                break
            alpha = np.where(pending, alpha * 0.5, alpha)
        if np.any(pending):
            break
    plan, residual, _ = equations(z)
    row_error = float(np.max(np.abs(plan.sum(axis=-1) - 1 / n)))
    col_error = float(np.max(np.abs(plan.sum(axis=-2) - 1 / n)))
    # If damped Newton cannot finish a nearly singular low-temperature case,
    # continue log-Sinkhorn from its current duals as a deterministic fallback.
    fallback_iterations = 0
    if max(row_error, col_error) > 1e-9:
        left = z[..., :n] / temperature
        right = np.concatenate((z[..., n:] / temperature, np.zeros((*leading,1))), axis=-1)
        for fallback_iterations in range(1, SINKHORN_MAX_ITER + 1):
            left = log_marginal - logsumexp(log_kernel + right[..., None, :], axis=-1)
            right = log_marginal - logsumexp(log_kernel + left[..., :, None], axis=-2)
            plan = np.exp(left[..., :, None] + log_kernel + right[..., None, :])
            row_error = float(np.max(np.abs(plan.sum(axis=-1) - 1/n)))
            col_error = float(np.max(np.abs(plan.sum(axis=-2) - 1/n)))
            if max(row_error, col_error) <= 1e-9:
                break
    if not np.all(np.isfinite(plan)) or max(row_error, col_error) > 1e-7:
        row_errors = np.max(np.abs(plan.sum(axis=-1) - 1/n), axis=-1)
        col_errors = np.max(np.abs(plan.sum(axis=-2) - 1/n), axis=-1)
        location = np.unravel_index(int(np.argmax(np.maximum(row_errors, col_errors))), leading)
        group_cost = cost[location]
        raise FloatingPointError(
            f"balanced OT failed at group {location}: row={row_error:g}, col={col_error:g}, "
            f"cost_range=[{float(group_cost.min()):g},{float(group_cost.max()):g}] m^2"
        )
    return plan, warm_iterations + newton_iterations + fallback_iterations, row_error, col_error


def make_transport_evaluator(model, q, observations, temperature):
    M, N, c = model.m, model.n, model.c
    uniform_log = -np.log(36.0)

    def evaluate(x, need_jac=True, include_assignment=False):
        raw_toas, raw_jac, order, state = raw_echoes_and_jacobian(x, model, q, observations, include_jac=need_jac)
        observed_m = observations * c
        pred_m = raw_toas * c
        groups = M * N
        all_residuals = pred_m[..., :, None] - observed_m[..., None, :]
        all_costs = all_residuals**2
        all_plans, sinkhorn_iterations, row_marginal_error, col_marginal_error = sinkhorn_plan(all_costs, temperature)
        smooth_losses = np.empty(groups)
        gradients = np.zeros((groups, x.size))
        expected_costs = np.empty(groups)
        regularizers = np.empty(groups)
        entropies = np.empty(groups)
        plans = np.empty((M, N, 6, 6)) if include_assignment else None
        assignments = np.empty((M, N, 6), dtype=np.int64)
        max_marginal_error = max(row_marginal_error, col_marginal_error)
        g = 0
        for i in range(M):
            for j in range(N):
                residual = all_residuals[i, j]
                cost = all_costs[i, j]
                plan = all_plans[i, j]
                log_plan = np.log(np.maximum(plan, np.finfo(float).tiny))
                kl = float(np.sum(plan * (log_plan - uniform_log)))
                expected = float(np.sum(plan * cost))
                reg = float(temperature * kl)
                # Six times the probability-mass-one transport objective.
                loss = 6.0 * (expected + reg)
                if loss < 0 and loss > -1e-12:
                    loss = 0.0
                if loss < 0 or not np.isfinite(loss):
                    raise FloatingPointError("invalid regularized transport loss")
                smooth_losses[g] = loss
                expected_costs[g] = 6.0 * expected
                regularizers[g] = 6.0 * reg
                entropies[g] = float(-np.sum(plan * log_plan))
                # Envelope derivative of min_P <P,C> + tau KL(P||U).
                if need_jac:
                    dcost = 2.0 * residual[:, :, None] * raw_jac[i, j, :, None, :]
                    gradients[g] = 6.0 * np.einsum("ab,abp->p", plan, dcost)
                hard_rows, hard_cols = linear_sum_assignment(-plan)
                assignments[i, j, hard_rows] = hard_cols
                if plans is not None:
                    plans[i, j] = plan
                g += 1
        direct_residual = state["direct_residual_s"].ravel() * c
        direct_jac = np.zeros((M * N, x.size))
        direct_jac[:, :model.size] = state["direct_jacobian_m"]
        echo_residual = np.sqrt(smooth_losses)
        if need_jac:
            echo_jac = gradients / np.maximum(2.0 * echo_residual[:, None], 1e-150)
            jac = np.vstack((direct_jac, echo_jac))
        else:
            jac = None
        residual = np.r_[direct_residual, echo_residual]
        return {
            "residual": residual, "jacobian": jac, "state": state,
            "smooth_losses": smooth_losses, "smooth_echo_norm_m": float(np.sqrt(np.sum(smooth_losses))),
            "expected_transport_squared_error_m2": float(np.sum(expected_costs)),
            "expected_transport_error_norm_m": float(np.sqrt(np.sum(expected_costs))),
            "entropy_regularization_m2": float(np.sum(regularizers)),
            "assignment_entropy_nats_sum": float(np.sum(entropies)),
            "mean_group_entropy_nats": float(np.mean(entropies)),
            # H(P) ranges from log(6) for a permutation plan to log(36) for
            # the fully uniform 6x6 plan under mass-one convention.
            "normalized_mean_entropy": float((np.mean(entropies) - np.log(6.0)) / np.log(6.0)),
            "hard_assignment": assignments,
            "assignment_matrices": plans,
            "sinkhorn_max_iterations": sinkhorn_iterations,
            "max_marginal_error": max_marginal_error,
            "raw_toas": raw_toas,
            "raw_echo_jacobian_m": raw_jac,
        }
    return evaluate


def exact_objective_and_jac(model, q, observations):
    def fun(x):
        return C11.split_and_residuals(x, model, q, observations)["residual_m"]
    def jac(x):
        return C12.full_jacobian(x, model, q, observations, "analytic")
    return fun, jac


def evaluation_diagnostics(x, model, problem, observations, true_normals, true_offsets):
    state = C11.split_and_residuals(x, model, problem.q, observations)
    exact_echo = state["echo_residual_s"]
    direct_lengths = np.linalg.norm(state["sources"][None, :, :] - state["microphones"][:, None, :], axis=2)
    corrected = problem.q - state["emissions"][None, :] - state["clocks"][:, None]
    direct_positive = bool(np.all(direct_lengths > 0) and np.all(corrected > 0)
                           and np.all(np.isfinite(direct_lengths)) and np.all(np.isfinite(corrected)))
    enclosure = C11.P58.feasible_geometry(state["normals"], state["offsets"], state["points"], state["gaps"])
    faces = C11.P58.reflection_face_validity(state["microphones"], state["sources"], state["normals"], state["offsets"])
    aligned, rotation, ce, ct = C11.align_transform(state["microphones"], state["sources"],
                                                    problem.microphones_truth, problem.sources_truth)
    geo = C11.P56.aligned_metrics(state["microphones"], state["sources"], problem)
    timing = C11.P56.timing_metrics(state["emissions"], state["clocks"], problem)
    wall = C11.wall_errors_after_alignment(state["normals"], state["offsets"], rotation, ce, ct,
                                           true_normals, true_offsets)
    return {
        "direct_residual_norm_s": float(np.linalg.norm(state["direct_residual_s"])),
        "direct_max_abs_residual_s": float(np.max(np.abs(state["direct_residual_s"]))),
        "exact_sorted_echo_residual_norm_s": float(np.linalg.norm(exact_echo)),
        "exact_sorted_echo_max_abs_residual_s": float(np.max(np.abs(exact_echo))),
        "coordinate_rmse_after_alignment_m": geo[2],
        "microphone_coordinate_rmse_after_alignment_m": geo[0],
        "source_coordinate_rmse_after_alignment_m": geo[1],
        "timing_errors": timing,
        "wall_plane_errors_evaluation_only": wall,
        "positive_direct_paths_and_corrected_TOAs": direct_positive,
        "positive_reflection_paths_and_arrivals": bool(np.all(state["path_lengths"] > 0)
            and np.all(state["predicted_echoes"] > 0) and np.all(np.isfinite(state["path_lengths"]))),
        "convex_enclosure": enclosure,
        "finite_face_bounce_validity": faces,
        "all_physical_checks_pass": bool(direct_positive and enclosure["valid_enclosure"]
            and faces["all_bounces_on_finite_faces"] and np.all(state["path_lengths"] > 0)
            and np.all(state["predicted_echoes"] > 0)),
        "minimum_predicted_arrival_gap_s": float(np.min(np.diff(state["predicted_echoes"], axis=2))),
        "minimum_corrected_direct_TOA_s": float(np.min(corrected)),
    }


def exact_hard_assignments(x, model, q, observations):
    raw, _, _, _ = raw_echoes_and_jacobian(x, model, q, observations, include_jac=False)
    pred = raw * model.c
    obs = observations * model.c
    out = np.empty((model.m, model.n, 6), dtype=np.int64)
    for i in range(model.m):
        for j in range(model.n):
            rr, cc = linear_sum_assignment((pred[i, j, :, None] - obs[i, j, None, :])**2)
            out[i, j, rr] = cc
    return out


def stage_report(x, tau, model, problem, observations, truth, true_normals, true_offsets,
                 evaluate, previous_hard, opt, runtime):
    details = evaluate(x, include_assignment=True)
    state = details["state"]
    J = details["jacobian"]
    sv = np.linalg.svd(J, compute_uv=False)
    rank = int(np.sum(sv > sv[0] * 1e-8))
    hard_changed = int(np.count_nonzero(np.any(details["hard_assignment"] != previous_hard, axis=2))) if previous_hard is not None else 0
    hard_pairs_changed = int(np.count_nonzero(details["hard_assignment"] != previous_hard)) if previous_hard is not None else 0
    diagnostics = evaluation_diagnostics(x, model, problem, observations, true_normals, true_offsets)
    return {
        "temperature_m2": tau,
        "direct_residual_norm_s": diagnostics["direct_residual_norm_s"],
        "exact_sorted_echo_residual_norm_s": diagnostics["exact_sorted_echo_residual_norm_s"],
        "smooth_echo_objective_norm_m_including_entropy": details["smooth_echo_norm_m"],
        "smooth_expected_data_cost_norm_m_excluding_entropy": details["expected_transport_error_norm_m"],
        "entropy_regularization_contribution_m2": details["entropy_regularization_m2"],
        "assignment_entropy_nats_sum": details["assignment_entropy_nats_sum"],
        "mean_group_assignment_entropy_nats": details["mean_group_entropy_nats"],
        "normalized_mean_assignment_entropy_0_to_1": details["normalized_mean_entropy"],
        "assignment_matrices_row_mass_1_over_6": details["assignment_matrices"].tolist(),
        "hard_assignment_predicted_row_to_observed_column": details["hard_assignment"].tolist(),
        "changed_hard_assignment_groups_from_previous_temperature": hard_changed,
        "changed_hard_assignment_pairs_from_previous_temperature": hard_pairs_changed,
        "minimum_predicted_arrival_gap_s": diagnostics["minimum_predicted_arrival_gap_s"],
        "coordinate_rmse_after_alignment_m": diagnostics["coordinate_rmse_after_alignment_m"],
        "timing_errors": diagnostics["timing_errors"],
        "wall_plane_errors_evaluation_only": diagnostics["wall_plane_errors_evaluation_only"],
        "convex_enclosure": diagnostics["convex_enclosure"],
        "finite_face_bounce_validity": diagnostics["finite_face_bounce_validity"],
        "all_physical_checks_pass": diagnostics["all_physical_checks_pass"],
        "smooth_jacobian_rank_rel_1e-8": rank,
        "smooth_jacobian_singular_values": sv.tolist(),
        "smooth_jacobian_condition": float(sv[0] / sv[-1]) if sv[-1] else float("inf"),
        "optimizer_status": int(opt.status), "optimizer_success": bool(opt.success),
        "optimizer_message": str(opt.message), "nfev": int(opt.nfev), "njev": int(opt.njev or 0),
        "runtime_s": runtime, "sinkhorn_max_iterations": details["sinkhorn_max_iterations"],
        "max_marginal_error": details["max_marginal_error"],
    }


def run_smooth_continuation(start, name, model, problem, observations, temperature_scale,
                            truth, true_normals, true_offsets):
    x = np.asarray(start, dtype=float).copy()
    stage_rows = []
    previous_hard = exact_hard_assignments(x, model, problem.q, observations)
    cumulative_nfev = 0
    failure = None
    final_tau = None
    for fraction in TEMPERATURE_FRACTIONS:
        tau = float(temperature_scale * fraction)
        evaluator = make_transport_evaluator(model, problem.q, observations, tau)
        fun = lambda v, ev=evaluator: ev(v, need_jac=False)["residual"]
        jac = lambda v, ev=evaluator: ev(v, need_jac=True)["jacobian"]
        t0 = perf_counter()
        try:
            opt = least_squares(fun, x, jac=jac, method="trf", x_scale="jac",
                                max_nfev=MAX_NFEV_PER_TEMPERATURE, ftol=TOL, xtol=TOL, gtol=TOL)
        except (FloatingPointError, ValueError, np.linalg.LinAlgError) as exc:
            elapsed = perf_counter() - t0
            failure = {"temperature_m2": tau, "error": repr(exc),
                       "runtime_until_failure_s": elapsed}
            start_eval = evaluator(x, need_jac=True, include_assignment=True)
            failed_opt = SimpleNamespace(jac=start_eval["jacobian"], status=-1, success=False,
                                         message=f"optimizer evaluation failed: {exc}", nfev=0, njev=0)
            failed_row = stage_report(x, tau, model, problem, observations, truth,
                                      true_normals, true_offsets, evaluator,
                                      previous_hard, failed_opt, elapsed)
            failed_row["optimizer_failure"] = repr(exc)
            failed_row["final_parameters_83"] = x.tolist()
            stage_rows.append(failed_row)
            final_tau = tau
            break
        elapsed = perf_counter() - t0
        x = opt.x
        cumulative_nfev += int(opt.nfev)
        row = stage_report(x, tau, model, problem, observations, truth, true_normals,
                           true_offsets, evaluator, previous_hard, opt, elapsed)
        row["final_parameters_83"] = x.tolist()
        row["temperature_fraction_of_fixed_scale"] = fraction
        row["cumulative_smooth_nfev"] = cumulative_nfev
        stage_rows.append(row)
        previous_hard = np.asarray(row["hard_assignment_predicted_row_to_observed_column"], dtype=int)
        final_tau = tau
    if final_tau is None:
        final_tau = temperature_scale * TEMPERATURE_FRACTIONS[0]
    final_eval = make_transport_evaluator(model, problem.q, observations, final_tau)(x, need_jac=False, include_assignment=True)
    return {"name": name, "final_parameters_83": x.tolist(), "stages": stage_rows,
            "smooth_nfev_total": cumulative_nfev,
            "failure": failure, "final_temperature_m2": final_tau,
            "final_stage_assignment_matrices": final_eval["assignment_matrices"].tolist(),
            "final_stage_hard_assignments": final_eval["hard_assignment"].tolist()}


def solve_exact(start, name, mode, model, problem, observations, truth, true_normals, true_offsets):
    if mode == "sorted_analytic":
        fun, jac = exact_objective_and_jac(model, problem.q, observations)
    elif mode == "exact_fd":
        fun = lambda x: C11.split_and_residuals(x, model, problem.q, observations)["residual_m"]
        jac = lambda x: C12.full_jacobian(x, model, problem.q, observations, "forward_fd")
    else:
        raise ValueError(mode)
    t0 = perf_counter()
    opt = least_squares(fun, np.asarray(start, dtype=float), jac=jac, method="trf", x_scale="jac",
                        max_nfev=MAX_NFEV_EXACT, ftol=TOL, xtol=TOL, gtol=TOL)
    elapsed = perf_counter() - t0
    metrics = evaluation_diagnostics(opt.x, model, problem, observations, true_normals, true_offsets)
    J = jac(opt.x)
    sv = np.linalg.svd(J, compute_uv=False)
    rank = int(np.sum(sv > sv[0] * 1e-8))
    exact = bool(metrics["direct_residual_norm_s"] < 1e-9
                 and metrics["exact_sorted_echo_residual_norm_s"] < 1e-9
                 and metrics["coordinate_rmse_after_alignment_m"] < 1e-6
                 and metrics["all_physical_checks_pass"])
    return {"name": name, "method": mode, **metrics,
            "jacobian_rank_rel_1e-8": rank, "jacobian_singular_values": sv.tolist(),
            "jacobian_condition": float(sv[0] / sv[-1]) if sv[-1] else float("inf"),
            "optimizer_status": int(opt.status), "optimizer_success": bool(opt.success),
            "optimizer_message": str(opt.message), "nfev": int(opt.nfev), "njev": int(opt.njev or 0),
            "runtime_s": elapsed, "exact_recovery_criteria_pass": exact,
            "final_parameters_83": opt.x.tolist()}


def main():
    problem, model, observations, endpoints = C11.load_exact_inputs()
    c11 = json.loads((HERE / "phase5c11_results.json").read_text(encoding="utf-8"))
    c12 = json.loads((HERE / "phase5c12_results.json").read_text(encoding="utf-8"))
    ref_row = next(r for r in c11["runs"] if r["name"] == "generating_endpoint_staged_data_derived_walls")
    ref = np.asarray(ref_row["final_complete_parameters_83"], dtype=float)
    pca_g = np.asarray(next(r for r in c11["runs"] if r["name"] == "generating_endpoint_PCA_wall_start")["initial_complete_parameters_83"], dtype=float)
    pca_c = np.asarray(next(r for r in c11["runs"] if r["name"] == "competing_endpoint_PCA_wall_start")["initial_complete_parameters_83"], dtype=float)
    room, raw_mics, _, _, _, _, _, _ = C11.P58.make_observations()
    true_normals, true_offsets, _, _ = C11.P59.true_planes_in_canonical_gauge(room, raw_mics)
    # Fixed data-derived squared-distance scale, independent of candidate starts.
    echo_distance = observations * model.c
    temperature_scale = float(np.median(np.var(echo_distance, axis=2)))
    if not np.isfinite(temperature_scale) or temperature_scale <= 0:
        raise RuntimeError("invalid fixed temperature scale")
    starts = [("exact_staged_reference", ref)]
    starts.extend([("generating_PCA_wall_start", pca_g), ("competing_PCA_wall_start", pca_c)])
    for magnitude in (1e-8, 1e-7, 1e-6, 1e-5, 1e-4, 1e-3):
        for seed in C12.DIRECTIONS:
            direction = np.random.default_rng(seed).normal(size=83)
            direction /= np.linalg.norm(direction)
            starts.append((f"perturb_{magnitude:g}_seed_{seed}", ref + magnitude * np.sqrt(83.0) * direction))
    for row in c11["blind_observation_starts"]:
        starts.append((row["name"], np.asarray(row["initial_complete_parameters_83"], dtype=float)))

    # Directional finite-difference check of the scalar smooth objective
    # gradient, especially at the two PCA starts that contain arrival ties.
    smooth_gradient_checks = []
    check_points = {"exact_staged_reference": ref, "generating_PCA_wall_start": pca_g,
                    "competing_PCA_wall_start": pca_c}
    for point_name, point in check_points.items():
        for frac in TEMPERATURE_FRACTIONS:
            tau = temperature_scale * frac
            evaluator = make_transport_evaluator(model, problem.q, observations, tau)
            base = evaluator(point, need_jac=True)
            grad = base["jacobian"].T @ base["residual"]
            for seed in (131, 132):
                direction = np.random.default_rng(seed).normal(size=83)
                direction /= np.linalg.norm(direction)
                h = 1e-6
                plus = evaluator(point + h*direction, need_jac=False)["residual"]
                minus = evaluator(point - h*direction, need_jac=False)["residual"]
                fd = 0.5 * (float(plus @ plus) - float(minus @ minus)) / (2*h)
                analytic = float(grad @ direction)
                smooth_gradient_checks.append({"checkpoint": point_name, "temperature_m2": tau,
                    "direction_seed": seed, "central_step_scaled_norm": h,
                    "analytic_directional_derivative": analytic,
                    "central_difference_directional_derivative": fd,
                    "absolute_discrepancy": abs(analytic-fd),
                    "relative_discrepancy": abs(analytic-fd)/max(abs(fd),1e-12),
                    "base_normalized_assignment_entropy_0_to_1": base["normalized_mean_entropy"],
                    "base_max_marginal_error": base["max_marginal_error"]})

    results = []
    total_start = perf_counter()
    for name, start in starts:
        # Identical smooth path is used by methods 2 and 3; method 3 adds only
        # the original exact hard-assignment refinement after the last stage.
        baseline = solve_exact(start, name, "sorted_analytic", model, problem, observations,
                               problem, true_normals, true_offsets)
        smooth = run_smooth_continuation(start, name, model, problem, observations,
                                         temperature_scale, problem, true_normals, true_offsets)
        smooth_x = np.asarray(smooth["final_parameters_83"])
        smooth_eval = make_transport_evaluator(model, problem.q, observations,
            smooth["final_temperature_m2"])(smooth_x, need_jac=False, include_assignment=True)
        smooth_metrics = evaluation_diagnostics(smooth_x, model, problem, observations, true_normals, true_offsets)
        smooth_method = {"name": name, "method": "smooth_continuation_only", **smooth_metrics,
                         "final_temperature_m2": smooth["final_temperature_m2"],
                         "final_smooth_echo_norm_including_entropy_m": smooth_eval["smooth_echo_norm_m"],
                         "final_smooth_expected_data_error_norm_m": smooth_eval["expected_transport_error_norm_m"],
                         "final_assignment_entropy_nats_sum": smooth_eval["assignment_entropy_nats_sum"],
                         "final_normalized_mean_assignment_entropy": smooth_eval["normalized_mean_entropy"],
                         "final_hard_assignment": smooth_eval["hard_assignment"].tolist(),
                         "smooth_nfev_total": smooth["smooth_nfev_total"],
                         "continuation_failure": smooth["failure"],
                         "stage_statuses": [r["optimizer_status"] for r in smooth["stages"]],
                         "stage_parameters_83": [r["final_parameters_83"] for r in smooth["stages"]] if "final_parameters_83" in smooth["stages"][0] else None,
                         "final_parameters_83": smooth_x.tolist()}
        # Store every stage's full transport plan/cost matrix in the continuation
        # object, along with exact/hard endpoint refinements.
        hard_after = solve_exact(smooth_x, name, "sorted_analytic", model, problem, observations,
                                 problem, true_normals, true_offsets)
        hard_after["method"] = "smooth_continuation_then_sorted_analytic_refinement"
        blind_oracle_labels = name.startswith("blind_")
        results.append({
            "start_name": name,
            "initial_parameters_83": np.asarray(start, dtype=float).tolist(),
            "start_kind": "blind observation-derived start" if blind_oracle_labels else
                ("oracle reference positive control" if name == "exact_staged_reference" else
                 "archived endpoint, PCA start, or deterministic reference perturbation"),
            "initial_metrics": evaluation_diagnostics(start, model, problem, observations, true_normals, true_offsets),
            "method_1_sorted_analytic": baseline,
            "method_2_smooth_continuation": smooth_method,
            "method_3_smooth_then_exact": hard_after,
            "temperature_stages": smooth["stages"],
        })
        print(f"completed {name}", flush=True)

    output = {
        "phase": "5C.13 smooth echo assignment and continuation investigation",
        "preservation": {"C11_and_C12_archives_read_only": True,
                         "exact_seed11_endpoints_and_echoes_reverified_by_C11_loader": True},
        "model": {
            "direct_model_and_gauges": "Unchanged C11 83-parameter model, m1 origin, m2 positive x, m3 in xy positive y, e1=0.",
            "echo_observations": "390 sorted storage values used only as unlabeled sets of six within each microphone/source event group.",
            "transport_cost": "C_ab = [c*(predicted_TOA_a - observed_TOA_b)]^2, in m^2.",
            "marginals": "Each group uses six predicted paths and six observations with uniform row/column marginal 1/6; transport mass sums to one.",
            "regularized_objective_per_group": "L_tau = 6*(sum_ab P_ab*C_ab + tau*KL(P || U)), U_ab=1/36; P minimizes the expression over the balanced transport polytope.",
            "residual_embedding": "Smooth least-squares uses one nonnegative residual sqrt(L_tau) per mic/source group; direct residual rows remain the original c-scaled values. This preserves the stated sum-of-squares objective exactly.",
            "entropy_in_objective": "Yes. The KL-to-uniform transport entropy penalty is included; the data-only expected matching cost is also reported separately.",
            "zero_temperature_limit": "As tau tends to zero, optimal P concentrates on a minimum-cost permutation and 6*sum(P*C) tends to the exact minimum sum of six squared matching errors; tau*KL tends to zero. No equivalence is claimed at finite tau.",
            "temperature_scale_m2": temperature_scale,
            "temperature_fractions": list(TEMPERATURE_FRACTIONS),
            "temperature_schedule_m2": [temperature_scale*f for f in TEMPERATURE_FRACTIONS],
            "assignment_derivative": "Envelope derivative: dL/dx = 6*sum_ab P_ab*dC_ab/dx. Path arrival derivatives are analytic C12 derivatives restored to physical wall order. Sinkhorn uses log-domain updates.",
            "sinkhorn": {"uniform_marginal": 1/6, "marginal_tolerance": SINKHORN_TOL,
                         "maximum_iterations": SINKHORN_MAX_ITER},
            "method_budgets": {"exact_sorted_max_nfev": MAX_NFEV_EXACT,
                "each_temperature_max_nfev": MAX_NFEV_PER_TEMPERATURE,
                "five_stage_smooth_budget_ceiling": MAX_NFEV_PER_TEMPERATURE*len(TEMPERATURE_FRACTIONS),
                "method_3_additional_exact_refinement_max_nfev": MAX_NFEV_EXACT,
                "optimizer": "SciPy least_squares TRF, x_scale=jac, ftol=xtol=gtol=1e-11"},
            "hard_assignment": "Hungarian minimum-cost one-to-one assignment used to count assignment changes; exact reference objective remains sorted squared error (equivalent scalar assignment).",
        },
        "recovery_criteria": {"direct_and_exact_echo_norm_each_below_s": 1e-9,
            "aligned_coordinate_rmse_below_m": 1e-6,
            "all_physical_checks_required": True},
        "results": results,
        "smooth_objective_gradient_checks": smooth_gradient_checks,
        "runtime_total_s": perf_counter()-total_start,
        "notes": ["Finite-temperature smooth objective is not the exact hard assignment objective.",
                  "All final candidate scores include exact sorted echo residuals.",
                  "Blind-start ground truth is used only for post-fit error reporting.",
                  "No finite multi-start study establishes global uniqueness or competing-endpoint infeasibility."],
    }
    OUT.write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(f"wrote {OUT}; starts={len(starts)}; elapsed={output['runtime_total_s']:.2f}s", flush=True)


if __name__ == "__main__":
    main()
