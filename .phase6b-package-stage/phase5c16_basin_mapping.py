"""Phase 5C.16: oracle-centered local basin mapping (exploratory only).

All perturbed states are derived from the staged C11 reference for local
diagnostics. They are not blind initializations and use no production code.
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
OUT = HERE / "phase5c16_results.json"
LOG = HERE / "phase5c16_run.log"
C11_JSON = HERE / "phase5c11_results.json"
C8_JSON = HERE / "phase5c8_results.json"
MAX_NFEV = 80
TOL = 1e-11
ALT_MAX_CYCLES = 4
ALT_REL_STOP = 1e-10
ALT_ABS_STOP = 1e-12
ACCEPTANCE_SLACK = 1e-12
MAGNITUDES = (1e-3, 5e-2, 4e-1)
DIRECTIONS = (0, 1)
BASE_SEED = 51616
RECOVERY = {
    "direct_residual_norm_max_s": 1e-9,
    "echo_residual_norm_max_s": 1e-9,
    "combined_position_rmse_max_m": 1e-6,
    "emission_time_rmse_max_s": 1e-9,
    "clock_offset_rmse_max_s": 1e-9,
    "wall_normal_max_error_max_deg": 1e-4,
    "wall_offset_max_error_max_m": 1e-6,
    "require_convex_enclosure": True,
    "require_all_finite_face_bounces": True,
    "require_positive_paths_and_toas": True,
}
WARNINGS: list[str] = []
HISTORICAL_SWEEP_WARNINGS = [
    "RuntimeWarning: overflow encountered in exp (experiments/exploratory/phase5c6_blind_initialization.py:130)",
    "RuntimeWarning: overflow encountered in exp (experiments/exploratory/phase5c6_blind_initialization.py:130)",
]
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

C11 = load("phase5c16_c11", "phase5c11_joint_direct_reflection_fit.py")
C12 = load("phase5c16_c12", "phase5c12_joint_basin_jacobian.py")
P56, P58, P59 = C11.P56, C11.P58, C11.P59

def json_safe(value):
    if isinstance(value, dict):
        return {k: json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]
    if isinstance(value, (float, np.floating)) and not np.isfinite(value):
        return None
    if isinstance(value, np.integer):
        return int(value)
    return value

def true_planes():
    room, raw_mics, *_ = P58.make_observations()
    normals, offsets, _, _ = P59.true_planes_in_canonical_gauge(room, raw_mics)
    return normals, offsets

def score(x, label, model, problem, echoes, normals_true, offsets_true, base_order):
    """Post-run scoring. Reference truth is not passed to any optimizer callback."""
    state = C11.split_and_residuals(x, model, problem.q, echoes)
    full_j = C12.full_jacobian(x, model, problem.q, echoes, "analytic")
    full_sv = np.linalg.svd(full_j, compute_uv=False)
    rank = int(np.count_nonzero(full_sv > full_sv[0] * 1e-8)) if full_sv.size and full_sv[0] else 0
    positions = P56.aligned_metrics(state["microphones"], state["sources"], problem)
    timing = P56.timing_metrics(state["emissions"], state["clocks"], problem)
    _, rotation, ce, ct = C11.align_transform(state["microphones"], state["sources"],
        problem.microphones_truth, problem.sources_truth)
    wall_errors = C11.wall_errors_after_alignment(state["normals"], state["offsets"], rotation, ce, ct,
        normals_true, offsets_true)
    enclosure = P58.feasible_geometry(state["normals"], state["offsets"], state["points"], state["gaps"])
    faces = P58.reflection_face_validity(state["microphones"], state["sources"], state["normals"], state["offsets"])
    direct_distances = np.linalg.norm(state["sources"][None,:,:] - state["microphones"][:,None,:], axis=2)
    corrected_direct = problem.q - state["emissions"][None,:] - state["clocks"][:,None]
    positive = bool(np.all(np.isfinite(direct_distances)) and np.all(direct_distances > 0)
        and np.all(np.isfinite(corrected_direct)) and np.all(corrected_direct > 0)
        and np.all(np.isfinite(state["path_lengths"])) and np.all(state["path_lengths"] > 0)
        and np.all(np.isfinite(state["predicted_echoes"])) and np.all(state["predicted_echoes"] > 0))
    direct_norm = float(np.linalg.norm(state["direct_residual_s"]))
    echo_norm = float(np.linalg.norm(state["echo_residual_s"]))
    obj = 0.5 * float(state["residual_m"] @ state["residual_m"])
    angle = float(wall_errors["normal_angle_max_deg"])
    offset = float(wall_errors["offset_max_abs_m"])
    recovered = bool(direct_norm <= RECOVERY["direct_residual_norm_max_s"]
        and echo_norm <= RECOVERY["echo_residual_norm_max_s"]
        and positions[2] <= RECOVERY["combined_position_rmse_max_m"]
        and timing["emission_rmse_s"] <= RECOVERY["emission_time_rmse_max_s"]
        and timing["clock_rmse_s"] <= RECOVERY["clock_offset_rmse_max_s"]
        and angle <= RECOVERY["wall_normal_max_error_max_deg"]
        and offset <= RECOVERY["wall_offset_max_error_max_m"]
        and enclosure["valid_enclosure"] and faces["all_bounces_on_finite_faces"] and positive)
    return {
        "label": label, "objective_half_sse_m2": obj,
        "direct_residual_norm_s": direct_norm,
        "direct_residual_max_abs_s": float(np.max(np.abs(state["direct_residual_s"]))),
        "reflection_residual_norm_s_exact_sorted": echo_norm,
        "reflection_residual_max_abs_s_exact_sorted": float(np.max(np.abs(state["echo_residual_s"]))),
        "microphone_rmse_after_alignment_m": float(positions[0]),
        "source_rmse_after_alignment_m": float(positions[1]),
        "combined_position_rmse_after_alignment_m": float(positions[2]),
        "timing_errors": timing, "wall_errors_evaluation_only": wall_errors,
        "wall_normals_unit": state["normals"].tolist(), "wall_offsets_m": state["offsets"].tolist(),
        "wall_support_gaps_m": state["gaps"].tolist(),
        "full_jacobian_rank_rel_1e-8": rank,
        "full_jacobian_condition": float(full_sv[0] / full_sv[-1]) if full_sv[-1] else float("inf"),
        "full_jacobian_singular_values": full_sv.tolist(),
        "echo_assignment_groups_changed": int(np.count_nonzero(np.any(state["echo_order"] != base_order,axis=2))),
        "echo_assignment_paths_changed": int(np.count_nonzero(state["echo_order"] != base_order)),
        "minimum_adjacent_echo_gap_s": float(np.min(np.diff(state["predicted_echoes"],axis=2))),
        "convex_enclosure": enclosure, "finite_face_bounce_validity": faces,
        "positive_paths_and_toas": positive, "recovery_thresholds_pass": recovered,
        "parameters_83": np.asarray(x).tolist(),
    }

def fit_block(start, indices, name, model, problem, echoes, base_order, normals_true, offsets_true):
    before = score(start, name+"_before", model, problem, echoes, normals_true, offsets_true, base_order)
    index = np.asarray(list(indices), dtype=int)
    fixed = np.asarray(start, dtype=float).copy()
    def assemble(z):
        result=fixed.copy(); result[index]=z; return result
    def residual(z):
        x=assemble(z); return C11.split_and_residuals(x,model,problem.q,echoes)["residual_m"]
    def jacobian(z):
        x=assemble(z); return C12.full_jacobian(x,model,problem.q,echoes,"analytic")[:,index]
    begin=perf_counter()
    try:
        opt=least_squares(residual,fixed[index].copy(),jac=jacobian,method="trf",x_scale="jac",
            max_nfev=MAX_NFEV,ftol=TOL,xtol=TOL,gtol=TOL)
        elapsed=perf_counter()-begin
        proposal=assemble(opt.x)
        after=score(proposal,name+"_proposal",model,problem,echoes,normals_true,offsets_true,base_order)
        sv=np.linalg.svd(opt.jac,compute_uv=False)
        rank=int(np.count_nonzero(sv>sv[0]*1e-8)) if sv.size and sv[0] else 0
        allowance=ACCEPTANCE_SLACK*max(1.0,before["objective_half_sse_m2"])
        accepted=bool(np.isfinite(after["objective_half_sse_m2"]) and
            after["objective_half_sse_m2"] <= before["objective_half_sse_m2"]+allowance)
        return (proposal if accepted else fixed), {
            "accepted":accepted,"reason":None if accepted else "objective increased/nonfinite",
            "before":before,"proposal":after,"optimizer":{"success":bool(opt.success),"status":int(opt.status),
                "message":str(opt.message),"nfev":int(opt.nfev),"njev":int(opt.njev or 0),"runtime_s":elapsed,
                "optimality":float(opt.optimality),"block_jacobian_rank_rel_1e-8":rank,
                "block_jacobian_condition":float(sv[0]/sv[-1]) if sv[-1] else float("inf"),
                "block_jacobian_singular_values":sv.tolist()},
            "scaled_parameter_step_norm":float(np.linalg.norm(opt.x-fixed[index]))}
    except Exception as exc:
        return fixed,{"accepted":False,"reason":type(exc).__name__+": "+str(exc),"before":before,
            "proposal":None,"optimizer":{"success":False,"status":None,"message":str(exc),
                "nfev":None,"njev":None,"runtime_s":perf_counter()-begin}}

def optimize_case(start, name, model, problem, echoes, normals_true, offsets_true, base_order):
    blocks={
        "timing":range(model.clock_start,model.size),
        "coordinates":range(0,model.coord_count),
        "joint":range(0,model.size+18),
    }
    runs={}
    for mode,indices in blocks.items():
        _,runs[mode]=fit_block(start,indices,name+"_"+mode,model,problem,echoes,base_order,normals_true,offsets_true)
    current=np.asarray(start,dtype=float).copy(); cycles=[]
    for cycle in range(1,ALT_MAX_CYCLES+1):
        prev=score(current,f"{name}_alt_{cycle}_before",model,problem,echoes,normals_true,offsets_true,base_order)
        local_order=C11.split_and_residuals(current,model,problem.q,echoes)["echo_order"].copy()
        current,timing_update=fit_block(current,blocks["timing"],f"{name}_alt_{cycle}_timing",model,problem,echoes,local_order,normals_true,offsets_true)
        local_order=C11.split_and_residuals(current,model,problem.q,echoes)["echo_order"].copy()
        current,coordinate_update=fit_block(current,blocks["coordinates"],f"{name}_alt_{cycle}_coordinate",model,problem,echoes,local_order,normals_true,offsets_true)
        after=score(current,f"{name}_alt_{cycle}_after",model,problem,echoes,normals_true,offsets_true,base_order)
        gain=prev["objective_half_sse_m2"]-after["objective_half_sse_m2"]
        cycles.append({"cycle":cycle,"before":prev,"timing_update":timing_update,
            "coordinate_update":coordinate_update,"after":after,"objective_improvement_m2":float(gain)})
        if gain <= ALT_ABS_STOP+ALT_REL_STOP*abs(prev["objective_half_sse_m2"]):
            stop="objective improvement at/below absolute-plus-relative threshold"; break
    else:
        stop="maximum alternating cycles reached"
    return {"initial":score(start,name+"_initial",model,problem,echoes,normals_true,offsets_true,base_order),
        "runs":runs,"alternating":{"cycles":cycles,"stop_reason":stop,"max_cycles":ALT_MAX_CYCLES}}

def perturb(reference, indices, magnitude, direction_seed):
    rng=np.random.default_rng(direction_seed)
    ix=np.asarray(list(indices),dtype=int)
    delta=np.zeros_like(reference,dtype=float)
    v=rng.normal(size=ix.size)
    v/=np.sqrt(np.mean(v*v))
    delta[ix]=magnitude*v
    return reference+delta,delta

def aggregate(records):
    summary=[]
    for group in sorted(set(r["group"] for r in records)):
        for magnitude in MAGNITUDES:
            rows=[r for r in records if r["group"]==group and r["magnitude"]==magnitude]
            if not rows:
                continue
            row={"group":group,"magnitude_rms_scaled":magnitude,"directions":len(rows)}
            for method in ("timing","coordinates","joint","alternating"):
                passed=[]; init_rmse=[]; final_rmse=[]
                for r in rows:
                    optimization=r["optimization"]
                    if "stage_failure" in optimization:
                        passed.append(False)
                        init_rmse.append(r["initial_metrics"]["combined_position_rmse_after_alignment_m"])
                        continue
                    result=optimization["runs"][method] if method != "alternating" else optimization["alternating"]
                    if method=="alternating":
                        final=result["cycles"][-1]["after"]
                    else:
                        final=result["proposal"]
                    passed.append(bool(final and final["recovery_thresholds_pass"]))
                    init_rmse.append(r["initial_metrics"]["combined_position_rmse_after_alignment_m"])
                    final_rmse.append(final["combined_position_rmse_after_alignment_m"] if final else None)
                row[method+"_recoveries"]=int(sum(passed))
                row[method+"_trials"]=len(passed)
                row[method+"_initial_position_rmse_mean_m"]=float(np.mean(init_rmse))
                vals=[v for v in final_rmse if v is not None]
                row[method+"_final_position_rmse_mean_m"]=float(np.mean(vals)) if vals else None
            summary.append(row)
    return summary

def main():
    problem,model,echoes,_=C11.load_exact_inputs()
    archive=json.loads(C11_JSON.read_text(encoding="utf-8"))
    echo_archive=json.loads(C8_JSON.read_text(encoding="utf-8"))
    saved=np.asarray(echo_archive["observations"]["observed_echo_TOAs_s_sorted_within_each_group"],dtype=float)
    if not np.array_equal(saved,echoes): raise RuntimeError("Archived C8 echo observations mismatch")
    c11runs={r["name"]:r for r in archive["runs"]}
    reference_row=c11runs["generating_endpoint_staged_data_derived_walls"]
    reference=np.asarray(reference_row["final_complete_parameters_83"],dtype=float)
    normals_true,offsets_true=true_planes()
    ref_state=C11.split_and_residuals(reference,model,problem.q,echoes)
    reference_order=ref_state["echo_order"].copy()
    resume=None
    if OUT.exists():
        try:
            candidate=json.loads(OUT.read_text(encoding="utf-8"))
            if candidate.get("phase")=="5C.16 local convergence basin mapping": resume=candidate
        except (OSError,json.JSONDecodeError):
            resume=None
    if resume is not None:
        positive=resume["positive_control"]
        blind_records=resume.get("blind_results",[])
        records=resume.get("perturbation_results",[])
        completed={(r["group"],float(r["magnitude"]),int(r["direction"])) for r in records}
    else:
        positive=optimize_case(reference,"staged_reference_positive_control",model,problem,echoes,normals_true,offsets_true,reference_order)
        blind_records=[]
        records=[]
        completed=set()
    groups={
        "microphone_coordinates":range(0,3*model.m-6),
        "source_coordinates":range(3*model.m-6,model.coord_count),
        "emission_times":range(model.emission_start,model.size),
        "microphone_clock_offsets":range(model.clock_start,model.emission_start),
        "wall_parameters":range(model.size,model.size+18),
        "combined_parameters":range(0,model.size+18),
    }
    log_lines=["Phase 5C.16 local basin map; oracle-centered synthetic diagnostic only",
        f"magnitude coordinates: scaled optimizer variables; levels={MAGNITUDES}; two seeded directions each",
        "methods: timing-only, coordinate-only, joint, alternating timing/coordinate (4-cycle cap)"]
    with LOG.open("a" if resume is not None else "w",encoding="utf-8") as log:
        if resume is None:
            log.write("\n".join(log_lines)+"\n"); log.flush()
        for group_index,(group,indices) in enumerate(groups.items()):
            for mag_index,magnitude in enumerate(MAGNITUDES):
                for direction in DIRECTIONS:
                    seed=BASE_SEED+group_index*10000+mag_index*100+direction
                    if (group,float(magnitude),int(direction)) in completed:
                        continue
                    start,delta=perturb(reference,indices,magnitude,seed)
                    init=score(start,f"{group}_mag{magnitude:g}_dir{direction}_initial",model,problem,echoes,normals_true,offsets_true,reference_order)
                    try:
                        fits=optimize_case(start,f"{group}_mag{magnitude:g}_dir{direction}",model,problem,echoes,normals_true,offsets_true,reference_order)
                    except Exception as exc:
                        fits={"stage_failure":type(exc).__name__+": "+str(exc)}
                    record={"group":group,"magnitude":magnitude,"direction":direction,"seed":seed,
                        "perturbed_parameter_indices":[int(min(indices)),int(max(indices))+1],
                        "perturbation_vector_83":delta.tolist(),"initial_metrics":init,"optimization":fits}
                    records.append(record)
                    line=f"{group} mag={magnitude:g} dir={direction} seed={seed} init_obj={init['objective_half_sse_m2']:.7g} "
                    if "stage_failure" in fits:
                        line+="FAIL "+fits["stage_failure"]
                    else:
                        endings=[]
                        for method in ("timing","coordinates","joint"):
                            v=fits["runs"][method]["proposal"]
                            endings.append(f"{method}:rec={v['recovery_thresholds_pass']} obj={v['objective_half_sse_m2']:.4g} xyz={v['combined_position_rmse_after_alignment_m']:.3g}")
                        alt=fits["alternating"]["cycles"][-1]["after"]
                        endings.append(f"alt:rec={alt['recovery_thresholds_pass']} obj={alt['objective_half_sse_m2']:.4g} xyz={alt['combined_position_rmse_after_alignment_m']:.3g} cycles={len(fits['alternating']['cycles'])}")
                        line+="; ".join(endings)
                    log.write(line+"\n");log.flush()
                    # Incremental checkpoint enables review/recovery during this large sweep.
                    checkpoint={"phase":"5C.16 local convergence basin mapping",
                        "recovery_thresholds":RECOVERY,"positive_control":positive,"blind_results":blind_records,
                        "perturbation_results":records,"summary":aggregate(records),"runtime_warnings":WARNINGS}
                    OUT.write_text(json.dumps(json_safe(checkpoint),indent=2,allow_nan=False),encoding="utf-8")
        log.write("\nPositive control:\n")
        for method in ("timing","coordinates","joint"):
            opt=positive["runs"][method];v=opt["proposal"]
            log.write(f"{method}: rec={v['recovery_thresholds_pass']} direct={v['direct_residual_norm_s']:.4g} echo={v['reflection_residual_norm_s_exact_sorted']:.4g} xyz={v['combined_position_rmse_after_alignment_m']:.4g} status={opt['optimizer']['status']} nfev={opt['optimizer']['nfev']}\n")
        for warning in WARNINGS: log.write("WARNING "+warning+"\n")
    final={"phase":"5C.16 local convergence basin mapping","provenance":{
        "exact_C11_staged_reference_used_as_perturbation_center":True,"all_perturbed_runs_are_oracle_derived_diagnostics":True,
        "C11_C15_artifacts_read_only":True,"C8_echo_TOAs_exactly_reverified":True,"truth_only_used_for_post_run_scoring":True},
        "model":{"M":model.m,"N":model.n,"direct_parameters":model.size,"coordinate_parameters":model.coord_count,
            "clock_parameters":model.m,"emission_parameters":model.n-1,"wall_parameters":18,"joint_parameters":model.size+18,
            "objective":"Exact sorted C11/C12 direct and first-order reflection residuals, distance-unit scaling",
            "analytic_jacobians":"C12 existing direct plus piecewise analytic echo Jacobian",
            "perturbation_coordinates":"Existing scaled optimizer vector; wall azimuth/elevation variables in radians and log support-gap coordinates; combined group perturbs all 83 optimizer entries with equal RMS in their native optimizer coordinates"},
        "optimizer":{"method":"SciPy TRF","x_scale":"jac","max_nfev_per_solve":MAX_NFEV,"ftol_xtol_gtol":TOL,
            "alternating_order":"timing then coordinates; walls held fixed in alternating method",
            "alternating_max_cycles":ALT_MAX_CYCLES,"alternating_stopping":"cycle objective improvement <= 1e-12 + 1e-10*abs(previous objective)",
            "proposal_acceptance":"finite full objective no greater than previous objective + 1e-12*max(1,previous objective)"},
        "recovery_thresholds":RECOVERY,"positive_control":positive,"blind_results":blind_records,
        "perturbation_results":records,"summary_by_group_magnitude":aggregate(records),
        "runtime_warnings_on_replay":WARNINGS,"runtime_warnings_observed_during_original_sweep":HISTORICAL_SWEEP_WARNINGS,
        "interpretation_scope":"Finite deterministic local sweep; no blind recovery, global uniqueness, or infeasibility claim."}
    OUT.write_text(json.dumps(json_safe(final),indent=2,allow_nan=False),encoding="utf-8")
    # Normalize the log after a run or resumed run so it contains no duplicated
    # checkpoint lines and no warnings from an interrupted earlier process.
    with LOG.open("w",encoding="utf-8") as log:
        log.write("Phase 5C.16 local basin map; oracle-centered synthetic diagnostic only\n")
        log.write(f"magnitudes={MAGNITUDES}; directions={len(DIRECTIONS)}; cases={len(records)}\n")
        log.write("method budgets: timing-only, coordinate-only, joint, alternating (4-cycle cap), max_nfev=80\n")
        for record in records:
            fits=record["optimization"]
            line=f"{record['group']} mag={record['magnitude']:g} dir={record['direction']} seed={record['seed']} init_obj={record['initial_metrics']['objective_half_sse_m2']:.7g} "
            if "stage_failure" in fits:
                line+="FAIL "+fits["stage_failure"]
            else:
                endings=[]
                for method in ("timing","coordinates","joint"):
                    result=fits["runs"][method]; value=result["proposal"]; opt=result["optimizer"]
                    endings.append(f"{method}:recovery={value['recovery_thresholds_pass']} obj={value['objective_half_sse_m2']:.5g} xyz={value['combined_position_rmse_after_alignment_m']:.4g} status={opt['status']} nfev={opt['nfev']}")
                alt=fits["alternating"]; value=alt["cycles"][-1]["after"]
                endings.append(f"alternating:recovery={value['recovery_thresholds_pass']} obj={value['objective_half_sse_m2']:.5g} xyz={value['combined_position_rmse_after_alignment_m']:.4g} cycles={len(alt['cycles'])}")
                line+="; ".join(endings)
            log.write(line+"\n")
        log.write("Positive control:\n")
        for method in ("timing","coordinates","joint"):
            opt=positive["runs"][method]; value=opt["proposal"]
            log.write(f"{method}: recovery={value['recovery_thresholds_pass']} direct={value['direct_residual_norm_s']:.4g} echo={value['reflection_residual_norm_s_exact_sorted']:.4g} xyz={value['combined_position_rmse_after_alignment_m']:.4g} status={opt['optimizer']['status']} nfev={opt['optimizer']['nfev']}\n")
        for warning in WARNINGS:
            log.write("WARNING "+warning+"\n")
        for warning in HISTORICAL_SWEEP_WARNINGS:
            log.write("HISTORICAL WARNING "+warning+"\n")
        log.write(f"results_json={OUT}\n")
    print(f"wrote {OUT}; perturbation runs={len(records)}")

if __name__=="__main__":main()
