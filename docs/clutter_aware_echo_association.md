# Phase 5E.2 — Clutter-aware echo association

## Scope and status

This is an exploratory, synthetic-only extension for the calibrated axis-aligned shoebox path. It consumes the Phase 5E.1 audio-derived unlabeled TOA candidates and known calibrated microphones, source events, emission times, synchronized clocks, and sound speed. It estimates only room dimensions and echo associations. It does not estimate positions or timing, and it is not real-recording validation.

The Phase 5D.2 labeled dimension objective and Phase 5D.3 Hungarian estimator are preserved. The new `estimate_dimensions_clutter_aware` procedure is an experimental candidate and is not accepted as a production method: in the predeclared 24-run synthetic matrix it passed the dimension recovery screen in 0/24 runs.

## Association procedure

For each microphone/event pair and current shoebox dimensions, the existing first-order predictor supplies up to six candidate wall arrivals. Each observed candidate is matched one-to-one with at most one wall. The cost matrix is augmented with dummy assignments so that a detection can remain unassigned (clutter) and a predicted path can remain unmatched (missed reflection). An explicit maximum TOA-error gate disallows implausible real matches. Costs use squared timing residual normalized by the larger of the declared timing scale and the gate-derived scale. Optional strength ranking contributes a weak relative tie-break cost; it is not interpreted as a probability and defaults to zero in the API.

After each assignment pass, the estimator calls the unchanged Phase 5D.2 dimension estimator using only assigned observations. It evaluates each assigned echo against the shared fitted box. Edges exceeding `max(consistency_gate_s, 3 sigma)` are forbidden in later passes; the detection remains available to match another wall or to be left unassigned. Iteration stops on stable assignments and dimensions or the configured iteration budget. Ambiguity diagnostics compare the selected assignment with an alternate assignment after forbidding selected edges within each pair.

These dummy penalties, gates, strength tie-break, ambiguity gap, and rejection loop are BatSight engineering choices. They are not described as the 2016 paper's algorithm. They do not change the Phase 5D.2 dimension objective. The procedure does not assert a global optimum or prove that rejected detections are physically false.

## Data provenance and scoring

Synthetic recordings are generated using the existing shoebox simulator through second order and analyzed with the Phase 5E.1 extractor. A fixed small number of extra candidate TOAs are injected as clutter. The estimator receives only unlabeled echoes. Simulator path order/wall labels are matched to extracted candidate times only after each fit for evaluation. The separately reported Phase 5D.2 upper-bound run receives these post-hoc first-order labels; it is not a blind method and is not a fair information-equivalent competitor.

The extraction recall metric counts extracted first-order candidates against all simulated first-order paths; it therefore reflects missed paths as well as extraction quality. Association accuracy is computed only on detected first-order candidates that the estimator assigned. Clutter rejection combines detected higher-order candidates and explicitly injected false detections. These are distinct outcomes.

## Experiment settings

`experiments/shoebox_clutter_aware_recovery.py` runs four fixed room/layout/reflection/noise cases, two seeds per case, and three initial-dimension starts per case (24 matched comparisons). The starts are predetermined and not derived from room truth. All methods receive the same unlabeled extracted dataset, except the explicitly labeled Phase 5D.2 ceiling. The common recovery screen requires a converged status, physical validity, maximum absolute dimension error no greater than 0.05 m, and maximum per-axis relative error no greater than 2%. This is a diagnostic screen for these synthetic cases, not an accuracy claim.

The association settings are: 6 ms maximum candidate-to-prediction gate, 0.5 ms post-fit consistency gate, missing-path and clutter penalties 9, optional strength weight 0.25, and maximum 20 association/fit iterations. The unchanged dimension fitter receives at most 400 evaluations per fit. Room upper bounds and initial starts are explicitly listed in the script and result JSON.

## Results

The generated complete JSON is `experiments/shoebox_clutter_aware_recovery_results.json`.

| Method | Recovery passes | Mean max axis error among returned fits | Mean detected first-order candidate recall | Mean first-order association accuracy | Mean clutter rejection |
|---|---:|---:|---:|---:|---:|
| Phase 5D.2 with post-hoc labels (upper bound) | 18/24 (75%) | 0.00124 m among 18 fits | 0.550 | Not applicable | 1.000 |
| Phase 5D.3 Hungarian | 0/24 | 1.204 m | 0.550 | 0.744 | 0.863 |
| Phase 5E.2 consistency rejection | 0/24 | 1.175 m | 0.550 | 0.730 | 0.866 |

For the labeled upper bound, 6/24 cases were `insufficient_information` because audio extraction did not supply the wall coverage needed by the unchanged dimension fitter. All 24 Phase 5D.3 runs returned `converged`, demonstrating that solver termination alone did not imply dimension recovery. The Phase 5E.2 method converged in 6/24 and reached its iteration cap in 18/24; its mean fit residual RMS was about 0.687 ms versus 0.277 ms for Phase 5D.3. Mean runtimes were about 1.14 s and 0.38 s per run, respectively, on the measured environment. Runtime is environment-specific.

The new procedure slightly increased mean clutter rejection in this particular scoring set but reduced association accuracy and did not improve the strict dimension recovery rate. No universal or real-world performance conclusion follows from these four synthetic cases. The symmetric case, weak reflections, extractor misses, and higher-order candidates remain challenging. A converged fit with a small residual can still be geometrically wrong.

## Limitations and next gate

- The observations are generated synthetically, and the calibration inputs are exact.
- The echo-strength term is only a within-pair rank heuristic; it has no calibrated acoustic likelihood model.
- Hard Hungarian assignments and edge forbidding remain discrete and can cycle or settle at a wrong assignment.
- The current consistency gate may reject valid noisy first-order observations or retain a coherent false assignment.
- The method has finite dimension bounds and shoebox assumptions; it does not apply to general convex rooms.
- Metrics are evaluated on extracted candidates, so missed reflections cannot be assigned by this estimator.
- No real microphone recording, robust uncertainty calibration, or global identifiability result is established.

The next justified work is a review of candidate extraction/uncertainty and failure cases, then a focused, predeclared ablation of assignment gates and missing/clutter costs on the same cases. Do not treat this exploratory version as a replacement for Phase 5D.3 until it passes recovery criteria across independent configurations and measured data.
