"""Phase 5C.15: exploratory timing/coordinate block profiling.

Loads the exact C11 blind vectors and staged positive control. Ground truth is
used only by the score routine after optimizer candidates have been produced.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import warnings
from time import perf_counter

import numpy as np
from scipy.optimize import least_squares

HERE = Path(__file__).resolve().parent
OUT = HERE / "phase5c15_results.json"
C11_JSON = HERE / "phase5c11_results.json"
C8_JSON = HERE / "phase5c8_results.json"
MAX_NFEV = 80
TOL = 1e-11
MAX_ALTERNATING_CYCLES = 8
OBJECTIVE_RELATIVE_STOP = 1e-10
OBJECTIVE_ABSOLUTE_STOP = 1e-12
ACCEPTANCE_RELATIVE_SLACK = 1e-12
WARNINGS: list[str] = []
_ORIG_SHOWWARNING = warnings.showwarning


def _showwarning(message, category, filename, lineno, file=None, line=None):
    WARNINGS.append(f"{category.__name__}: {message} ({filename}:{lineno})")
    _ORIG_SHOWWARNING(message, category, filename, lineno, file=file, line=line)

warnings.showwarning = _showwarning
warnings.simplefilter("always", RuntimeWarning)


def load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {filename}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


C11 = load("phase5c15_c11", "phase5c11_joint_direct_reflection_fit.py")
C12 = load("phase5c15_c12", "phase5c12_joint_basin_jacobian.py")
P56, P58, P59 = C11.P56, C11.P58, C11.P59


def truth_planes():
    room, raw_mics, *_ = P58.make_observations()
    normals, offsets, _, _ = P59.true_planes_in_canonical_gauge(room, raw_mics)
    return normals, offsets


def json_safe(value):
    """Encode non-finite diagnostics as null while preserving them in calculations."""
    if isinstance(value, dict):
        return {key: json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    if isinstance(value, (float, np.floating)) and not np.isfinite(value):
        return None
    if isinstance(value, np.integer):
        return int(value)
    return value


def diagnostics(x, label, model, problem, echoes, normals_true, offsets_true, previous_order=None):
    """Evaluate all reporting diagnostics; truth is only consumed here."""
    state = C11.split_and_residuals(x, model, problem.q, echoes)
    direct_distances = np.linalg.norm(state["sources"][None, :, :] - state["microphones"][:, None, :], axis=2)
    corrected_direct_toas = problem.q - state["emissions"][None, :] - state["clocks"][:, None]
    direct_physical = bool(np.all(np.isfinite(direct_distances)) and np.all(direct_distances > 0)
        and np.all(np.isfinite(corrected_direct_toas)) and np.all(corrected_direct_toas > 0))
    jac = C12.full_jacobian(x, model, problem.q, echoes, "analytic")
    singular = np.linalg.svd(jac, compute_uv=False)
    rank = int(np.count_nonzero(singular > singular[0] * 1e-8)) if singular.size and singular[0] else 0
    direct = state["direct_residual_s"]
    echo = state["echo_residual_s"]
    metrics = P56.aligned_metrics(state["microphones"], state["sources"], problem)
    timing = P56.timing_metrics(state["emissions"], state["clocks"], problem)
    _, rotation, ce, ct = C11.align_transform(state["microphones"], state["sources"],
        problem.microphones_truth, problem.sources_truth)
    walls = C11.wall_errors_after_alignment(state["normals"], state["offsets"], rotation, ce, ct,
        normals_true, offsets_true)
    enclosure = P58.feasible_geometry(state["normals"], state["offsets"], state["points"], state["gaps"])
    faces = P58.reflection_face_validity(state["microphones"], state["sources"],
        state["normals"], state["offsets"])
    changed_groups = None
    changed_paths = None
    if previous_order is not None:
        changed_groups = int(np.count_nonzero(np.any(state["echo_order"] != previous_order, axis=2)))
        changed_paths = int(np.count_nonzero(state["echo_order"] != previous_order))
    obj = 0.5 * float(state["residual_m"] @ state["residual_m"])
    return {
        "label": label,
        "direct_residual_norm_s": float(np.linalg.norm(direct)),
        "direct_residual_max_abs_s": float(np.max(np.abs(direct))),
        "reflection_residual_norm_s_exact_sorted": float(np.linalg.norm(echo)),
        "reflection_residual_max_abs_s_exact_sorted": float(np.max(np.abs(echo))),
        "combined_objective_half_sse_m2": obj,
        "microphone_rmse_after_alignment_m": float(metrics[0]),
        "source_rmse_after_alignment_m": float(metrics[1]),
        "combined_position_rmse_after_alignment_m": float(metrics[2]),
        "timing_errors": timing, "wall_plane_errors_evaluation_only": walls,
        "wall_normals_unit": state["normals"].tolist(),
        "wall_offsets_m": state["offsets"].tolist(),
        "wall_support_gaps_m": state["gaps"].tolist(),
        "echo_assignment_groups_changed": changed_groups,
        "echo_assignment_paths_changed": changed_paths,
        "minimum_predicted_echo_gap_s": float(np.min(np.diff(state["predicted_echoes"], axis=2))),
        "full_jacobian_rank_rel_1e-8": rank,
        "full_jacobian_condition": float(singular[0] / singular[-1]) if singular[-1] else float("inf"),
        "full_jacobian_singular_values": singular.tolist(),
        "convex_enclosure": enclosure, "finite_face_bounce_validity": faces,
        "positive_direct_paths_and_corrected_toas": bool(np.all(np.isfinite(state["path_lengths"]))
            and np.all(state["path_lengths"] > 0) and np.all(state["predicted_echoes"] > 0) and direct_physical),
        "all_physical_checks_pass": bool(direct_physical and enclosure["valid_enclosure"]
            and faces["all_bounces_on_finite_faces"] and np.all(state["path_lengths"] > 0)),
        "parameters_83": np.asarray(x, dtype=float).tolist(),
    }


def run_block(x, block_name, indices, model, problem, echoes, normals_true, offsets_true, previous_order):
    """Optimize one coordinate/timing slice under the full exact joint objective."""
    before = diagnostics(x, block_name + "_before", model, problem, echoes, normals_true, offsets_true, previous_order)
    index = np.asarray(indices, dtype=int)
    base = np.asarray(x, dtype=float).copy()

    def assemble(z):
        candidate = base.copy()
        candidate[index] = z
        return candidate

    def residual(z):
        candidate = assemble(z)
        return C11.split_and_residuals(candidate, model, problem.q, echoes)["residual_m"]

    def jacobian(z):
        candidate = assemble(z)
        return C12.full_jacobian(candidate, model, problem.q, echoes, "analytic")[:, index]

    started = perf_counter()
    try:
        opt = least_squares(residual, base[index].copy(), jac=jacobian, method="trf",
            x_scale="jac", max_nfev=MAX_NFEV, ftol=TOL, xtol=TOL, gtol=TOL)
        runtime = perf_counter() - started
        proposal = assemble(opt.x)
        after = diagnostics(proposal, block_name + "_proposal", model, problem, echoes,
                            normals_true, offsets_true, previous_order)
        block_singular = np.linalg.svd(opt.jac, compute_uv=False)
        block_rank = int(np.count_nonzero(block_singular > block_singular[0] * 1e-8)) if block_singular.size and block_singular[0] else 0
        allowance = ACCEPTANCE_RELATIVE_SLACK * max(1.0, before["combined_objective_half_sse_m2"])
        accepted = bool(np.isfinite(after["combined_objective_half_sse_m2"]) and
                        after["combined_objective_half_sse_m2"] <= before["combined_objective_half_sse_m2"] + allowance)
        update = {
            "block": block_name, "parameter_indices": [int(index[0]), int(index[-1]) + 1],
            "accepted": accepted, "rejection_reason": None if accepted else "objective increased or non-finite",
            "before": before, "proposal": after,
            "optimizer": {"method": "SciPy TRF with existing C12 analytic Jacobian columns",
                "success": bool(opt.success), "status": int(opt.status), "message": str(opt.message),
                "nfev": int(opt.nfev), "njev": int(opt.njev or 0), "runtime_s": runtime,
                "optimality": float(opt.optimality), "active_mask": np.asarray(opt.active_mask).tolist(),
                "block_jacobian_rank_rel_1e-8": block_rank,
                "block_jacobian_condition": float(block_singular[0] / block_singular[-1]) if block_singular[-1] else float("inf"),
                "block_jacobian_singular_values": block_singular.tolist()},
            "parameter_step_norm_scaled": float(np.linalg.norm(opt.x - base[index])),
        }
        return (proposal if accepted else base), update
    except Exception as exc:
        runtime = perf_counter() - started
        return base, {"block": block_name, "parameter_indices": [int(index[0]), int(index[-1]) + 1],
            "accepted": False, "rejection_reason": type(exc).__name__ + ": " + str(exc),
            "before": before, "proposal": None,
            "optimizer": {"success": False, "status": None, "message": str(exc),
                "nfev": None, "njev": None, "runtime_s": runtime}}


def profile_start(name, x0, model, problem, echoes, normals_true, offsets_true):
    start_state = C11.split_and_residuals(x0, model, problem.q, echoes)
    start_order = start_state["echo_order"].copy()
    initial = diagnostics(x0, name + "_initial", model, problem, echoes, normals_true, offsets_true)
    direct_count = model.coord_count
    timing_indices = range(model.clock_start, model.size)
    coordinate_indices = range(0, direct_count)

    current_t, timing_update = run_block(x0, name + "_timing_only", timing_indices, model, problem, echoes,
                                         normals_true, offsets_true, start_order)
    current_c, coordinate_update = run_block(x0, name + "_coordinate_only", coordinate_indices, model, problem, echoes,
                                             normals_true, offsets_true, start_order)
    alternating_x = np.asarray(x0, dtype=float).copy()
    iterations = []
    previous_objective = initial["combined_objective_half_sse_m2"]
    stop_reason = "maximum alternating cycles reached"
    for cycle in range(1, MAX_ALTERNATING_CYCLES + 1):
        before_cycle = diagnostics(alternating_x, f"{name}_cycle_{cycle}_before", model, problem, echoes,
                                   normals_true, offsets_true, start_order)
        cycle_start_order = C11.split_and_residuals(alternating_x, model, problem.q, echoes)["echo_order"].copy()
        x_after_t, update_t = run_block(alternating_x, f"{name}_cycle_{cycle}_timing", timing_indices,
            model, problem, echoes, normals_true, offsets_true, cycle_start_order)
        alternating_x = x_after_t
        post_timing_order = C11.split_and_residuals(alternating_x, model, problem.q, echoes)["echo_order"].copy()
        x_after_c, update_c = run_block(alternating_x, f"{name}_cycle_{cycle}_coordinate", coordinate_indices,
            model, problem, echoes, normals_true, offsets_true, post_timing_order)
        alternating_x = x_after_c
        after_cycle = diagnostics(alternating_x, f"{name}_cycle_{cycle}_after", model, problem, echoes,
                                  normals_true, offsets_true, start_order)
        improvement = before_cycle["combined_objective_half_sse_m2"] - after_cycle["combined_objective_half_sse_m2"]
        relative = improvement / max(abs(before_cycle["combined_objective_half_sse_m2"]), 1e-30)
        iterations.append({"cycle": cycle, "before": before_cycle, "timing_update": update_t,
                           "coordinate_update": update_c, "after": after_cycle,
                           "objective_improvement": float(improvement),
                           "relative_objective_improvement": float(relative)})
        if improvement <= OBJECTIVE_ABSOLUTE_STOP + OBJECTIVE_RELATIVE_STOP * abs(before_cycle["combined_objective_half_sse_m2"]):
            stop_reason = "objective improvement at or below documented absolute-plus-relative threshold"
            break
        previous_objective = after_cycle["combined_objective_half_sse_m2"]
    return {
        "name": name, "initial": initial,
        "timing_only": timing_update, "coordinate_only": coordinate_update,
        "alternating": {"cycles": iterations, "stop_reason": stop_reason,
            "max_cycles": MAX_ALTERNATING_CYCLES, "final": iterations[-1]["after"] if iterations else initial},
    }


def main():
    problem, model, echoes, _ = C11.load_exact_inputs()
    archive = json.loads(C11_JSON.read_text(encoding="utf-8"))
    echo_archive = json.loads(C8_JSON.read_text(encoding="utf-8"))
    saved_echoes = np.asarray(echo_archive["observations"]["observed_echo_TOAs_s_sorted_within_each_group"], dtype=float)
    if not np.array_equal(saved_echoes, echoes):
        raise RuntimeError("C11 loader did not reproduce archived C8 observations exactly")
    runs = {row["name"]: row for row in archive["runs"]}
    reference_row = runs["generating_endpoint_staged_data_derived_walls"]
    positive = np.asarray(reference_row["final_complete_parameters_83"], dtype=float)
    blind_rows = archive["blind_observation_starts"]
    normals_true, offsets_true = truth_planes()
    output = {
        "phase": "5C.15 timing and coordinate block profiling",
        "preservation": {"C11_blind_vectors_loaded_verbatim": True,
            "C11_staged_positive_control_loaded_verbatim": True,
            "C8_echo_observations_exactly_reverified": True,
            "ground_truth_used_only_in_diagnostics": True},
        "model": {"direct_observation_equation": "q_ij=e_j+||s_j-m_i||/c+b_i",
            "gauge": "m1=origin; m2 positive x; m3 in xy plane positive y; e0=0",
            "dimensions": {"M": model.m, "N": model.n, "direct_parameters": model.size,
                "coordinate_parameter_count": model.coord_count, "timing_parameter_count": model.m+model.n-1,
                "wall_parameter_count": 18, "joint_parameter_count": model.size+18},
            "residual": "C11 exact sorted direct plus first-order echo residuals, distance-unit scaling",
            "analytic_jacobian": "C12 direct analytic block plus C12 fixed-branch analytic echo derivatives; exact sorting is recomputed in residual evaluation",
            "optimizer": {"method": "SciPy TRF", "x_scale": "jac", "max_nfev_per_block": MAX_NFEV,
                "ftol_xtol_gtol": TOL},
            "block_acceptance": "accept proposal if full exact-sorted half-SSE is finite and does not increase beyond 1e-12*max(1, prior objective); physical validity is recorded, not used as a hidden objective or constraint",
            "alternating_stopping": {"maximum_cycles": MAX_ALTERNATING_CYCLES,
                "stop_if_cycle_improvement_le": f"{OBJECTIVE_ABSOLUTE_STOP:g} + {OBJECTIVE_RELATIVE_STOP:g}*abs(previous objective)"},
            "ordering": "timing then coordinates per alternating cycle; each block solve starts from the last accepted complete state"},
        "positive_control_source": reference_row["name"],
        "positive_control": profile_start("staged_reference_positive_control", positive, model, problem, echoes, normals_true, offsets_true),
        "blind_results": [profile_start(row["name"], np.asarray(row["initial_complete_parameters_83"], dtype=float),
            model, problem, echoes, normals_true, offsets_true) for row in blind_rows],
        "runtime_warnings": WARNINGS,
        "interpretation_scope": "Synthetic seed-11 diagnostics only; no global uniqueness, infeasibility, or production-method claim.",
    }
    OUT.write_text(json.dumps(json_safe(output), indent=2, allow_nan=False), encoding="utf-8")
    log_path = HERE / "phase5c15_run.log"
    with log_path.open("w", encoding="utf-8") as f:
        f.write("Phase 5C.15 block profiling; exact archived seed-11 data; synthetic only\n")
        for warning in WARNINGS:
            f.write("WARNING " + warning + "\n")
        for record in [output["positive_control"], *output["blind_results"]]:
            f.write(f"\n{record['name']}\n")
            for label, update in (("timing-only", record["timing_only"]), ("coordinate-only", record["coordinate_only"])):
                prop = update.get("proposal") or {}
                opt = update.get("optimizer", {})
                f.write(f"  {label}: accepted={update['accepted']} direct={prop.get('direct_residual_norm_s')} echo={prop.get('reflection_residual_norm_s_exact_sorted')} xyz={prop.get('combined_position_rmse_after_alignment_m')} timing={prop.get('timing_errors')} status={opt.get('status')} nfev={opt.get('nfev')} runtime_s={opt.get('runtime_s')}\n")
            for cycle in record["alternating"]["cycles"]:
                a=cycle["after"]
                f.write(f"  cycle {cycle['cycle']}: objective={a['combined_objective_half_sse_m2']:.9g} direct={a['direct_residual_norm_s']:.8g} echo={a['reflection_residual_norm_s_exact_sorted']:.8g} xyz={a['combined_position_rmse_after_alignment_m']:.8g} timing_rmse_e_s={a['timing_errors']['emission_rmse_s']:.8g} timing_rmse_b_s={a['timing_errors']['clock_rmse_s']:.8g} accepted=({cycle['timing_update']['accepted']},{cycle['coordinate_update']['accepted']}) assignment_changes=({cycle['timing_update'].get('proposal',{}).get('echo_assignment_groups_changed')},{cycle['coordinate_update'].get('proposal',{}).get('echo_assignment_groups_changed')})\n")
            f.write("  stop=" + record["alternating"]["stop_reason"] + "\n")
        f.write(f"\nresults_json={OUT}\n")
    print(f"wrote {OUT}; blind starts={len(blind_rows)}")


if __name__ == "__main__":
    main()
