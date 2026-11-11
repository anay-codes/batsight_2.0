"""Phase 5C.17: exploratory direct-path initializer comparison."""
from __future__ import annotations
import importlib.util, json, sys, warnings
from pathlib import Path
from time import perf_counter
import numpy as np
HERE=Path(__file__).resolve().parent
OUT=HERE/"phase5c17_results.json"; LOG=HERE/"phase5c17_run.log"
C=343.0; BUDGET=500; BASE_SEED=51700; WARNINGS=[]
_original=warnings.showwarning
def _warning(message,category,filename,lineno,file=None,line=None):
    WARNINGS.append(f"{category.__name__}: {message} ({filename}:{lineno})")
    _original(message,category,filename,lineno,file=file,line=line)
warnings.showwarning=_warning; warnings.simplefilter("always",RuntimeWarning)
def load(name,file):
    spec=importlib.util.spec_from_file_location(name,HERE/file)
    if spec is None or spec.loader is None: raise RuntimeError(file)
    mod=importlib.util.module_from_spec(spec);sys.modules[name]=mod;spec.loader.exec_module(mod);return mod
C6=load("phase5c17_c6","phase5c6_blind_initialization.py"); C4=C6.C4
def safe(v):
    if isinstance(v,dict): return {k:safe(x) for k,x in v.items()}
    if isinstance(v,(list,tuple)): return [safe(x) for x in v]
    if isinstance(v,np.ndarray): return safe(v.tolist())
    if isinstance(v,(float,np.floating)) and not np.isfinite(v): return None
    if isinstance(v,(np.integer,np.bool_)): return int(v) if isinstance(v,np.integer) else bool(v)
    return v
def make_problem(cfg):
    rng=np.random.default_rng(cfg["seed"]);m,n=cfg["M"],cfg["N"]
    dims=np.array((8.,7.,5.));margin=np.full(3,.45);kind=cfg["distribution"]
    if kind=="uniform":
        m0=rng.uniform(margin,dims-margin,(m,3));s0=rng.uniform(margin,dims-margin,(n,3))
    elif kind=="clustered":
        center=dims/2;sig=cfg.get("cluster_sigma_m",.3)
        m0=np.clip(center+rng.normal(0,sig,(m,3)),margin,dims-margin)
        s0=np.clip(center+rng.normal(0,sig,(n,3)),margin,dims-margin)
    elif kind=="planar":
        mxy=rng.uniform((.5,.5),dims[:2]-.5,(m,2));sxy=rng.uniform((.5,.5),dims[:2]-.5,(n,2))
        m0=np.column_stack((mxy,np.full(m,dims[2]/2)));s0=np.column_stack((sxy,np.full(n,dims[2]/2)))
    else: raise ValueError(kind)
    e=np.r_[0.,rng.normal(0,cfg["emission_std_s"],n-1)];b=rng.normal(0,cfg["clock_std_s"],m)
    q=e[None,:]+np.linalg.norm(s0[None,:,:]-m0[:,None,:],axis=2)/C+b[:,None]
    if cfg["noise_std_s"]: q+=np.random.default_rng(cfg["noise_seed"]).normal(0,cfg["noise_std_s"],q.shape)
    mic,src=C6.canonicalize(m0,s0)
    problem=C6.Problem(cfg["name"],q,C,mic,src,e,b,cfg["noise_std_s"])
    return problem,{"seed":cfg["seed"],"distribution":kind,"noise_std_s":cfg["noise_std_s"],
        "noise_seed":cfg["noise_seed"],"clock_std_s":cfg["clock_std_s"],"emission_std_s":cfg["emission_std_s"],
        "room_dimensions_m":dims.tolist(),"truth_used_to_construct_initializer":False}
def score(state,model,problem,label,p=None):
    mic,src,e,b=state;dist=np.linalg.norm(src[None,:,:]-mic[:,None,:],axis=2)
    residual=problem.q-e[None,:]-dist/problem.c-b[:,None]
    _,jac=model.residual_jac(model.pack(mic,src,e,b));sv=np.linalg.svd(jac,compute_uv=False)
    mm,sm,pm=C6.aligned_metrics(mic,src,problem);tm=C6.timing_metrics(e,b,problem);corr=problem.q-e[None,:]-b[:,None]
    out={"label":label,"direct_residual_norm_s":float(np.linalg.norm(residual)),
        "direct_residual_max_abs_s":float(np.max(np.abs(residual))),"microphone_rmse_after_alignment_m":mm,
        "source_rmse_after_alignment_m":sm,"combined_position_rmse_after_alignment_m":pm,"timing_errors":tm,
        "jacobian_rank_rel_1e-8":int(np.sum(sv>sv[0]*1e-8)),
        "jacobian_condition":float(sv[0]/sv[-1]) if sv[-1] else float("inf"),
        "jacobian_singular_values":sv.tolist(),"corrected_toas_positive":bool(np.all(np.isfinite(corr)) and np.all(corr>0)),
        "ranges_finite_positive":bool(np.all(np.isfinite(dist)) and np.all(dist>0)),
        "coordinates_canonical_m":np.vstack((mic,src)).tolist(),"truth_used_to_construct_start":False}
    if p is not None:
        x=C4.dd_squared(problem.q);a,g=C4.timing_matrices(problem.q,p);x=x+a+g
        u,s,v=np.linalg.svd(x,full_matrices=False);x3=(u[:,:3]*s[:3])@v[:3]
        out["corrected_double_difference"]={"shape":list(x.shape),"singular_values":s.tolist(),
            "rank3_discarded_norm":float(np.linalg.norm(x-x3)),
            "rank3_relative_discarded_norm":float(np.linalg.norm(x-x3)/max(np.linalg.norm(x),1e-30))}
    return out
def thresholds(problem):
    sig=problem.noise_std_s
    return (1e-8 if sig==0 else 3*sig*np.sqrt(problem.q.size),
        1e-3 if sig==0 else max(1e-3,5*C*sig),1e-7 if sig==0 else max(1e-7,5*sig))
def fit_start(problem,model,name,state,metadata):
    initial=score(state,model,problem,name);started=perf_counter()
    try: fit=model.optimize(model.pack(*state),max_nfev=BUDGET)
    except Exception as exc: return {"method":name,"initial":initial,"metadata":metadata,"stage_failure":type(exc).__name__+": "+str(exc)}
    elapsed=perf_counter()-started;final_state=(fit["microphones"],fit["sources"],fit["emissions"],fit["offsets"])
    final=score(final_state,model,problem,name+"_final");rlim,plim,tlim=thresholds(problem)
    final["screen_thresholds"]={"residual_norm_s":rlim,"position_rmse_m":plim,"timing_rmse_s":tlim,
        "status":"BatSight diagnostic thresholds, not paper criteria"}
    final["measurement_fit_pass"]=final["direct_residual_norm_s"]<=rlim
    final["geometry_timing_pass"]=(final["combined_position_rmse_after_alignment_m"]<=plim
        and final["timing_errors"]["emission_rmse_s"]<=tlim and final["timing_errors"]["clock_rmse_s"]<=tlim)
    final["physical_valid"]=final["corrected_toas_positive"] and final["ranges_finite_positive"]
    opt=fit["optimizer"]
    return {"method":name,"initial":initial,"final":final,"metadata":metadata,
        "optimizer":{"success":bool(opt.success),"status":int(opt.status),"message":str(opt.message),
            "nfev":int(opt.nfev),"njev":int(opt.njev or 0),"runtime_s":elapsed,
            "jacobian_rank":int(fit["rank"]),"jacobian_condition":float(fit["condition"]),
            "singular_values":fit["singular_values"].tolist()},
        "measurement_fit_pass":final["measurement_fit_pass"],"geometric_recovery_pass":final["geometry_timing_pass"],
        "recovered":bool(final["measurement_fit_pass"] and final["geometry_timing_pass"] and final["physical_valid"]),
        "final_parameters_scaled":fit["x"].tolist()}
def crocco_start(problem,model,p,label,seed):
    state,detail=C6.algebraic_metric_start(problem.q,problem.c,p,label,seed=seed)
    if state is None:return None,{"rejected":detail,"timing_parameters_s":np.asarray(p).tolist()}
    return state,{"crocco_details":detail,"timing_parameters_s":np.asarray(p).tolist(),
        "pre_refinement":score(state,model,problem,label,p)}
def pairwise_distinct(rows,limit):
    eligible=[x for x in rows if x.get("final") and x["final"]["direct_residual_norm_s"]<=limit];pairs=[]
    for i in range(len(eligible)):
        for j in range(i+1,len(eligible)):
            a=np.asarray(eligible[i]["final"]["coordinates_canonical_m"]);b=np.asarray(eligible[j]["final"]["coordinates_canonical_m"])
            ac=a.mean(0);bc=b.mean(0);u,_,vt=np.linalg.svd((a-ac).T@(b-bc));rot=u@vt
            err=float(np.sqrt(np.mean(np.sum(((a-ac)@rot+bc-b)**2,axis=1))))
            if err>.1:pairs.append({"method_a":eligible[i]["method"],"method_b":eligible[j]["method"],
                "residual_a_s":eligible[i]["final"]["direct_residual_norm_s"],
                "residual_b_s":eligible[j]["final"]["direct_residual_norm_s"],"pairwise_aligned_geometry_rmse_m":err})
    return pairs
CONFIGS=[
 {"name":"minimum_well_spread","M":5,"N":13,"seed":51701,"distribution":"uniform","clock_std_s":.0005,"emission_std_s":.0005,"noise_std_s":0.,"noise_seed":87001},
 {"name":"below_reference_count","M":4,"N":10,"seed":51702,"distribution":"uniform","clock_std_s":.0005,"emission_std_s":.0005,"noise_std_s":0.,"noise_seed":87002},
 {"name":"larger_high_timing","M":8,"N":20,"seed":51703,"distribution":"uniform","clock_std_s":.003,"emission_std_s":.004,"noise_std_s":0.,"noise_seed":87003},
 {"name":"planar_minimum_count","M":5,"N":13,"seed":51704,"distribution":"planar","clock_std_s":.001,"emission_std_s":.001,"noise_std_s":0.,"noise_seed":87004},
 {"name":"clustered_noisy_minimum","M":5,"N":13,"seed":51705,"distribution":"clustered","cluster_sigma_m":.30,"clock_std_s":.002,"emission_std_s":.002,"noise_std_s":20e-6,"noise_seed":87005},
 {"name":"larger_noisy_spread","M":8,"N":20,"seed":51706,"distribution":"uniform","clock_std_s":.0015,"emission_std_s":.0015,"noise_std_s":50e-6,"noise_seed":87006},
]
def run_case(cfg):
    problem,provenance=make_problem(cfg);length,ts=C6.characteristic_scales(problem.q,problem.c)
    model=C6.DirectFit(problem.q,problem.c,length,ts);rows=[];m,n=model.m,model.n
    p0=np.zeros(m+n-1);state,meta=crocco_start(problem,model,p0,"zero_timing_Crocco",BASE_SEED+cfg["seed"]%1000)
    if state is None:rows.append({"method":"A_zero_timing_Crocco","family":"A_zero_timing_Crocco","stage_failure":meta["rejected"],"metadata":meta})
    else:
        row=fit_start(problem,model,"A_zero_timing_Crocco",state,meta);row["family"]="A_zero_timing_Crocco";row["initial"]=meta["pre_refinement"]
        _,plim,tlim=thresholds(problem);row["initial"]["geometry_timing_pass"]=(row["initial"]["combined_position_rmse_after_alignment_m"]<=plim and row["initial"]["timing_errors"]["emission_rmse_s"]<=tlim and row["initial"]["timing_errors"]["clock_rmse_s"]<=tlim);rows.append(row)
    timer=perf_counter()
    try:
        p,tmeta=C6.gaubitch_timing_start(problem.q,ts,outer_iterations=100);truntime=perf_counter()-timer
        state,meta=crocco_start(problem,model,p,"Gaubitch100_Crocco",BASE_SEED+1000+cfg["seed"]%1000)
        meta={"timing_stage":tmeta,"timing_stage_runtime_s":truntime,**meta}
        if state is None:rows.append({"method":"B_Gaubitch100_Crocco","family":"B_Gaubitch100_Crocco","stage_failure":meta.get("rejected","Crocco rejected"),"metadata":meta})
        else:
            row=fit_start(problem,model,"B_Gaubitch100_Crocco",state,meta);row["family"]="B_Gaubitch100_Crocco";row["initial"]=meta["pre_refinement"]
            _,plim,tlim=thresholds(problem);row["initial"]["geometry_timing_pass"]=(row["initial"]["combined_position_rmse_after_alignment_m"]<=plim and row["initial"]["timing_errors"]["emission_rmse_s"]<=tlim and row["initial"]["timing_errors"]["clock_rmse_s"]<=tlim);rows.append(row)
    except Exception as exc:
        rows.append({"method":"B_Gaubitch100_Crocco","family":"B_Gaubitch100_Crocco","stage_failure":type(exc).__name__+": "+str(exc),"metadata":{"timing_stage_runtime_s":perf_counter()-timer}})
    starts=C6.structured_starts(problem,model,scales=(.5,1.,2.))
    for seed in (17,29):starts.append((f"random_blind_seed_{seed}",model.pack(*C6.random_blind_start(problem,seed,length))))
    for name,vec in starts:
        try:
            st=model.unpack(vec);md={"initializer_kind":name,"inputs":["q","c","M,N","q-derived length scale"],"uses_truth_to_construct_start":False}
            row=fit_start(problem,model,"C_"+name,st,md)
        except Exception as exc:row={"method":"C_"+name,"family":"C_C6_direct_multistart","stage_failure":type(exc).__name__+": "+str(exc)}
        row["family"]="C_C6_direct_multistart";row.setdefault("method","C_"+name);rows.append(row)
    rlim=residual_limit=thresholds(problem)[0];families={}
    for row in rows:families.setdefault(row["family"],[]).append(row)
    summary={}
    for family,items in families.items():
        valid=[x for x in items if x.get("final")]
        summary[family]={"trials":len(items),"rejected":sum("stage_failure" in x for x in items),
            "initial_geometry_passes":sum(bool(x.get("initial",{}).get("geometry_timing_pass",False)) for x in items),
            "final_geometric_recoveries":sum(bool(x.get("recovered",False)) for x in items),
            "measurement_fit_passes":sum(bool(x.get("measurement_fit_pass",False)) for x in items),
            "final_position_rmse_m":[x["final"]["combined_position_rmse_after_alignment_m"] for x in valid],
            "distinct_low_residual_geometries":pairwise_distinct(items,rlim)}
    return {"configuration":cfg,"generator_metadata":provenance,"dimensions":{"M":m,"N":n,"observations":int(problem.q.size),
        "gauge_fixed_unknowns":model.size,"residual_dof":int(problem.q.size-model.size)},
        "q_derived_length_scale_m":length,"q_derived_time_scale_s":ts,"direct_fit_max_nfev":BUDGET,
        "methods":rows,"summary":summary,"truth_used_only_for_scoring":True}
def main():
    scenarios=[]
    with LOG.open("w",encoding="utf-8") as log:
        log.write("Phase 5C.17 direct-path initializer comparison; deterministic synthetic blind starts only\n")
        log.write(f"DirectFit max_nfev={BUDGET}; input observations are complete except explicit missing-data rejection\n")
        for cfg in CONFIGS:
            t=perf_counter();case=run_case(cfg);case["runtime_s"]=perf_counter()-t;scenarios.append(case)
            items=[f"{fam}: recovered={v['final_geometric_recoveries']}/{v['trials']}, measurement-fit={v['measurement_fit_passes']}/{v['trials']}" for fam,v in case["summary"].items()]
            log.write(f"{cfg['name']} M={cfg['M']} N={cfg['N']} noise={cfg['noise_std_s']:g}s; "+"; ".join(items)+"\n");log.flush()
        base,_=make_problem(CONFIGS[0]);mask=np.random.default_rng(51799).random(base.q.shape)<.10
        missing={"name":"minimum_well_spread_with_10pct_missing_TOAs","missing_count":int(mask.sum()),"mask_seed":51799,
            "handling":"reject; no imputation","supported":{"A_zero_timing_Crocco":False,"B_Gaubitch_Crocco":False,"C_C6_DirectFit":False},
            "reason":"archived methods require a dense finite TOA matrix"}
        log.write("missing data: "+json.dumps(missing,sort_keys=True)+"\n")
        for warning in WARNINGS:log.write("WARNING "+warning+"\n")
    result={"phase":"5C.17 direct-path initialization recovery","status":"exploratory; no production initializer accepted",
        "measurement_model":"q_ij=e_j+||s_j-m_i||/c+b_i+noise",
        "equation_boundary":{"literal_2016_Eq13":"not used or silently corrected; the archived audit flags the printed missing baseline term",
            "methods_A_B":"reference-derived corrected four-term double difference from C4 and references [7]/[28], not literal 2016 reproduction",
            "method_C":"existing C6 direct Euclidean TOA objective and blind starts; separate exploratory alternative"},
        "math":{"double_difference":"G_ij=d_ij^2-d_i1^2-d_1j^2+d_11^2=-2(r_i-r_1)^T(s_j-s_1)",
            "timing":"T+A(p)+Gamma(p), p=[b_1..b_M,e_2..e_N], e_1=0, Gamma_ij=2(b_i-b_1)e_j",
            "rank":"truncated SVD rank-3 projection of complete corrected (M-1)x(N-1) matrix",
            "coordinate_recovery":"general Crocco quadratic Euclidean constraints on both determinant branches; not the co-location special case",
            "gauges":"coordinate translation/orthogonal ambiguity represented by mic-anchor canonicalization; timing origin e_1=0; no synchronized-clock assumption",
            "identifiability":"[7] gives necessary M>=5,N>=13 counts under its model, not sufficiency for degenerate geometry"},
        "settings":{"direct_optimizer":"existing C6 DirectFit; TRF, analytic Jacobian, x_scale=jac, max_nfev=500",
            "noiseless_screen":{"residual_norm_s":1e-8,"position_RMSE_m":1e-3,"timing_RMSE_s":1e-7},
            "noisy_screen":{"residual_norm_s":"3*sigma*sqrt(MN)","position_RMSE_m":"max(1e-3,5*c*sigma)","timing_RMSE_s":"max(1e-7,5*sigma)"},
            "thresholds":"BatSight diagnostic conventions; not paper accuracy thresholds"},
        "scenarios":scenarios,"missing_data_case":missing,"runtime_warnings":WARNINGS,
        "interpretation":"Finite deterministic synthetic trials only; low TOA residual is not geometric recovery; no global uniqueness or infeasibility conclusion."}
    OUT.write_text(json.dumps(safe(result),indent=2,allow_nan=False),encoding="utf-8")
    print(f"wrote {OUT}; scenarios={len(scenarios)}")
if __name__=="__main__":main()


