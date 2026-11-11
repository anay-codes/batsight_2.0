"""C10 follow-up: longer runs, block sensitivities, and penalty continuation."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
from time import perf_counter

import numpy as np
from scipy.optimize import least_squares

HERE=Path(__file__).resolve().parent
P10_SPEC=importlib.util.spec_from_file_location("p10_follow",HERE/"phase5c10_competing_endpoint_reflection_fit.py")
P10=importlib.util.module_from_spec(P10_SPEC);sys.modules[P10_SPEC.name]=P10;P10_SPEC.loader.exec_module(P10)
OUT=HERE/"phase5c10_followup_results.json"


def block_fit(endpoint,target,x0,free,*,label,max_nfev=300):
    points=np.vstack((endpoint["mics"],endpoint["sources"]))
    x0=np.asarray(x0,float); free=np.asarray(free,int); fixed=np.setdiff1d(np.arange(18),free)
    def f(z):
        x=x0.copy();x[free]=z
        return P10.objective_residual(x,endpoint,target,points)
    begin=perf_counter()
    opt=least_squares(f,x0[free],method="trf",x_scale="jac",max_nfev=max_nfev,ftol=P10.TOL,xtol=P10.TOL,gtol=P10.TOL)
    elapsed=perf_counter()-begin
    x=x0.copy();x[free]=opt.x
    out=P10.diagnostics(x,endpoint,target,points,opt,name=label,start=x0,runtime=elapsed)
    out.update({"free_parameter_block":label,"free_parameter_count":len(free),"fixed_indices":fixed.tolist()})
    return out


def main():
    old=json.loads((HERE/"phase5c10_results.json").read_text(encoding="utf-8"))
    endpoints,target,_=P10.fixed_endpoint_observations()
    endpoint=endpoints["competing"]
    starts=old["competing_data_derived_multistart"]
    valid=[r for r in starts if r["all_physical_checks_pass"]]
    best_valid=min(valid,key=lambda r:r["reflection_residual_norm_s"])
    best_any=min(starts,key=lambda r:r["reflection_residual_norm_s"])
    continuation=old["competing_solver_variants"]["face_penalty_continuation"][-1]
    seed_states={
      "best_multistart_physically_complete":np.asarray(best_valid["parameters"]),
      "best_multistart_any":np.asarray(best_any["parameters"]),
      "penalty_continuation_weight10":np.asarray(continuation["parameters"]),
    }
    longer={}
    for name,x in seed_states.items():
        longer[name]=P10.fit(endpoint,target,x,max_nfev=1200,face_weight=P10.FACE_WEIGHT,name=f"long_{name}")

    # Continue increasing the face-penalty weight from the existing w=10 state.
    x=np.asarray(continuation["parameters"]); penalty=[]
    for w in (100.0,1000.0):
        row=P10.fit(endpoint,target,x,max_nfev=500,face_weight=w,name=f"continued_face_weight_{w:g}")
        penalty.append(row);x=np.asarray(row["parameters"])

    base=np.asarray(best_valid["parameters"])
    offsets_only=block_fit(endpoint,target,base,np.arange(12,18),label="freeze_orientations_optimize_offsets",max_nfev=300)
    orientations_only=block_fit(endpoint,target,base,np.arange(0,12),label="optimize_orientations_freeze_support_gaps",max_nfev=300)
    output={
      "phase":"5C.10 follow-up diagnostics; competing endpoint only",
      "preservation":{"C8_C9_C10_records_read_only":True,"exact_endpoint_and_observation_archive_reused":True,"true_wall_data_used":False},
      "selected_start_names":{"best_valid":best_valid["name"],"best_any":best_any["name"]},
      "longer_budget_runs":longer,
      "face_penalty_continuation_10_to_100_to_1000":penalty,
      "parameter_block_diagnostics":{"offsets_only":offsets_only,"orientations_only":orientations_only},
      "conclusion_scope":"Diagnostic optimizer trials; nonconvergence and invalid face counts do not prove incompatibility.",
    }
    OUT.write_text(json.dumps(output,indent=2),encoding="utf-8")
    for k,v in longer.items(): print("long",k,v["reflection_residual_norm_s"],v["reflection_max_abs_residual_s"],v["all_physical_checks_pass"],v["finite_face_bounce_validity"]["valid_first_order_bounce_count"],v["optimizer_status"],v["nfev"],v["runtime_s"])
    for v in penalty: print("penalty",v["face_penalty_weight"],v["reflection_residual_norm_s"],v["all_physical_checks_pass"],v["finite_face_bounce_validity"]["valid_first_order_bounce_count"],v["optimizer_success"],v["nfev"],v["runtime_s"])
    for v in (offsets_only,orientations_only): print("block",v["name"],v["reflection_residual_norm_s"],v["all_physical_checks_pass"],v["finite_face_bounce_validity"]["valid_first_order_bounce_count"],v["optimizer_success"],v["nfev"],v["runtime_s"])
    print("results_json",OUT)


if __name__=="__main__":main()
