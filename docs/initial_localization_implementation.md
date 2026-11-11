# Initial localization implementation status

## Status: blocked before delivery

Phase 5C implementation was stopped before an engine was delivered. A prototype of the approved timing iteration was exercised on a deterministic, noiseless `M=5, N=13` synthetic observation fixture. It did not meet the approved convergence conditions within the configured outer-iteration budget.

Observed in the fixture:

| Outer iterations | Relative rank-3 residual |
|---:|---:|
| 200 | approximately `5.60e-4` |
| 3,000 | approximately `1.69e-4` |

The rank residual continued decreasing slowly. The timing parameters had not converged under the specified scaled-step/objective checks, so no localization result or coordinate-recovery score is reported. This was noiseless data; the failure is therefore an optimizer/convergence issue, not evidence of geometry degeneracy.

## Source of the blocker

The approved design uses the Gaubitch alternating procedure:

1. Correct the four-term double-difference matrix with `A(p)+Gamma(p)`.
2. Project the corrected matrix onto rank 3 by truncated SVD.
3. Update timing parameters by nonlinear least squares to fit the projected correction target.
4. Repeat until rank, objective, and parameter-change conditions hold.

The documented initialization is zero plus seeded random starts. The Phase 5B design intentionally declined to enable Gaubitch et al.'s temporary `lambda ||T_hat||_F^2` continuation by default because the 2016 paper does not specify it. However, the Gaubitch paper describes the unregularized iteration as potentially very slow and uses that continuation to improve its initial convergence. The observed slow convergence means the approved default cannot currently support the requested deterministic exact-recovery tests within practical runtime.

Enabling the cited continuation, adding a separate linearized warm start, or optimizing the rank residual directly would change the approved numerical strategy. No such change has been made silently.

## Verification performed

- Checked the elementwise general bilinear correction against hand-generated noiseless geometry; the corrected double difference matched the true geometric double difference to floating-point precision (`~1.4e-19` maximum absolute error) in the exploratory fixture.
- Confirmed the four-term matrix and timing formulas are dimensionally consistent in that fixture.
- The exploratory localization prototype did not pass the timing convergence gate. The prototype files were removed; no incomplete engine is left in `src/batsight/localization/`.
- The complete test suite, formatting, lint, and type checks were not run because implementation was stopped at this convergence blocker. No localization synthetic example or ZIP is presented as a completed deliverable.

## Phase 5C.1: Gaubitch regularization investigation

### Source statements and ambiguity

Gaubitch, Kleijn, and Heusdens (ICASSP 2013), Section 3.1, Eq. (8), prints an alternating timing update with data-fit term

\[
\|E^{(n)}-(A(\hat p^{(n)})+\hat\Gamma)\|_F^2
\quad\text{and regularizer}\quad
\lambda\|\hat T^{(n)}\|_F^2.
\]

Eq. (9) defines `E^(n) = T_tilde_3^(n) - T`; the surrounding text defines the corrected matrix from `T + A(p) + Gamma(p)` and its rank-3 approximation. The paper says the norm constraint helps keep the estimate at “reasonable dimensions,” improves initial convergence, and that lambda is set to zero when the norm change between successive corrected matrices is below a threshold. It separately reports `lambda=0.7` and an Algorithm 1 convergence check `|F(n-1)-F(n)| < 1e-12` in Section 4. It does not explicitly equate the norm-change threshold with that `1e-12` threshold.

The printed superscript on the penalty is `n`, while the left side is the next iterate and the surrounding text describes a constraint on the quantity being minimized. If `T_hat^(n)` means the already-fixed matrix at the start of the iteration, the penalty is constant with respect to the next timing vector and cannot change its least-squares minimizer. If it denotes the corrected matrix formed from the candidate timing parameters inside the minimization, it is variable and can change the minimizer. The text supports the latter as an interpretation, but the printed indexing does not uniquely establish it. The author-hosted PDF text is available at the [Gaubitch paper URL](https://www.commsp.ee.ic.ac.uk/~ndg/papers/Gaubitch2013.pdf); a fresh direct PDF fetch returned 404 during this audit, so visual glyph confirmation could not be repeated. The cached full-text extraction shows the `n` superscript.

### BatSight continuation experiment (engineering interpretation only)

To test the prose-supported candidate-dependent reading without representing it as a corrected Gaubitch equation, the experiment used

\[
J_\lambda(p\mid E^{(k)})=
\|E^{(k)}-A(p)-\Gamma(p)\|_F^2
+\lambda\|T+A(p)+\Gamma(p)\|_F^2.
\]

Here the measured `T` and projected target `E^(k)` are fixed for the timing subproblem; timing vector `p` is optimized jointly through both `A(p)` and the bilinear `Gamma(p)`. The first term is the approved unregularized timing fit. The second is a candidate-dependent penalty on the corrected matrix. With `lambda=0`, this reduces exactly to the approved unregularized update. Lambda does not alter the rank-3 SVD formula; it changes the timing fit and therefore the corrected matrix presented to the next SVD. This objective is dimensionally consistent because both terms square a matrix whose elements are in seconds squared; lambda is dimensionless under that unit convention.

The source gives an initial experimental value `lambda=0.7` and describes switching lambda to zero after the corrected-matrix norm stabilizes. It does not give a numerical threshold for this switch, a decay schedule, or a proof that the full alternating procedure converges to the unregularized solution. For the controlled test only, BatSight used constant `lambda=0.7` until the absolute change in `||T_hat||_F` fell below `1e-12`, then set it to zero. This threshold is an explicitly labeled engineering choice borrowed numerically from the separate Section 4 `F`-change tolerance; equivalence is not stated by the paper. No gradual annealing schedule was used.

### Controlled single-start comparison

Both procedures used the Phase 5C noiseless fixture: shoebox `(8, 7, 5) m`, `c=343 m/s`, `M=5`, `N=13`, fixture seed 11, same observed TOAs, zero initial timing vector, same four-term double difference, bilinear corrections, truncated SVD, scaling, trust-region least-squares settings, 200 outer iterations, and convergence gates. The scale was `8.77191949e-3 s`; both methods exhausted the outer budget without meeting the original gates. Timing error is compared against truth after setting the first emission-time gauge to zero.

Selected checkpoints (rank residual is `||X-X_3||_F/||X||_F`; fit objective is the scaled norm `||E-A-Gamma||_F/t_scale^2`; corrected norm is `||X||_F` in seconds squared; timing step is the scaled parameter change):

| Method | Iter. | Rank residual | Scaled fit norm | Corrected norm (s²) | Scaled timing step | Lambda |
|---|---:|---:|---:|---:|---:|---:|
| A: unregularized | 1 | 2.9582e-3 | 3.3598e-2 | 8.4687e-4 | 4.9162e-3 | 0 |
| A | 10 | 1.7440e-3 | 1.9729e-2 | 8.4685e-4 | 1.5525e-3 | 0 |
| A | 25 | 9.1641e-4 | 1.0231e-2 | 8.4686e-4 | 9.4476e-4 | 0 |
| A | 50 | 6.9546e-4 | 7.6658e-3 | 8.4687e-4 | 2.9102e-4 | 0 |
| A | 100 | 6.3783e-4 | 7.0251e-3 | 8.4688e-4 | 2.7755e-4 | 0 |
| A | 200 | 5.5969e-4 | 6.1637e-3 | 8.4687e-4 | 1.3803e-4 | 0 |
| B: candidate penalty | 1 | 5.3147e-3 | 4.5173 | 5.0211e-4 | 1.3970 | 0.7 |
| B | 10 | 2.7041e-2 | 4.6338e-2 | 7.1869e-5 | 2.1999e-2 | 0.7 |
| B | 25 | 2.5639e-2 | 2.3911e-2 | 7.1729e-5 | 7.2732e-4 | 0.7 |
| B | 48 | 2.5728e-2 | 2.3984e-2 | 7.1729e-5 | 1.4473e-5 | 0.7 |
| B | 49 | 2.3505e-2 | 2.2353e-2 | 7.1741e-5 | 4.2068e-3 | 0 |
| B | 100 | 1.1900e-2 | 1.1218e-2 | 7.2141e-5 | 9.9891e-4 | 0 |
| B | 200 | 4.6576e-3 | 4.4264e-3 | 7.2812e-5 | 3.7126e-4 | 0 |

The B timing fit produced a large norm change at the lambda switch; the first unregularized post-switch update therefore has a large parameter step. At iteration 200, A's gauge-aligned timing RMSE was approximately `0.362 ms`; B's was approximately `8.34 ms`. Neither recovered the known timing values within numerical tolerance, and neither met convergence. Runtime was `2.12 s` for A and `2.92 s` for B on this environment. Repeating A with the same deterministic fixture and initialization reproduced the reported 200-iteration metrics to printed precision.

### Deterministic multiple-start check (after the single-start comparison)

The zero start and two additional seeded starts (seeds 2 and 3, `p=t_scale*z`, standard-normal `z`) were evaluated for both A and the same B interpretation; all used the same 200-iteration budget. The results below give final relative rank residual, gauge-aligned timing error norm divided by `t_scale`, and runtime.

| Start | A rank residual | A scaled timing error | A runtime (s) | B rank residual | B scaled timing error | B runtime (s) |
|---|---:|---:|---:|---:|---:|---:|
| Zero | 5.5969e-4 | 0.1700 | 2.12 | 4.6576e-3 | 3.9249 | 2.92 |
| Seed 2 | 5.3012e-3 | 3.7185 | 2.14 | 4.7811e-3 | 3.9245 | 2.92 |
| Seed 3 | 6.1669e-3 | 5.6192 | 2.56 | 4.1994e-3 | 3.9287 | 2.86 |

The seed-2 and seed-3 candidate-dependent regularized runs also switched lambda to zero after 52 and 36 iterations, respectively. The regularizer drives `||X||_F` to roughly `7.2e-5 s²`, compared with `8.47e-4 s²` for unregularized zero-start A, and leaves a biased timing state. The rank residual alone is not a valid acceptance measure. No start met timing recovery plus the original convergence gates.

### Phase 5C.1 finding and implementation decision

The source does not uniquely specify whether its printed penalty is fixed or candidate-dependent. The prose makes a candidate-dependent penalty plausible, but does not resolve the indexing or provide a complete switch rule. BatSight's candidate-dependent experiment is therefore a labeled interpretation, not a source equation correction; it fails the scientific acceptance criteria and is not accepted for implementation. Under the literal fixed-current-iterate reading, the term is constant during the next timing update and has no effect on the minimizer. No regularization or continuation is enabled in the design, and the approved timing formulation and convergence criteria remain unchanged. The timing convergence blocker remains open; no localization engine exists in the source tree.

## Phase 5C.2: Direct rank-residual optimization

### Mathematical proposal and derivation

This section defines a BatSight research proposal, not a method attributed to Gaubitch or Crocco. Let `X(p)=T+A(p)+Gamma(p)`, with the already approved four-term double difference and general bilinear timing correction. For the Frobenius norm, the Eckart-Young best rank-at-most-3 approximation satisfies

\[
f(p)=\min_{\operatorname{rank}(Z)\le 3}\|X(p)-Z\|_F^2
     =\|X(p)-X_3(p)\|_F^2
     =\sum_{k=4}^{r}\sigma_k(X(p))^2,
\]

where `r=min(M-1,N-1)` and singular values are in descending order. Thus, minimizing `f(p)` penalizes all energy outside the three-dimensional singular subspace and enforces rank at most three at a zero objective. For the experiment, `s=t_scale^2` has units of seconds squared, and the dimensionless objective is `f(p)/s^2`; the denominator therefore has units seconds to the fourth. Here `t_scale=8.77191949e-3 s`, so `s=7.69465716e-5 s²`.

This objective is also the reduced form of a joint problem:

\[
\min_{p,Z:\,\operatorname{rank}(Z)\le3}\|T+A(p)+\Gamma(p)-Z\|_F^2.
\]

For fixed `p`, minimizing over `Z` is exactly the rank-3 SVD projection. For fixed `Z`, minimizing over `p` is exactly the unregularized timing fit `||Z-T-A(p)-Gamma(p)||_F²` used by the approved alternating procedure. Therefore, with exact block minimization, the alternating scheme is block coordinate minimization of this same joint objective, and eliminating `Z` yields the direct rank-residual objective. Under a unique best rank-3 projection and regularity, the envelope theorem gives the same first-order timing stationarity condition for both formulations. This does **not** establish that finite alternating trajectories match direct-optimizer trajectories, that either reaches a global minimum, or that an implementation's local least-squares timing update is an exact block minimizer.

The rank-3 projection is unique and the reduced objective is differentiable locally when there is a strict spectral gap `sigma_3 > sigma_4`. Multiplicity wholly within the retained or discarded singular-value groups does not by itself invalidate the sum-of-squares objective; a repeated value straddling the rank cutoff (`sigma_3=sigma_4`) can make the best rank-3 subspace nonunique and the reduced objective nonsmooth. At such points, finite-difference gradients may vary abruptly as the selected singular subspace changes. A true rank-3 point with `sigma_3>0=sigma_4` is locally on the smooth side of that boundary. Implementations would need to record the cutoff gap and avoid interpreting a failed finite-difference step at a cutoff tie as geometric degeneracy.

The timing model and timing gauge do not change: the shared additive time ambiguity is removed with `e_1=0`, and the parameter vector still has `M+N-1` entries. The method adds no measurements or geometric prior, so the existing minimum-count/identifiability conditions do not improve. The rank objective enforces a necessary low-rank condition, but by itself it does not check positive corrected propagation times, the separate quadratic coordinate constraints, or uniqueness of the timing vector. It can have nonconvex local minima because `X(p)` is bilinear in timing parameters and the singular-value objective is nonconvex. The objective set includes every timing vector for which `X(p)` has rank at most three, regardless of whether that vector is the generating timing vector; no uniqueness theorem for `p` follows from the rank condition alone. The experimental alternate low-residual timing solutions below show this is a practical concern. More local minima than the alternating method are not established: under exact block updates, both methods concern the same reduced landscape, though numerical optimizers can reach different basins.

### Numerical optimizer and controlled setup

Method B used SciPy `minimize` with L-BFGS-B as an unconstrained limited-memory quasi-Newton optimizer on the scalar objective. This is a practical choice for the 17 timing unknowns; it does not require differentiating SVD singular vectors analytically. The implementation evaluated the sorted singular values and used a three-point central finite-difference gradient (`finite_diff_rel_step=1e-5`) in dimensionless variables `u=p/t_scale`. This derivative strategy is appropriate only while the rank-cutoff gap stays open; it is not a cure for cutoff multiplicity. The optimizer used `ftol=1e-12`, `gtol=1e-8`, and at most `15,046` objective evaluations. The reported status can be success by relative objective reduction even when the gradient or timing-step criteria remain unmet.

Method A was the approved unregularized alternating update, rerun with the same dimensionless timing vector, float64 arithmetic, `t_scale`, four-term matrix, bilinear correction, fixture, and initial zero vector. It used 200 outer iterations and SciPy trust-region least squares for each correction fit, with up to 2,000 residual evaluations per update. It used `15,046` total timing-fit residual evaluations in this run. Method B received the same maximum function-evaluation budget (15,046), but it could stop earlier under its solver stopping condition. Both methods exhausted or stopped within the same cap; neither had its acceptance thresholds relaxed.

The fixture was regenerated exactly from seed 11: shoebox `(8,7,5) m`, `c=343 m/s`, five microphones and 13 sources sampled within the documented bounds, emissions `[0, Normal(0, 0.0005 s)]`, offsets `Normal(0,0.0005 s)`, and no timing noise. The truth parameters were transformed into the `e_1=0` gauge before error calculation. Wall-clock measurements are from this local run and are not performance guarantees.

### Zero-start comparison (performed first)

| Diagnostic | A: alternating unregularized | B: direct rank residual |
|---|---:|---:|
| Iterations / optimizer iterations | 200 outer | 38 L-BFGS-B iterations |
| Timing/objective evaluations | 15,046 residual evaluations | 1,645 objective evaluations |
| Runtime | 4.92 s | 0.63 s |
| Final relative rank residual `||X-X_3||_F/||X||_F` | 5.5969e-4 | 1.7363e-7 |
| Final scaled correction-fit norm (where applicable) | 6.1637e-3 | 1.914e-6, from `sqrt(f)` |
| Final scaled timing parameter step | 1.3803e-4 | 8.4032e-6 between final two optimizer iterates |
| Timing parameter RMSE after gauge alignment | 0.3616 ms | 0.2131 ms |
| Direct objective `f/s²` | — | 3.6626e-12 |
| Corrected-matrix norm `||X||_F` | 8.4687e-4 s² | 8.4813e-4 s² |
| Singular values around cutoff (`sigma_3`, `sigma_4`) | `sigma_4` implied by rank residual; not recorded in A trace | 1.0445e-4, 1.4726e-10 s² |
| Optimizer / original convergence status | Outer budget exhausted; original gates failed | L-BFGS-B reports success by `ftol`, but `||grad||_inf=1.5745e-7 > 1e-8` and step `8.4032e-6 > 1e-8`; original gates failed |

The direct method improved the zero-start timing RMSE and sharply reduced rank residual with fewer objective evaluations. It still did not recover the timing parameters to the original tolerance. Its small rank residual is therefore insufficient for acceptance. At its final point `sigma_3/sigma_4` is about `7.1e5`, so this particular endpoint has a clear rank-cutoff gap; the failure is not explained by a repeated singular value at the endpoint. The solver's `success=True` status reflects its relative-objective stopping rule and must not be confused with BatSight convergence acceptance.

### Seeded starts (run only after the zero-start comparison)

Two deterministic random starts were then formed as `u_0 ~ Normal(0,I)` using seeds 2 and 3. A zero-start repeat checked reproducibility. All B runs used the same 15,046-evaluation cap and optimizer settings.

| Start | B objective `f/s²` | Relative rank residual | Gauge-aligned timing RMSE | Final scaled step | Evaluations | Runtime | Optimizer result |
|---|---:|---:|---:|---:|---:|---:|---|
| Zero-start repeat | 3.6626e-12 | 1.7363e-7 | 0.2131 ms | 8.4032e-6 | 1,645 | 0.56 s | ftol success; BatSight gates fail |
| Seed 2 | 2.6416e-12 | 7.5957e-8 | 8.7866 ms | 2.7803e-5 | 11,340 | 3.37 s | ftol success; BatSight gates fail |
| Seed 3 | 3.6664e-13 | 1.0388e-8 | 11.3692 ms | 2.7535e-6 | 1,085 | 0.40 s | ftol success; BatSight gates fail |

Seed 3 reached a rank residual near `1e-8` while its aligned timing RMSE was over `11 ms`; seed 2 also reached a very small rank residual with a substantially incorrect timing vector. This directly fails the criterion that low rank residual cannot accompany incorrect timing. Final cutoff gaps remained open for these runs (`sigma_3` about `2.42e-4` and `2.02e-4 s²`, respectively, versus `sigma_4` about `1.25e-10` and `4.66e-11 s²`), so their wrong timing estimates were not caused by a final SVD cutoff tie. The large variation in timing recovery across starts shows the nonconvex basin sensitivity despite deterministic, finite, reproducible diagnostics.

### Finding and decision

The direct objective is mathematically the reduced rank-constrained objective underlying exact alternating projection and timing minimization, and its first-order stationarity agrees with the alternating fixed-point condition at regular points with a unique rank-3 projection. This is a mathematical relation, not evidence of equal convergence behavior or correct timing identification. In the controlled fixture, direct optimization reached much smaller rank residuals, but the timing errors remained far outside the required tolerance and varied sharply across starts. Solver success by objective reduction did not meet the original step/gradient gates. Therefore this proposal is **not accepted** as the Phase 5C timing optimizer. No production code or localization module was added; the experiment was run as an ephemeral script only. The Phase 5C blocker remains open, and the approved coordinate-recovery method is unchanged.

## Phase 5C.3: Timing identifiability and observability

### Setup and generating solution

The exact Phase 5C noiseless fixture was regenerated from seed 11 with the same `(8,7,5) m` room, `c=343 m/s`, `M=5`, `N=13`, random source/microphone coordinates, emission-time and microphone-offset vectors, zero timing noise, and `[microphone, source]` TOA orientation. The corrected model and four-term matrix conventions above were kept unchanged. Timing is represented in the gauge `e_1=0`: add the original first emission time to every clock offset and subtract it from every emission time.

At the gauge-adjusted generating vector, the corrected matrix `X` has singular values

`[7.32024478e-4, 3.82731492e-4, 1.01017911e-4, 2.05140806e-19] s²`.

Thus its relative rank-3 residual is `2.47e-16`, and the cutoff gap `sigma_3-sigma_4` is `1.01018e-4 s²` (`sigma_3/sigma_4` about `4.92e14`). The fixture's generating timing vector produces the expected rank-3 matrix to floating-point precision.

### Local Jacobian of the discarded matrix residual

At an exact rank-3 point, the scalar residual `sigma_4(X(p))` is not a useful ordinary Jacobian residual: it is zero and behaves locally like the norm of a normal perturbation, so it has a cusp at zero. Instead, the observability calculation uses the full discarded-matrix residual

\[
r(u)=\operatorname{vec}(X(u)-X_3(u))/s,\qquad u=p/t_{scale},\quad s=t_{scale}^2,
\]

and central finite differences `J[:,k]=(r(u+h e_k)-r(u-h e_k))/(2h)`. Here `r` is a 48-vector and there are 17 gauge-fixed timing parameters. Both residual and parameter coordinates are dimensionless. Multiplying residuals or changing parameter scales multiplies/rescales Jacobian columns and changes their numerical singular values and condition number, but does not change exact Jacobian rank under nonsingular scaling. This normalization is needed to interpret weak directions numerically.

The rank-3 matrix variety in `R^(4x12)` has codimension `(4-3)(12-3)=9`. At a point with a strict rank cutoff, the differential of `X-X_3` lies in the 9-dimensional normal space. The finite-difference Jacobian therefore has at most nine mathematically nonzero singular values. The nine stable values here are approximately

`[1.00872, 0.104200, 0.102447, 0.0556644, 0.0475423, 0.0257175, 0.0235251, 0.0226648, 0.0147946]`.

With the explicit numerical diagnostic threshold `sigma_j > 1e-6 sigma_1` (a BatSight analysis threshold, not a paper value), the effective rank is 9 and the first-order nullity is 8. The observable-subspace condition ratio `sigma_1/sigma_9` is about 68.2. A stable eight-dimensional right-nullspace is present; its directions combine clock offsets and emission times rather than isolating one single parameter. Representative largest coefficients of the null vectors, in parameter order `[o_1..o_5,e_2..e_13]`, include offset/emission mixtures `(o_2,o_3,e_9)`, `(o_5,o_4,e_2)`, and emission-dominated mixtures involving `e_5,e_8,e_11,e_12,e_13`. Signs of singular vectors are arbitrary.

The last eight computed singular values are finite-difference artifacts, not evidence for additional observable directions. The largest of them changes from `2.23e-7` at `h=1e-3`, to `2.24e-9` at `1e-4`, `1.02e-9` at `1e-5`, `8.70e-9` at `1e-6`, and `7.93e-8` at `1e-7`; the leading nine values and their subspace remain stable. Comparing the estimated eight-dimensional null subspaces from `h=1e-3` through `1e-7` gave maximum principal-angle differences below `2e-5` degrees. At very small steps, cancellation and SVD roundoff dominate the nominally zero singular values. The scalar `sigma_4` central-difference Jacobian norm also shrank approximately proportionally to `h`, consistent with its non-differentiability at zero rather than a meaningful rank-9 constraint derivative.

### Exact alternative timing vectors under rank alone

The local nullity was checked with an exact rank-constraint chart, rather than treating small first-order directions as exact alternatives. For a `4x12` matrix, choose any nonsingular `3x3` pivot block and permute rows/columns to write `X=[[P,Q],[L,D]]`. In that chart, `rank(X)<=3` exactly when the `1x9` Schur complement `D-L solve(P,Q)` is zero. This is an algebraic rewrite of the rank condition, not an added physical assumption. A well-conditioned pivot block (condition number 2.08) was selected at the generating point. The finite-difference Jacobian of the nine Schur-complement equations has nine singular values from `2.438` down to `0.0275`, hence rank 9. The implicit function theorem then predicts a local rank-feasible timing set of dimension `17-9=8`, provided this Jacobian rank remains locally constant. The numerical continuation below confirms that prediction for several perturbations.

For each test, one dimensionless coordinate along a right-null direction was fixed to `alpha`, and the nine observable coordinates were solved to make the exact Schur complement zero. The maximum scaled Schur residual was below `2e-13` for the reported roots. This is an isolated equation-solving diagnostic, not a production optimizer or a proposed timing method.

| Rank-only candidate | Null direction / `alpha` | Gauge-aligned timing RMSE | `X` singular values (s²) | Relative rank residual | Minimum corrected TOF | Rank/positivity | Crocco quadratic test |
|---|---:|---:|---|---:|---:|---|---|
| Generating vector | — | 0 | `7.320e-4, 3.827e-4, 1.010e-4, 2.05e-19` | 2.47e-16 | positive | Exact rank 3; positive | Not run |
| Alternative 1 | 1 / 0.1 | 0.213 ms | `7.438e-4, 3.937e-4, 9.978e-5, 6.94e-20` | 8.20e-17 | 1.783 ms | Exact rank 3; positive | Not run; physical validity unverified |
| Alternative 2 | 1 / 0.5 | 1.084 ms | `7.964e-4, 4.378e-4, 9.544e-5, 6.48e-20` | 7.09e-17 | 1.233 ms | Exact rank 3; positive | Not run; physical validity unverified |
| Alternative 3 | 1 / 1.0 | 2.235 ms | `8.808e-4, 4.830e-4, 9.122e-5, 1.17e-17` | 1.16e-14 | 0.699 ms | Exact rank 3; positive | Not run; physical validity unverified |

All alternatives retain `e_1=0`, are finite, and have strictly positive corrected direct-path TOFs. They are **exact alternatives to the rank constraint**, not merely low-residual approximations. Before the Schur-complement correction, raw perturbations along a null direction gave relative rank residuals about `1.6e-5`, `1.7e-7`, and `1.7e-9` for dimensionless amplitudes `0.1`, `0.01`, and `0.001`; the correction step then moved the observable components to make the nine constraints zero to solver precision. These checks do not certify that their corrected full distance matrices satisfy Crocco's quadratic coordinate-recovery constraints; their physical realizability as alternate complete microphone/source configurations remains unverified. A more distant continuation along a second null direction at `alpha=0.5` failed to converge, so the observed continuation is local and does not characterize the entire feasible set.

For comparison, previously tested direct rank-residual optimizer candidates were recomputed and checked for propagation-time positivity:

| Start | Relative rank residual | Timing RMSE after gauge | `X` singular values (s²) | Minimum corrected TOF | Positivity | Crocco quadratic test |
|---|---:|---:|---|---:|---|---|
| Zero | 1.736e-7 | 0.213 ms | `7.494e-4, 3.832e-4, 1.045e-4, 1.473e-10` | 2.022 ms | Pass | Not run; physical validity unverified |
| Seed 2 | 7.596e-8 | 8.787 ms | `1.316e-3, 9.596e-4, 2.423e-4, 1.251e-10` | -25.516 ms | Fail | Not run; also rejected by positivity |
| Seed 3 | 1.039e-8 | 11.369 ms | `4.337e-3, 1.124e-3, 2.023e-4, 4.659e-11` | -40.105 ms | Fail | Not run; also rejected by positivity |

The direct optimizer's extremely small residuals therefore do not identify valid timing parameters. The two seeded endpoints are not valid propagation solutions even before coordinate recovery; the zero-start endpoint is physically positive but remains an approximation with nontrivial timing error.

### Rank-only versus full coordinate identifiability

**Source-derived distinction:** a rank-3 factorization gives an arbitrary invertible factor `C`; it is not itself a Euclidean coordinate reconstruction. Crocco et al.'s general method adds squared-distance quadratic constraints (journal Eqs. (10)–(12)); the BatSight-approved form is `g_ij(C,alpha)=||r_i||²-2 r_i^T s_j-(d_ij²-d_1j²)` from `docs/reference_derived_localization_design.md`. Those constraints tie the bilinear factors to the individual corrected ranges. They must remain in any claim about complete geometry/timing consistency. Rank-three alone also does not enforce positive corrected TOFs. See Crocco, Del Bue & Murino, [“A Bilinear Approach to the Position Self-Calibration of Multiple Sensors,” IEEE TSP 2012](https://doi.org/10.1109/TSP.2011.2175387).

**BatSight local check:** after fixing six Euclidean coordinate gauges (`m_1` at the origin, `m_2` on the positive x-axis, `m_3` in the xy-plane) and the shared timing gauge, the original noiseless TOA model has 65 observations and 65 unknown coordinate/timing parameters for this minimum-count fixture. This matches the necessary sample-count threshold derived in [7] (`M=5,N=13`), which is not by itself a sufficient geometric condition. The analytic measurement Jacobian uses `∂t_ij/∂m_i=(m_i-s_j)/(c||m_i-s_j||)`, `∂t_ij/∂s_j=(s_j-m_i)/(c||m_i-s_j||)`, and unit derivatives for the associated offset and emission time. After scaling coordinate increments by `5 m`, timing increments by `t_scale`, and residuals by `t_scale`, the complete range-plus-timing Jacobian has rank 65 at the random 3D fixture under a relative `1e-8` singular-value threshold; its condition number is `4.38e4`. This supports local identifiability of the *full* measurement model for this fixture, not global uniqueness. It shows why the extra coordinate/range constraints can add information absent from the timing-only rank condition. The exact rank-only alternatives above have not been passed through the approved coordinate-recovery objective, so no conclusion is made about whether they survive those constraints.

### Geometry comparison

The second deterministic case reused the same `x,y` coordinates and timing values but set every microphone and source `z=2.5 m`, creating an exactly planar (degenerate for 3D) configuration.

| Geometry | `X` singular values (s²) | Rank-3 cutoff | Discarded-residual Jacobian | Full gauge-fixed TOA Jacobian |
|---|---|---|---|---|
| Random 3D fixture | `7.320e-4, 3.827e-4, 1.010e-4, 2.05e-19` | Clear gap; rank exactly 3 | Stable effective rank 9; eight timing-null directions | 65/65 at relative threshold `1e-8`; condition `4.38e4` |
| Exact planar fixture | `7.423e-4, 4.005e-4, 1.16e-19, 6.45e-20` | `sigma_3` and `sigma_4` both numerical zero; no 3D cutoff gap | SVD residual Jacobian is not interpretable as a smooth local derivative; finite-difference singular values are roundoff-dominated and step-dependent | 50/65 at relative threshold `1e-8`; condition about `2.24e19` |

The planar case confirms that rank at most three does not establish three-dimensional observability. Since it is rank at most two, the rank-3 SVD subspace is nonunique at the cutoff and the derivative test is not stable; the full range Jacobian independently loses out-of-plane directions. This is a geometric degeneracy, not evidence about generic 3D timing uniqueness.

### Finding and remaining uncertainty

**Answer to the core question:** no. After fixing the timing gauge, the rank-three constraint does **not** uniquely identify the generating timing vector for the `M=5,N=13` fixture. The matrix has only nine independent rank constraints locally, while there are 17 timing variables; an eight-dimensional exact local family of rank-three timing solutions was both predicted by the rank-9 Jacobian and confirmed with exact Schur-complement solves. Several alternatives have positive corrected propagation times and materially different timing values.

This does not establish that all these alternatives correspond to valid Euclidean microphone/source configurations. The source-derived quadratic coordinate-recovery constraints are additional necessary checks, and the full gauge-fixed TOA Jacobian is locally full rank for the generic fixture. Thus the complete model may locally isolate the generating timing and geometry even though the rank-only subproblem cannot. The exact number of rank-only alternatives that survive Crocco's metric constraints, and global uniqueness of the complete noiseless solution, remain unknown. No alternative optimizer is proposed or accepted, no production code was added, and the approved coordinate-recovery formulation is unchanged.

## Phase 5C.4: Metric consistency of rank-only timing solutions

### Parameterization correction

The approved factor parameterization is now nonredundant:

`C=L0 exp(ell) D_delta R(omega) exp(H(h))`, where `delta∈{-1,+1}`, `R∈SO(3)`, and `H` is symmetric traceless with five independent Frobenius-orthonormal coefficients. The continuous factor has `1+3+5=9` degrees of freedom, matching `GL(3)`; the anchor adds one more scalar. This replaces the redundant six-entry symmetric `H` plus separate scale design. By polar decomposition, any invertible `C` belongs to one of the two determinant branches: take `C=QP`, `delta=sign(det Q)`, `R=D_delta Q`, `L0 exp(ell)=(det P)^(1/3)`, and `H=log(P/(det P)^(1/3))`. Thus the only excluded invertible factors are those beyond the explicit numerical condition cap.

Because the orthogonal and scalar factors do not affect the 2-norm condition number, `cond_2(C)=exp(lambda_max(H)-lambda_min(H))`. The cap `kappa_max` is enforced by `lambda_max(H)-lambda_min(H) <= log(kappa_max)`, rather than a coordinate box. The cap values/progression in the design remain proposed engineering settings, not paper parameters. Both determinant branches are optimized independently. Coordinate recovery computes the inverse-factor action with a checked linear solve, never an explicit inverse. This analytic parameterization coverage and condition identity were checked against synthetic factors of each determinant sign and varying condition; the Phase 5C.4 coordinate fixture below additionally exercises both branches.

### Experiment method and acceptance rule

This is an isolated deterministic diagnostic in `experiments/exploratory/phase5c4_metric_consistency.py`, not production localization code. It uses the exact seed-11 `M=5,N=13` fixture and regenerates the three Schur-complement rank-only roots and three direct-rank starts (zero, seed 2, seed 3). The earlier ephemeral candidate vectors were not archived; the latter are deterministic reruns of the recorded optimizer recipe, so their displayed direct-rank endpoint values are regenerated values and not a bitwise comparison against unavailable vectors.

For positive corrected TOAs, the experiment computes pairwise distances `d_ij=c*tau_ij`, the four-term corrected double-difference matrix and its truncated rank-3 SVD, then fits Crocco's general coordinate objective `g_ij=||r_i||^2-2 r_i^T s_j-(d_ij^2-d_1j^2)`. It optimizes both `delta` branches with SLSQP, checked solves, the design's condition cap `1e8`, and deterministic multi-starts (four starts per branch for alternatives; five for the generating positive control). The objective is the squared Frobenius norm of `g/L0^2`; reported `||g||_F` and `max|g_ij|` are in m². Optimizer success is recorded separately from metric acceptance.

For this numerical fixture, the prespecified diagnostic acceptance threshold is `max|g_ij| <= 1e-6 m²`, alongside finite coordinates, valid condition cap, positive corrected TOFs, and successful optimizer status. This is an engineering tolerance chosen relative to the roughly 10–100 m² squared-distance scale; it is not a tolerance from Crocco or the 2016 paper. The generating positive control passes both branches by more than an order of magnitude. A second oracle-start sensitivity run with finite-difference step `1e-7` was also performed; it reduced residuals consistently and left aligned errors at approximately 1e-9 m.

### Results

| Candidate | Rank residual of `X` | Timing RMSE after gauge (ms) | Min corrected TOF (ms) | Best branch | Best `||g||_F` (m²) | Best `max|g|` (m²) | Factor condition | Metric gate |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| Generating truth | 2.85e-16 | 0 | -1 | `delta=-1` | 4.40e-7 | 9.15e-8 | 5.83 | Pass |
| Exact Schur alternative 1 | 1.21e-16 | 0.213 | 1.783 | `delta=+1` | 2.54e-4 | 5.19e-5 | 1.31e3 | Fail |
| Exact Schur alternative 2 | 2.02e-16 | 1.084 | 1.233 | `delta=-1` | 4.00e-4 | 8.33e-5 | 1.08e4 | Fail |
| Exact Schur alternative 3 | 1.16e-14 | 2.235 | 0.699 | `delta=-1` | 4.21e-4 | 9.69e-5 | 7.15 | Fail |
| Direct optimizer, zero start | 7.22e-8 | 0.213 | 2.022 | `delta=+1` | 1.57e-4 | 3.90e-5 | 8.54 | Fail |
| Direct optimizer, seed 2 | 7.60e-8 (prior run) | 8.787 (prior run) | -24.844 (regenerated) | — | — | — | — | Rejected: nonpositive TOF |
| Direct optimizer, seed 3 | 1.04e-8 (prior run) | 11.369 (prior run) | -40.104 (regenerated) | — | — | — | — | Rejected: nonpositive TOF |

The positive control's fitted geometry, after the documented Euclidean gauge alignment, had microphone/source/combined RMS coordinate errors `1.42e-8 m`, `1.13e-8 m`, and `1.22e-8 m` on the `delta=-1` branch; the reflected `delta=+1` branch had `1.24e-8 m`, `1.50e-8 m`, and `1.43e-8 m`. Both branches had successful SLSQP exits and all deterministic starts terminated successfully. Their best objective values were `2.64e-15` and `2.74e-15`. The oracle-start step-size sensitivity run gave combined RMS errors `1.22e-9 m` and `1.43e-9 m` at `eps=1e-7`.

All three exact rank-only alternatives have strictly positive corrected TOAs and rank residuals near numerical precision, but their best coordinate-fit `max|g|` values exceed the positive-control residual by hundreds to over a thousand times and fail the stated metric gate. The zero-start direct candidate is also positive but fails the metric gate. Both sign branches and all stated starts returned optimizer success for these fits; that status only means SLSQP met its numerical termination condition. None of the alternative fits is accepted as a valid Euclidean reconstruction. The seed-2 and seed-3 regenerated direct candidates are rejected before coordinate fitting because corrected propagation TOAs are negative.

| Candidate | `delta=-1` best `max|g|` (m²) | `delta=+1` best `max|g|` (m²) | Starts successful / total per branch |
|---|---:|---:|---|
| Generating truth | 9.15e-8 | 7.98e-8 | 5/5, 5/5 |
| Exact alternative 1 | 7.99e-5 | 5.19e-5 | 4/4, 4/4 |
| Exact alternative 2 | 8.33e-5 | 1.73e-4 | 4/4, 4/4 |
| Exact alternative 3 | 9.69e-5 | 1.44e-4 | 4/4, 4/4 |
| Direct zero start | 8.15e-5 | 3.90e-5 | 4/4, 4/4 |

Best-branch optimizer diagnostics (all finite, condition-feasible, and `success=True`; no trial failures were reported):

| Candidate | Best `delta` | Normalized objective `sum((g/L0²)^2)` | `||g||_F` (m²) | `max|g|` (m²) | `cond_2(C)` | Starts / branch |
|---|---:|---:|---:|---:|---:|---:|
| Generating truth | -1 | 2.642e-15 | 4.401e-7 | 9.147e-8 | 5.828 | 5 |
| Exact alternative 1 | +1 | 8.122e-10 | 2.544e-4 | 5.191e-5 | 1.315e3 | 4 |
| Exact alternative 2 | -1 | 1.244e-9 | 4.003e-4 | 8.333e-5 | 1.082e4 | 4 |
| Exact alternative 3 | -1 | 1.023e-9 | 4.205e-4 | 9.693e-5 | 7.149 | 4 |
| Direct zero start | +1 | 3.285e-10 | 1.569e-4 | 3.904e-5 | 8.539 | 4 |

The experiment script prints each full gauge-fixed timing vector and corrected TOA matrix, as well as the branch-specific best-fit diagnostics. For the known control, the generating timing vector is `[2.99298324e-4, -5.24815943e-5, 2.46241312e-4, -2.60918753e-4, 5.43100772e-4, 4.77834782e-4, -6.65989920e-4, 3.06964829e-4, 3.01388417e-4, -8.83859289e-4, 1.73515051e-4, -1.25210673e-4, 3.90761348e-4, -2.19531094e-4, -9.12042882e-6, 1.71425759e-4, -4.38130844e-4] s`, with the documented first-microphone timing gauge applied. The experiment seed and generation are fixed in the script.

### Interpretation and remaining uncertainty

This establishes that the three tested exact rank-only alternatives and the regenerated positive zero-start direct candidate did not satisfy the Crocco metric constraints under the stated bounded multi-start searches. It supports the mathematical distinction between rank-3 factorization and Euclidean metric consistency. It does **not** prove that no other point in the eight-dimensional rank-only family satisfies those constraints, that SLSQP found each global coordinate minimum, or that the complete timing/geometry solution is globally unique. The separate full gauge-fixed measurement Jacobian result remains evidence only for local identifiability at the generating nondegenerate fixture. The current Phase 5C timing convergence blocker remains unresolved; no optimizer is accepted and no production engine was added.

## Remaining blockers before Phase 5C

- Determine which exact rank-only alternatives, if any, satisfy the approved Crocco quadratic coordinate-recovery constraints and positive-distance geometry simultaneously; the current rank roots are not complete physical solutions.
- Resolve the unregularized timing iteration's convergence and timing-recovery failure with a method that uses the full approved model and passes the preapproved gates; rank-only timing optimization is demonstrably insufficient.
- Validate coordinate recovery, gauge-aligned geometry errors, and full localization diagnostics only after the timing and observability issues are addressed. These remain unestablished.
- The Gaubitch Eq. (8) indexing/switch ambiguity remains documented if that continuation is reconsidered; the tested candidate-dependent interpretation is not accepted.

## Phase 5C.5: Direct Euclidean TOA joint-fit investigation

### Status and distinction from the paper

This is a BatSight exploratory alternative, implemented only in `experiments/exploratory/phase5c5_direct_euclidean_toa.py`. It directly minimizes the original observation residual

`r_ij = q_ij - e_j - ||s_j-m_i||/c - b_i`,

using `0.5 * sum_ij (r_ij/t_scale)^2`, with `t_scale=8.77191949225e-3 s`. Coordinates are scaled by `L_scale=5 m`; time parameters are scaled by `t_scale`. The solver is SciPy trust-region reflective `least_squares`, using an analytic Jacobian, Jacobian column scaling, tolerances `1e-13`, and `max_nfev=2500`. These solver choices are BatSight settings, not settings attributed to the papers. No rank-three residual is optimized.

The 2016 method is staged: timing correction/rank-3 projection, followed by distance-factor and coordinate recovery. This experiment instead optimizes all coordinates, emission times, and clock offsets jointly against raw direct-path TOAs. A successful local fit therefore neither reproduces the paper's prescribed initializer nor establishes a blind initialization method. It remains a separate nonlinear reconstruction alternative unless future evidence justifies using it as a local refiner after an independent initializer.

### Gauge derivation and dimensions

For a generic non-collinear microphone triplet, set `m_1=(0,0,0)`, `m_2=(a,0,0)` with `a>0`, and `m_3=(u,v,0)` with `v>0`. Translation fixes three continuous degrees of freedom; choosing the directed `m_1→m_2` baseline fixes two rotational degrees; requiring `m_3` to lie in the xy-plane fixes rotation about that baseline. The positive signs select a canonical orientation. Fixing `e_1=0` removes the continuous time-origin gauge: the transformation `e_j→e_j+k`, `b_i→b_i-k` otherwise leaves all observations invariant. This does not fix or remove physical shape parameters; it chooses representatives of the coordinate/time gauge orbits. A reflection through the xy-plane remains a discrete distance-preserving ambiguity and is treated as equivalent in coordinate-error alignment.

For `M=5,N=13`, the free microphone coordinates are `1+2+3(M-3)=9`; source coordinates contribute `3N=39`; clock offsets contribute `M=5`; and emission times other than `e_1` contribute `N-1=12`. There are therefore 65 unknowns for 65 direct-path TOA observations. This necessary count does not guarantee a unique or well-conditioned solution. The script's scaled full measurement Jacobian is evaluated at every fitted point; numerical rank uses singular values greater than `1e-8` times the largest singular value. The experiment's random 3D seed-11 point is full rank; the planar geometry is not.

The gauge parameterization uses logarithms for `a` and `v`, so those quantities remain strictly positive. All other coordinates and timing parameters are unconstrained. The objective imposes no shoebox-wall or inside-room bounds; corrected propagation times and finite, noncoincident positions are reported as physical diagnostics, not enforced by an undocumented penalty.

### Reproducible experiments

The original seed-11 fixture preserves the generated measured TOA matrix and room speed `343 m/s`; the raw generated coordinates are rigidly transformed into the stated coordinate gauge. The exact generating state is run first as a positive control. Perturbation starts add deterministic Gaussian perturbations with coordinate standard deviations `0.01`, `0.1`, or `0.5 m`; corresponding emission/clock perturbation standard deviations are `10`, `100`, or `500 microseconds`. Seeded blind runs then use: each of the three Phase 5C.4 exact rank-only timing vectors, the three Phase 5C.4 direct-rank optimizer timing vectors, zero timing, and two deterministic random coordinate starts. For these blind runs, only the timing portion is reused; coordinates are initialized independently without ground-truth positions. The direct-rank starts were regenerated from the Phase 5C.4 deterministic recipes and seeds; the exact historical endpoint vectors were not archived, so this is not a bitwise replay of those earlier endpoints.

Two transformed geometry cases use the same seed-11 point pattern and timing values but generate their own exact observations: (a) an exactly planar layout and (b) a deliberately flattened nonplanar layout with all canonical z coordinates multiplied by `0.01`. For each, the exact state and one deterministic `0.02 m / 20 microsecond` perturbation are tested. The latter is poorly conditioned relative to the random 3D case, not an arbitrary room model.

The script writes all per-run optimizer status, residual and coordinate/timing metrics, full 65-value Jacobian singular spectra, rank, condition number, positivity diagnostic, and scaled starting/final parameters to `experiments/exploratory/phase5c5_results.json`. Runtime varies by machine and is recorded per run. Coordinate errors use a joint rigid alignment over microphones and sources with reflection allowed; timing errors are computed after the fixed `e_1=0` gauge.

### Results

| Geometry / start | Residual norm (s) | Max residual (s) | Coordinate combined RMSE (m) | Emission RMSE (s) | Clock RMSE (s) | Jacobian rank / condition | nfev | Runtime (s) | Outcome |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| Seed-11 / oracle exact | 7.99e-17 | 2.79e-17 | 1.31e-15 | 0 | 0 | 65 / 4.08e4 | 1 | 0.002 | Positive control |
| Seed-11 / perturb 0.01 m, 10 us | 1.52e-17 | 7.97e-18 | 6.59e-13 | 2.16e-15 | 5.78e-16 | 65 / 4.08e4 | 6 | 0.010 | Recovered |
| Seed-11 / perturb 0.1 m, 100 us | 1.75e-17 | 6.40e-18 | 1.38e-13 | 8.46e-16 | 5.68e-16 | 65 / 4.08e4 | 87 | 0.142 | Recovered |
| Seed-11 / perturb 0.5 m, 500 us | 1.58e-17 | 4.99e-18 | 1.36e-12 | 5.32e-15 | 2.23e-15 | 65 / 4.08e4 | 93 | 0.138 | Recovered |
| Blind exact rank alt 1 + blind coordinates | 6.92e-5 | 2.48e-5 | 2.23 | 4.79e-3 | 1.48e-3 | 65 / 3.98e4 | 2500 | 4.59 | Budget exhausted; min corrected TOA slightly negative |
| Blind exact rank alt 2 + blind coordinates | 5.38e-6 | 3.00e-6 | 5.62 | 1.20e-2 | 1.13e-2 | 64 / 4.85e11 | 1221 | 2.23 | ftol success, but wrong and ill-conditioned geometry |
| Blind exact rank alt 3 + blind coordinates | 9.11e-6 | 3.84e-6 | 46.5 | 3.81e-3 | 2.63e-1 | 64 / 1.88e8 | 2500 | 4.62 | Budget exhausted; wrong geometry |
| Blind direct-rank zero + blind coordinates | 1.38e-5 | 5.21e-6 | 29.0 | 1.01e-1 | 2.41e-2 | 65 / 6.88e6 | 2500 | 4.07 | Budget exhausted; wrong geometry |
| Blind direct-rank seed 2 + blind coordinates | 1.42e-5 | 6.12e-6 | 641 | 2.26 | 2.57e-3 | 64 / 9.15e9 | 2500 | 4.20 | Budget exhausted; wrong geometry |
| Blind direct-rank seed 3 + blind coordinates | 1.55e-4 | 6.57e-5 | 442 | 0.742 | 2.75 | 62 / 1.57e15 | 2500 | 3.56 | Budget exhausted; wrong, severely ill-conditioned geometry |
| Blind zero timing + blind coordinates | 3.35e-5 | 1.51e-5 | 54.0 | 0.164 | 0.118 | 65 / 9.55e7 | 2500 | 4.72 | Budget exhausted; wrong geometry |
| Blind random coordinates, seed 11 | 7.13e-5 | 4.04e-5 | 11.8 | 2.91e-3 | 6.19e-2 | 64 / 2.26e10 | 2500 | 3.93 | Budget exhausted; wrong geometry |
| Blind random coordinates, seed 29 | 4.22e-5 | 2.22e-5 | 21.9 | 2.94e-2 | 7.40e-2 | 65 / 1.97e6 | 2500 | 3.75 | Budget exhausted; wrong geometry |
| Planar / oracle exact | 6.06e-18 | 3.36e-18 | 7.32e-16 | 0 | 0 | 50 / 3.53e19 | 1 | 0.002 | Zero residual but degenerate |
| Planar / perturb 0.02 m, 20 us | 5.07e-16 | 2.67e-16 | 3.92e-7 | 1.16e-15 | 1.25e-15 | 54 / 2.65e9 | 22 | 0.040 | Near-planar numerical solution; deficient/weak directions |
| Flattened nonplanar / oracle exact | 1.04e-17 | 6.83e-18 | 1.22e-15 | 0 | 0 | 65 / 7.29e5 | 1 | 0.001 | Positive control |
| Flattened nonplanar / perturb 0.02 m, 20 us | 2.55e-17 | 1.26e-17 | 7.07e-4 | 1.00e-7 | 1.92e-7 | 65 / 7.81e5 | 116 | 0.173 | Recovered locally, increased error/conditioning |

At the main seed-11 positive control, the scaled Jacobian's largest singular value was `6.2503` and smallest was `1.5320e-4`; all 65 singular values exceed the experiment's relative rank threshold. On the planar oracle, rank drops to 50 and the smallest singular value is `1.85e-19`. The perturbed planar run can acquire small nonzero out-of-plane estimates from numerical optimization, so its thresholded rank is 54 rather than the exact geometry's 50; its condition number remains about `2.65e9`. The flattened nonplanar Jacobian remains full rank but its condition number rises to about `7.3e5` at truth and `7.8e5` after local fitting. The blind runs' low residual values in some cases do not imply recovery: they can coincide with large coordinate/timing errors and severe Jacobian ill-conditioning.

The analytic Jacobian was checked against central finite differences over all 65 scaled parameters at the seed-11 truth (`h=1e-6`): maximum absolute element discrepancy was `2.42e-10`, and relative Frobenius discrepancy was `7.33e-11`. The full singular spectra and per-run maxima for timing errors, exact optimizer status, and evaluation counts are in the JSON artifact; the table rounds runtimes to milliseconds and residual summaries for readability.

The optimizer status is not used as a success criterion by itself. For example, blind exact alternative 2 terminated on `ftol` while retaining a `5.62 m` combined coordinate error, `11.96 ms` emission RMSE, and rank 64/65. Other blind runs exhausted their evaluation budget. None of the tested blind starts recovered the generating solution. Conversely, all tested local perturbations of the known state converged to it on the nondegenerate geometry; that demonstrates local recoverability in this fixture, not a known basin size or global uniqueness.

### Interpretation and implementation decision

The direct Euclidean TOA objective can recover the known seed-11 configuration locally under this gauge, with a full-rank Jacobian and very small residuals. The nondegenerate fixture is moderately conditioned; the planar case demonstrates exact geometric non-identifiability; the flattened case demonstrates sensitivity despite nominal full rank. The blind results do not support this objective as a practical standalone initializer from timing-only candidates or random coordinates. A future study may evaluate it as a local refinement when a defensible independent initializer exists, but that use is not accepted here. This experiment neither changes the paper-derived staged design nor resolves its convergence blocker.

No global uniqueness claim is made. The finite start set cannot exclude distant minima, and full local Jacobian rank is only a local statement. The synthetic experiment is noiseless and direct-path-only; it says nothing about reverberation, TOA errors, room plane assignment, or real-world performance.

## Phase 5C.6: Blind initialization research

### Research objective and scope

This investigation asks whether a deterministic starting state can be constructed from measured TOAs `q`, known `c`, and the stated timing model, without using room dimensions or any ground-truth positions/times. The exploratory optimizer remains the direct objective `r_ij=q_ij-e_j-||s_j-m_i||/c-b_i`; clocks and emissions remain free throughout every fit. A zero timing vector is only a numerical start and is not a synchronization assumption.

The sources do not prescribe the direct joint-fit strategy or a general blind initializer for it. The paper-derived equations remain unchanged: Gaubitch's timing correction and rank-3 SVD can provide corrected-distance and bilinear-factor candidates; the general Crocco constraints can attempt to turn corrected cross distances into Euclidean coordinates. BatSight's tested pipeline composes these as an initializer, then uses the Phase 5C.5 direct TOA objective as a separate refinement. The Cross-distance SVD/Crocco stage is not credited as a solution when its own metric residual gate fails.

### Candidate approaches and remaining ambiguity

Here `[7]` denotes Gaubitch et al. (2013) and `[28]` denotes Crocco et al. (2012) under the 2016 preprint's bibliography numbering, as documented in the Phase 5A/5B research audit.

| Candidate | What it can initialize from TOAs | What it cannot establish by itself |
|---|---|---|
| Approved Gaubitch timing correction | Timing vector candidates through alternating bilinear correction and rank-3 projection; corrected distances follow if every corrected TOA is positive | Rank-only timing has multiple solutions on the minimum-count fixture; slow or nonconverged timing is possible; rank 3 does not guarantee metric consistency |
| Rank-3 SVD factors | Three-dimensional bilinear subspaces/factors of the double-differenced squared-distance matrix, after a timing candidate is supplied | SVD factors are defined only up to an invertible `3x3` factor; no Euclidean scale/shape/coordinates or timing recovery without further constraints |
| Crocco general metric constraints | A candidate Euclidean coordinate set from a complete corrected cross-distance matrix, using the approved `g_ij(C,alpha)` objective | Depends on timing candidate; nonconvex factor fit can terminate at a poor metric fit; its squared-distance objective is not the direct TOA objective |
| Algebraic cross-distance reconstruction | Given candidate corrected distances, four-term differencing removes the separate squared-norm terms and yields a rank-at-most-3 cross-Gram matrix; SVD plus metric constraints is a cross-distance analogue of MDS | It cannot create corrected distances from raw `q` without handling `e,b`; arbitrary rank-3 factorization is not metric consistency |
| Classical MDS | Could initialize coordinates if within-microphone or within-source distances were available | The dataset has only cross-array TOAs, and clock/emission terms are unknown; standard complete pairwise-distance MDS is not directly applicable. The tested cross-Gram route is the relevant algebraic analogue |
| Structured multistart | Deterministic coordinate clouds at a TOA-derived scale, with candidate timing starts, can sample several basins reproducibly | No guarantee of basin coverage or recovery; direct optimization can drive points far away or become ill-conditioned |

The full measurement Jacobian rank `65/65` at the seed-11 solution is a local observability result. It neither proves global uniqueness nor provides a basin-finding method. Phase 5C.6 also found a numerically distinct full-rank, machine-precision solution from the Gaubitch-derived start (coordinate error about `0.524 m`, with different timing parameters). This is strong numerical evidence for a second isolated solution of the unconstrained Euclidean TOA model on this fixture; it is not a symbolic proof of an exact second root. Without known room bounds or additional physical constraints, TOA equality alone cannot select the generating configuration from such a pair.

### Initialization-only versus optimizer configuration

Every initializer below receives only `(q,c,M,N)` (and fixed engineering seed/settings). Evaluation routines receive truth only after a candidate is formed. The seed-11 generation still uses its original deterministic synthetic shoebox, but its dimensions and true coordinates are not passed to an initializer. Its raw measured TOA matrix is unchanged; truth positions are rigidly transformed into the required gauge only for scoring.

The blind random baseline samples coordinates in a cube whose half-width is the TOA-derived characteristic length `L0=c*median(|q|)`; this replaces the Phase 5C.5 room-sized blind box and does not encode room dimensions. The structured baseline uses deterministic unscrambled Halton coordinate clouds at `0.5 L0`, `L0`, and `2 L0`. For both, initial offsets/emissions are zero but are optimized freely. The data-driven algebraic initializer uses zero timing, forms provisional cross distances `d_ij=c q_ij`, factors their four-term squared-distance matrix with rank-3 SVD, and runs both Crocco determinant branches. A direct-rank candidate instead estimates timing from q only, then uses the same SVD/Crocco coordinate stage. The approved alternating timing initializer uses 100 unregularized Gaubitch outer updates from zero, then the same coordinate stage. These are experimental combinations, not source-prescribed initialization rules.

All direct fits use the same Phase 5C.5 optimizer configuration and this study's strict noiseless recovery gates: SciPy trust-region reflective least squares, validated analytic Jacobian, objective `0.5 sum((r_ij/t_scale)^2)`, `x_scale='jac'`, `ftol=xtol=gtol=1e-13`, and `max_nfev=2500`. For noisy and larger cases, all starts in the same case share a reduced evaluation cap of 500 and 300 respectively; those budgets are recorded and are not treated as successful recovery gates. Coordinate error is evaluated after joint Euclidean alignment with reflection allowed. Timing errors use `e_1=0`. Full initial/final position and timing errors, residuals, complete Jacobian spectra, rank/condition, status, evaluations, runtime, and scaled parameter vectors are saved in `experiments/exploratory/phase5c6_results.json`.

For this study, explicit strict noiseless recovery gates are: aligned combined coordinate RMSE `<=1e-6 m`, emission and clock maximum absolute errors `<=1e-8 s`, maximum TOA residual `<=1e-12 s`, finite noncoincident coordinates, positive corrected propagation TOAs, and full gauge-fixed Jacobian rank. A solver success flag or low TOA residual alone does not pass this gate. The noisy case is descriptive; it is not judged against exact-zero noiseless tolerances.

The generalized Phase 5C.6 analytic Jacobian was checked against central finite differences over every parameter at truth on both the `M=5,N=13` and `M=8,N=20` fixtures, using `h=1e-6`. Relative Frobenius discrepancies were `9.67e-11` and `8.92e-11` (maximum absolute element discrepancies `3.95e-10` and `5.56e-10`).

### Seed-11 noiseless comparison

The data-derived zero-timing/Crocco initializer produced initial aligned coordinate RMSE `12.999 m`, emission RMSE `0.403 ms`, clock RMSE `0.321 ms`, and raw TOA residual norm `0.3384 s`. Despite its large initial errors and Crocco metric residual `0.302 m²` (rank residual `3.15e-3`), direct refinement converged to the generating configuration within numerical precision. Re-running the Crocco fit with three deterministic multistart seeds returned the same starting state and same successful direct-fit endpoint. Two deterministic perturbations of that data-derived starting state, `0.1 m/100 us` and `0.5 m/500 us`, also passed all noiseless recovery gates. Thus this is a repeatable initializer for this fixture and these local perturbations, not a general guarantee.

| Initializer | Initial coordinate RMSE (m) | Initial emission / clock RMSE (ms) | Initial TOA norm (s) | Final coordinate RMSE (m) | Final emission / clock RMSE (ms) | Final TOA norm (s) | Rank / condition | Status; nfev; runtime (s) |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| Zero timing + Crocco, seed 5 | 12.999 | 0.403 / 0.321 | 3.384e-1 | 1.79e-13 | 4.12e-13 / 2.81e-13 | 2.104e-17 | 65 / 3.91e4 | success; 971; 1.82 |
| Zero timing + Crocco, seed 2 | 12.999 | 0.403 / 0.321 | 3.384e-1 | 1.79e-13 | 4.12e-13 / 2.81e-13 | 2.104e-17 | 65 / 3.91e4 | success; 971; 1.80 |
| Zero timing + Crocco, seed 11 | 12.999 | 0.403 / 0.321 | 3.384e-1 | 1.79e-13 | 4.12e-13 / 2.81e-13 | 2.104e-17 | 65 / 3.91e4 | success; 971; 1.63 |
| Crocco zero-timing state + `0.1 m/100 us` perturbation | 13.015 | 0.354 / 0.348 | 3.384e-1 | 6.14e-13 | 2.47e-12 / 1.42e-12 | 2.436e-16 | 65 / 3.91e4 | success; 729; 1.51 |
| Crocco zero-timing state + `0.5 m/500 us` perturbation | 13.042 | 0.852 / 0.424 | 3.391e-1 | 2.58e-13 | 5.69e-13 / 6.45e-13 | 1.477e-17 | 65 / 3.91e4 | success; 773; 2.79 |
| Direct-rank zero timing + Crocco | 6.509 | 0.188 / 0.251 | 1.630e-1 | 4.795 | 11.539 / 6.458 | 2.465e-6 | 64 / 1.25e11 | success but failed recovery; 906; 1.58 |
| Gaubitch timing, 100 iterations + Crocco | 7.122 | 0.396 / 0.253 | 1.758e-1 | 0.524 | 1.807 / 0.732 | 1.978e-17 | 65 / 9.18e4 | success, distinct fit; 330; 0.58 |
| Blind random, seed 11 | 3.620 | 0.403 / 0.321 | 7.922e-2 | 28.057 | 63.557 / 117.512 | 3.975e-5 | 65 / 7.79e6 | max evaluations; 2500; 13.77 |
| Blind random, seed 29 | 3.814 | 0.403 / 0.321 | 7.624e-2 | 140.372 | 798.934 / 1340.938 | 9.832e-5 | 64 / 6.95e8 | max evaluations; 2500; 4.88 |
| Halton structured, `0.5 L0` | 2.468 | 0.403 / 0.321 | 5.052e-2 | 10.393 | 2.927 / 52.691 | 8.971e-5 | 65 / 1.15e6 | max evaluations; 2500; 6.74 |
| Halton structured, `L0` | 3.026 | 0.403 / 0.321 | 7.159e-2 | 57.401 | 14.492 / 320.566 | 5.111e-5 | 64 / 2.73e8 | max evaluations; 2500; 5.99 |
| Halton structured, `2 L0` | 5.594 | 0.403 / 0.321 | 2.303e-1 | 123.509 | 426.770 / 44.271 | 5.657e-4 | 63 / 1.46e12 | max evaluations; 2500; 4.95 |
| Oracle positive control | 1.37e-15 | 0 / 0 | 8.13e-17 | 1.37e-15 | 2.71e-17 / 3.03e-18 | 8.13e-17 | 65 / 3.91e4 | success; 1; 0.001 |

The Gaubitch-derived endpoint's final minimum corrected propagation TOA is positive (`2.692 ms`); it is not rejected as nonphysical by the direct model. Its machine-precision residual and full Jacobian rank, combined with `0.524 m` aligned geometry error and millisecond timing errors, demonstrate why the full-rank local Jacobian at the truth cannot guarantee global uniqueness. The direct-rank seed-2 and seed-3 timing candidates had negative corrected TOAs and were rejected before coordinate fitting; the metadata records their minima. The direct-rank seed-0 candidate passed the positivity check, but its coordinate residual had already failed Crocco's Phase 5C.4 gate and the subsequent direct joint fit remained inaccurate.

### Noisy and larger-observation cases

The noisy fixture adds deterministic independent Gaussian TOA noise with standard deviation `20 us` (seed `116`) to the exact seed-11 matrix. With 500 evaluations, none of its nine blind/data-derived starts met the noiseless recovery gate; their final coordinate errors ranged from about `6.72 m` to `350.6 m`, and final residual norms from `4.97e-5 s` to `2.09e-3 s`. The oracle-start noisy fit stopped successfully but shifted by `0.943 m` aligned coordinate RMSE and had Jacobian rank `64/65` under the selected relative threshold. This is evidence of sensitivity for this minimum-count noisy case, not a general noise threshold.

The larger deterministic case has `M=8,N=20`, 160 observations, and 105 gauge-fixed unknowns. One of two blind TOA-scaled random starts recovered the generating solution to numerical precision (`1.34e-14 m` coordinate RMSE, `2.36e-17 s` residual norm, rank `105/105`, 42 evaluations); the other did not converge within 300 evaluations. All three structured Halton starts failed within that budget, with coordinate errors from `22.8 m` to `248.8 m`. The oracle control passed immediately. This single larger noiseless fixture shows that added observations can coincide with a successful blind basin, but the mixed outcomes do not establish repeatable performance.

### Finding and implementation decision

The zero-timing plus corrected cross-distance SVD/Crocco coordinate fit is the only tested initializer that repeatedly reached the seed-11 generating solution under the documented local perturbations: all five non-oracle starts derived from this initializer passed the noiseless recovery gate. It uses only q and c and leaves timing variables free, so it meets the narrow deterministic seed-11 demonstration. However, the initializer is poor in raw coordinate and TOA error, its Crocco metric residual is not small, all nine noisy blind/data-derived starts fail within the recorded 500-evaluation budget, and it has not been evaluated over an independent set of minimum-count geometries. It is a promising research candidate for further blinded validation, not an accepted production initializer.

The Gaubitch-derived initialization found a different numerically exact Euclidean fit; this indicates the direct TOA objective can have distant competing solutions under the measurement assumptions alone. Rank-3 alone, an optimizer success flag, or a tiny residual cannot select the intended room. Additional independent priors/data or a validated global strategy may be needed. Known room dimensions and ground-truth positions are specifically not assumed here. The 2016 staged initialization remains distinct and its convergence blocker remains unresolved; no equations, production modules, or prior experiment records were changed.


## Phase 5C.7 — competing-solution disambiguation (exploratory)

### Evidence and preserved baseline

The two seed-11 endpoint parameter vectors were loaded verbatim from `experiments/exploratory/phase5c6_results.json`: `oracle_positive_control` and `Gaubitch100_plus_Crocco`. The endpoint vectors and the Phase 5C.6 archive were not rewritten. All direct-model endpoint scores below use the existing direct TOA model and gauge. The truth endpoint has TOA residual norm `8.1252e-17 s`, coordinate RMSE `1.37e-15 m`, full Jacobian rank `65/65`, condition `3.9126e4`, optimizer status 1, and positive minimum propagation TOA `1.935 ms`. The archived Gaubitch endpoint has residual `1.9783e-17 s`, coordinate RMSE `0.523824 m`, emission RMSE `1.807 ms`, clock RMSE `0.732 ms`, rank `65/65`, condition `9.1830e4`, optimizer status 1, 330 evaluations, and positive minimum TOA `2.692 ms`. Its endpoint remains a competing numerical solution; a small residual is not evidence that its room is the generating room.

The C7 experiment script is `experiments/exploratory/phase5c7_competing_solution_disambiguation.py`; its machine-readable full output (including endpoint vectors, full Jacobian spectra and per-run parameter vectors) is `experiments/exploratory/phase5c7_results.json`. Settings and seed provenance are included there. The script does not write to earlier experiment records.

### A. Convex room as a physical constraint

**Source status.** The direct TOA objective has no room-wall observations. A common convex enclosure is an added BatSight physical assumption here, not an independent measurement established by the cited initialization formulation.

**Experiment.** Each candidate's microphone and source points were separately enclosed by a data-derived, slightly expanded convex hull; a third hull enclosed the union of both endpoint point sets. No known room dimensions or assumed face count were supplied. The generating point set fit its expanded hull (22 facets, volume `55.848 m^3`, positive interior slack `1.269e-6 m`); the competitor fit its own (20 facets, `59.498 m^3`, slack `1.387e-6 m`). Both fit one shared expanded hull (26 facets, `110.240 m^3`, slack `2.141e-6 m`).

This is deliberately a feasibility demonstration, not an independent fit or prior: the hull is constructed from the candidate coordinates being tested, and a finite set of points always admits such an enclosing convex polyhedron. Therefore the competing endpoint remains feasible under “inside some unknown convex room”; this constraint does not disambiguate. It supplies no independent information to the TOA Jacobian and has no meaningful optimizer status/evaluation count. The hull facet counts are outputs of the hull algorithm, not a face-count assumption.

As an oracle-only diagnostic, the seed-11 simulator's actual shoebox has dimensions `8 x 7 x 5 m`: truth points are inside with minimum wall margin `0.5214 m`, while four competing endpoint points lie outside (minimum signed wall margin `-1.4292 m`). This rejects the competing endpoint only if those exact room planes/dimensions are supplied. They are unavailable to a blind reconstruction; using them would be circular leakage of simulator truth. No known-room constraint was used in any C7 fit.

### B. First-order reflection observations

**Source/model distinction.** The existing image-source module supplies the forward shoebox model. The C7 reflection sets are synthetic simulator observations, not detections from a recording or a paper-reported extension to the direct-path initialization. In an unknown room, wall planes are latent shared geometry and echo-to-wall labels are unknown.

**Controlled check.** For the original room and seed-11 source/microphone events, six first-order image paths were generated per pair, yielding 390 echo TOAs (`5 x 13 x 6`). Wall identifiers were withheld. Within each known microphone/source group, sorting both predicted and observed TOA sets provides the minimum one-dimensional sum-of-squares association without assigning a wall label. All six echoes per group and noiseless detection are explicit ideal-simulator assumptions. For the generating endpoint, the grouped reflection residual norm is `2.4864e-17 s` and maximum absolute error `5.8981e-17 s`. The archived competitor has no prediction under that same room because it places points outside the supplied shoebox. The result is not an independent disambiguation: known room planes already exclude it.

A blind direct-plus-reflection fit was **not run**. Computing image-source locations from an unknown convex room requires estimating wall planes and their association to echoes, which is wall estimation and outside this phase. Fixing the actual shoebox would confound reflection evidence with the known-room constraint. Thus C7 does not establish whether unknown-association first-order echoes alone reject the competitor. It does establish the additional-observation model is feasible for truth in the known synthetic shoebox. A future reflection study needs a separately specified latent-wall/association problem and must count those as unknowns, not as known labels.

### C. Observation count and spatial placement

All direct fits used the same Phase 5C.6 objective, scaling, coordinate/time gauges, analytic residual Jacobian and `max_nfev=300`. Truth-Jacobian rank uses the recorded relative singular-value threshold `1e-8`. New count variants use deterministic additional microphone/source/emission/clock seeds 731–734. Random blind starts use seeds 17 and 29. Oracle rows are positive controls, not blind initialization. Baseline `M=5,N=13` endpoints are references to the preserved Phase 5C.6 records; the baseline was not refit. Aligned coordinate error allows rigid alignment with reflection as in the existing evaluator. Unknown count follows `3M-6 + 3N + (N-1) + (M-1) = 4M+4N-8`; observation redundancy is `MN - unknown_count`.

| Case | M,N; observations / unknowns (redundancy) | Truth Jacobian rank / condition | Blind seed 17: coordinate RMSE; TOA norm; rank / condition; optimizer / nfev / seconds | Blind seed 29: coordinate RMSE; TOA norm; rank / condition; optimizer / nfev / seconds |
|---|---:|---:|---|---|
| Original baseline | 5,13; 65 / 65 (0) | 65 / 3.91e4 | Archived competing endpoint: 0.524 m; 1.978e-17 s; 65 / 9.18e4; success / 330 / 0.582 (Gaubitch start) | same preserved endpoint |
| More sources | 5,20; 100 / 93 (7) | 93 / 7.59e3 | 4.118 m; 2.720e-4 s; 93 / 1.45e5; max evaluations / 300 / 0.838 | 2.737 m; 1.344e-4 s; 93 / 5.95e4; max evaluations / 300 / 0.975 |
| More microphones | 8,13; 104 / 77 (27) | 77 / 3.60e2 | `5.78e-15 m`; `1.869e-17 s`; 77 / 3.60e2; success / 164 / 0.656 | 1.174 m; 8.331e-4 s; 75 / 6.73e9; max evaluations / 300 / 0.739 |
| More of both | 8,20; 160 / 105 (55) | 105 / 4.05e2 | 0.1167 m; 5.565e-4 s; 105 / 8.04e7; max evaluations / 300 / 1.685 | 0.1167 m; 5.565e-4 s; 103 / 7.35e10; max evaluations / 300 / 1.684 |
| Clustered points | 5,13; 65 / 65 (0) | 65 / 3.91e4 | `5.32e-13 m`; `7.070e-18 s`; 65 / 3.91e4; success / 168 / 0.279 | 2.501 m; 6.356e-5 s; 64 / 1.88e9; max evaluations / 300 / 0.470 |
| Spread points | 5,13; 65 / 65 (0) | 65 / 3.91e4 | 5.717 m; 1.189e-5 s; 65 / 1.19e6; max evaluations / 300 / 0.661 | 6.755 m; 2.028e-4 s; 64 / 1.13e8; max evaluations / 300 / 0.495 |

The full per-fit timing errors, maximum TOA residuals, minimum corrected TOAs, initial residuals, optimizer messages, source/microphone-specific RMSEs, complete spectra and output vectors are in the JSON record. Oracle controls for every new fixture terminate in one evaluation at numerical precision (coordinate RMSE `2.60e-16` to `1.12e-15 m`, residual norms `1.73e-17` to `1.30e-16 s`). These controls confirm fixture/model consistency, not blind recovery.

This small experiment separates observation count from placement only partially. More sources at fixed five microphones improved truth conditioning versus the baseline but neither blind random start recovered. Adding microphones at fixed 13 sources produced a much better conditioned truth Jacobian and one of two starts recovered; the other became very ill-conditioned. Adding both increased redundancy but both starts stalled at an incorrect solution. Clustered and spread cases kept counts fixed, but these two recorded placement variants are generated from the same normalized seed-11 coordinates (uniform scaling about their centroid); the true-Jacobian diagnostics therefore remain nearly unchanged because the time scale is rescaled along with geometry in this fixture. They do not isolate spatial diversity independently. The cases are exploratory and cannot support a general count/placement law.

### Interpretation and decision

A constraint that says “there exists some convex polyhedron containing the candidate points” is vacuous for finite point clouds without observed or prior wall information. First-order reflections can add measurements, but the fair unknown-room formulation couples those measurements to unknown planes and unknown associations; this study intentionally did not implement that later inverse problem. More observations changed local conditioning and blind optimizer outcomes in this sample, but recovery was inconsistent and the full-rank truth Jacobian did not prevent poor basins. None of these results proves global uniqueness or accepts a new optimizer/initializer.

Paper-derived: direct TOA measurement concept and the cited image-source forward model. BatSight choices: unknown convex enclosure feasibility test, synthetic all-six-echo sets, sorted unlabeled matching, fixture variations, starts, and direct-fit metrics. Numerical regularization: none added beyond the existing solver's documented scaling/termination configuration. Phase 5C remains blocked; no production localization module, wall estimate, or Phase 6 work is included.

#### Full C-study optimizer outcomes

Errors are gauge-aligned; timing errors are RMSE. `Oracle` rows use truth only as positive controls. Full vectors and diagnostics remain in the JSON artifact.

| Case | Start | Position RMSE (m) | Emission RMSE (ms) | Clock RMSE (ms) | TOA norm (s) | Max TOA abs (s) | Rank / condition | Status; nfev; runtime (s) |
|---|---|---:|---:|---:|---:|---:|---:|---|
| more_sources_M5_N20 | oracle_control | 1.069e-15 | 1.249e-17 | 0 | 1.055e-16 | 2.786e-17 | 93 / 7595 | success; 1; 0.001 |
| more_sources_M5_N20 | blind_random_17 | 4.118 | 4.503 | 22.96 | 0.000272 | 0.0001144 | 93 / 1.453e+05 | failed; 300; 0.838 |
| more_sources_M5_N20 | blind_random_29 | 2.737 | 6.22 | 10.87 | 0.0001344 | 5.316e-05 | 93 / 5.952e+04 | failed; 300; 0.975 |
| more_microphones_M8_N13 | oracle_control | 9.483e-16 | 3.683e-17 | 1.917e-17 | 9.823e-17 | 2.786e-17 | 77 / 360.2 | success; 1; 0.001 |
| more_microphones_M8_N13 | blind_random_17 | 5.785e-15 | 1.115e-14 | 1.56e-14 | 1.869e-17 | 5.204e-18 | 77 / 360.2 | success; 164; 0.656 |
| more_microphones_M8_N13 | blind_random_29 | 1.174 | 1.494 | 2.63 | 0.0008331 | 0.0002221 | 75 / 6.735e+09 | failed; 300; 0.739 |
| more_both_M8_N20 | oracle_control | 1.118e-15 | 6.073e-18 | 0 | 1.301e-16 | 2.786e-17 | 105 / 404.9 | success; 1; 0.002 |
| more_both_M8_N20 | blind_random_17 | 0.1167 | 0.2124 | 0.4095 | 0.0005565 | 0.00024 | 105 / 8.042e+07 | failed; 300; 1.685 |
| more_both_M8_N20 | blind_random_29 | 0.1167 | 0.2124 | 0.4095 | 0.0005565 | 0.00024 | 103 / 7.349e+10 | failed; 300; 1.684 |
| clustered_M5_N13 | oracle_control | 2.599e-16 | 0 | 3.03e-18 | 1.728e-17 | 7.698e-18 | 65 / 3.912e+04 | success; 1; 0.001 |
| clustered_M5_N13 | blind_random_17 | 5.316e-13 | 1.917e-12 | 6.237e-13 | 7.07e-18 | 3.632e-18 | 65 / 3.912e+04 | success; 168; 0.279 |
| clustered_M5_N13 | blind_random_29 | 2.501 | 10.66 | 21.44 | 6.356e-05 | 3.081e-05 | 64 / 1.876e+09 | failed; 300; 0.470 |
| spread_M5_N13 | oracle_control | 1.212e-15 | 3.683e-17 | 0 | 6.492e-17 | 2.439e-17 | 65 / 3.913e+04 | success; 1; 0.001 |
| spread_M5_N13 | blind_random_17 | 5.717 | 9.026 | 17.27 | 1.189e-05 | 4.664e-06 | 65 / 1.194e+06 | failed; 300; 0.661 |
| spread_M5_N13 | blind_random_29 | 6.755 | 28.95 | 57.69 | 0.0002028 | 9.928e-05 | 64 / 1.125e+08 | failed; 300; 0.495 |


## Phase 5C.8 — unlabeled echoes with unknown shared walls (exploratory)

### Question and fixed baseline

This experiment asks whether each archived seed-11 direct-TOA endpoint, held fixed, can explain the same ideal first-order reflection TOA sets using some unknown shared six-plane convex enclosure. It does not update the direct-path endpoint or implement a joint direct-plus-reflection reconstruction. The two endpoint vectors are read verbatim from `experiments/exploratory/phase5c6_results.json`; neither is regenerated or modified. Baseline direct-fit scores remain: generating endpoint direct residual `8.1252e-17 s`, coordinate RMSE `1.37e-15 m`, emission/clock RMSE `2.71e-20 / 3.03e-21 s`, status 1, 1 evaluation, `0.0012 s`; Gaubitch competing endpoint direct residual `1.9783e-17 s`, coordinate RMSE `0.523824 m`, emission/clock RMSE `1.807 / 0.732 ms`, status 1, 330 evaluations, `0.582 s`. Both have full gauge-fixed direct Jacobian rank `65/65` and positive corrected direct TOAs.

The observation generator uses the existing shoebox image-source simulator solely to make `5 x 13 x 6 = 390` deterministic echo TOAs. The inverse fit receives no true room dimensions, wall coefficients, or echo wall labels. Six faces are an explicit assumed input for this study, consistent with the stated six-wall problem setup; this does not assert the room is a shoebox. Echoes are noiseless, all six first-order paths are assumed detected per known microphone/source-event group, and the grouping itself is known.

### Inverse parameterization, association and objective

Each candidate gets six shared planes `n_k^T x + d_k = 0`, `||n_k||=1`, with inside defined as `n_k^T x+d_k < 0`. A normal is parameterized by azimuth and elevation (two unconstrained angles); the offset is

`d_k = -max_x(n_k^T x) - (10^-4 L + exp(g_k))`,

where the max is over that candidate's fixed microphones and sources and `L` is their maximum coordinate span (at least 1 m). Thus all candidate points are strictly inside by construction. This enforces a small numerical clearance of `10^-4 L`; that margin is a BatSight numerical guard, not a paper parameter or known physical wall clearance. There are 18 fitted variables (12 angles and 6 log gaps). Arbitrary orientations are allowed during fitting; the approximate antipodal starts are only starts, not paired-wall constraints.

For a plane `(n,d)` and source `s_j`, the image source is `s'_jk = s_j - 2(n^T s_j+d)n`; predicted reflection arrival at microphone `m_i` is `e_j+b_i+||m_i-s'_jk||/c`. At each known `(i,j)` group the six predicted arrivals are matched to the six observed arrivals by sorting both scalar sets. For squared residuals and equal-cardinality scalar sets, the rearrangement inequality shows that sorted-to-sorted pairing minimizes the sum over all permutations. This is an optimal unlabeled association per group; it does **not** assign a permanent wall identity to an arrival rank. Plane labels themselves are exchangeable.

The least-squares echo residual is `(predicted_TOA-observed_TOA)*c`, in distance-equivalent metres. The fit adds a weight-10 hinge penalty on the positive signed halfspace violations of each specular bounce point against the other five wall planes. Final finite-face validity remains a hard acceptance check: all 390 bounce intersections must lie on their corresponding bounded polygonal faces. The penalty weight is an explicit BatSight engineering choice, not source-derived. Optimizer: SciPy trust-region reflective `least_squares`, finite-difference Jacobian, `x_scale='jac'`, `ftol=xtol=gtol=1e-11`, and `max_nfev=400`. Starts: candidate-coordinate PCA frame plus six fixed-seed generic frames from perturbed antipodal random directions; PCA-derived or random support gaps. PCA uses only the endpoint point cloud, not room planes. No true-wall start, bound, or prior is used. No regularizer is added.

A fitted plane set is a bounded convex enclosure only if (1) all endpoint points are strictly inside and (2) the origin lies strictly inside the convex hull of the six outward normals. The latter is equivalent to positive spanning of directions and hence boundedness of the halfspace intersection. The normal-matrix condition and scaled augmented plane-design condition are recorded. Positive image-source path lengths and positive arrivals are checked. A solver success flag is not accepted as a good echo fit.

### Results

| Fixed direct endpoint | Start | Echo residual norm (s) | Maximum absolute (s) | Valid bounded enclosure | Valid bounce points / 390 | Normal / scaled plane-design condition | Optimizer success / status | nfev / runtime (s) |
|---|---:|---:|---:|---|---:|---:|---|---:|
| generating | PCA | 0.07097 | 0.01168 | True | 387/390 | 1.27 / 1.9 | False / 0 | 400 / 4.36 |
| generating | 7 | 0.2012 | 0.02699 | False | 196/390 | 2.99 / 7.38e+05 | False / 0 | 400 / 4.36 |
| generating | 11 | 0.2418 | 0.0265 | True | 324/390 | 5.56 / 5.94 | False / 0 | 400 / 4.81 |
| generating | 23 | 0.08151 | 0.01809 | True | 302/390 | 2.75 / 2.91 | False / 0 | 400 / 4.18 |
| generating | 37 | 0.1479 | 0.02066 | False | 382/390 | 2.61 / 3.43 | False / 0 | 400 / 4.34 |
| generating | 41 | 0.1242 | 0.0156 | False | 385/390 | 2.52 / 3.45 | False / 0 | 400 / 4.57 |
| generating | 53 | 0.1905 | 0.02628 | True | 386/390 | 4.17 / 5.32 | False / 0 | 400 / 4.93 |
| competing | PCA | 0.09723 | 0.01641 | True | 384/390 | 1.4 / 2.07 | False / 0 | 400 / 5.22 |
| competing | 7 | 0.1673 | 0.02758 | False | 331/390 | 3.71 / 8.26 | False / 0 | 400 / 4.68 |
| competing | 11 | 0.2161 | 0.03087 | True | 330/390 | 3.97 / 4.38 | False / 0 | 400 / 4.62 |
| competing | 23 | 0.1632 | 0.02386 | False | 324/390 | 3.93 / 9.52 | False / 0 | 400 / 4.66 |
| competing | 37 | 0.1794 | 0.02609 | False | 336/390 | 3.9 / 6.87 | False / 0 | 400 / 4.76 |
| competing | 41 | 0.1957 | 0.02611 | False | 387/390 | 1.84 / 6.09 | False / 0 | 400 / 4.49 |
| competing | 53 | 0.1498 | 0.02205 | False | 386/390 | 5.94 / 10.9 | False / 0 | 400 / 4.39 |


None of the 14 runs reached the 400-evaluation cap with the solver's convergence status marked successful. Some resulting plane sets did bound and contain all endpoint points (four of seven generating starts; two of seven competing starts), but all 14 failed the finite-face acceptance check: the best generating start had 387/390 bounce points on faces, and the best competing start had 384/390. The other paths remain positive and finite, but image paths that hit outside the corresponding finite polygon are not valid reflections in the proposed polyhedron. Echo residuals were also large: best `0.07097 s` (generating PCA start) and `0.09723 s` (competing PCA start); maximum absolute residuals were `0.01168 s` and `0.01641 s`. Because results were capped and physically incomplete, these values are not valid candidate fits and their difference is not disambiguating evidence.

The normal and scaled plane-design conditions for bounded-enclosure runs ranged from `1.27–5.56` and `1.90–5.94` for the generating endpoint, and `1.40–3.97` and `2.07–4.38` for the competing endpoint. Their convex-normal origin slacks are positive when enclosure validity is true; invalid runs fail the positive-spanning condition. Arrival-rank ties below `1e-10 s` occurred in zero generating starts and one competing start; plane-index-by-rank counts are retained because association rankings vary and wall labels are latent. The optimizer's endpoint scores, per-run full plane vectors, face-hit counts, rank-association counts, penalty objective, and diagnostics are preserved in `experiments/exploratory/phase5c8_results.json`.

### Interpretation and decision

The experiment is **unresolved**, not a rejection of either endpoint. The generating endpoint is the positive control, but it did not receive true wall initialization and the chosen deterministic multistart strategy failed to find a low-residual physically valid plane fit. The actual simulator planes would reproduce the generating echo sets, but they were not used to initialize or constrain inverse fitting. The competing endpoint also has some enclosing six-plane arrangements, but none of its tested fits jointly explains the echoes and satisfies all finite-face checks. Optimizer failure and finite multistart do not establish infeasibility or global uniqueness.

Source distinction: the image-source reflection model is used by the existing simulator. The six-face assumption, fixed-endpoint test, sorted unlabeled assignment, PCA/random starts, `10^-4 L` clearance, weight-10 bounce hinge, solver settings, and geometric acceptance diagnostics are BatSight exploratory choices. This is not an algorithm specified by the 2016 paper and does not change its equations. No production wall estimator or localization module was added; Phase 5C remains blocked and Phase 6 has not begun.


## Phase 5C.9 — unknown-wall solver validation (exploratory)

### C8 record preservation and forward-model diagnosis

The Phase 5C.8 script, JSON, run log, Phase 5C.6 endpoint vectors, and all earlier records were preserved. C9 reads the exact sorted echo observation array from the C8 results and asserts bitwise equality against deterministic regeneration from seed 11. The C9 corrected predictor is isolated in `experiments/exploratory/phase5c9_unknown_wall_solver_validation.py`; it does not edit or overwrite C8 code or results.

The oracle wall test revealed a concrete C8 inverse-predictor defect. In the C8 prediction helper, `np.einsum("jkd,kd->jk", sources[:,None,:]*normals[None,:,:], normals)` in both C8 prediction helpers computes `sum_d(s_d n_kd^2)`, not `n_k^T s_j`. This incorrect image coordinate caused a `0.121063 s` residual norm and `0.021703 s` maximum echo error even when C8's predictor was given the true walls. C9 computes signed source-plane distance directly as `sources @ normals.T + offsets`, then reflects by `s' = s - 2(n^T s+d)n`. With the same true endpoint, true planes transformed into the endpoint's canonical coordinate gauge, and exact C8 observations, the corrected predictor residual norm is `4.5768e-16 s` and maximum absolute residual is `5.8981e-17 s`. All 390 image paths have positive lengths/arrivals and all 390 specular bounce points lie on their finite faces. This is an oracle forward/inverse consistency test, not blind recovery.

At the oracle, the residual vector includes 390 distance-scaled echo residuals and 390 finite-face hinge residuals. The full 18-variable central-difference Jacobian has rank `18/18` at relative threshold `1e-8`, condition `10.044`, and central-difference estimates agree across steps: relative Frobenius differences from the `1e-6` result are `2.83e-9` (`h=1e-4`) and `3.23e-10` (`h=1e-5`). C9's forward finite-difference Jacobian differs from central differences by relative Frobenius `8.53e-7` and maximum element `6.05e-6`. The central objective-gradient norms at `h=1e-4, 1e-5, 1e-6` are `9.67e-6, 9.67e-8, 9.67e-10` (scaled objective units), consistent with a zero gradient at the solution and finite-difference truncation. The exact residual components, Jacobian singular values, and gradients for each step size are retained in the C9 JSON.

### Perturbed-wall recovery

The true wall parameters were used only for these explicitly labelled local-basin experiments. All use the same corrected C8-style residual, weight-10 finite-face hinge, least-squares settings (`TRF`, numerical Jacobian, `x_scale='jac'`, tolerances `1e-11`, cap 400). Each perturbation is deterministic. Normal perturbations are standard deviations in radians; offset perturbations are standard deviations in metres; all-parameter perturbations use the listed magnitude for angle and log-gap entries. Plane errors are reported after minimizing over the six-plane label permutation; this assignment is evaluation-only.

| Perturbation | Magnitude | Initial normal-angle RMSE / offset RMSE | Final max angle / max offset error | Final reflection norm / max residual (s) | Valid bounces | Jacobian rank / condition | Success / nfev / seconds |
|---|---:|---:|---:|---:|---:|---:|---|
| normal_orientation_rad | 0.005 | 0.2979 / 0.008393 | 1.91e-06 / 1.78e-15 | 1.57e-16 / 2.78e-17 | 390/390 | 18 / 10 | True / 5 / 0.088 |
| normal_orientation_rad | 0.02 | 1.05 / 0.03832 | 1.91e-06 / 2.66e-15 | 1.81e-16 / 2.78e-17 | 390/390 | 18 / 10 | True / 5 / 0.097 |
| normal_orientation_rad | 0.05 | 2.647 / 0.07135 | 1.91e-06 / 1.78e-15 | 1.65e-16 / 2.78e-17 | 390/390 | 18 / 10 | True / 6 / 0.128 |
| normal_orientation_rad | 0.1 | 5.56 / 0.09389 | 1.91e-06 / 1.78e-15 | 1.65e-16 / 2.78e-17 | 390/390 | 18 / 10 | True / 6 / 0.118 |
| wall_offset_m | 0.005 | 1.046e-06 / 0.003227 | 1.91e-06 / 1.78e-15 | 1.63e-16 / 2.78e-17 | 390/390 | 18 / 10 | True / 4 / 0.076 |
| wall_offset_m | 0.02 | 1.046e-06 / 0.0203 | 1.91e-06 / 1.55e-15 | 1.74e-16 / 2.78e-17 | 390/390 | 18 / 10 | True / 5 / 0.101 |
| wall_offset_m | 0.05 | 1.046e-06 / 0.0462 | 1.91e-06 / 2.22e-15 | 1.74e-16 / 2.78e-17 | 390/390 | 18 / 10 | True / 5 / 0.086 |
| wall_offset_m | 0.1 | 1.046e-06 / 0.1036 | 1.91e-06 / 2.66e-15 | 1.65e-16 / 2.78e-17 | 390/390 | 18 / 10 | True / 6 / 0.108 |
| all_parameter_coordinates | 0.005 | 0.3394 / 0.007489 | 1.91e-06 / 1.78e-15 | 1.64e-16 / 2.78e-17 | 390/390 | 18 / 10 | True / 5 / 0.089 |
| all_parameter_coordinates | 0.02 | 1.27 / 0.03483 | 1.91e-06 / 1.55e-15 | 1.63e-16 / 2.78e-17 | 390/390 | 18 / 10 | True / 5 / 0.100 |
| all_parameter_coordinates | 0.05 | 2.481 / 0.09654 | 1.91e-06 / 1.33e-15 | 1.59e-16 / 2.78e-17 | 390/390 | 18 / 10 | True / 6 / 0.096 |
| all_parameter_coordinates | 0.1 | 7.563 / 0.3025 | 1.91e-06 / 1.78e-15 | 1.63e-16 / 2.78e-17 | 390/390 | 18 / 10 | True / 7 / 0.109 |

All 12 perturbation runs converged to the generating plane set, passed bounded-convex enclosure and all finite-face checks, and reached residual norms below `1.82e-16 s`; final maximum normal-angle errors were about `1.7–1.9e-6°` and offset errors were at floating-point scale (`<=2.7e-15 m`). Final Jacobian rank/condition remained `18/18` / approximately `10.044`. This characterizes a local basin for these perturbation patterns and this one fixture only.

### Arrival-order and assignment diagnostics

The squared-error assignment between two equal-size scalar TOA sets is minimized by sorted-to-sorted pairing; a Hungarian assignment on the six-by-six squared cost matrix returned the same cost to floating-point precision (differences `0` to `5.42e-20 s^2`). At the oracle the minimum adjacent predicted echo gap is `6.47 us`, so there are no exact ties, but the margin is small. With seeded orientation perturbations, 4/65 groups changed arrival order by standard deviation `0.01 rad`, and 32–33 groups changed order at `0.05–0.10 rad`. The sorted objective is therefore piecewise smooth and can have kinks at assignment ties/crossings. Fixed correspondences taken from the oracle are smooth only locally; after crossings their cost diverges from sorted assignment. These fixed labels were used only as an oracle diagnostic, never as the fitted association rule.

| Orientation perturbation std (rad) | Groups with order crossing | Minimum adjacent predicted gap (s) | Sorted vs Hungarian cost difference (s²) | Fixed-oracle cost (s²) | Sorted cost (s²) |
|---:|---:|---:|---:|---:|---:|
| 0 | 0/65 | 6.47e-06 | 0 | 2.09e-31 | 2.09e-31 |
| 0.001 | 0/65 | 9.68e-06 | 1.32e-23 | 4.53e-08 | 4.53e-08 |
| 0.01 | 4/65 | 6.74e-07 | 0 | 2.55e-06 | 2.54e-06 |
| 0.05 | 33/65 | 1.16e-05 | 5.42e-20 | 0.000199 | 0.000175 |
| 0.1 | 32/65 | 4.77e-06 | 5.42e-20 | 0.000393 | 0.00033 |


### Blind starts (run only after oracle and local tests passed)

The local gate passed, so C9 then tested the PCA start plus six deterministic generic orientation/gap starts for each fixed endpoint. These starts use only candidate point coordinates and deterministic seeds; no true planes, dimensions, or echo labels enter initialization. Plane errors below are scored against simulator truth after optimization and with plane permutation alignment, not used by the fitter.

| Endpoint | Start | Reflection norm (s) | Max abs (s) | Bounded enclosure | Valid bounces | Success / nfev / seconds | Final plane error (angle RMSE / offset RMSE) |
|---|---:|---:|---:|---|---:|---|---|
| generating | PCA | 1.55e-16 | 2.78e-17 | True | 390/390 | True / 12 / 0.18 | 1.16e-06° / 1.12e-15 m |
| generating | 7 | 0.126 | 0.0219 | False | 205/390 | False / 400 / 5.00 | 61.5° / 1.51 m |
| generating | 11 | 0.233 | 0.0225 | True | 328/390 | False / 400 / 5.19 | 46.2° / 2.29 m |
| generating | 23 | 0.159 | 0.0193 | True | 276/390 | False / 400 / 4.97 | 46.3° / 1.6 m |
| generating | 37 | 0.201 | 0.0193 | False | 324/390 | False / 400 / 5.51 | 55° / 1.78 m |
| generating | 41 | 0.13 | 0.0207 | True | 386/390 | False / 400 / 7.04 | 43.2° / 1.65 m |
| generating | 53 | 0.175 | 0.0211 | True | 385/390 | False / 400 / 5.70 | 45.9° / 2 m |
| competing | PCA | 0.0291 | 0.00658 | True | 389/390 | False / 400 / 5.09 | 23° / 1.12 m |
| competing | 7 | 0.221 | 0.0272 | False | 336/390 | False / 400 / 5.35 | 45.7° / 1.94 m |
| competing | 11 | 0.248 | 0.0271 | True | 326/390 | False / 400 / 5.06 | 46.7° / 2.29 m |
| competing | 23 | 0.191 | 0.0215 | True | 330/390 | False / 400 / 6.59 | 49.4° / 2.44 m |
| competing | 37 | 0.207 | 0.02 | False | 325/390 | False / 400 / 5.03 | 52.7° / 2.34 m |
| competing | 41 | 0.151 | 0.0229 | True | 385/390 | False / 400 / 4.83 | 44.5° / 2.13 m |
| competing | 53 | 0.135 | 0.017 | True | 385/390 | False / 400 / 5.51 | 44.9° / 1.94 m |


For the generating direct endpoint, the PCA start recovered an unlabeled six-plane set matching the true room to `1.16e-6°` normal RMSE and `2.00e-15 m` offset RMSE; it explained all echoes with residual norm `1.55e-16 s`, maximum `2.78e-17 s`, valid bounded enclosure, and all `390/390` finite-face paths. It terminated successfully in 12 evaluations (`0.18 s`). The other six generating-endpoint starts did not recover the wall set within 400 evaluations.

For the competing direct endpoint, none of seven blind starts established a low-residual, physically complete solution. Its best echo norm was `0.02915 s` (PCA start), but only `389/390` bounces passed the finite-face check and the solver hit the cap; other starts had substantially larger residuals. This is not proof the competing endpoint is infeasible: the inverse is nonconvex, and the tested starts/evaluation budget are finite.

### Interpretation and decision

C9 establishes that the C8 failure on the generating positive control was caused by the image-source predictor's incorrect source-plane dot product, not evidence against the reflection model. The corrected forward/inverse equations are consistent at oracle walls, the local optimizer is stable for the tested true-wall perturbations, and a blind PCA start recovered the generating room for this endpoint. However, competing-endpoint fitting remains inadequate. Consequently, C9 does **not** establish competing-solution disambiguation or global uniqueness. More independent starts or a separately validated initialization is needed to determine whether the competing endpoint can also explain the unlabeled echoes.

C9's corrected predictor and validation code are experimental only. C8 files are intentionally left unchanged as historical records. No production estimator, approved paper equation, or Phase 6 component was changed.


## Phase 5C.10 — competing endpoint reflection-fit investigation

### Preserved inputs and regression control

C10 uses the seed-11 direct endpoint vectors verbatim from the Phase 5C.6 archive and the exact 390 sorted reflection observations stored by C8; it asserts those observations match deterministic seed-11 regeneration exactly. C8 and C9 scripts/results/logs are read-only. The corrected C9 image predictor and face-intersection checks are reused. The competing endpoint's coordinates and timing are fixed during every wall fit. No true walls, room dimensions, wall labels, or ground-truth wall errors are used in competing starts, objectives, or scoring.

The generating endpoint PCA regression reproduced its C9 result: reflection residual `1.551e-16 s`, maximum `2.776e-17 s`, all `390/390` finite-face paths, valid bounded enclosure, optimizer success in 12 evaluations (`0.176 s`). Thus the C9 positive control was retained.

### Competing endpoint: data-derived starts

Nineteen deterministic starts used the competing candidate's point-cloud PCA frame, five seeded rotations of that frame (`10°,20°,35°,55°,80°`), and support gaps at `3%,8%,16%` of candidate point-cloud span, plus the original C9 PCA start. These start frames and offsets use no room truth. The baseline objective is the C9 corrected sorted-TOA residual scaled by `c`, plus the weight-10 finite-face hinge. Every run had a 200 evaluation cap.

| Start | Reflection norm (s) | Maximum absolute (s) | All physical checks | Bounces | Jacobian rank / condition | Status / nfev / seconds |
|---|---:|---:|---|---:|---:|---|
| pca_0deg_gap_0.03span | 0.03142 | 0.006539 | False | 386/390 | 18 / 1.21e+04 | 0 / 200 / 1.55 |
| pca_0deg_gap_0.08span | 0.03012 | 0.006911 | False | 389/390 | 18 / 8.89e+03 | 0 / 200 / 1.34 |
| pca_0deg_gap_0.16span | 0.02947 | 0.006601 | True | 390/390 | 18 / 3.97e+03 | 0 / 200 / 1.24 |
| pca_rot_10deg_seed_101_gap_0.03span | 0.0286 | 0.006738 | True | 390/390 | 18 / 7.73e+03 | 0 / 200 / 1.33 |
| pca_rot_10deg_seed_101_gap_0.08span | 0.02824 | 0.006564 | False | 389/390 | 18 / 1.1e+04 | 0 / 200 / 1.29 |
| pca_rot_10deg_seed_101_gap_0.16span | 0.02609 | 0.006315 | False | 389/390 | 18 / 8.31e+03 | 0 / 200 / 1.32 |
| pca_rot_20deg_seed_202_gap_0.03span | 0.03418 | 0.006798 | False | 388/390 | 18 / 6.52e+04 | 0 / 200 / 1.28 |
| pca_rot_20deg_seed_202_gap_0.08span | 0.03445 | 0.006865 | True | 390/390 | 18 / 4.87e+03 | 0 / 200 / 1.27 |
| pca_rot_20deg_seed_202_gap_0.16span | 0.03475 | 0.006785 | False | 389/390 | 18 / 9.46e+03 | 0 / 200 / 1.23 |
| pca_rot_35deg_seed_303_gap_0.03span | 0.04496 | 0.007432 | False | 387/390 | 18 / 1.66e+04 | 0 / 200 / 1.29 |
| pca_rot_35deg_seed_303_gap_0.08span | 0.0458 | 0.007339 | False | 386/390 | 18 / 4.89e+03 | 0 / 200 / 1.25 |
| pca_rot_35deg_seed_303_gap_0.16span | 0.04633 | 0.007817 | False | 386/390 | 18 / 4.85e+03 | 0 / 200 / 1.28 |
| pca_rot_55deg_seed_404_gap_0.03span | 0.02686 | 0.005243 | False | 389/390 | 17 / 7.19e+08 | 0 / 200 / 1.21 |
| pca_rot_55deg_seed_404_gap_0.08span | 0.0263 | 0.00548 | True | 390/390 | 18 / 9.23e+04 | 0 / 200 / 1.33 |
| pca_rot_55deg_seed_404_gap_0.16span | 0.04061 | 0.008805 | False | 389/390 | 18 / 5.22e+03 | 0 / 200 / 1.29 |
| pca_rot_80deg_seed_505_gap_0.03span | 0.05825 | 0.01008 | False | 387/390 | 18 / 3.89e+07 | 0 / 200 / 1.41 |
| pca_rot_80deg_seed_505_gap_0.08span | 0.05705 | 0.009605 | False | 388/390 | 18 / 5.07e+06 | 0 / 200 / 1.24 |
| pca_rot_80deg_seed_505_gap_0.16span | 0.05286 | 0.009798 | False | 389/390 | 18 / 1.28e+04 | 0 / 200 / 1.25 |
| C9_PCA_start | 0.02972 | 0.006582 | False | 389/390 | 18 / 5.12e+03 | 0 / 200 / 1.26 |


None of the 19 fits reported optimizer convergence within the 200-evaluation budget. Four yielded bounded enclosures with all 390 finite-face paths, but their reflection residual norms were `0.02630–0.03445 s`; the best physical result (`55°` PCA rotation, `8%` gap) had maximum error `5.480 ms`, rank `18/18`, condition `9.23e4`. The lowest norm at this budget (`0.026095 s`, max `6.315 ms`) missed one finite-face bounce. Across starts, rank was 17 or 18 and measurement-Jacobian condition ranged `3.97e3` to `7.19e8`. The fitted plane-normal matrices themselves were well conditioned (condition `1.09–1.37`; scaled plane-design condition `1.52–1.70`), so poor normal-vector matrix conditioning does not explain the residual plateau. Norm errors were spread across all six arrival ranks (best run rank-wise norms `0.0059–0.0125 s`), rather than isolated to one rank. Complete singular values, residual vectors by microphone/source/rank, and plane vectors are in `phase5c10_results.json`.

### Solver variants and diagnostics

The C9 PCA competing baseline at 400 evaluations had `0.02915 s` echo norm and `389/390` bounces. C10's explicit `x_scale=[0.25 rad (12 angle variables), 1 (6 log-gap variables)]` reached `0.03013 s`, `388/390` bounces, and did not converge; this scaling did not improve the baseline. A four-round current-assignment/fixed-correspondence block fit ended at `0.03139 s`, `387/390` bounces; all four fixed-correspondence subproblems exhausted their 120-evaluation limits, and it did not improve the sorted baseline. Per-group sorted assignment remains the exact minimum squared assignment for scalar TOAs, so the block scheme changes optimization path, not the underlying matching objective.

Penalty continuation from one PCA start gave:

| Method | Reflection norm (s) | Maximum absolute (s) | Bounces | All physical checks | Jacobian rank / condition | Success / nfev / seconds |
|---|---:|---:|---:|---|---:|---|
| penalty 0 | 0.02283 | 0.005593 | 385/390 | False | 17 / 1.06e+18 | True / 16 / 0.12 |
| penalty 0.1 | 0.02362 | 0.006012 | 387/390 | False | 17 / 2.14e+18 | True / 35 / 0.25 |
| penalty 1 | 0.02362 | 0.006015 | 387/390 | False | 17 / 6.89e+19 | True / 10 / 0.07 |
| penalty 10 | 0.02362 | 0.006015 | 388/390 | False | 17 / 2.08e+20 | True / 19 / 0.03 |
| penalty 100 | 0.02362 | 0.006015 | 390/390 | True | 17 / 4.39e+20 | True / 22 / 0.09 |
| penalty 1000 | 0.02362 | 0.006015 | 390/390 | True | 17 / 6.09e+22 | True / 17 / 0.03 |

Weight 100 reached a bounded enclosure and `390/390` valid bounces with a solver success flag, but reflection norm remained `0.023623 s` and maximum error `6.015 ms`. Its Jacobian had rank `17/18` and condition `4.39e20`; weight 1000 had condition `6.09e22`. These are badly conditioned penalized-objective stationary points, not adequate echo explanations. Starting from the best multistart candidate and allowing 1,200 evaluations reduced the echo norm to `0.02542 s`, with all 390 paths valid, but hit the evaluation cap. A different 1,200-evaluation start had `0.02571 s` and lost one bounce. Longer optimization did not produce a low-residual converged solution.

Parameter-block diagnostics around the best fully physical 200-evaluation multistart point showed limited one-block improvement: optimizing log gaps with orientations held fixed gave `0.02621 s` and `389/390` bounces; optimizing orientations while holding support-gap coordinates fixed gave `0.02581 s` and `388/390`, with no convergence at 300 evaluations. This is a chart-level sensitivity check, not a strict physical offset-only/orientation-only decomposition, because plane offsets depend on both orientation and support gap in the chosen parameterization.

### Evidence by proposed explanation

- **Wall orientation:** changing data-derived frames materially changes the basin and best residual (`0.0261–0.0583 s`); the best physically complete finite-budget run is at a rotated PCA frame. Orientation is influential, but no tested frame solves the echoes adequately.
- **Wall offsets:** changing support gaps also shifts residuals substantially. Offset-only refinement from a good candidate improves little (`0.02630` to `0.02621 s`) and loses one valid bounce. Offsets alone do not explain the mismatch.
- **Echo assignment:** assignment mappings changed in many groups from start to endpoint; final minimum adjacent sorted gaps ranged down to `22 ns`, so kinks/order sensitivity are plausible. Yet exact sorted scalar assignment and Hungarian assignment are equivalent, and assignment-aware block updates did not improve the best results. Assignment non-smoothness may hinder optimization, but this experiment does not identify it as the primary cause.
- **Finite-face constraints:** raising the hinge weight improved the count from `385/390` to `390/390`, while echo norm rose from `0.02283` to `0.02362 s`. This reveals a tradeoff, not an exact physically valid fit. The weight-100 stationary result remains severely ill-conditioned.
- **Scaling/conditioning:** explicit parameter scaling did not help. Many ordinary multistart endpoints were full rank but conditions varied widely; the high-penalty fits became numerically rank-deficient (`17/18`, condition above `1e20`). This is evidence of optimizer/parameter conditioning limits, not proof of model incompatibility.
- **Metric incompatibility:** not established. Some candidates satisfy boundedness and all finite-face checks, but none gives a sufficiently small reflection residual. The tested local minima, finite evaluation budgets, and penalty continuation cannot prove no six-plane metric solution exists.

### Conclusion

The competing endpoint remains **unresolved**. Deterministic frame/gap exploration and longer budgets improved residuals modestly; penalty continuation produced a solver-successful, physically complete but high-residual, severely ill-conditioned result. No result is an adequate echo fit. C10 therefore does not claim reflection disambiguation or infeasibility. The generating endpoint still passes its PCA regression. More robust competing-endpoint initialization/optimization or a stronger mathematical infeasibility certificate would be needed before this reflection evidence can distinguish the endpoints.

All C10 work is exploratory. No production wall estimator, localization code, approved paper equation, or Phase 6 component was changed.


## Phase 5C.11 — joint direct-TOA and first-order reflection fit (exploratory)

### Inputs, gauges, and objective

C11 loads the exact seed-11 generating and Gaubitch competing 65-parameter vectors from Phase 5C.6 and the exact 390 sorted echo observations from Phase 5C.8. The script verifies the echo matrix against deterministic regeneration but does not write to earlier results. The generating/competing vectors are used only in their labelled initialization rows and as evaluation references; blind starts use neither endpoint.

The joint unknown is 83 parameters: the existing 65 gauge-fixed direct-model parameters (microphone and source coordinates, independent clocks and emissions subject to `m1=(0,0,0)`, `m2` on +x, `m3` in xy with positive y, and `e1=0`) plus the existing 18 wall parameters (six azimuth/elevation normals and six log support gaps). There are 455 observations: 65 direct TOAs (`M=5,N=13`) and 390 first-order reflection TOAs (`5 x 13 x 6`). The fitted endpoint geometry/timing and wall planes vary jointly.

The direct residual is the supplied model `q_ij-e_j-||s_j-m_i||/c-b_i`. The reflection residual uses the corrected C9 predictor `e_j+b_i+||m_i-(s_j-2(n_k^T s_j+d_k)n_k)||/c`. The six echo arrivals remain unlabeled and are matched by sorted-to-sorted order within each known microphone/source-event group; this is the minimum squared one-to-one assignment for equal-cardinality scalar observations. Assignment is recomputed at each residual evaluation.

Both residual groups are multiplied by `c`, converting seconds to distance-equivalent metres, and each observation receives unit weight. The sixfold larger echo count therefore contributes sixfold more terms than the direct group under the equal-error assumption; no group normalization is applied. No regularization or finite-face penalty is included. Convex boundedness, positive direct/reflection paths, and finite-face bounce validity are reported as separate physical diagnostics. The support-gap parameterization enforces strict containment; it does not force the normals to bound a convex room or force bounce points onto finite faces.

The optimizer is TRF least squares with the existing analytic direct-residual Jacobian block and a forward finite-difference echo block (step `1e-6` in scaled parameters), `x_scale='jac'`, `ftol=xtol=gtol=1e-11`, and `max_nfev=80`. Full rank diagnostics use the resulting `455 x 83` Jacobian and relative threshold `1e-8`. This finite-difference echo Jacobian is an exploratory engineering implementation; assignment changes can make it piecewise nonsmooth.

### Controlled runs

A and B use the same candidate-point PCA normals and `12%` point-span gap start. The PCA wall initialization uses no true plane values, room dimensions, or wall labels. C perturbs all 83 scaled parameters with deterministic Gaussian noise (`sigma=0.005` or `0.02`) around each endpoint-derived complete start. D uses three seeded random direct-coordinate starts generated at a TOA-derived length scale with zero clock/emission start values; their PCA wall starts use only those candidate coordinates. A staged data-derived wall initialization is also reported: the generating wall vector is the C9 echo-only PCA fit with endpoint fixed; the competing wall vector is the C10 weight-100 echo-only continuation result with endpoint fixed. Both are released jointly with the corresponding archived direct vector and neither uses the true walls.

| Run | Direct norm / max (s) | Echo norm / max (s) | Aligned position RMSE (m) | Emission / clock RMSE (ms) | Wall normal / offset RMSE (deg / m; evaluation only) | Physical checks (bounces) | Joint rank / condition | Status / nfev / seconds |
|---|---:|---:|---:|---:|---:|---|---:|---:|
| generating_endpoint_PCA_wall_start | 0.00232 / 0.00123 | 0.00795 / 0.00251 | 0.383 | 0.342 / 0.164 | 5.22 / 0.063 | True (390/390) | 83 / 370 | 2 / 24 / 1.92 |
| competing_endpoint_PCA_wall_start | 0.00132 / 0.000619 | 0.00424 / 0.00179 | 0.118 | 0.147 / 0.0317 | 1.45 / 0.0298 | True (390/390) | 83 / 345 | 2 / 39 / 1.64 |
| generating_endpoint_staged_data_derived_walls | 8.13e-17 / 2.79e-17 | 1.55e-16 / 2.78e-17 | 1.37e-15 | 2.71e-17 / 3.03e-18 | 1.1e-06 / 6.54e-16 | True (390/390) | 83 / 333 | 1 / 1 / 0.04 |
| competing_endpoint_staged_data_derived_walls | 0.00255 / 0.00133 | 0.00697 / 0.00231 | 0.319 | 0.331 / 0.271 | 3.94 / 0.139 | True (390/390) | 82 / 2.09e+17 | 3 / 33 / 0.78 |
| generating_derived_full_perturb_0.005 | 0.00214 / 0.00134 | 0.00928 / 0.00383 | 0.37 | 0.12 / 0.167 | 4.55 / 0.0784 | True (390/390) | 83 / 345 | 2 / 21 / 1.04 |
| generating_derived_full_perturb_0.02 | 0.00266 / 0.00116 | 0.00936 / 0.00334 | 0.362 | 0.418 / 0.385 | 4.73 / 0.205 | True (390/390) | 83 / 490 | 2 / 32 / 1.44 |
| competing_derived_full_perturb_0.005 | 0.00118 / 0.000533 | 0.00417 / 0.00194 | 0.105 | 0.125 / 0.0914 | 1.3 / 0.0315 | True (390/390) | 83 / 346 | 2 / 32 / 1.94 |
| competing_derived_full_perturb_0.02 | 0.00573 / 0.00232 | 0.0225 / 0.00601 | 0.622 | 0.699 / 0.817 | 10.8 / 0.376 | True (390/390) | 83 / 451 | 2 / 29 / 1.61 |
| blind_observation_start_17 | 0.0174 / 0.0068 | 0.0454 / 0.0079 | 2.67 | 1.85 / 2.11 | 31.5 / 0.686 | False (383/390) | 83 / 253 | 2 / 39 / 2.22 |
| blind_observation_start_29 | 0.0166 / 0.00473 | 0.0383 / 0.00593 | 2.85 | 4.35 / 1.83 | 45.1 / 0.497 | False (285/390) | 83 / 3.23e+07 | 0 / 80 / 3.43 |
| blind_observation_start_41 | 0.0179 / 0.00509 | 0.0446 / 0.0107 | 3.4 | 4.26 / 4.13 | 45.5 / 1.77 | False (338/390) | 81 / 2.51e+17 | 2 / 71 / 3.14 |


### Interpretation

The generating endpoint with only the PCA wall start did **not** remain at truth: it ended at `0.383 m` aligned position RMSE, direct residual norm `2.32e-3 s`, and echo norm `7.95e-3 s`, despite passing the geometry/path checks. This shows the unrefined PCA wall start is outside the joint solver's successful basin for the exact solution. The additional staged generating initialization, obtained by fitting walls to echoes with the archived endpoint held fixed, then jointly released, recovered the exact generating configuration: direct and echo residual norms `8.13e-17 s` and `1.55e-16 s`, `1.37e-15 m` coordinate RMSE, all physical checks, and `83/83` Jacobian rank. It stopped at one evaluation. This positive control is data-derived, not true-wall-initialized.

The competing archived endpoint plus the same PCA/gap initialization moved closer to truth (`0.524 m` initial archived coordinate error to `0.118 m` after alignment). Its result is a distinct, physically valid approximate configuration: direct residual norm `1.318e-3 s`, echo norm `4.240e-3 s`, maximum residuals `0.619 ms` and `1.790 ms`, coordinate RMSE `0.118 m`, rank `83/83`, condition `345`, and all `390/390` finite-face paths. Optimizer termination was status 2 after 39 evaluations. Its errors remain far above numerical precision for the noiseless fixture, so it does not explain both observation sets as an exact solution and is not accepted as a competing valid reconstruction.

The staged competing initialization performed worse (`0.319 m` position RMSE, direct/echo norms `2.55e-3 / 6.97e-3 s`) and was rank `82/83` with condition `2.09e17`. A small competing-derived perturbation returned to a similar approximate basin (`0.105 m` position RMSE); the larger perturbation did not. Generating-derived PCA perturbations also moved away from truth. Three blind starts failed the physical checks and retained large residuals (`0.0166–0.0179 s` direct and `0.0383–0.0454 s` reflection norms). Thus joint fitting did not make blind recovery reliable.

C11 establishes two things on this fixture: a staged data-derived positive control can reach the exact generating joint solution, and the joint direct-plus-echo objective moves the competing candidate toward a closer, physically valid but still inaccurate configuration. It does not establish that the competing endpoint is infeasible, nor that the generating solution is globally unique. The endpoint-derived competing fit is locally full rank but not an exact measurement solution; finite starts cannot certify global absence of another solution. The high residuals and start sensitivity indicate initialization/local-minimum issues remain. All complete 83-vectors, residuals, singular spectra, assignments, and physical diagnostics are in `experiments/exploratory/phase5c11_results.json`.

C11 is exploratory only. No production localization/wall-estimation code, paper equations, or Phase 6 work was changed.


## Phase 5C.12 — joint solver basin and echo-Jacobian investigation

### Preserved reference and model

The study reads (without modifying) the archived C11 seed-11 direct endpoint vectors, the 390 sorted first-order echo observations, and the 83-parameter model. Its oracle-derived reference is the final vector from C11's staged generating-endpoint/data-derived-wall positive control. The coordinate gauge remains `m1=(0,0,0)`, `m2` on positive x, `m3` in xy with positive y, and `e1=0`; six unit wall normals and six support gaps define the wall chart. The objective remains the 65 direct plus 390 echo residuals, each in distance units (`c * seconds`), with unit weights, no regularization, and all C11 physical checks. TRF tolerances remain `1e-11`, `x_scale='jac'`, and `max_nfev=80`.

At the reference, direct and echo residual norms are `8.13e-17 s` and `1.55e-16 s`; aligned position RMSE is `1.37e-15 m`. The coordinate and emission-time gauges are satisfied. The six planes reproduce their evaluation-only truth to `1.48e-6 deg` maximum normal angle and `8.9e-16 m` maximum offset difference after alignment. The fitted planes enclose all points, their normals positively span 3D, and all `390/390` bounce points lie on finite faces. The `455 x 83` joint Jacobian has rank `83/83` at relative threshold `1e-8`, condition number `332.9`; the full singular spectrum is stored in the results JSON. This is an oracle-derived positive control, not blind recovery.

### Analytic echo derivative

For wall `k`, write its unit normal as `n(az,el)`, offset as `d`, and signed source distance as `z = n^T s + d`. The image point is `s' = s - 2 z n`; image distance is `rho = ||s' - m||`. The residual in the existing distance scaling is `r = c(e+b) + rho - c*y`, where `y` is the matched observed TOA. Within a fixed wall association, its differential is `dr = c(de+db) + u^T(ds' - dm)`, with `u=(s'-m)/rho` and `ds' = ds - 2[(dn^T s + n^T ds + dd)n + z dn]`.

The implementation differentiates the unit normal with respect to azimuth and elevation, and differentiates the support-derived plane offset with respect to its active support point, normal, log-gap, and the coordinate-span clearance floor. The direct-coordinate derivatives pass through the existing scaled, gauge-fixed parameter chart. The six predicted arrivals are sorted per microphone/source event; the analytic rows select the wall IDs in the current sort order. This is an exact derivative inside a region where that order, each support maximizer, and the active coordinate-span axis remain fixed. At arrival ties or changes in support extrema it is only a one-sided chart derivative; the globally sorted residual is piecewise smooth and kinked at ties.

The Jacobian comparison uses central finite differences at steps `1e-4` through `1e-8` in the scaled parameters. Full analytic and numerical singular spectra and ranks are retained for every step and checkpoint in `phase5c12_results.json`.

| Checkpoint | Re-sorted FD relative Frobenius error at `1e-5` | Fixed-association FD relative error at `1e-5` | Rank (analytic / re-sorted FD) |
|---|---:|---:|---:|
| Exact staged reference | `4.45e-11` | `4.45e-11` | 83 / 83 |
| Generating PCA wall start | `8.53e-3` | `3.88e-11` | 83 / 83 |
| Competing PCA wall start | `8.55e-3` | `3.88e-11` | 83 / 83 |
| Small perturbation (`1e-5`) | `4.56e-11` | `4.56e-11` | 83 / 83 |

The fixed-association finite difference holds the checkpoint's predicted wall ordering constant only as a derivative diagnostic; it does not change the fitted objective. At both PCA starts, the minimum adjacent predicted echo gap is at floating-point zero, creating arrival ties. Thus the roughly `0.85%` discrepancy for re-sorted central differences is attributable to the sort boundary, not a smooth-region derivative error. Away from ties, the analytic Jacobian agrees to approximately `1e-10` relative Frobenius error at the useful central-difference steps. At the exact reference, the best discrepancy is `4.45e-11` at step `1e-5`; the `1e-8` discrepancy rises to `2.11e-8` as subtraction roundoff becomes visible.

A targeted crossing probe starts from the exact reference, where the smallest adjacent gap is `6.469 microseconds`. Along the negative gap-gradient direction it decreases to `0.537 microseconds` at scaled step `3e-4` and changes wall ordering by step `5e-4`. The sorted residual therefore does cross a nonsmooth ordering boundary at finite distance, while the tested reference itself remains locally smooth.

### Local basin measurements

Three deterministic normalized Gaussian directions were used at each perturbation magnitude. Each perturbation has RMS component size equal to the listed magnitude in the 83-dimensional scaled parameter chart. Both the C11 forward-difference echo Jacobian and the new analytic echo Jacobian were run from each same start, for 36 runs total.

| Per-coordinate perturbation RMS | Exact recoveries | Final direct norm, maximum (s) | Final echo norm, maximum (s) | Maximum aligned coordinate RMSE (m) | Maximum evaluations |
|---:|---:|---:|---:|---:|---:|
| `1e-8` | 6/6 | `3.37e-17` | `1.34e-16` | `4.50e-15` | 3 |
| `1e-7` | 6/6 | `2.21e-17` | `1.29e-16` | `4.50e-15` | 3 |
| `1e-6` | 6/6 | `2.02e-17` | `1.32e-16` | `4.50e-15` | 3 |
| `1e-5` | 6/6 | `4.23e-17` | `3.33e-16` | `4.64e-15` | 3 |
| `1e-4` | 6/6 | `5.76e-17` | `1.62e-16` | `4.38e-15` | 4 |
| `1e-3` | 6/6 | `1.94e-17` | `9.99e-17` | `4.44e-15` | 5 |

All these runs passed the enclosure and finite-face checks. This shows a broad successful local neighborhood through the largest tested perturbation (`1e-3`) for this exact solution and these directions. It does not define a universal radius or characterize other fixtures.

### Controlled Jacobian/solver comparison

The only change between methods A and B is the echo Jacobian: C11's one-sided finite differences with relative step `1e-6` versus the analytic derivative above. Starts, objective, scaling, optimizer settings, budget, and acceptance rules are identical.

| Start | Jacobian | Final direct / echo norm (s) | Aligned position RMSE (m) | Status / evaluations | Runtime (s) | Exact recovery |
|---|---|---:|---:|---:|---:|---|
| Exact staged reference | FD / analytic | `8.13e-17 / 1.55e-16` for both | `1.37e-15` for both | 1 / 1 for both | 0.046 / 0.066 | Yes / yes |
| Generating PCA walls | FD | `2.32e-3 / 7.95e-3` | 0.383 | 2 / 24 | 1.17 | No |
| Generating PCA walls | Analytic | `1.19e-3 / 4.16e-3` | 0.105 | 2 / 27 | 1.88 | No |
| Competing PCA walls | FD | `1.32e-3 / 4.24e-3` | 0.118 | 2 / 39 | 1.89 | No |
| Competing PCA walls | Analytic | `1.18e-3 / 4.17e-3` | 0.105 | 2 / 47 | 2.79 | No |
| Perturbation `1e-8` | FD / analytic | both below `2e-16` per group | below `5e-15` | 3 / 2 | 0.160 / 0.125 | Yes / yes |
| Perturbation `1e-6` | FD / analytic | both below `2e-16` per group | below `5e-15` | 3 / 3 | 0.150 / 0.194 | Yes / yes |
| Perturbation `1e-4` | FD / analytic | both below `5e-16` per group | below `5e-15` | 4 / 3 | 0.222 / 0.212 | Yes / yes |
| Perturbation `1e-3` | FD / analytic | both below `2e-16` per group | below `4e-15` | 4 / 4 | 0.215 / 0.261 | Yes / yes |

The PCA runs pass the reported convexity and all finite-face checks but remain non-exact; exactness additionally requires both residual norms below `1e-9 s` and aligned coordinate RMSE below `1e-6 m`. Their timing and wall errors are included in the machine-readable results. The analytic Jacobian improved both PCA endpoints' residual and coordinate errors, especially the generating PCA endpoint, but did not recover the exact solution. It also took longer on those starts due additional solver/Jacobian work. The local perturbation comparisons show similar recovery from both Jacobians.

Additional PCA endpoint diagnostics (errors are evaluated after coordinate gauge alignment; they do not enter the objective):

| Start / Jacobian | Emission RMSE (ms) | Clock RMSE (ms) | Wall normal RMSE (deg) | Wall offset RMSE (m) | Valid finite-face bounces | Joint rank / condition |
|---|---:|---:|---:|---:|---:|---:|
| Generating PCA / FD | 0.342 | 0.164 | 5.22 | 0.0630 | 390/390 | 83 / 370 |
| Generating PCA / analytic | 0.120 | 0.0898 | 1.33 | 0.0310 | 390/390 | 83 / 347 |
| Competing PCA / FD | 0.147 | 0.0317 | 1.45 | 0.0298 | 390/390 | 83 / 345 |
| Competing PCA / analytic | 0.125 | 0.0914 | 1.30 | 0.0315 | 390/390 | 83 / 346 |


### Findings and limits

The exact staged solution is well-conditioned enough for this fixture (full rank and condition `332.9`) and the analytic derivative is verified in smooth association regions. Perturbations through `1e-3` in scaled per-coordinate RMS recover the exact solution consistently. The PCA starts contain arrival-order ties, where the sorted residual is nondifferentiable; central differences across those ties disagree with a fixed-branch analytic derivative. Replacing forward differences with the analytic derivative improves but does not eliminate the PCA-start failure. These results support assignment nonsmoothness as a real complication, but do not show it is the only cause. The full-rank PCA Jacobians and remaining nonzero residuals are consistent with convergence to a different local minimum; no causal proof or global uniqueness claim follows.

The practical basin estimate is limited to one noiseless seed-11 fixture, the chosen scaled coordinates, three directions per radius, and the existing optimizer. No objective, gauge, paper equation, acceptance threshold, production module, or Phase 6 implementation changed. C11 artifacts remain unchanged. The exploratory implementation, full vectors, per-run diagnostics, Jacobian singular spectra, and runtime/evaluation data are in `experiments/exploratory/phase5c12_joint_basin_jacobian.py` and `experiments/exploratory/phase5c12_results.json`.


## Phase 5C.13 — smooth echo assignment and continuation investigation

### Proposal and objective

This is a BatSight numerical proposal, not a formulation attributed to Crocco, Gaubitch, or another source. Each microphone/source event has six predicted image-path arrivals `p_a` in path-ID order and six unlabeled observed arrivals `y_b`. The cost matrix is

`C_ab = [c (p_a - y_b)]^2`, in `m^2`.

For each event, use balanced transport plans `P` with six row and column marginals equal to `1/6` (total plan mass one), and uniform reference `U_ab=1/36`. At temperature `tau` (in `m^2`), solve

`P_tau = argmin_P { sum_ab P_ab C_ab + tau KL(P || U) }`

and define the event loss `L_tau = 6 { sum_ab P_tau,ab C_ab + tau KL(P_tau || U) }`. The factor six makes the zero-temperature data term converge to the sum of six squared errors used by the exact hard assignment. Entropy is **included** in the smooth objective; the expected data cost and entropy contribution are also reported separately. A least-squares residual `sqrt(L_tau)` per event preserves the total direct-SSE-plus-transport objective. This is not the same objective as hard assignment at finite temperature.

The envelope gradient is `dL_tau/dx = 6 sum_ab P_tau,ab dC_ab/dx`. The echo path derivatives reuse the C12 analytic image-source Jacobian, restored to physical path-ID order. Sinkhorn scaling uses log-domain updates with a damped Newton solve of the 11 independent marginal equations; row/column cost centering removes only separable constants and leaves the balanced plan unchanged. The observed marginal error is recorded for every evaluation stage. The complete 6x6 plans and hard assignments are preserved in the JSON results.

For entropy reporting, `H(P)=-sum P log P` ranges from `log(6)` for a permutation plan to `log(36)` for the uniform 6x6 plan. Reported normalized excess entropy is `(H-log(6))/log(6)` in `[0,1]`.

### Deterministic configuration

The fixed data-only scale is `s^2 = median_ij Var_a(c*y_ija) = 5.6036735 m^2`. The four-stage schedule is `tau/s^2 = [0.5, 0.3, 0.2, 0.1]`, or `[2.8018368, 1.6811021, 1.1207347, 0.5603674] m^2`. The same observations, gauges, 83 variables, sound speed, and C11 physical checks are used throughout. Exact sorted fitting uses the analytic C12 Jacobian and max 80 function evaluations. Each smooth temperature stage uses TRF, `x_scale='jac'`, `ftol=xtol=gtol=1e-11`, and max 16 evaluations; method 3 then gets the same max 80 exact sorted-refinement budget. No penalty or additional geometric prior is added.

The 24 starts comprise the staged exact reference, both archived PCA endpoint starts, all 18 deterministic C12 perturbation starts (three directions at each RMS magnitude from `1e-8` through `1e-3`), and the three archived observation-derived blind starts. The staged exact vector is an oracle positive control; the blind starts use no ground-truth values in initialization.

### Gradient and numerical checks

Twenty-four directional finite-difference checks cover the exact reference and both PCA starts at all four temperatures, with two deterministic directions per case. At step `1e-6` in scaled parameter norm, the smooth scalar-objective gradient had median relative discrepancy `7.81e-10` and maximum `3.06e-7`. Sinkhorn row/column marginal error across successful reported stage evaluations stayed below `1.0e-12`. This verifies the envelope derivative numerically at those checkpoints, including the PCA arrival ties: entropic assignment has no hard sort boundary at finite temperature.

However, the continuation did not complete its four stages for any of the 24 starts. The first stage reached its 16-evaluation budget (status 0); at the next temperature, the optimizer proposed extreme trial costs, and the transport solve failed its marginal criterion. Recorded failing groups include cost ranges up to `9.42e17 m^2` and row-marginal errors of `0.5`. One blind start completed two stages before a similar failure at the third. These are explicit solver failures, not evidence that the mathematical OT problem is infeasible. In addition, a pilot at still lower temperatures (`0.02` and `0.01` of `s^2`) did not meet the configured marginal tolerance at some PCA starts, so those temperatures were not used in the final schedule.

### Controlled outcomes

The table reports the exact hard-sorted score at each method's endpoint. Smooth-only endpoints use the last accepted continuation state; method 3 continues from that state with the original exact objective. Coordinate errors are after Euclidean gauge alignment.

| Start | Method | Exact direct / echo norm (s) | Position RMSE (m) | Exact criteria | Physical checks |
|---|---|---:|---:|---|---|
| Staged reference | Sorted analytic | `8.13e-17 / 1.55e-16` | `1.37e-15` | Pass | Pass |
| Staged reference | Smooth only | `1.08e-3 / 1.261e-2` | 0.0707 | Fail | Pass |
| Staged reference | Smooth then exact | `5.95e-17 / 3.15e-16` | `3.75e-15` | Pass | Pass |
| Generating PCA | Sorted analytic | `1.19e-3 / 4.16e-3` | 0.105 | Fail | Pass |
| Generating PCA | Smooth only | `3.59e-3 / 1.781e-2` | 0.215 | Fail | Pass |
| Generating PCA | Smooth then exact | `6.34e-17 / 3.62e-16` | `3.07e-15` | Pass | Pass |
| Competing PCA | Sorted analytic | `1.18e-3 / 4.17e-3` | 0.105 | Fail | Pass |
| Competing PCA | Smooth only | `5.95e-3 / 2.976e-2` | 0.529 | Fail | Fail |
| Competing PCA | Smooth then exact | `1.25e-3 / 4.25e-3` | 0.127 | Fail | Pass |

All three starts retain full rank in their reported smooth-stage Jacobians. At the exact reference, hard refinement restored the generating solution to numerical precision. The smooth-only endpoint is biased away from truth even there, as expected for a finite-temperature objective. Smooth-then-exact changed the generating PCA basin favorably on this one start, but did not improve the competing PCA fit to an exact solution.

For the 18 local perturbations, the exact sorted baseline recovered the generating solution in `18/18` runs; smooth-only passed exact criteria in `0/18`, while smooth-then-exact passed in `17/18`. Thus continuation did not improve this already-successful perturbation set and missed one start that the baseline recovered. None of the three blind starts passed exact criteria or all physical checks. Their smooth-then-exact echo residual norms ranged `0.0355–0.0396 s` and aligned position RMSE ranged `2.26–7.40 m`.

### Decision and interpretation

The balanced entropic objective is differentiable and its envelope derivative is validated on the tested smooth and tied-arrival checkpoints. The continuation schedule did **not** demonstrate stable annealing: extreme optimizer trial costs caused marginal-solver failure before reaching the last temperatures. The one useful result—exact recovery from the generating PCA start after a single successful smooth stage followed by exact refinement—is not reproducible across both PCA starts, and the competing endpoint remains non-exact and unresolved. The exact staged reference remains a positive control, but it already passed with the baseline.

Therefore this proposal is **not accepted** as a replacement initializer or production method. Evidence does show that a smooth stage can alter the hard solver's basin on one generating PCA start, but not robustly enough to meet acceptance. Hard refinement does not rescue the competing PCA endpoint. No global uniqueness or competing-endpoint infeasibility conclusion follows. Full per-temperature plans, entropy, hard assignments, cost diagnostics, all 83-vectors, singular spectra, optimizer statuses, timings, and errors are in `experiments/exploratory/phase5c13_results.json`; the experiment is isolated in `experiments/exploratory/phase5c13_smooth_echo_assignment.py`.
