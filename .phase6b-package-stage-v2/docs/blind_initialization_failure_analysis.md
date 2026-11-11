# Phase 5C.14 — Blind Initialization Failure Analysis

## Scope and provenance

This is an exploratory diagnostic, not a production localization method. The runner reads the exact seed-11 blind 83-parameter starts archived in Phase 5C.11, the direct observation fixture, and the 390 first-order echo observations archived in Phase 5C.8. It checks the echo matrix against the archived record before running. C11, C12, and C13 artifacts are read-only; the new measurements are in `experiments/exploratory/phase5c14_results.json` and its concise run log.

The blind starts were constructed from TOAs and sound speed only: random gauge-fixed microphone/source coordinates at a TOA-derived metric scale; all timing parameters initialized to zero; six PCA-derived wall orientations and support gaps derived from those candidate points. Ground-truth geometry, clocks, emissions, and planes are used only to score outputs. The conditional timing ablation is a linear least-squares diagnostic conditional on candidate geometry, not a source-paper method. The wall-only fit uses the existing C9 residual and PCA start; true planes enter that routine only for reported plane errors, not its residual or initialization.

The joint residual is the unchanged C11/C12 distance-scaled objective (metres), with exact sorted first-order echo assignment for the primary runs. Joint refinements use the C12 analytic Jacobian, SciPy TRF, `x_scale="jac"`, tolerances `1e-11`, and an 80-function-evaluation cap. The original C11 forward-difference joint run is also reproduced from each exact archived starting vector. A frozen initial wall-ID/arrival-rank association is included only as an ablation, then scored against the original exact sorted objective. Results are not evidence of global uniqueness or infeasibility.

## Pipeline traced

1. **Direct-path TOA initialization:** the saved blind direct state already has large position and TOA errors. This is the earliest observed divergence.
2. **Coordinate recovery:** the random coordinates are not a solved estimate. In the direct-only ablation, direct residuals become small while aligned coordinate errors remain large, showing that residual reduction does not certify correct geometry.
3. **Timing estimation:** initial clocks and emissions are zero. A conditional linear fit can only fit additive timing terms given the incorrect coordinates; it worsens the direct residual in all three runs. Joint timing subsequently drifts substantially from the generating values in the poorer fits.
4. **Wall initialization:** PCA planes are computed from each candidate's coordinates, not the true room. Wall-only fitting lowers reflection residuals but generally does not reach zero, and two of three outcomes fail at least one finite-face bounce check.
5. **Echo association:** sorted assignment can change while the model moves. Freezing the initial assignment converges quickly by `xtol`, but leaves very large direct and echo residuals. This rules out interpreting optimizer termination alone as successful recovery; it does not isolate association switching as the cause of the sorted objective's failures.
6. **Joint refinement:** the saved blind PCA starts remain far from the exact reference. Direct-only, conditional-timing, wall-only, and frozen-association starts do not recover it within the fixed budgets.

## Measured stage summaries

Residuals are Euclidean norms over all 65 direct observations and all 390 echo observations. Position error is combined microphone/source RMSE after the documented rigid alignment. The exact per-run arrays, parameter vectors, wall diagnostics, association changes, optimizer metadata, singular values, and failure details are in the JSON artifact.

| Archived start | Initial direct norm (s) | Initial echo norm (s) | Initial combined position RMSE (m) | Direct-only final norm (s) | Direct-only position RMSE (m) | Sorted joint final direct / echo norms (s) | Sorted joint position RMSE (m) | Frozen-association final direct / exact-sorted echo norms (s) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| seed 17 | 0.05399 | 0.17909 | 3.342 | 4.96e-5 | 3.186 | 0.01294 / 0.03939 | 2.253 | 0.05388 / 0.17816 |
| seed 29 | 0.07624 | 0.18250 | 3.814 | 2.06e-4 | 1.347 | 0.01619 / 0.03864 | 3.517 | 0.07601 / 0.18158 |
| seed 41 | 0.05299 | 0.14585 | 3.497 | 1.68e-4 | 3.084 | 0.01794 / 0.04464 | 3.405 | 0.05289 / 0.14518 |

The three direct-only optimizers all exhausted the 80 evaluation budget (status 0). Their direct residual norms decreased by roughly 2–3 orders of magnitude, but the coordinate RMSE stayed between 1.35 and 3.19 m and clock/emission errors grew to millisecond scale. The seed-29 direct-only endpoint became invalid for the joint model due to coincident/invalid microphone/source coordinates. This is a recorded stage failure, not silently repaired.

The replay also recorded a `RuntimeWarning: overflow encountered in exp` from the inherited C6 direct-coordinate parameter decoder during optimizer exploration. It did not terminate the whole experiment, but it is consistent with the broad blind parameter search reaching extreme trial values. The subsequent invalid seed-29 candidate is explicitly rejected by the joint model; no clipped or substituted coordinates are used.

All three exact sorted joint runs from the original PCA starts ended with nonzero residuals and multi-metre errors. Two terminated by `ftol`/`xtol` before the budget; the seed-17 run hit the cap. The frozen-association fits each stopped by `xtol` after 16 evaluations, but retained approximately the entire initial residual (see table). Their full gauge-fixed Jacobians have rank 83 at the reported relative threshold and condition numbers approximately 77–86; thus those local diagnostics do not explain away the wrong solutions.

The conditional timing fit has a 65×17 design matrix of rank 17 and condition number 7.92 for all three starts. Its direct residual remains 0.0311–0.0382 s, and joint refinement from that timing-only update does not improve the corresponding PCA-start outcome materially.

Wall-only fitting reduced echo norms to 0.0992, 0.1406, and 0.1011 s. Starts 17 and 29 used 400 evaluations without convergence and ended with 388/390 and 387/390 finite-face bounce points, respectively. Start 41 terminated successfully after 113 evaluations and passed enclosure plus 390/390 finite-face checks, but its echo norm remained 0.1011 s. Thus a numerically successful wall optimizer and a valid enclosure are not sufficient to explain the echo data. None of these is a wall-recovery claim.

## Controlled interpretation by possible failure source

### A. Direct-path initialization — supported as the first divergence

**Evidence:** before any optimizer or wall fitting, direct residuals are 0.0530–0.0762 s and position RMSE is 3.34–3.81 m. Emission/clock vectors start at zero despite nonzero generating timing terms. This identifies the direct-path seed as already far from the generating state. It does not establish that direct-path initialization alone makes recovery impossible.

### B. Timing parameter estimation — supported contributor; causal role unresolved

**Evidence:** conditional additive timing LS, holding candidate coordinates fixed, does not absorb their geometric error and yields 0.0311–0.0382 s direct residual. Direct-only joint optimization can lower residual dramatically while producing 4.3–6.4 ms emission RMSE and 3.0–6.0 ms clock RMSE. These are measured outcomes. Since timing and coordinates are coupled in the full objective, they do not establish timing as the sole cause.

### C. Wall initialization — supported contributor; not an isolated explanation

**Evidence:** PCA walls are derived from poor candidate points. Wall-only fits remain far from zero echo residual; two runs are nonconverged and have invalid finite-face bounces. One run achieves enclosure and finite-face validity yet still has a 0.1011 s echo norm. Wall parameter errors and all plane values are retained in JSON. The experiment does not determine whether better data-derived wall starts would solve the jointly incorrect state.

### D. Echo association — plausible numerical complication, not established as primary cause

**Evidence:** the primary exact-sorted residual is piecewise smooth and can change associations; the frozen-association ablation removes that switching but terminates at large residuals close to its initial values. It does not recover truth and does not show that frozen association is an adequate model far from the solution. Association changes are recorded in JSON for each optimized stage. This ablation therefore fails to support assignment switching as a sufficient explanation, while leaving interactions with local minima unresolved.

### E. Joint optimization — supported as unable to bridge these starts under tested settings

**Evidence:** same-objective sorted analytic joint runs, direct-only-refined starts, timing-conditioned starts, and wall-only starts all remain non-exact. Some stop early by step/objective tolerances; others hit the 80-call cap. The frozen-association fits stop by `xtol` with poor residual. This supports a basin/initialization problem under the tested model and budgets, not a universal optimizer failure or infeasibility claim. C12's exact-reference perturbation tests show a local basin around the staged solution, but do not give a blind basin radius.

## Supported mechanisms and unresolved hypotheses

**Supported by these measurements:** divergence exists before joint refinement; residual-only direct fitting can select a geometrically wrong state; the zero timing initialization is inconsistent with this fixture; candidate-dependent PCA wall estimates do not supply a reliable wall recovery; successful termination does not imply echo consistency or correct geometry; the joint solver did not bridge the archived blind starts under the fixed budgets.

**Still unresolved:** whether a different TOA-only geometric initializer can enter the local basin; whether a better coupled coordinate/timing seed is required; the contribution of sorted-assignment crossings versus local minima and parameter scaling; whether any observed alternative is globally or physically equivalent; and whether more independent measurements improve the actual blind basin rather than only local Jacobian conditioning.

## Next scientifically justified experiment

Run a staged *ablation diagnostic* from the same saved blind vectors that holds geometry fixed and profiles timing, then holds timing fixed and profiles coordinates, before testing alternating blocks with the unchanged exact objective. Log each accepted/rejected block step, physical validity, assignment changes, and the same alignment-aware metrics. This directly distinguishes whether either block can improve when the other is temporarily fixed, without introducing an initializer or changing the scientific model. Treat it strictly as exploratory; compare against the archived exact staged positive control and use no truth in the start or objective.

## Artifacts and reproducibility

- Runner: `experiments/exploratory/phase5c14_blind_initialization.py`
- Machine-readable results (all starts, ablations, vectors, and diagnostics): `experiments/exploratory/phase5c14_results.json`
- Concise run log: `experiments/exploratory/phase5c14_run.log`
- Source baselines preserved: `phase5c11_*`, `phase5c12_*`, and `phase5c13_*` artifacts in `experiments/exploratory/`.

Run from the repository root with `python experiments/exploratory/phase5c14_blind_initialization.py`. The script uses the already configured NumPy/SciPy environment and requires no network or dataset download.
