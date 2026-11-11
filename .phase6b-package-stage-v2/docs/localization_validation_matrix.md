# Initial localization validation matrix

**Purpose:** prescribe tests for the reference-derived initialization specified in [the design document](reference_derived_localization_design.md). This is a validation plan only; no algorithm code or result is provided here. Synthetic ground truth is available to the test harness for scoring but must never be passed into estimator inputs.

## Dataset protocol

Use the Phase 4 forward direct-path TOA generator with known source/microphone positions, independent emission times and offsets, known `c`, optional Gaussian timing noise, and fixed seeds. For every trial, retain the full ground-truth dataset and create a separate estimator input containing only measured TOAs, `c`, identifiers, and permitted metadata. Mark missing observations explicitly. Tests should include generic 3D point clouds and deliberately degenerate cases.

The reference [7] degree-count lower bound is `M>=5`, `N >= ceil((4M-7)/(M-4))`; use `M=5,N=13` as the smallest reference-count case, then larger cases such as `M=8,N=20` and `M=12,N=20`. Also include small cases that satisfy only the rank matrix dimensions (`M,N>=4`) but fail the reference timing count. Those must return insufficient-count status rather than pretending a rank-3 SVD alone establishes joint identifiability.

## Test matrix

| ID | Configuration | Variation | Expected checks |
|---|---|---|---|
| V1 | Generic full-rank geometry, `M=5,N=13`, zero offsets and zero emissions (with `e_1=0`) | noiseless | Timing correction can recover a zero-equivalent timing gauge; corrected distance double difference has numerical rank 3; result succeeds if geometry is well-conditioned. |
| V2 | Generic 3D geometry, `M=5,N=13` | independent nonzero microphone offsets, zero emissions | Recovers TOAs and relative geometry within alignment/error tolerances; confirms offset vector is not forced equal or zero. |
| V3 | Generic 3D geometry, `M=8,N=20` | nonzero source emission times and independent offsets | All timing terms are represented; gauge-fixed event 1 emission equals zero and other estimates compare after gauge alignment. |
| V4 | Same known geometry/timing nuisance parameters | noiseless then low/moderate/high Gaussian timing noise, multiple fixed seeds | Repeatability per seed; record singular spectra, residuals, convergence and position error. No unsupported monotonic-accuracy claim; characterize observed behavior. |
| V5 | Same TOAs under transformed nuisance gauge: add `q` to all emissions and subtract `q` from all offsets | exact gauge transform | Predicted TOAs unchanged. After normalizing `e_1=0`, timing estimates agree to tolerance. |
| V6 | Apply common translation, rotation, and reflection to all ground-truth source/mic points | exact coordinate gauge transformations | Predicted distances/TOAs unchanged; estimated coordinates compare after rigid orthogonal alignment including reflection policy. |
| V7 | Spatially collinear points, coplanar points, repeated source positions, clustered geometry, and near-collisions | noiseless then noisy | Rank/conditioning diagnostics identify degeneracy or poor conditioning; algorithm fails/warns as designed, never reports an unqualified successful reconstruction. |
| V8 | Counts below minimum; e.g. `M=4,N=13`, `M=5,N=12`; counts above minimum | complete matrix | Insufficient cases return the documented count failure; larger cases execute and preserve dimensions/index mapping. |
| V9 | Any complete dataset with a single missing direct-path entry, an entire missing row, or an entire missing column | mask set true | Explicit missing-data rejection before SVD; no implicit imputation or mask dropping. |
| V10 | Inject nonfinite arrivals, malformed matrix shape, nonpositive/nonfinite `c`, extreme magnitude/overflow, and synthetic timing combinations yielding nonpositive corrected TOF | invalid inputs | Deterministic validation errors or typed failure statuses; no NaN coordinates and no clipping. |
| V11 | Randomize pair/source/microphone identifiers while permuting corresponding matrix axes | valid complete input | Output ordering follows IDs and inputs; source/microphone axis transposition is caught. |
| V12 | Construct matrices with controlled singular-value spectra/noise | rank diagnostic | Top-three projection agrees with independent SVD; report ratios and normalized rank residual; near-rank-deficiency is flagged under configured threshold. |
| V13 | Coordinate recovery with multiple factor initializations and sign/reflection branches | exact/noisy | Candidate objective values and branch metadata are retained; selected solution is finite and aligns to ground truth; multistart does not claim global optimality. |

## Coordinate alignment and reported errors

Estimator coordinates use a canonical gauge different from the synthetic room frame. Align estimates against known ground truth **only after estimation**, using a rigid Procrustes/Kabsch alignment separately for microphone and source arrays jointly:

1. Concatenate microphones and sources in a single point set so both sets share the same rigid transform.
2. Center estimated and ground-truth point sets.
3. Solve the orthogonal Procrustes problem. Record whether reflections are allowed. For a geometry-only distance estimator, reflection is observationally equivalent; the primary score should allow reflections, with a secondary proper-rotation-only score if handedness is relevant.
4. Translation-align the point sets; do not fit a scale because the speed-of-sound/TOA model is metric. A fitted scale may be reported only as a diagnostic and must not be used to improve the primary error.
5. Report microphone and source position errors separately: mean, median, RMSE, maximum Euclidean error in metres. Also report per-point errors, timing offset/emission errors after timing-gauge alignment, and pairwise distance residuals.

Report the following alongside errors: configuration dimensions, noise standard deviation and seed, missing count, convergence status, start count/winner, timing correction residual, rank residual, singular values/ratios, coordinate algebraic residual, corrected TOF validity count, alignment reflection choice, and failed trials. Aggregate across trials with number of attempted/successful runs and failure percentage; do not omit failed starts/trials from the success-rate accounting.

## Proposed acceptance gates

These are **engineering gates to review and tune**, not claims from the paper:

- Algebraic unit fixtures: four-term double difference equals `-2 Rbar Sbar^T` within floating-point tolerance for noiseless hand-calculated positions.
- Timing correction fixture: substituting known `e,o` into the [7] correction recovers the true double-difference matrix within floating-point tolerance.
- Gauge tests: synthetic time and coordinate gauge transformations preserve estimator inputs/outputs modulo the declared gauges.
- Noiseless generic geometry: successful runs achieve a relative pairwise-distance residual below a predeclared numeric tolerance, and alignment-aware coordinate errors below a predeclared metre tolerance. Thresholds must be chosen from precision and conditioning analysis before test results are observed.
- Noise tests: all metrics and failures are reported; no claim of robustness until a measured distribution over fixed seeds/configurations supports it.
- Degenerate/missing/invalid cases: typed failures are deterministic and no misleading coordinate result is emitted.
- Reproducibility: identical inputs/config/seed produce identical start vectors, statuses, diagnostics within documented floating-point tolerances.

Do not choose the numeric position/error gates after inspecting results. Record them with the eventual implementation commit and report any exceptions.

## Unresolved validation dependencies

- The 2016 literal Eq. (13) has a missing/ambiguous reference baseline relative to the cited four-term double difference; validation here targets the explicitly reference-derived matrix and separately tests/document the literal formula as a source comparison.
- 2016 does not define timing initialization, the nonlinear update, stopping tolerances, or missing-data behavior. This design's numerical choices must be validated and remain labeled BatSight engineering choices.
- Synthetic validation checks mathematical consistency and numerical behavior only. It does not validate peak detection, waveform acoustics, real-room robustness, or exact reproduction of the paper's full experiment.
