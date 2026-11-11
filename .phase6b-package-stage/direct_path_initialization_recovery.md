# Phase 5C.17 — Direct-Path Initialization Recovery

## Scope and scientific boundary

This exploratory study asks whether existing TOA-only initialization paths can recover microphone/source geometry without ground-truth coordinates in their starts. It does not add or accept a production initializer. Six deterministic synthetic configurations were generated; positions, timing, and room dimensions are available to the forward generator and post-run evaluator only. Initializers receive measured direct-path TOAs, sound speed, dimensions, and (for the algebraic timing stage) a timing vector estimated from TOAs. No wall information or ground-truth positions enter an initializer.

The 2016 paper's printed Equation 13 remains a separate unresolved literal formulation. The SVD/Crocco experiment uses the reference-derived four-term centered distance double difference recoverable from references [7] and [28], not a silent correction presented as a literal implementation of Equation 13.

## Mathematical basis and method map

The forward measurement model is

`q_ij = e_j + ||s_j - m_i|| / c + b_i + noise_ij`,

where `q,e,b` are seconds, coordinates and distances are metres, and `c` is metres/second. The timing origin is fixed by `e_1=0`; microphone offsets are independent and are not set to zero. A common coordinate translation and orthogonal transform are gauge freedoms; evaluation aligns estimates rigidly before computing position errors. Reflection is a discrete coordinate ambiguity.

For a complete TOA matrix and a candidate timing vector, the reference-derived corrected squared-distance matrix is

`T_ij = d_ij^2 - d_i1^2 - d_1j^2 + d_11^2 = -2 (r_i-r_1)^T (s_j-s_1)`,

with `d_ij = c(q_ij-e_j-b_i)`. It has shape `(M-1) x (N-1)` and rank at most three in exact Euclidean 3D. The timing correction is represented in the existing C4 implementation as `X(p)=T+A(p)+Gamma(p)`, with `p=[b_1,...,b_M,e_2,...,e_N]`, bilinear `Gamma_ij=2(b_i-b_1)e_j`; the update used by C6 is an alternating nonlinear timing/rank-projection procedure. Rank-three SVD truncation gives factors, and Crocco's general coordinate fit imposes the quadratic Euclidean metric constraints, testing both determinant-sign branches. Rank feasibility alone is not metric consistency.

| Method | Existing procedure tested | Inputs to initializer | Scientific status |
|---|---|---|---|
| A | Zero timing, then C4/C6 rank/SVD and general Crocco metric coordinate fit | TOA matrix, sound speed, zero timing seed | Reference-derived variant; not literal 2016 Eq. 13 reproduction |
| B | C6 Gaubitch-derived general timing stage (100 outer iterations), then the same SVD/Crocco coordinate fit | TOA matrix and sound speed | Existing exploratory reference-derived timing method; nonlinear update choices are not all fixed by the sources |
| C | Existing C6 direct Euclidean blind multistart: three deterministic structured Halton starts and two fixed-seed random starts, fitted directly on the original TOA objective | TOAs, sound speed, dimensions/counts, TOA-derived scales | Existing exploratory alternative, distinct from the paper's staged rank initialization |

The gauge-fixed direct-fit unknown count is `4M + 4N - 7`: `3M-6` microphone coordinates, `3N` source coordinates, `M` clock offsets, and `N-1` emission times. Thus the M=5,N=13 case has 65 scalar observations and 65 gauge-fixed unknowns; M=4,N=10 has 40 observations and 49 unknowns. Count equality is not a uniqueness guarantee. The cited necessary count M≥5,N≥13 is not sufficient for identifiability; planar, clustered, or otherwise degenerate layouts can lower rank or worsen conditioning.

The archived methods require complete finite matrices. A deterministic 10% missing-observation mask was generated and explicitly rejected; no imputation or masked objective was added.

## Predeclared evaluation screens

These are BatSight diagnostic thresholds, not paper thresholds or validated accuracy claims:

- Noiseless: direct residual norm ≤ `1e-8 s`, combined aligned position RMSE ≤ `1e-3 m`, and both emission and clock RMSE ≤ `1e-7 s`.
- Noisy: residual norm ≤ `3 sigma sqrt(MN)`, position RMSE ≤ `max(1e-3 m, 5 c sigma)`, and each timing RMSE ≤ `max(1e-7 s, 5 sigma)`.
- A measurement-fit pass is reported independently of geometric/timing recovery. A run is recovered only if both screens and finite positive range/TOA checks pass.

All methods use the same existing C6 direct optimizer for refinement: TRF least squares, analytic direct-path Jacobian, `x_scale='jac'`, `max_nfev=500`. Method A/B each use one deterministic initializer per scenario; method C uses five starts. This is a comparison of existing approaches under a fixed budget, not an exhaustive hyperparameter search.

## Results

There were 42 initializer slots (seven per case); 33 reached direct refinement and nine were rejected during initialization. Rejected Crocco starts are retained as failures. The full per-run artifact records initial and final residuals, aligned coordinate/timing errors, Jacobian singular values/rank/condition, optimizer status/evaluations/runtime, timing-correction rank diagnostics, and physical checks.

| Synthetic case | A: Crocco from zero timing | B: Gaubitch timing + Crocco | C: existing direct multistart |
|---|---:|---:|---:|
| Minimum well-spread, M=5,N=13, noiseless | 0/1 recovered; 0/1 measurement pass | 0/1; 0/1 | 0/5; 1/5 |
| Below reference count, M=4,N=10, noiseless | 0/1; 1/1 measurement pass | 0/1; 1/1 | 0/5; 4/5 |
| Larger spread, M=8,N=20, 3–4 ms timing variation, noiseless | 0/1; 0/1 | 1/1; 1/1 | 2/5; 2/5 |
| Planar minimum-count, noiseless | 0/1; 0/1 | 0/1; 0/1 | 0/5; 2/5 |
| Clustered minimum-count, 20 µs noise | 0/1; 0/1 | 0/1; 0/1 | 0/5; 5/5 |
| Larger spread, M=8,N=20, 50 µs noise | 0/1; 0/1 | 0/1; 0/1 | 0/5; 3/5 |

Entries are `geometric/timing recoveries / trials; measurement-fit passes / trials`. None of the raw blind starts met the strict geometry/timing screen before direct refinement (initial_geometry_passes=0 for every method/case). The largest noiseless high-diversity case is the only configuration in which refinement of a blind start met the strict geometry/timing screen: B recovered its single trial, and C recovered 2 of 5 starts. In the minimum-count well-spread case, none recovered geometry/timing; one of five direct multistarts met the residual screen but had 1.446 m aligned position RMSE. In the below-count case, many fits met the residual screen but none recovered geometry/timing, as expected to be a serious identifiability risk with 49 unknowns and 40 observations. All five clustered-noisy direct fits met the residual screen but none recovered geometry/timing; low residual was therefore not evidence of geometric recovery. The planar case also had measurement-fitting starts with millimetre-level coordinate error in some runs but did not satisfy all timing and joint screens.

The exact values for every run, including optimizer diagnostics and Jacobian condition/rank, are in `experiments/exploratory/phase5c17_results.json`; stdout summary and missing-data rejection are in the run log. Deterministic seeds and settings are embedded in the JSON and script.

## Findings and limits

- **Most reliable among tested settings:** the existing direct multistart had the broadest coverage and most measurement-fit passes, while the reference-derived Gaubitch→Crocco path recovered the one larger, noiseless, spatially diverse case. Neither is reliable across the tested regimes, and neither is accepted as a production initializer.
- **Measurement fit is not reconstruction:** below-count and noisy-cluster trials frequently fit TOAs under the diagnostic threshold while retaining large position/timing error. Distinct candidate geometries and Jacobian conditioning are available per trial for inspecting this fit/recovery gap; finite starts cannot establish global multiplicity or uniqueness.
- **Geometry/distribution matters:** increased observation count plus spatial diversity coincided with the only noiseless recovery. Because both count and layout changed together across some cases, this does not isolate a causal effect. The planar and clustered cases show failure under these tested placements, not a universal impossibility result.
- **Timing variation matters but is not isolated:** the Gaubitch-derived start succeeded on the larger noiseless high-timing case but failed the other cases. No causal inference follows from one success.
- **Noise:** all tested noisy configurations had zero geometric/timing recoveries under these strict screens, including many direct objective measurement-fit passes. Noise levels/settings are exploratory and do not establish a general noise threshold.
- **Missing data:** rejected because current candidate methods implement dense TOA matrices only.
- **Known limitations:** small finite seeded starts; synthetic TOAs; chosen screening thresholds; no wall or reflection data; metric fit and direct optimizer settings inherited from exploratory code; no global search or proof of uniqueness/infeasibility. The source papers' initialization details and literal 2016 Eq. 13 issue remain unresolved as recorded in prior audits.

No existing method is ready to become a production initializer. The next justified step is a preregistered factorial synthetic study that varies microphone/source counts independently from spatial spread and timing magnitude, runs more predetermined TOA-only starts with a fixed compute budget, and reports measurement fit and aligned geometry recovery separately. Before adoption, it should also investigate the competing exact-fit geometries and evaluate identifiability with the full gauge-fixed measurement Jacobian. No Phase 6 work is authorized or undertaken.


