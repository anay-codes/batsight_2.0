"""Phase 5C.11 exploratory joint direct-TOA / first-order echo optimization.

Coordinates, timing variables, and six shared planes are fit together. True
room planes are used only for post-fit evaluation, never for initialization or
the objective. This is not a production reconstruction algorithm.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
from time import perf_counter
from types import SimpleNamespace

import numpy as np
from scipy.optimize import least_squares

HERE = Path(__file__).resolve().parent
OUT = HERE / "phase5c11_results.json"
DIRECT_ARCHIVE = HERE / "phase5c6_results.json"
ECHO_ARCHIVE = HERE / "phase5c8_results.json"
C = 343.0
MAX_NFEV = 80
TOL = 1e-11
ECHO_FD_STEP = 1e-6


def load(name: str, file: str):
    spec = importlib.util.spec_from_file_location(name, HERE / file)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {file}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


P56 = load("phase5c11_p56", "phase5c6_blind_initialization.py")
P59 = load("phase5c11_p59", "phase5c9_unknown_wall_solver_validation.py")
P58 = P59.P58


def load_exact_inputs():
    direct_archive = json.loads(DIRECT_ARCHIVE.read_text(encoding="utf-8"))
    echo_archive = json.loads(ECHO_ARCHIVE.read_text(encoding="utf-8"))
    problem = P56.seed11_problem()
    c8_echoes = np.asarray(
        echo_archive["observations"]["observed_echo_TOAs_s_sorted_within_each_group"],
        dtype=np.float64,
    )
    _, _, _, _, _, regenerated, _, _ = P58.make_observations()
    if not np.array_equal(c8_echoes, regenerated):
        raise RuntimeError("Phase 5C.8 echo matrix differs from the deterministic seed-11 fixture")
    rows = direct_archive["problems"]["seed11_noise_0s"]["runs"]
    output = {}
    length, tscale = P56.characteristic_scales(problem.q, C)
    model = P56.DirectFit(problem.q, C, length, tscale)
    for key, init_name in (("generating", "oracle_positive_control"), ("competing", "Gaubitch100_plus_Crocco")):
        row = next(item for item in rows if item["initializer"] == init_name)
        vector = np.asarray(row["final_parameters_scaled"], dtype=np.float64)
        mic, src, emissions, clocks = model.unpack(vector)
        output[key] = {
            "archive_initializer": init_name,
            "direct_parameters": vector,
            "microphones": mic,
            "sources": src,
            "emissions": emissions,
            "clocks": clocks,
            "archive_row": row,
        }
    return problem, model, c8_echoes, output


def joint_start(direct_x: np.ndarray, model: P56.DirectFit) -> np.ndarray:
    mic, src, _, _ = model.unpack(direct_x)
    wall_x = P58.initial_start(-1, np.vstack((mic, src)))
    return np.r_[direct_x, wall_x]


def split_and_residuals(x, model, q, echo_observations):
    direct_x = x[:model.size]
    wall_x = x[model.size:]
    direct_scaled, direct_jac_scaled = model.residual_jac(direct_x)
    microphones, sources, emissions, clocks = model.unpack(direct_x)
    points = np.vstack((microphones, sources))
    normals, offsets, gaps = P58.plane_parameters(wall_x, points)
    predicted, order, _, lengths = P59.corrected_echoes_with_associations(
        {"mics": microphones, "sources": sources, "emissions": emissions, "clocks": clocks},
        normals,
        offsets,
    )
    direct_m = direct_scaled * model.ts * model.c
    echo_m = (predicted - echo_observations) * model.c
    residual = np.r_[direct_m, echo_m.ravel()]
    return {
        "direct_x": direct_x,
        "wall_x": wall_x,
        "microphones": microphones,
        "sources": sources,
        "emissions": emissions,
        "clocks": clocks,
        "points": points,
        "normals": normals,
        "offsets": offsets,
        "gaps": gaps,
        "predicted_echoes": predicted,
        "echo_order": order,
        "path_lengths": lengths,
        "direct_residual_s": direct_m / model.c,
        "echo_residual_s": predicted - echo_observations,
        "residual_m": residual,
        "direct_jacobian_m": direct_jac_scaled * model.ts * model.c,
    }


def joint_jacobian(x, model, q, echo_observations):
    """Analytic direct block plus forward finite differences for echo rows.

    Direct TOA derivatives use the existing validated DirectFit Jacobian.
    Echo derivatives use a one-sided 1e-6 step in the existing scaled
    parameter chart; sorted assignment is recomputed at each perturbation.
    """
    base = split_and_residuals(x, model, q, echo_observations)
    rows_direct = model.m * model.n
    total = model.size + 18
    jac = np.zeros((rows_direct + echo_observations.size, total), dtype=np.float64)
    jac[:rows_direct, :model.size] = base["direct_jacobian_m"]
    for k in range(total):
        h = ECHO_FD_STEP * max(1.0, abs(float(x[k])))
        shifted = np.asarray(x, dtype=np.float64).copy()
        shifted[k] += h
        values = split_and_residuals(shifted, model, q, echo_observations)["echo_residual_s"].ravel() * model.c
        jac[rows_direct:, k] = (values - base["echo_residual_s"].ravel() * model.c) / h
    return jac


def align_transform(est_m, est_s, truth_m, truth_s):
    estimated = np.vstack((est_m, est_s))
    truth = np.vstack((truth_m, truth_s))
    ce, ct = estimated.mean(axis=0), truth.mean(axis=0)
    u, _, vt = np.linalg.svd((estimated - ce).T @ (truth - ct))
    rotation = u @ vt  # preserve evaluator's O(3), including reflection branch
    aligned = (estimated - ce) @ rotation + ct
    return aligned, rotation, ce, ct


def wall_errors_after_alignment(normals, offsets, rotation, ce, ct, true_normals, true_offsets):
    aligned_normals = (rotation.T @ normals.T).T
    aligned_offsets = offsets + normals @ ce - aligned_normals @ ct
    return {
        **P59.plane_errors(aligned_normals, aligned_offsets, true_normals, true_offsets),
        "aligned_normals": aligned_normals.tolist(),
        "aligned_offsets_m": aligned_offsets.tolist(),
    }


def run_joint(name, start, start_kind, model, problem, echoes, truth, true_normals, true_offsets, *, max_nfev=MAX_NFEV):
    start = np.asarray(start, dtype=np.float64)
    fun = lambda x: split_and_residuals(x, model, problem.q, echoes)["residual_m"]
    jac = lambda x: joint_jacobian(x, model, problem.q, echoes)
    initial = split_and_residuals(start, model, problem.q, echoes)
    begin = perf_counter()
    opt = least_squares(fun, start, jac=jac, method="trf", x_scale="jac", max_nfev=max_nfev, ftol=TOL, xtol=TOL, gtol=TOL)
    runtime = perf_counter() - begin
    final = split_and_residuals(opt.x, model, problem.q, echoes)
    m, n = model.m * model.n, echoes.size
    singular = np.linalg.svd(opt.jac, compute_uv=False)
    rank = int(np.count_nonzero(singular > singular[0] * 1e-8))
    enclosure = P58.feasible_geometry(final["normals"], final["offsets"], final["points"], final["gaps"])
    face = P58.reflection_face_validity(final["microphones"], final["sources"], final["normals"], final["offsets"])
    aligned, rotation, ce, ct = align_transform(final["microphones"], final["sources"], truth.microphones_truth, truth.sources_truth)
    geo = P56.aligned_metrics(final["microphones"], final["sources"], truth)
    timing = P56.timing_metrics(final["emissions"], final["clocks"], truth)
    direct_res = final["direct_residual_s"]
    echo_res = final["echo_residual_s"]
    assignment_changes = int(np.count_nonzero(np.any(final["echo_order"] != initial["echo_order"], axis=2)))
    direct_corrected = problem.q - final["emissions"][None, :] - final["clocks"][:, None]
    direct_lengths = np.linalg.norm(final["sources"][None, :, :] - final["microphones"][:, None, :], axis=2)
    direct_physical = bool(np.all(direct_lengths > 0) and np.all(np.isfinite(direct_lengths)) and np.all(direct_corrected > 0) and np.all(np.isfinite(direct_corrected)))
    return {
        "name": name,
        "start_kind": start_kind,
        "initial_direct_residual_norm_s": float(np.linalg.norm(initial["direct_residual_s"])),
        "initial_echo_residual_norm_s": float(np.linalg.norm(initial["echo_residual_s"])),
        "direct_residual_norm_s": float(np.linalg.norm(direct_res)),
        "direct_max_abs_residual_s": float(np.max(np.abs(direct_res))),
        "reflection_residual_norm_s": float(np.linalg.norm(echo_res)),
        "reflection_max_abs_residual_s": float(np.max(np.abs(echo_res))),
        "microphone_coordinate_rmse_after_alignment_m": geo[0],
        "source_coordinate_rmse_after_alignment_m": geo[1],
        "combined_coordinate_rmse_after_alignment_m": geo[2],
        "timing_errors": timing,
        "wall_plane_errors_evaluation_only": wall_errors_after_alignment(final["normals"], final["offsets"], rotation, ce, ct, true_normals, true_offsets),
        "convex_enclosure": enclosure,
        "positive_direct_path_lengths_and_corrected_TOAs": direct_physical,
        "minimum_direct_path_length_m": float(np.min(direct_lengths)),
        "minimum_corrected_direct_TOA_s": float(np.min(direct_corrected)),
        "positive_image_path_lengths": bool(np.all(np.isfinite(final["path_lengths"])) and np.all(final["path_lengths"] > 0) and np.all(final["predicted_echoes"] > 0)),
        "minimum_image_path_length_m": float(np.min(final["path_lengths"])),
        "finite_face_bounce_validity": face,
        "all_physical_checks_pass": bool(direct_physical and enclosure["valid_enclosure"] and face["all_bounces_on_finite_faces"] and np.all(final["path_lengths"] > 0) and np.all(final["predicted_echoes"] > 0)),
        "echo_assignment_groups_changed_from_start": assignment_changes,
        "minimum_adjacent_echo_arrival_gap_s": float(np.min(np.diff(final["predicted_echoes"], axis=2))),
        "full_joint_jacobian_rank_relative_1e-8": rank,
        "full_joint_jacobian_singular_values": singular.tolist(),
        "full_joint_jacobian_condition": float(singular[0] / singular[-1]) if singular[-1] > 0 else float("inf"),
        "optimizer_success": bool(opt.success),
        "optimizer_status": int(opt.status),
        "optimizer_message": str(opt.message),
        "nfev": int(opt.nfev),
        "njev": int(opt.njev or 0),
        "runtime_s": float(runtime),
        "initial_complete_parameters_83": start.tolist(),
        "final_complete_parameters_83": opt.x.tolist(),
        "final_direct_parameters_65": opt.x[:model.size].tolist(),
        "final_wall_parameters_18": opt.x[model.size:].tolist(),
    }


def make_direct_blind_start(model, q, seed):
    length, _ = P56.characteristic_scales(q, C)
    pseudo_problem = SimpleNamespace(q=q, c=C)
    mic, src, emissions, clocks = P56.random_blind_start(pseudo_problem, seed, length)
    return model.pack(mic, src, emissions, clocks)


def main():
    problem, model, echoes, endpoints = load_exact_inputs()
    # Ground truth and true planes are confined to evaluation below.
    truth = problem
    room, raw_m, _, _, _, _, _, _ = P58.make_observations()
    true_normals, true_offsets, _, _ = P59.true_planes_in_canonical_gauge(room, raw_m)

    output_runs = []
    initial_direct = {}
    initial_full = {}
    for key in ("generating", "competing"):
        direct_x = endpoints[key]["direct_parameters"].copy()
        start = joint_start(direct_x, model)
        initial_direct[key] = direct_x
        initial_full[key] = start
        output_runs.append(run_joint(f"{key}_endpoint_PCA_wall_start", start, f"archived_{key}_direct_endpoint + data-derived PCA/gap wall start", model, problem, echoes, truth, true_normals, true_offsets))

    # Additional staged starts: walls are first fit to echoes while the
    # corresponding archived endpoint is fixed, then all 83 parameters are
    # jointly released. No true wall coefficients or labels enter these starts.
    c9_results = json.loads((HERE / "phase5c9_results.json").read_text(encoding="utf-8"))
    c10_followup = json.loads((HERE / "phase5c10_followup_results.json").read_text(encoding="utf-8"))
    staged_g_wall = np.asarray(next(r for r in c9_results["blind_start_investigation"]["runs_by_endpoint"]["generating"] if r["seed"] == -1)["final_parameters"])
    staged_c_wall = np.asarray(next(r for r in c10_followup["face_penalty_continuation_10_to_100_to_1000"] if r["face_penalty_weight"] == 100.0)["parameters"])
    staged_runs = []
    for key, wall_x, label in (
        ("generating", staged_g_wall, "C9-generated-endpoint echo-fit wall solution"),
        ("competing", staged_c_wall, "C10-competing-endpoint echo-fit continuation wall solution"),
    ):
        staged = np.r_[endpoints[key]["direct_parameters"], wall_x]
        row = run_joint(f"{key}_endpoint_staged_data_derived_walls", staged, f"archived {key} direct endpoint + {label}; all variables jointly released", model, problem, echoes, truth, true_normals, true_offsets)
        staged_runs.append(row)

    perturb_rows = []
    for key in ("generating", "competing"):
        base = initial_full[key]
        for magnitude, seed in ((0.005, 511), (0.02, 922)):
            rng = np.random.default_rng(seed + (0 if key == "generating" else 1000))
            perturbed = base + rng.normal(0.0, magnitude, base.size)
            row = run_joint(f"{key}_derived_full_perturb_{magnitude:g}", perturbed, f"complete vector perturbed around archived {key} endpoint; sigma={magnitude}", model, problem, echoes, truth, true_normals, true_offsets, max_nfev=MAX_NFEV)
            perturb_rows.append(row)

    blind_rows = []
    for seed in (17, 29, 41):
        direct_x = make_direct_blind_start(model, problem.q, seed)
        start = joint_start(direct_x, model)
        blind_rows.append(run_joint(f"blind_observation_start_{seed}", start, f"q,c-derived random geometry and zero timing; seed={seed}; PCA wall start from candidate points", model, problem, echoes, truth, true_normals, true_offsets, max_nfev=MAX_NFEV))

    total_unknowns = model.size + 18
    total_observations = model.m * model.n + echoes.size
    output = {
        "phase": "5C.11 joint Euclidean direct-TOA and first-order reflection experiment",
        "preservation": {
            "Phase_5C6_endpoint_vectors_loaded_verbatim": True,
            "Phase_5C8_echo_TOAs_loaded_verbatim_and_exactly_reverified": True,
            "all_prior_experiment_files_read_only": True,
        },
        "model": {
            "direct_equation": "q_ij=e_j+||s_j-m_i||/c+b_i",
            "reflection_equation": "e_j+b_i+||m_i-(s_j-2(n_k^T s_j+d_k)n_k)||/c",
            "direct_gauges": "m1=(0,0,0); m2 on +x; m3 in xy with positive y; e1=0",
            "wall_parameterization": "12 azimuth/elevation parameters and six log support gaps; offsets derived from current endpoint point support with the C9/C10 numerical clearance floor",
            "unknown_count": {"direct_gauge_fixed": model.size, "wall_parameters": 18, "total": total_unknowns},
            "observation_count": {"direct": model.m * model.n, "reflection": int(echoes.size), "total": total_observations},
            "residual_scaling_and_weights": "Direct and echo TOA residuals are both multiplied by known c, converting seconds to distance-equivalent metres. Every individual observation has unit weight; the 390 echo terms are not normalized down to the 65 direct terms. No regularization or face-penalty residual is used.",
            "assignment": "Within each known microphone/source event group, sort predicted and observed six scalar arrival sets. For squared residual this is the globally optimal one-to-one assignment by the rearrangement inequality. Assignment is recomputed at every residual evaluation.",
            "physical_checks": "Containment follows the C9 support-gap parameterization. Bounded convexity, positive path lengths/arrivals, and finite-face bounce points are separate acceptance diagnostics, not weighted residual terms.",
            "optimizer": "SciPy least_squares TRF; analytic existing direct block Jacobian plus forward finite-difference echo block Jacobian (relative parameter step 1e-6); x_scale=jac; tolerances 1e-11; max_nfev=80.",
            "full_jacobian": "Optimizer Jacobian for stacked 455 distance-equivalent residuals and all 83 parameters; numerical rank threshold 1e-8 relative to largest singular value.",
        },
        "generating_positive_control": output_runs[0],
        "competing_endpoint_start": output_runs[1],
        "staged_wall_initialization_runs": staged_runs,
        "perturbed_endpoint_starts": perturb_rows,
        "blind_observation_starts": blind_rows,
        "runs": output_runs + staged_runs + perturb_rows + blind_rows,
        "metric_notes": "Coordinate and timing errors and wall-plane errors are evaluation-only against seed-11 simulation truth after Euclidean alignment and plane permutation. They do not enter any start or objective.",
    }
    OUT.write_text(json.dumps(output, indent=2), encoding="utf-8")
    for row in output["runs"]:
        print(row["name"], "direct", row["direct_residual_norm_s"], "echo", row["reflection_residual_norm_s"], "coord", row["combined_coordinate_rmse_after_alignment_m"], "phys", row["all_physical_checks_pass"], "rank/cond", row["full_joint_jacobian_rank_relative_1e-8"], row["full_joint_jacobian_condition"], "status", row["optimizer_status"], "nfev", row["nfev"], "sec", row["runtime_s"])
    print("unknowns", total_unknowns, "observations", total_observations, "results", OUT)


if __name__ == "__main__":
    main()
