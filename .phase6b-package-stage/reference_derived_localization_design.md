# Reference-derived initial localization: implementation design

**Status: design only. No algorithm is implemented by this document.** The proposed estimator combines the general unequal-offset timing model from Gaubitch et al. [7] with the general (non-co-location) Euclidean coordinate recovery of Crocco et al. [28]. It does not claim to be a literal reproduction of every printed step in Crocco, Trucco & Del Bue (2016). In particular, the literal 2016 Eq. (13) and Algorithm 2 timing-update statements are retained below as unresolved source formulations.

## Sources and decision boundary

- 2016 preprint, Section 4.2, Eqs. (12)–(15), Algorithm 2: [archived PDF](../research/Uncalibrated_3D_Room_Reconstruction_from_Sound.pdf), [arXiv full text](https://arxiv.org/html/1606.06258).
- [7] Gaubitch, Kleijn & Heusdens (2013), Sections 2–3, Eqs. (1), (3)–(10), Algorithm 1: [author-hosted PDF](https://www.commsp.ee.ic.ac.uk/~ndg/papers/Gaubitch2013.pdf).
- [28] Crocco, Del Bue, Bustreo & Murino (2012), Sections 2.1–2.2, Eqs. (3)–(20): [ICASSP proceedings PDF](https://dihana.cps.unizar.es/proceedings/ICASSP/2012/pdfs/0002597.pdf).

The reference-derived formulation below assumes known sound speed `c`, a complete matrix of correctly identified direct-path measured arrival times, and independent unknown emission and microphone offset times. The localization routine receives no ground-truth coordinates. Ground truth is only available to validation code.

## 1. Inputs, outputs, and dimensions

### Input contract

Conceptual typed input `DirectTOAInput`:

| Field | Shape/type | Unit / rule |
|---|---|---|
| `arrival_times_s` | finite float matrix `A ∈ R^(M×N)` | seconds; row `i` microphone, column `j` source event; direct path only |
| `speed_of_sound_m_s` | positive finite scalar `c` | m/s |
| `source_ids`, `microphone_ids` | ordered unique identifiers | preserve index mapping |
| `mask` | optional Boolean `M×N` | `true` means unavailable |
| `metadata` | sampling/provenance/settings record | cannot contain known positions as estimator inputs |

The reference method requires a complete matrix. The proposed behavior is to **reject any missing value or true mask entry** with an explicit `IncompleteTOAMatrix` result before constructing a double difference. Do not impute, interpolate, or silently discard rows/columns. A missing-aware estimator would be a separately researched extension.

Arrival times are finite numbers relative to the supplied time origin. Do not require them to be positive: a global time origin is arbitrary when emission times and clock offsets are unknown. A negative corrected propagation time after estimation is invalid and must cause failure, not clipping.

### Output contract

Conceptual typed `InitialLocalizationResult`:

- Estimated source coordinates `sources_m ∈ R^(N×3)` and microphone coordinates `microphones_m ∈ R^(M×3)`, in a reported canonical gauge.
- Estimated emission times `emission_times_s ∈ R^N`, microphone offsets `clock_offsets_s ∈ R^M`, with `emission_times_s[0]=0` gauge.
- Input apparent TOAs and distances, timing correction matrices, corrected double-difference matrix, rank-3 approximation, singular values, rank diagnostics, residual histories, optimizer statuses, selected start, and all failed-start reasons.
- Per-pair corrected TOFs `A_ij - e_j - o_i`, distances `c * TOF`, and flags for invalid/nonpositive propagation times.
- Status enum: success, invalid input, insufficient count, degenerate geometry, ill-conditioned factor recovery, optimizer failure, nonconvergence, or invalid corrected TOFs.
- Provenance tag `reference_derived_variant`, equation convention version, and explicit statement that this is not the literal unresolved Eq. (13) implementation.

All public coordinate arrays should be microphone/source by xyz (row points). Internally, matrix dimensions and axis labels below are fixed as stated.

## 2. Measurement and double-difference model

For microphone `i=1..M`, source event `j=1..N`, the measured direct-path TOA is

\[
a_{ij}=\frac{\|\mathbf r_i-\mathbf s_j\|_2}{c}+o_i+e_j+\nu_{ij},
\]

where coordinates `r_i,s_j` are unknown metres; `o_i` is an unknown microphone clock/sampling offset in seconds; `e_j` an unknown source emission time in seconds; `nu_ij` a measurement error in seconds. The timing model and nuisance terms are paper-derived (2016 Eqs. (1), (5); [7] Eq. (1)); additive noise is explicit in [7].

For complete observations, define apparent distance `q_ij = c a_ij` in metres. The reference-derived four-term double-difference squared-distance matrix is

\[
T_{i-1,j-1}=a_{ij}^2-a_{1j}^2-a_{i1}^2+a_{11}^2,
\quad i=2..M,\ j=2..N,
\]

with `T ∈ R^((M-1)×(N-1))` in seconds squared. Equivalently `D0=c²T` is in square metres. The two forms differ only by positive scalar `c²`; they have the same exact rank and singular vectors. Work in `seconds²` during timing correction because the correction is parameterized by seconds; convert to `metres²` before Euclidean coordinate recovery.

With true timing removed and no noise,

\[
c^2 T_{i-1,j-1}=-2(\mathbf r_i-\mathbf r_1)^T(\mathbf s_j-\mathbf s_1).
\]

Let `Rbar ∈ R^((M-1)×3)` contain `(r_i-r_1)^T`, and `Sbar ∈ R^((N-1)×3)` contain `(s_j-s_1)^T`. Then `c²T=-2 Rbar Sbar^T`, rank at most 3. This is the consistent [28] double-difference construction (Eqs. (4)–(7)); it is used as the explicit reference-derived formulation.

### Literal 2016 Eq. (13), retained separately

The archived 2016 preprint prints an `N×M` matrix using three squared apparent distances, without a visible fourth baseline term. It is not the `T` defined above, and as printed it does not generally have the stated bilinear rank-3 factorization. It must remain stored/documented as `D_2016_literal` for source comparison only. It must **not** be passed into the implementation designed here, renamed as `T`, or silently repaired. See the open-question register in `docs/initial_localization_open_questions.md`.

## 3. Timing correction from [7], general unequal offsets

Use timing gauge `e_1=0`. This removes the shared additive ambiguity: adding the same constant to all emission times while subtracting it from every microphone offset leaves every TOA unchanged. The remaining unknown vector has `M+N-1` entries:

\[
p=[o_1,\ldots,o_M,e_2,\ldots,e_N]^T\in\mathbb R^{M+N-1}.
\]

For each `i=2..M,j=2..N`, define linear correction

\[
A_{i-1,j-1}(p)=-2o_i(a_{ij}-a_{i1})+2o_1(a_{1j}-a_{11})-2e_j(a_{ij}-a_{1j}),
\]

and bilinear correction

\[
\Gamma_{i-1,j-1}(p)=2(o_i-o_1)e_j.
\]

Both matrices are `(M-1)×(N-1)` in seconds squared. These signs and terms are from [7] Eqs. (4)–(6), with notation mapped to 2016. Thus `T+A(p)+Gamma(p)` is the timing-corrected relative TOA-square matrix in [7]'s convention; multiply it by `c²` to obtain the geometric squared-distance double difference in `m²`.

For a concrete implementation, define the linear design matrix `W ∈ R^((M-1)(N-1) × (M+N-1))` so `vec_F(A(p))=Wp`, with a declared Fortran/column-major pair ordering. For row corresponding to `(i,j)`, insert coefficients:

- `-2(a_ij-a_i1)` in column `o_i`;
- `+2(a_1j-a_11)` in column `o_1`;
- `-2(a_ij-a_1j)` in column `e_j`;
- zero in all other timing columns.

Here `vec_F` and row ordering are an engineering schema decision; the elementwise formula defines the math independently of storage order. Implementations must test that `reshape(vec_F(A), (M-1,N-1), order='F')` equals the elementwise expression.

### Alternating rank projection and nonlinear timing update

Initialize `p^(0)` and repeat:

1. Form `X^(k)=T+A(p^(k))+Gamma(p^(k))` (`seconds²`).
2. Compute SVD `X=U Sigma V^T`; retain three singular triplets to obtain `X_3^(k)`.
3. Define **correction target** `C^(k)=X_3^(k)-T` and **rank residual** `R_rank^(k)=X_3^(k)-X^(k)`. These are different quantities. The correction target corresponds to [7]'s `E = T_3 - T`; the rank residual corresponds to 2016 Algorithm 2 Step 4. Do not interchange them.
4. Update all offsets/emissions jointly by nonlinear least squares:

\[
p^{(k+1)}=\arg\min_{p:e_1=0}\left\|C^{(k)}-A(p)-\Gamma(p)\right\|_F^2.
\]

This uses the general unequal-offset model and retains the bilinear `Gamma`. It is the [7] general-case update. The 2016 Algorithm 2 describes a linear least-squares step; this design does not claim to resolve that discrepancy and selects [7]'s general nonlinear update as the documented reference-derived variant.
5. Recompute correction matrices and `X^(k+1)` with updated `p`.
6. Evaluate scaled correction-fit norm, rank residual norm, and relative parameter change. Stop only when all configured convergence checks pass or a failure/max-iteration condition occurs.

Do not add [7]'s temporary `lambda ||X||_F²` continuation by default. [7] reports it as a convergence aid but 2016 does not specify it. A regularized/annealed mode can be evaluated as a separate, explicitly enabled engineering option.

### Timing initialization and multistart

Neither 2016 nor [7] specifies a general production initialization rule for this exact setting. Proposed BatSight initialization, clearly an engineering choice:

- Start A: all free offsets and emissions zero (`e_1=0`).
- Additional starts: deterministic pseudorandom vectors centered at zero, generated from a recorded seed, with scale derived from the observed TOA matrix rather than fixed paper values.
- Define a characteristic time `t_scale = max(sqrt(median(abs(T))), 1.4826 * median(abs(a - median(a))))`. If either scale is nonfinite or the resulting scale is numerically zero, report degeneracy and require an explicit caller scale; do not insert an undocumented numerical floor.
- Draw randomized start values as `p = t_scale * z`, with `z` standard normal, then set the first emission to zero by parameterization (it is absent from `p`). Proposed default number of starts: 8 including zero start, seed recorded. This count/seed policy is BatSight configuration, not a paper setting.
- Optimize every start; retain only converged starts with finite, physically positive corrected propagation times. Select the candidate with the smallest normalized correction-fit objective, then use rank residual as a deterministic tie-breaker. Preserve all starts and diagnostics.

These choices are provisional until synthetic validation demonstrates stable behavior. Multistart does not guarantee the global minimum.

## 4. Rank-3 SVD and numerical diagnostics

For `X ∈ R^((M-1)×(N-1))`, require both dimensions at least 3. Use a full-precision economy SVD `X=U diag(sigma) V^T`; construct `X_3=U[:,0:3] diag(sigma[0:3]) V[:,0:3]^T`. The minimum rank is from the algebra; the joint timing reference [7] additionally derives its count condition described below.

Report singular values, ratios `sigma_3/sigma_1` and `sigma_4/sigma_1` where available, rank-3 residual `||X-X_3||_F/||X||_F`, and the condition ratio `sigma_1/sigma_3`. Do not use a universal numeric rank threshold as if the papers specify one. Proposed diagnostics: treat zero/nonfinite `sigma_1`, nonfinite values, or `sigma_3` below a documented floating-point-relative threshold as failure; mark a large `sigma_4/sigma_3` under noisy data as model mismatch rather than automatically rejecting. Exact cutoffs are BatSight settings to establish during validation.

At least 3 rows and columns are required by the factorization. For the timing-identifiability count, [7] derives `M>=5` and `N >= (4M-7)/(M-4)`; for integer event counts use the ceiling. At `M=5`, this gives `N>=13`. These are a degrees-of-freedom lower bound for [7]'s model, not a sufficient condition: repeated/collinear/coplanar or poorly spread layouts can still fail rank/conditioning checks. The 2016 paper does not separately state this minimum.

## 5. General coordinate recovery from [28]

After timing convergence, form corrected pairwise TOFs and distances:

\[
\hat\tau_{ij}=a_{ij}-\hat o_i-\hat e_j,\qquad \hat d_{ij}=c\hat\tau_{ij}.
\]

Require every corrected TOF to be finite and strictly positive. Form `D0 ∈ R^((M-1)×(N-1))`, `D0=c²(T+A(p)+Gamma(p))` in square metres, and compute its rank-3 SVD `D0=U_3 Sigma_3 V_3^T`.

Parameterize the SVD factors by arbitrary invertible `C ∈ R^(3×3)`:

\[
\bar R=U_3C,\qquad \bar S^T=-\tfrac12 C^{-1}\Sigma_3V_3^T.
\]

Coordinate gauge (reference-derived from [28]): place the first microphone at origin, `r_1=(0,0,0)`, and the first source on the x-axis, `s_1=(alpha,0,0)`. For `i>=2`, set `r_i` to row `i-1` of `Rbar`; for `j>=2`, `s_j=s_1+row_(j-1)(Sbar)`. The mathematical unknowns remain the nine degrees of freedom of general invertible `C` plus anchor scalar `alpha`; the optimizer parameterizes `C` through the polar strategy below rather than raw entries.

The general [28] quadratic coordinate-recovery residual for `i=2..M,j=2..N` is

\[
g_{ij}(C,\alpha)=\|r_i\|_2^2-2r_i^Ts_j-(\hat d_{ij}^2-\hat d_{1j}^2).
\]

Minimize `sum_{i=2}^M sum_{j=2}^N g_ij²`, using corrected distances and the SVD parameterization. This is the non-co-location general route corresponding to [28] Eqs. (10)–(12), [7] Eqs. (15)–(16). Do **not** use [28]'s special closed-form branch that assumes a source coincides with a microphone. The objective is a squared-distance algebraic residual, not the original range-domain maximum-likelihood objective; report its units and do not equate its minimizer with guaranteed ML under noisy TOAs.

The first microphone/origin and first source/x-axis gauges leave a rotation around x unresolved. Proposed engineering canonicalization: after coordinate recovery, rotate the whole configuration around x so the first non-collinear microphone lies in the xy-plane with nonnegative y. If no such microphone is numerically distinguishable, report axial-gauge degeneracy. Reflection/triangular sign choices can still yield equivalent configurations; choose the lowest objective candidate and retain the branch metadata. This extra canonical orientation convention is not stated as a specific 2016 choice.

## 6. Optimizer, scaling, and conditioning proposal

All settings in this section are **BatSight engineering proposals**, not values claimed from the papers.

### Timing optimizer

- Optimizer: SciPy `least_squares`, trust-region reflective method, finite-difference Jacobian initially; use analytic Jacobian only after independently validated.
- Residual vector: `vec_F((C^(k)-A(p)-Gamma(p))/t_scale²)`; the dimensionless scale improves conditioning and does not change the unweighted least-squares minimizer.
- Parameterization: optimize dimensionless `u=p/t_scale`; reconstruct seconds before evaluating `A,Gamma`. Scale every timing parameter by the same `t_scale` initially; later per-variable scales may be added only with recorded configuration.
- Loss: linear least squares to match [7]'s Gaussian/Frobenius assumption. Robust losses are not part of this reference-derived version.
- Bounds: none on offsets or emission times; they may be signed relative to chosen clocks/time origin. Reject invalid corrected TOFs after a candidate update instead of clipping them.
- Stop a start when the scaled gradient/optimality, relative cost change, and relative parameter-step criteria are all satisfied; use explicit max evaluations. Proposed initial thresholds: `gtol=1e-8`, relative objective change `1e-8`, relative scaled step `1e-8`, max evaluations 2000 per update, max outer iterations 200. These are provisional engineering values and must be tuned only through the validation matrix.

### Coordinate optimizer

- **Nonredundant parameterization:** do not optimize the nine raw entries of `C`. Use the polar decomposition

  \[
  C=L_0\exp(\ell)\,D_\delta R(\omega)\exp(H(h)),\qquad
  D_\delta=\mathrm{diag}(1,1,\delta),\quad \delta\in\{-1,+1\},
  \]

  Here `L0>0` is a fixed characteristic length scale, `ell∈R` is the optimized isotropic log-scale, `R(omega)∈SO(3)` is the matrix exponential of the 3-vector's skew-symmetric matrix, and `H(h)` is a symmetric traceless matrix with exactly five independent parameters. Use an orthonormal Frobenius basis:

  \[
  E_1=\frac{1}{\sqrt2}\begin{bmatrix}1&0&0\\0&-1&0\\0&0&0\end{bmatrix},\quad
  E_2=\frac{1}{\sqrt6}\begin{bmatrix}1&0&0\\0&1&0\\0&0&-2\end{bmatrix},
  \]
  and `E3,E4,E5` with symmetric unit-Frobenius off-diagonal `(1,2)`, `(1,3)`, `(2,3)` entries. Set `H(h)=sum_(k=1)^5 h_k E_k`; this guarantees `trace(H)=0` and `||H||_F=||h||_2`. The continuous factor count is `1+3+5=9`; with the separately optimized anchor `alpha/L0`, the coordinate objective has ten continuous variables. There is no redundant isotropic scale in `trace(H)`.

  Coverage follows from polar decomposition. For any `C∈GL(3,R)`, write `C=Q P`, where `Q` is orthogonal and `P` is symmetric positive definite. Set `delta=sign(det Q)`, `R=D_delta Q∈SO(3)`, `L=L0 exp(ell)=(det P)^(1/3)`, and `H=log(P/L)`. Then `trace(H)=0` and the displayed parameterization recovers `C` exactly. The two `delta` branches preserve both determinant signs; no invertible factor is excluded except one whose condition number exceeds the explicitly selected numerical cap.

  The condition number is exactly `cond_2(C)=exp(lambda_max(H)-lambda_min(H))`; isotropic scale and orthogonal factors do not change it. Enforce the cap as the nonlinear inequality `lambda_max(H)-lambda_min(H) <= log(kappa_max)`, rather than bounding five coordinates with a box that would exclude otherwise admissible factors. The cap is an engineering numerical policy, not a paper parameter. Proposed progression remains `kappa_max=1e8`, then `1e12`, then `1e16` if the best factor is cap-limited. Record cap activity and return an ill-conditioned-factor failure if the final cap remains active with improving objective.

- **Safe inverse-factor evaluation:** construct `Cbar=C/L0=exp(ell)D_delta R exp(H)`. Never call an explicit matrix inverse. Compute `Sbar^T = -0.5/L0 * solve(Cbar, Sigma_3 V_3^T)` using a stable linear solve, after checking finite entries, determinant sign consistency, and `cond_2(Cbar) <= kappa_max`. Since the exponential parameterization guarantees mathematical nonsingularity for finite parameters, a failed solve or excessive condition estimate is a numerical failure. Evaluate `exp(H)` via a symmetric eigendecomposition and reject overflow/nonfinite results. Keep `L0` out of the solve to reduce scale-related conditioning.

- Optimizer variables: `ell`, the 3 rotation-vector entries, 5 traceless symmetric-log coefficients, and scaled anchor `alpha/L0`; run the two discrete `delta` branches separately. Every factor is nonsingular for finite parameters. Enforce the exact spectral-spread condition-number inequality with a constrained optimizer; the Phase 5C.4 exploratory check used SLSQP with finite differences, deterministic starts, and both branches. This is an engineering solver choice, not a Crocco prescription. Bound each rotation-vector component to `[-pi,pi]`, which contains a principal axis-angle chart. Start at zero shape/rotation with a deterministic set of signed anchor guesses and seeded perturbations. Start count and tolerances remain recorded BatSight settings, not paper values.

- **Conditioning behavior:** near-singular raw matrices cannot be proposed because `exp(H)` has strictly positive singular values and the spectral-spread inequality caps the condition number. Near-singular solutions are represented only as the cap expands. The factor solve is checked at every residual evaluation. If a trial becomes nonfinite or fails the safe solve, return a large finite fixed penalty residual for that trial and record the event; never return NaN/Inf to the optimizer and never change the objective for valid candidates. If a whole start encounters invalid trials or all starts terminate at a condition cap, classify as numerical/conditioning failure rather than geometric degeneracy unless independent SVD/Jacobian diagnostics also indicate degeneracy.

- **Determinant, sign, and reflection branches:** run `delta=-1` and `delta=+1` separately because a continuous optimizer cannot cross `det(C)=0` between them. The factorization itself permits both. Preserve all converged branches with their objectives; select by normalized Crocco residual, then corrected-distance residual, then deterministic branch/start ordering. Reflections of the final point cloud are distance-equivalent; final rigid alignment may allow reflection for validation. Never discard the negative-determinant branch solely because it is a reflection.

- Residual vector: `g_ij/L0²`, where the positive characteristic scale `L0 = sqrt(median(abs(D0)))`; set `L_scale` in older notation equal to `L0`. If zero/nonfinite, fail conditioning rather than invent a scale.
- Loss: sum of squared normalized coordinate residuals to match [28]'s algebraic LS construction. Parameter residuals use `L0` as the coordinate length scale; [28] does not specify a universal initial factor.
- Check `cond(Cbar)`, smallest singular value, Jacobian rank, coordinate factor consistency, and the H-bound activity. One null direction from the remaining axial coordinate gauge is expected before canonicalization; a rank deficiency beyond this known gauge is a degeneracy/conditioning warning.

### Optimizer failure versus geometric degeneracy

Do not infer geometry failure merely because a nonlinear optimizer failed. Return separate diagnoses:

- `optimizer_failure`: no start reached a finite candidate satisfying the optimizer's termination checks, while the corrected matrix has adequate rank and there is no stable geometry-degeneracy evidence.
- `degenerate_geometry`: corrected double-difference SVD has effective rank below 3 under the declared numerical threshold, or converged candidates have an additional coordinate-objective Jacobian rank deficiency after accounting for known gauge freedom. This indicates the observations do not constrain a full 3D configuration locally.
- `ill_conditioned_geometry`: rank is nominally 3 but singular-value/Jacobian condition diagnostics are poor or estimates vary materially across converged starts/noise-level perturbations. This is not the same as exact degeneracy.
- `ill_conditioned_factor`: coordinate fit only improves while a factor cap is active, safe solves exceed the declared condition cap, or no cap level yields stable factors.
- `unclassified_numerical_failure`: numerical failures occur without enough evidence to identify optimizer failure versus geometry degeneracy. Preserve the status instead of overstating the cause.

Report corrected-matrix singular values, coordinate Jacobian singular values, optimizer exit codes, active bounds, objective per start, and cross-start coordinate spread to support the classification. The rank and condition thresholds remain explicit configuration and require validation; they are not paper settings.

### Matrix-parameterization validation plan

Before applying `C` optimization to generated observations, validate the parameterization independently:

1. **Coverage fixture:** generate deterministic nonsingular matrices with positive and negative determinant and a range of condition numbers. Compute their polar factors, recover `(delta, omega, H)`, rebuild `C`, and compare relative matrix error. Confirm both signs are represented and determinant signs are preserved.
2. **Known-coordinate factor fixture:** choose nondegenerate known 3D microphone/source coordinates, form the exact centered factor matrix `D0=-2 Rbar Sbar^T`, take its rank-3 SVD, and optimize the general quadratic coordinate residual from multiple starts and both determinant branches. Confirm the residual reaches floating-point tolerance and recovered coordinates align rigidly (with reflection allowed) to the known points.
3. **Branch fixture:** reflect one coordinate axis of both known point sets, regenerate the same pairwise distances, and verify the reflected solution remains an accepted equivalent branch rather than being discarded by determinant filtering.
4. **Condition-cap fixture:** use a sequence of matrices/configurations with increasingly anisotropic coordinate spread. Confirm safe solves stay finite below the cap, cap expansion is recorded when needed, and the algorithm returns `ill_conditioned_factor` rather than NaN coordinates at the final cap.
5. **Degeneracy/failure separation:** run a coplanar/collinear fixture and a well-conditioned fixture with intentionally inadequate optimizer evaluations. The former should be diagnosed from rank/Jacobian evidence; the latter should report optimizer failure, not geometry degeneracy.

These are design-level validations. Thresholds for “effective rank,” cross-start spread, optimizer tolerances, and condition caps must be fixed before interpreting results and recorded as BatSight engineering settings.

### Outer stopping and failure conditions

### Phase 5C.4 parameterization audit

The exploratory metric-consistency check removed the scale/trace redundancy by retaining `ell` and restricting `H` to the five-dimensional symmetric-traceless subspace described above. For any `C∈GL(3)`, polar decomposition yields `C=QP`; `delta=sign(det Q)`, `R=D_delta Q∈SO(3)`, `L=L0 exp(ell)=(det P)^(1/3)`, and `H=log(P/L)` is symmetric with zero trace. Therefore the two branches cover all invertible factors before the numerical condition cap. Since `cond_2(C)=cond_2(exp(H))=exp(lambda_max(H)-lambda_min(H))`, the cap is the spectral-spread constraint `lambda_max(H)-lambda_min(H) <= log(kappa_max)`. The cap is the only intentional exclusion. This replaces the earlier redundant six-parameter symmetric `H` plus independent scale and supersedes any older formulation text.

The seed-11 Phase 5C.4 exploratory test passed a known-coordinate positive control on both determinant branches and rejected the three tested positive-TOA rank-only alternatives by their Crocco residual gate; see `docs/initial_localization_implementation.md` for numerical tables. This is evidence about those tested candidates only, not a change to the timing formulation or a global uniqueness result. SLSQP and its tolerances are experimental engineering settings, not prescribed by Crocco.

Proposed outer-loop stop requires both (a) relative change in rank residual and correction-fit objective below configured tolerances and (b) scaled timing parameter change below tolerance, for two consecutive iterations. Also stop with `nonconvergence` after the configured iteration limit. The printed 2016 criterion `||E||_F < threshold` is retained in diagnostics as a paper-reference quantity, but its numeric threshold is unknown and this design does not claim an exact setting.

Fail explicitly for: nonfinite/inconsistent input shape; missing TOAs; fewer than reference-derived count; `c<=0`; zero/near-zero rank support; numerical overflow; optimizer failure/no converged starts; singular coordinate factor; no finite coordinate candidate; or corrected propagation time `<=0`. High residual or poor conditioning should be surfaced as `degenerate_geometry` or `model_mismatch`, not converted to coordinates without a warning.

## 7. Paper statement versus chosen design

| Component | Source status | Design decision |
|---|---|---|
| Four-term double difference | Explicit in [28], required for the rank factorization; not the literal printed 2016 Eq. (13). | Use four-term matrix for algorithm; preserve 2016 literal separately. |
| Unequal microphone delays | [7] Eqs. (4)–(6) give linear plus bilinear terms. | Retain both; nonlinear LS update. |
| Rank-3 approximation | 2016 Algorithm 2 and [7] specify truncated SVD. | Use top three singular components and diagnostics. |
| General coordinate recovery | [28] gives a general nonlinear LS over factor ambiguity and quadratic constraints. | Use 10 continuous variables (9 for `C`, 1 for `alpha`) in an invertible polar parameterization, with two enumerated determinant branches; no co-location assumption. |
| Initialization, optimizer settings, scaling, start counts, tolerances | Not fully specified in 2016; only some experimental settings in [7]/[28]. | Marked proposals above; record in result provenance and validate empirically. |
| Missing values/outliers | No supported complete-data initialization procedure. | Reject missing matrix; no imputation or robust loss. |

This specification is a review artifact. Phase 5C implementation should not begin until the proposed choices, especially timing initialization/convergence and coordinate multistart behavior, are reviewed and approved.
