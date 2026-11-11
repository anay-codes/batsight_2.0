"""Phase 5C.18 controlled identifiability study; exploratory only."""
from __future__ import annotations
import importlib.util, json, sys, warnings
from pathlib import Path
from time import perf_counter
import numpy as np
HERE=Path(__file__).resolve().parent
OUT=HERE/'phase5c18_results.json'; LOG=HERE/'phase5c18_run.log'
P17=importlib.util.spec_from_file_location('phase5c18_c17',HERE/'phase5c17_direct_initialization.py')
C17=importlib.util.module_from_spec(P17);sys.modules[P17.name]=C17;P17.loader.exec_module(C17)
C6=C17.C6; C4=C17.C4; C=343.0; MAX_NFEV=500; STARTS=8
RUNTIME_WARNINGS=[]
_old_showwarning=warnings.showwarning
def _capture_warning(message,category,filename,lineno,file=None,line=None):
    RUNTIME_WARNINGS.append(f'{category.__name__}: {message} ({Path(filename).name}:{lineno})')
    _old_showwarning(message,category,filename,lineno,file=file,line=line)
warnings.showwarning=_capture_warning
warnings.simplefilter('always',RuntimeWarning)

def safe(x):
    if isinstance(x,dict): return {k:safe(v) for k,v in x.items()}
    if isinstance(x,(list,tuple)): return [safe(v) for v in x]
    if isinstance(x,np.ndarray): return safe(x.tolist())
    if isinstance(x,(np.integer,)): return int(x)
    if isinstance(x,(np.bool_,)): return bool(x)
    if isinstance(x,(float,np.floating)) and not np.isfinite(x): return None
    return x

# Factorial one-at-a-time matrix: baseline plus levels changing exactly one factor.
BASE={'name':'base_M5_N13_uniform_mid_timing_clean','M':5,'N':13,'seed':51800,'distribution':'uniform','clock_std_s':.0005,'emission_std_s':.0005,'noise_std_s':0.,'noise_seed':91800}
def cfg(name,**changes):
    x=dict(BASE);x.update(changes);x['name']=name
    # all OAT cells share deterministic generator/noise seeds
    x['seed']=51800
    x['noise_seed']=91800
    return x
CONFIGS=[
 BASE,
 cfg('microphones_below_M4',M=4),cfg('microphones_above_M7',M=7),
 cfg('sources_below_N10',N=10),cfg('sources_above_N17',N=17),
 cfg('clustered_3d_sigma_0p30m',distribution='clustered',cluster_sigma_m=.30),
 cfg('planar_3d_layout',distribution='planar'),
 cfg('timing_zero',clock_std_s=0.,emission_std_s=0.),
 cfg('timing_low_0p10ms',clock_std_s=.0001,emission_std_s=.0001),
 cfg('timing_high_4ms',clock_std_s=.004,emission_std_s=.004),
 cfg('noise_20us',noise_std_s=20e-6),cfg('noise_100us',noise_std_s=100e-6),
]

def make_oat_problem(config):
    """Generate matched OAT cells from fixed, independent random streams."""
    dims=np.array((8.,7.,5.));margin=np.full(3,.45);m,n=config['M'],config['N']
    kind=config['distribution']
    rm=np.random.default_rng(51800);rs=np.random.default_rng(51801)
    re=np.random.default_rng(51802);rb=np.random.default_rng(51803)
    if kind=='uniform':
        m0=rm.uniform(margin,dims-margin,(m,3));s0=rs.uniform(margin,dims-margin,(n,3))
    elif kind=='clustered':
        sigma=config.get('cluster_sigma_m',.30);center=dims/2
        m0=np.clip(center+rm.normal(0,sigma,(m,3)),margin,dims-margin)
        s0=np.clip(center+rs.normal(0,sigma,(n,3)),margin,dims-margin)
    elif kind=='planar':
        mxy=rm.uniform((.5,.5),dims[:2]-.5,(m,2));sxy=rs.uniform((.5,.5),dims[:2]-.5,(n,2))
        m0=np.column_stack((mxy,np.full(m,dims[2]/2)));s0=np.column_stack((sxy,np.full(n,dims[2]/2)))
    else: raise ValueError(kind)
    e=np.r_[0.,re.normal(0,config['emission_std_s'],n-1)]
    b=rb.normal(0,config['clock_std_s'],m)
    q=e[None,:]+np.linalg.norm(s0[None,:,:]-m0[:,None,:],axis=2)/C+b[:,None]
    if config['noise_std_s']:
        q+=np.random.default_rng(91800).normal(0,config['noise_std_s'],q.shape)
    mic,src=C6.canonicalize(m0,s0)
    truth=C6.Problem(config['name'],q,C,mic,src,e,b,config['noise_std_s'])
    provenance={'independent_stream_seeds':{'microphones':51800,'sources':51801,'emissions':51802,'clocks':51803,'noise':91800},
        'distribution':kind,'noise_std_s':config['noise_std_s'],'room_dimensions_generator_only_m':dims.tolist(),
        'truth_used_to_construct_initializer':False}
    return truth,provenance

def jacobian_diagnostics(problem,model):
    x=model.pack(problem.microphones_truth,problem.sources_truth,problem.emissions_truth,problem.offsets_truth)
    _,jac=model.residual_jac(x)
    u,sv,vh=np.linalg.svd(jac,full_matrices=True)
    rank=int(np.sum(sv>sv[0]*1e-8)) if len(sv) else 0
    cond=float(sv[0]/sv[-1]) if len(sv) and sv[-1]>0 else float('inf')
    # Vectors in scaled, gauge-fixed parameter coordinates; block energy is descriptive only.
    mic_end=3*model.m-6;src_end=mic_end+3*model.n;clock_end=src_end+model.m
    blocks={'microphones':slice(0,mic_end),'sources':slice(mic_end,src_end),'clocks':slice(src_end,clock_end),'emissions':slice(clock_end,model.size)}
    vectors=[]
    for idx in range(max(0,len(sv)-3),len(sv)):
        vec=vh[idx];vectors.append({'singular_value':float(sv[idx]),'relative_to_max':float(sv[idx]/sv[0]),
            'block_energy':{name:float(np.sum(vec[sl]**2)) for name,sl in blocks.items()}})
    nulls=[]
    for vec in vh[rank:rank+min(3,model.size-rank)]:
        nulls.append({'block_energy':{name:float(np.sum(vec[sl]**2)) for name,sl in blocks.items()}})
    return {'evaluation_point':'generating parameters, gauge fixed; evaluation only','jacobian_shape':list(jac.shape),
        'singular_values':sv.tolist(),'rank_relative_1e-8':rank,'condition_number':cond,
        'parameter_nullity':int(model.size-rank),'full_column_rank':bool(rank==model.size),
        'condition_number_scope':'largest/smallest reported nonzero row-space singular values; does not encode nullity',
        'three_weakest_measured_directions':vectors,'first_exact_numerical_null_directions':nulls,
        'warning':'scaled-parameter Jacobian; rank/conditioning depend on parameter scaling and threshold; local only'}

def evaluate(state,model,truth,label):
    return C17.score(state,model,truth,label)

def fit_blind(q,c,length,t_scale,truth,name,state,meta):
    # The optimizer sees only q,c through model; truth enters only post-run scoring.
    model=C6.DirectFit(q,c,length,t_scale)
    initial=evaluate(state,model,truth,name+'_initial'); x0=model.pack(*state);started=perf_counter()
    try: fit=model.optimize(x0,max_nfev=MAX_NFEV)
    except Exception as exc:return {'method':name,'metadata':meta,'initial':initial,'failure':type(exc).__name__+': '+str(exc)}
    elapsed=perf_counter()-started;st=(fit['microphones'],fit['sources'],fit['emissions'],fit['offsets'])
    final=evaluate(st,model,truth,name+'_final');r_lim,p_lim,t_lim=C17.thresholds(truth)
    fit_screen=final['direct_residual_norm_s']<=r_lim
    geo_screen=(final['combined_position_rmse_after_alignment_m']<=p_lim and final['timing_errors']['emission_rmse_s']<=t_lim and final['timing_errors']['clock_rmse_s']<=t_lim)
    final['screen_thresholds']={'direct_residual_norm_s':r_lim,'combined_aligned_position_rmse_m':p_lim,'emission_and_clock_rmse_s':t_lim}
    opt=fit['optimizer']
    return {'method':name,'metadata':meta,'initial':initial,'final':final,'measurement_fit_pass':bool(fit_screen),
        'geometric_timing_recovery_pass':bool(geo_screen),'physical_valid':final['corrected_toas_positive'] and final['ranges_finite_positive'],
        'recovered':bool(fit_screen and geo_screen and final['corrected_toas_positive'] and final['ranges_finite_positive']),
        'estimated_emission_times_s':fit['emissions'].tolist(),'estimated_microphone_clock_offsets_s':fit['offsets'].tolist(),
        'optimizer':{'success':bool(opt.success),'status':int(opt.status),'message':str(opt.message),'nfev':int(opt.nfev),
            'njev':int(opt.njev or 0),'runtime_s':elapsed,'jacobian_rank':int(fit['rank']),
            'jacobian_condition':float(fit['condition']),'singular_values':fit['singular_values'].tolist()}}

def align_pair(a,b):
    a=np.asarray(a);b=np.asarray(b);ac=a.mean(0);bc=b.mean(0);u,_,vt=np.linalg.svd((a-ac).T@(b-bc));rot=u@vt
    return float(np.sqrt(np.mean(np.sum(((a-ac)@rot+bc-b)**2,axis=1))))
def alternative_solutions(rows,limit):
    eligible=[r for r in rows if r.get('final') and r['final']['direct_residual_norm_s']<=limit]
    out=[]
    for i in range(len(eligible)):
        for j in range(i+1,len(eligible)):
            a=eligible[i]['final'];b=eligible[j]['final']
            geo=align_pair(a['coordinates_canonical_m'],b['coordinates_canonical_m'])
            if geo>.1:
                out.append({'method_a':eligible[i]['method'],'method_b':eligible[j]['method'],
                    'residual_a_s':a['direct_residual_norm_s'],'residual_b_s':b['direct_residual_norm_s'],
                    'pairwise_geometry_rmse_m':geo,
                    'emission_vector_difference_rmse_s':float(np.sqrt(np.mean((np.asarray(eligible[i]['estimated_emission_times_s'])-np.asarray(eligible[j]['estimated_emission_times_s']))**2))),
                    'clock_vector_difference_rmse_s':float(np.sqrt(np.mean((np.asarray(eligible[i]['estimated_microphone_clock_offsets_s'])-np.asarray(eligible[j]['estimated_microphone_clock_offsets_s']))**2))),
                    'clock_rmse_truth_a_s':a['timing_errors']['clock_rmse_s'],'clock_rmse_truth_b_s':b['timing_errors']['clock_rmse_s'],
                    'interpretation':'distinct aligned geometries with low residual; not proof of exact global ambiguity'})
    return out

def run_config(config):
    truth,provenance=make_oat_problem(config);q=truth.q;c=truth.c
    length,t_scale=C6.characteristic_scales(q,c);model=C6.DirectFit(q,c,length,t_scale);m,n=q.shape
    blind=C6.Problem(truth.name,q,c,None,None,None,None,truth.noise_std_s)
    truth_jac=jacobian_diagnostics(truth,model);rows=[]
    pzero=np.zeros(m+n-1)
    try:pgaub,timing_detail=C6.gaubitch_timing_start(q,t_scale,outer_iterations=100)
    except Exception as exc:pgaub=None;timing_detail={'failure':type(exc).__name__+': '+str(exc)}
    for rep in range(STARTS):
        # Distinct deterministic Crocco multistart seeds. Initializers receive q,c,p and dimensions only.
        for key,label,p in [('A','A_zero_timing_SVD_Crocco',pzero),('B','B_Gaubitch_SVD_Crocco',pgaub)]:
            if p is None:
                rows.append({'method':label,'replicate':rep,'failure':'timing initializer failed','metadata':timing_detail});continue
            seed=518000+sum(config['name'].encode())*17+rep+(0 if key=='A' else 10000)
            st,detail=C6.algebraic_metric_start(q,c,p,label,seed=seed)
            if st is None:
                rows.append({'method':label,'replicate':rep,'initialization_rejected':True,'failure':str(detail),
                    'timing_estimate_s':p.tolist(),'initializer_seed':seed});continue
            md={'initializer_seed':seed,'timing_parameters_s':p.tolist(),'timing_details':timing_detail if key=='B' else None,
                'truth_used_by_initializer':False,'inputs':['complete TOA matrix','sound speed','counts','fixed zero or TOA-estimated timing vector']}
            rows.append(fit_blind(q,c,length,t_scale,truth,f'{label}_rep{rep:02d}',st,md))
        # Existing direct multistart: 3 deterministic Halton starts plus 5 fixed-seed random starts.
        starts=C6.structured_starts(blind,model,scales=(.5,1.,2.))
        starts += [(f'random_seed_{700+rep}',model.pack(*C6.random_blind_start(blind,700+rep,length))) for _ in [0]]
        # For replicates 0..2 use three different deterministic structured starts; later reps random starts.
        if rep>=3:
            name=f'random_seed_{700+rep}'; start=starts[-1][1]
        else:
            name,start=starts[rep]
        rows.append(fit_blind(q,c,length,t_scale,truth,f'C_direct_TOA_{name}',model.unpack(start),
            {'initializer_seed':700+rep if rep>=3 else 'deterministic_halton_index_'+str(rep),
             'truth_used_by_initializer':False,'inputs':['complete TOA matrix','sound speed','counts','TOA-derived length/time scales']}))
    rlim=C17.thresholds(truth)[0]; summaries={}
    for method in ('A_zero_timing_SVD_Crocco','B_Gaubitch_SVD_Crocco','C_direct_TOA'):
        rs=[r for r in rows if r['method']==method or r['method'].startswith(method+'_')]
        finals=[r for r in rs if r.get('final')]
        summaries[method]={'attempts':len(rs),'initializer_rejections':sum(bool(r.get('initialization_rejected') or r.get('failure')) for r in rs),
            'refinements':len(finals),'measurement_fit_passes':sum(bool(r.get('measurement_fit_pass')) for r in finals),
            'geometric_timing_recoveries':sum(bool(r.get('recovered')) for r in finals),
            'position_rmse_m':[r['final']['combined_position_rmse_after_alignment_m'] for r in finals],
            'timing_rmse_s':[r['final']['timing_errors'] for r in finals],
            'final_jacobian_ranks':[r['optimizer']['jacobian_rank'] for r in finals],
            'final_jacobian_conditions':[r['optimizer']['jacobian_condition'] for r in finals],
            'distinct_low_residual_solution_pairs':alternative_solutions(finals,rlim)}
    return {'configuration':config,'factor_change_from_baseline':[k for k in config if config[k]!=BASE.get(k)],
        'dimensions':{'M':m,'N':n,'observations':int(q.size),'gauge_fixed_unknowns':model.size,'residual_dof':int(q.size-model.size)},
        'provenance':provenance,'q_derived_scales':{'length_m':length,'time_s':t_scale},
        'generating_solution_jacobian':truth_jac,'screen_thresholds':{'direct_residual_norm_s':rlim,
            'position_rmse_m':C17.thresholds(truth)[1],'each_timing_rmse_s':C17.thresholds(truth)[2],
            'source':'same predeclared C17 engineering screens; not publication criteria'},
        'methods':rows,'summary':summaries,'truth_used_only_for_generation_and_post_run_scoring':True}

def main():
    all_cases=[];log_lines=[f'C18 factorial OAT study; starts/method/case={STARTS}; direct max_nfev={MAX_NFEV}; seed protocol fixed']
    for i,config in enumerate(CONFIGS,1):
        t=perf_counter();case=run_config(config);case['runtime_s']=perf_counter()-t;all_cases.append(case)
        desc='; '.join(f'{k}: fit={v["measurement_fit_passes"]}/{v["refinements"]}, recovered={v["geometric_timing_recoveries"]}/{v["refinements"]}, rejected={v["initializer_rejections"]}' for k,v in case['summary'].items())
        line=f'{i:02d}/{len(CONFIGS)} {config["name"]} M={config["M"]} N={config["N"]} dist={config["distribution"]} timing={config["clock_std_s"]:g}/{config["emission_std_s"]:g}s noise={config["noise_std_s"]:g}s {desc}'
        log_lines.append(line);LOG.write_text('\n'.join(log_lines)+'\n',encoding='utf-8');print(line,flush=True)
    result={'phase':'5C.18 direct-path identifiability and controlled design','status':'exploratory; no production initializer accepted',
        'model':'q_ij=e_j+||s_j-m_i||/c+b_i+noise_ij; unchanged from C17',
        'factorial_design':{'type':'one-factor-at-a-time','baseline':BASE,'configurations':CONFIGS,'starts_per_method_per_configuration':STARTS,
            'methods':['A zero-timing SVD/Crocco','B Gaubitch-derived timing plus SVD/Crocco','C direct Euclidean TOA multistart'],
            'fixed_direct_optimizer_budget':MAX_NFEV,'reference_necessary_counts':'M>=5,N>=13 from cited reference model; necessary, not sufficient'},
        'initializer_access_control':'Optimizers and initializer routines receive q,c,dimensions, candidate timing vector and derived scales only. Truth-bearing Problem is withheld from direct-start generation; evaluation functions access truth only after fit.',
        'criteria':'same C17 diagnostic screens; residual fit and aligned geometry/timing recovery reported separately; no paper accuracy threshold',
        'cases':all_cases,'runtime_warnings':RUNTIME_WARNINGS,'limitations':['Finite deterministic starts; no global uniqueness proof.','Jacobian is local and uses scaled gauge-fixed parameters.','Room shape and spatial distribution are controlled synthetic generator factors, not inverse inputs.','Cross-case effects are descriptive; only one factor changes from baseline in each case.','No missing-data method is supported or evaluated in the existing candidate initializers.'],
        'interpretation':'See docs/direct_path_identifiability_study.md; distinguish local rank, measurement fit, and global identifiability.'}
    OUT.write_text(json.dumps(safe(result),indent=2,allow_nan=False),encoding='utf-8')
    if RUNTIME_WARNINGS:
        with LOG.open('a',encoding='utf-8') as log:
            log.write('Runtime warnings observed during optimizer trial evaluations:\n')
            for warning in RUNTIME_WARNINGS: log.write('WARNING '+warning+'\n')
    print(f'Wrote {OUT}',flush=True)
if __name__=='__main__':main()






