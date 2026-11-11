"""Phase 5C.14: diagnostic tracing of seed-11 blind joint initializations.

This script reads C11/C12/C13 artifacts and uses their blind starts verbatim.
All truth values are confined to post-run scoring. No production algorithm or
approved paper equation is changed.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
from time import perf_counter
import warnings

import numpy as np
from scipy.optimize import least_squares

HERE = Path(__file__).resolve().parent
OUT = HERE / "phase5c14_results.json"
DIRECT_ARCHIVE = HERE / "phase5c6_results.json"
ECHO_ARCHIVE = HERE / "phase5c8_results.json"
C11_ARCHIVE = HERE / "phase5c11_results.json"
C13_ARCHIVE = HERE / "phase5c13_results.json"
C = 343.0
JOINT_MAX_NFEV = 80
TOL = 1e-11
RECORDED_WARNINGS: list[str] = []
_ORIGINAL_SHOWWARNING = warnings.showwarning


def _record_warning(message, category, filename, lineno, file=None, line=None):
    RECORDED_WARNINGS.append(f"{category.__name__}: {message} ({filename}:{lineno})")
    _ORIGINAL_SHOWWARNING(message, category, filename, lineno, file=file, line=line)


warnings.showwarning = _record_warning
warnings.simplefilter("always", RuntimeWarning)


def load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {filename}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


C11 = load("phase5c14_c11", "phase5c11_joint_direct_reflection_fit.py")
C12 = load("phase5c14_c12", "phase5c12_joint_basin_jacobian.py")
C13 = load("phase5c14_c13", "phase5c13_smooth_echo_assignment.py")
P56 = C11.P56
P58 = C11.P58
P59 = C11.P59


def truth_planes():
    room, raw_mics, *_ = P58.make_observations()
    normals, offsets, _, _ = P59.true_planes_in_canonical_gauge(room, raw_mics)
    return room, normals, offsets


def score_state(name, x, model, problem, echoes, true_normals, true_offsets,
                reference_order=None, optimizer=None):
    state = C11.split_and_residuals(x, model, problem.q, echoes)
    direct = state["direct_residual_s"]
    reflection = state["echo_residual_s"]
    direct_lengths = np.linalg.norm(state["sources"][None, :, :] - state["microphones"][:, None, :], axis=2)
    corrected_direct = problem.q - state["emissions"][None, :] - state["clocks"][:, None]
    direct_positive = bool(np.all(np.isfinite(direct_lengths)) and np.all(direct_lengths > 0)
                           and np.all(np.isfinite(corrected_direct)) and np.all(corrected_direct > 0))
    enclosure = P58.feasible_geometry(state["normals"], state["offsets"], state["points"], state["gaps"])
    face = P58.reflection_face_validity(state["microphones"], state["sources"], state["normals"], state["offsets"])
    aligned, rotation, ce, ct = C11.align_transform(state["microphones"], state["sources"],
                                                    problem.microphones_truth, problem.sources_truth)
    pos = P56.aligned_metrics(state["microphones"], state["sources"], problem)
    timing = P56.timing_metrics(state["emissions"], state["clocks"], problem)
    wall = C11.wall_errors_after_alignment(state["normals"], state["offsets"], rotation, ce, ct,
                                           true_normals, true_offsets)
    j = C12.full_jacobian(x, model, problem.q, echoes, "analytic")
    sv = np.linalg.svd(j, compute_uv=False)
    rank = int(np.sum(sv > sv[0] * 1e-8))
    assignment_changes = None
    changed_pairs = None
    if reference_order is not None:
        assignment_changes = int(np.count_nonzero(np.any(state["echo_order"] != reference_order, axis=2)))
        changed_pairs = int(np.count_nonzero(state["echo_order"] != reference_order))
    objective = 0.5 * float(np.dot(state["residual_m"], state["residual_m"]))
    result = {
        "stage": name,
        "direct_residual_norm_s": float(np.linalg.norm(direct)),
        "direct_max_abs_residual_s": float(np.max(np.abs(direct))),
        "reflection_residual_norm_s_exact_sorted": float(np.linalg.norm(reflection)),
        "reflection_max_abs_residual_s_exact_sorted": float(np.max(np.abs(reflection))),
        "joint_objective_half_sse_m2_exact_sorted": objective,
        "aligned_microphone_rmse_m": pos[0], "aligned_source_rmse_m": pos[1],
        "aligned_combined_position_rmse_m": pos[2],
        "timing_errors": timing,
        "wall_plane_errors_evaluation_only": wall,
        "wall_normals_unit": state["normals"].tolist(),
        "wall_offsets_m": state["offsets"].tolist(),
        "wall_support_gaps_m": state["gaps"].tolist(),
        "direct_path_valid": direct_positive,
        "positive_reflection_path_lengths_and_arrivals": bool(np.all(state["path_lengths"] > 0)
            and np.all(np.isfinite(state["path_lengths"])) and np.all(state["predicted_echoes"] > 0)),
        "convex_enclosure": enclosure,
        "finite_face_bounce_validity": face,
        "all_physical_checks_pass": bool(direct_positive and enclosure["valid_enclosure"]
            and face["all_bounces_on_finite_faces"] and np.all(state["path_lengths"] > 0)),
        "echo_assignment_groups_changed_from_reference": assignment_changes,
        "echo_assignment_pairs_changed_from_reference": changed_pairs,
        "minimum_predicted_echo_gap_s": float(np.min(np.diff(state["predicted_echoes"], axis=2))),
        "jacobian_rank_rel_1e-8": rank,
        "jacobian_singular_values": sv.tolist(),
        "jacobian_condition": float(sv[0] / sv[-1]) if sv[-1] else float("inf"),
        "complete_parameters_83": np.asarray(x).tolist(),
    }
    if optimizer is not None:
        result["optimizer"] = optimizer
    return result


def endpoint_from_direct(x, model):
    mic, src, emissions, clocks = model.unpack(x)
    return {"mics": mic, "sources": src, "emissions": emissions, "clocks": clocks}


def conditional_timing_fit(direct_x, model, problem):
    """Fit b_i and e_j linearly given candidate coordinates (engineering ablation)."""
    mic, src, emissions, clocks = model.unpack(direct_x)
    distances = np.linalg.norm(src[None, :, :] - mic[:, None, :], axis=2)
    y = problem.q - distances / problem.c
    m, n = y.shape
    # e_0 is fixed at zero; columns are b_0..b_(M-1), e_1..e_(N-1).
    design = np.zeros((m*n, m+n-1))
    target = y.ravel()
    row = 0
    for i in range(m):
        for j in range(n):
            design[row, i] = 1.0
            if j > 0:
                design[row, m+j-1] = 1.0
            row += 1
    solution, _, rank, singular = np.linalg.lstsq(design, target, rcond=None)
    new_clocks = solution[:m]
    new_emissions = np.r_[0.0, solution[m:]]
    return model.pack(mic, src, new_emissions, new_clocks), {
        "method": "linear least squares for clocks/emissions conditional on blind candidate coordinates",
        "uses_ground_truth": False,
        "design_shape": list(design.shape), "design_rank": int(rank),
        "design_condition": float(singular[0]/singular[-1]) if singular[-1] else float("inf"),
        "conditional_timing_residual_norm_s": float(np.linalg.norm(design @ solution-target)),
    }


def direct_only_fit(direct_x, model, problem, echoes, truth_normals, truth_offsets, label):
    started = perf_counter()
    fit = model.optimize(direct_x, max_nfev=JOINT_MAX_NFEV)
    elapsed = perf_counter()-started
    joint_start = C11.joint_start(fit["x"], model)  # wall PCA is recomputed from candidate points only
    record = score_state(label, joint_start, model, problem, echoes, truth_normals, truth_offsets,
                         optimizer={"method": "direct Euclidean TOA only; wall planes not optimized",
                                    "success": bool(fit["optimizer"].success),
                                    "status": int(fit["optimizer"].status),
                                    "message": str(fit["optimizer"].message),
                                    "nfev": int(fit["optimizer"].nfev),
                                    "njev": int(fit["optimizer"].njev or 0),
                                    "runtime_s": elapsed,
                                    "direct_only_position_rmse_m": P56.aligned_metrics(fit["microphones"], fit["sources"], problem)[2],
                                    "direct_only_emission_clock_errors": P56.timing_metrics(fit["emissions"], fit["offsets"], problem),
                                    "direct_only_jacobian_rank": fit["rank"],
                                    "direct_only_jacobian_condition": fit["condition"],
                                    "direct_only_toa_residual_norm_s": float(np.linalg.norm(fit["residual_s"]))})
    return fit, joint_start, record


def optimize_joint(start, label, model, problem, echoes, truth_normals, truth_offsets,
                   reference_order, *, fixed_order=None, max_nfev=JOINT_MAX_NFEV):
    """Analytic-Jacobian joint fit; optional frozen wall-to-echo map is an ablation."""
    if fixed_order is None:
        row = C12.run_solver(label, start, "sorted_analytic", model, problem, echoes,
                             problem, truth_normals, truth_offsets)
        return {**row, "association_mode": "recomputed exact sorted assignment"}

    fixed_targets = np.empty_like(echoes)
    start_state = C11.split_and_residuals(start, model, problem.q, echoes)
    start_order = start_state["echo_order"]
    for i in range(model.m):
        for j in range(model.n):
            fixed_targets[i, j, start_order[i, j]] = echoes[i, j]

    def evaluate(x):
        state = C11.split_and_residuals(x, model, problem.q, echoes)
        pred_sorted, order, _, distances = P59.corrected_echoes_with_associations(
            endpoint_from_direct(x[:model.size], model), state["normals"], state["offsets"])
        raw_arrivals = state["emissions"][None, :, None] + state["clocks"][:, None, None] + distances/model.c
        sorted_jac = C12.analytic_echo_jacobian(x, model, problem.q, echoes).reshape(model.m, model.n, 6, -1)
        raw_jac = np.empty_like(sorted_jac)
        for i in range(model.m):
            for j in range(model.n):
                raw_jac[i, j, order[i,j], :] = sorted_jac[i,j]
        residual = np.r_[state["direct_residual_s"].ravel()*model.c,
                         ((raw_arrivals-fixed_targets)*model.c).ravel()]
        jac = np.zeros((model.m*model.n+echoes.size, x.size))
        jac[:model.m*model.n,:model.size] = state["direct_jacobian_m"]
        jac[model.m*model.n:] = (raw_jac*model.c).reshape(echoes.size, x.size)
        return residual, jac, state

    started=perf_counter()
    opt=least_squares(lambda z:evaluate(z)[0],np.asarray(start,dtype=float),jac=lambda z:evaluate(z)[1],
                      method="trf",x_scale="jac",max_nfev=max_nfev,ftol=TOL,xtol=TOL,gtol=TOL)
    runtime=perf_counter()-started
    res,jac,state=evaluate(opt.x)
    sv=np.linalg.svd(jac,compute_uv=False)
    rank=int(np.sum(sv>sv[0]*1e-8))
    scored=score_state(label,opt.x,model,problem,echoes,truth_normals,truth_offsets,reference_order)
    scored.update({"association_mode":"frozen predicted wall-ID to observed-rank map from initial PCA start",
                   "frozen_echo_targets_by_wall_id_s":fixed_targets.tolist(),
                   "optimizer":{"method":"SciPy TRF, analytic direct and raw-path echo Jacobian",
                       "success":bool(opt.success),"status":int(opt.status),"message":str(opt.message),
                       "nfev":int(opt.nfev),"njev":int(opt.njev or 0),"runtime_s":runtime},
                   "fixed_association_objective_half_sse_m2":0.5*float(res@res),
                   "fixed_association_jacobian_rank_rel_1e-8":rank,
                   "fixed_association_jacobian_condition":float(sv[0]/sv[-1]) if sv[-1] else float("inf"),
                   "fixed_association_jacobian_singular_values":sv.tolist()})
    return scored


def safe_analytic_joint(label, start, model, problem, echoes, truth, truth_normals, truth_offsets):
    """Preserve a stage failure as data; do not let one invalid candidate abort the audit."""
    try:
        return C12.run_solver(label, start, "analytic", model, problem, echoes,
                              truth, truth_normals, truth_offsets)
    except Exception as exc:  # exploratory adversarial starts can leave the model domain
        return {"start_name": label, "stage_failure": type(exc).__name__ + ": " + str(exc),
                "optimizer": {"success": False, "status": None, "nfev": None,
                              "runtime_s": None}}


def main():
    problem, model, echoes, _ = C11.load_exact_inputs()
    c11 = json.loads(C11_ARCHIVE.read_text(encoding="utf-8"))
    c13 = json.loads(C13.OUT.read_text(encoding="utf-8"))
    direct_archive = json.loads(DIRECT_ARCHIVE.read_text(encoding="utf-8"))
    echo_archive = json.loads(ECHO_ARCHIVE.read_text(encoding="utf-8"))
    archived_echo = np.asarray(echo_archive["observations"]["observed_echo_TOAs_s_sorted_within_each_group"], dtype=float)
    if not np.array_equal(archived_echo, echoes):
        raise RuntimeError("Phase C11 loader no longer reproduces exact C8 echo observations")
    _, true_normals, true_offsets = truth_planes()
    c11_blinds = c11["blind_observation_starts"]
    c13_by_name = {r["start_name"]:r for r in c13["results"]}
    c6_runs=direct_archive["problems"]["seed11_noise_0s"]["runs"]
    c6_by_name={r["initializer"]:r for r in c6_runs}

    seed_results=[]
    for historical in c11_blinds:
        name=historical["name"]
        seed=int(name.rsplit("_",1)[1])
        start=np.asarray(historical["initial_complete_parameters_83"],dtype=float)
        start_direct=start[:model.size]
        initial_state=C11.split_and_residuals(start,model,problem.q,echoes)
        initial_order=initial_state["echo_order"].copy()
        start_score=score_state("blind_start_before_optimization",start,model,problem,echoes,
                                true_normals,true_offsets,initial_order)
        start_score["initialization_provenance"]={
            "direct_geometry":"seeded random coordinates at TOA-derived metric scale; m1 origin, m2 +x, m3 xy positive-y gauge",
            "clock_offsets_s":"all zero",
            "source_emission_times_s":"all zero (including e0 gauge)",
            "walls":"PCA orientation and 12% point-span support-gap start from these candidate coordinates",
            "uses_ground_truth":False,
        }
        # Original C11 forward-difference run is repeated from its archived vector.
        room,raw_mics,*_=P58.make_observations()
        legacy=C11.run_joint(name+"_reproduced_C11_forward_difference",start,
            historical["start_kind"],model,problem,echoes,problem,true_normals,true_offsets,
            max_nfev=JOINT_MAX_NFEV)
        # C13's exact sorted analytic baseline is a stored, same-start comparison.
        c13_row=c13_by_name[name]
        analytic_baseline=c13_row["method_1_sorted_analytic"]

        # A: direct-path objective from the exact historical blind direct vector.
        direct_fit, direct_only_joint, direct_diag=direct_only_fit(
            start_direct,model,problem,echoes,true_normals,true_offsets,
            name+"_direct_only_fit_then_PCA_walls")

        # B: estimate timing linearly, conditional on current blind coordinates.
        timed_direct,timing_fit_meta=conditional_timing_fit(start_direct,model,problem)
        timed_state=C11.split_and_residuals(np.r_[timed_direct,start[model.size:]],model,problem.q,echoes)
        timing_stage=score_state(name+"_conditional_linear_timing_fit",np.r_[timed_direct,start[model.size:]],
            model,problem,echoes,true_normals,true_offsets,initial_order,
            optimizer={**timing_fit_meta,"optimizer":"numpy.linalg.lstsq for additive e_j+b_i timing model"})
        timed_fit,timed_joint_start,timed_direct_diag=direct_only_fit(
            timed_direct,model,problem,echoes,true_normals,true_offsets,
            name+"_conditional_timing_then_direct_only")

        # C: fit only wall planes to echoes, with blind direct coordinates/timing fixed.
        blind_endpoint=endpoint_from_direct(start_direct,model)
        points=np.vstack((blind_endpoint["mics"],blind_endpoint["sources"]))
        pca_wall=start[model.size:]
        wall_fit_begin=perf_counter()
        wall_only=P59.optimize_start(pca_wall,blind_endpoint,echoes,points,true_normals,true_offsets)
        wall_fit_runtime=perf_counter()-wall_fit_begin
        wall_start=np.r_[start_direct,np.asarray(wall_only["final_parameters"],dtype=float)]
        wall_stage=score_state(name+"_wall_only_echo_fit_fixed_blind_coordinates",wall_start,
            model,problem,echoes,true_normals,true_offsets,initial_order,
            optimizer={"method":"C9 fixed-endpoint wall-only echo fit; C9 finite-face hinge; truth only in scoring",
                       "success":wall_only["optimizer_success"],"status":wall_only["optimizer_status"],
                       "message":wall_only["optimizer_message"],"nfev":wall_only["nfev"],
                       "njev":wall_only["njev"],"runtime_s":wall_fit_runtime,
                       "wall_only_reflection_norm_s":wall_only["final_reflection_residual_norm_s"],
                       "wall_only_max_abs_reflection_residual_s":wall_only["final_reflection_max_abs_residual_s"],
                       "wall_only_convex_enclosure":wall_only["convex_enclosure"],
                       "wall_only_finite_face_validity":wall_only["finite_face_bounce_validity"],
                       "wall_only_final_parameters_18":wall_only["final_parameters"]})

        # E: run the same exact sorted analytic joint objective from four starts.
        joint_direct=safe_analytic_joint(name+"_joint_after_direct_only",direct_only_joint,
            model,problem,echoes,problem,true_normals,true_offsets)
        joint_timing=safe_analytic_joint(name+"_joint_after_conditional_timing_fit",np.r_[timed_direct,start[model.size:]],
            model,problem,echoes,problem,true_normals,true_offsets)
        joint_wall=safe_analytic_joint(name+"_joint_after_wall_only_fit",wall_start,
            model,problem,echoes,problem,true_normals,true_offsets)
        joint_baseline=safe_analytic_joint(name+"_joint_sorted_analytic_baseline",start,
            model,problem,echoes,problem,true_normals,true_offsets)

        # D: freeze the initial wall-to-observation association. Score final output
        # against the original exact sorted objective as well as its fitted one.
        joint_frozen=optimize_joint(np.r_[start_direct,pca_wall],name+"_joint_frozen_initial_echo_association",
            model,problem,echoes,true_normals,true_offsets,initial_order,fixed_order=initial_order)

        # Stagewise divergence and historical cross-check data.
        old_c6=c6_by_name.get("blind_random_seed_"+str(seed))
        if old_c6 is None:
            old_c6=c6_by_name.get("blind_random_seed_11") if seed==17 else None
        seed_results.append({
            "blind_start_name":name,"seed":seed,
            "initial_parameters_83":start.tolist(),
            "historical_C11_record":historical,
            "historical_C13_sorted_analytic_record":analytic_baseline,
            "reproduced_C11_forward_difference_record":legacy,
            "C6_direct_initializer_comparison":old_c6,
            "stages":{
                "initial_blind_state":start_score,
                "direct_only_fit_from_blind_state":direct_diag,
                "conditional_linear_timing_fit_fixed_coordinates":timing_stage,
                "conditional_timing_then_direct_only_fit":timed_direct_diag,
                "wall_only_echo_fit_fixed_direct_state":wall_stage,
                "joint_from_original_PCA_start_sorted":joint_baseline,
                "joint_from_direct_only_fit_plus_recomputed_PCA_walls":joint_direct,
                "joint_from_conditional_timing_fit_plus_PCA_walls":joint_timing,
                "joint_from_wall_only_fit":joint_wall,
                "joint_from_frozen_initial_echo_association":joint_frozen,
            },
        })

    output={
        "phase":"5C.14 blind initialization failure analysis",
        "preservation":{"C11_C12_C13_artifacts_read_only":True,
            "seed11_TOAs_and_390_echo_observations_exactly_reverified":True,
            "blind_start_vectors_loaded_verbatim_from_C11":True},
        "model":{"direct_equation":"q_ij=e_j+||s_j-m_i||/c+b_i",
            "reflection_equation":"e_j+b_i+||m_i-(s_j-2(n_k^T s_j+d_k)n_k)||/c",
            "gauges":"m1 origin; m2 positive x; m3 xy positive y; e0=0",
            "dimensions":{"microphones":5,"sources":13,"direct_observations":65,
                          "first_order_echo_observations":390,"direct_gauge_fixed_parameters":65,
                          "wall_parameters":18,"joint_parameters":83},
            "initialization_used_by_C11":"C6 random_blind_start with q/c-derived length scale; zero clocks and emissions; PCA wall start from candidate points.",
            "objective":"C11/C12 direct plus exact sorted reflection residuals; distance-unit scaling; unchanged exact objective for sorted-joint ablations.",
            "joint_optimizer":"SciPy TRF, x_scale=jac, 1e-11 tolerances, max_nfev=80; analytic Jacobian for controlled ablations.",
            "C11_reproduction":"Original C11 forward finite-difference echo Jacobian and same stored 83-start; max_nfev=80.",
            "frozen_association_ablation":"Initial PCA predicted path IDs are frozen to observed arrival ranks; final state is also scored under the original exact sorted objective.",
            "conditional_timing_ablation":"Linear least-squares estimate of additive source emission and microphone clock terms conditional on blind candidate coordinates; engineering diagnostic, not a paper-derived estimator.",
            "wall_only_ablation":"C9 wall-only echo fitting with blind direct state held fixed and PCA wall initialization; C9 finite-face penalty retained and labelled. Truth planes enter scoring only."},
        "results":seed_results,
        "runtime_warnings":RECORDED_WARNINGS,
        "interpretation_scope":"All coordinate, timing, plane, and physical checks use truth only after a run. Finite starts and local optimizers do not prove uniqueness or infeasibility.",
    }
    OUT.write_text(json.dumps(output,indent=2),encoding="utf-8")
    log=HERE/"phase5c14_run.log"
    with log.open("w",encoding="utf-8") as f:
        for warning in RECORDED_WARNINGS:
            f.write(f"WARNING {warning}\n")
        for row in seed_results:
            f.write(f"{row['blind_start_name']} initial_direct={row['stages']['initial_blind_state']['direct_residual_norm_s']:.8g} initial_echo={row['stages']['initial_blind_state']['reflection_residual_norm_s_exact_sorted']:.8g} ")
            for key in ("joint_from_original_PCA_start_sorted","joint_from_direct_only_fit_plus_recomputed_PCA_walls","joint_from_conditional_timing_fit_plus_PCA_walls","joint_from_wall_only_fit","joint_from_frozen_initial_echo_association"):
                r=row['stages'][key]
                dn=r.get("direct_residual_norm_s",r.get("final_direct_residual_norm_s",float("nan")))
                en=r.get("reflection_residual_norm_s_exact_sorted",r.get("final_reflection_residual_norm_s",float("nan")))
                prm=r.get("aligned_combined_position_rmse_m",r.get("coordinate_rmse_after_alignment_m",float("nan")))
                o=r.get("optimizer",{})
                status=o.get("status",r.get("optimizer_status",-9));nfev=o.get("nfev",r.get("nfev",0))
                if "stage_failure" in r:
                    status="FAIL:"+r["stage_failure"]
                f.write(f"{key}:D={dn:.5g},E={en:.5g},xyz={prm:.5g},status={status},n={nfev}; ")
            f.write("\n")
        f.write(f"results_json={OUT}\n")
    print(f"wrote {OUT}; blind starts={len(seed_results)}")


if __name__ == "__main__":
    main()
