# Implementation plan

This is a staged roadmap, not evidence that inverse work has been implemented. Forward signal, shoebox simulation, synthetic direct-TOA, and forward experiment foundations exist. Inverse localization and room reconstruction remain unimplemented. The first release is prioritized around a rectangular shoebox mode; the broader arbitrary convex-polyhedral mode and its research record remain preserved. The exact 2016 Eq. (13) and Algorithm 2 discrepancies are preserved as open research issues; the reference-derived variant in `reference_derived_localization_design.md` must not be described as a verbatim 2016 implementation.

## Foundation — forward components implemented; research audit and architecture maintained

- Audit the full reference and separate supported facts, engineering proposals, and open questions.
- Establish package/API/client/test/experiment boundaries without algorithm code or UI styling.
- Document dataset provenance and validation criteria.

## Phase 2 — forward signal foundation (core implemented; capture/visualization deferred)

- Confirm chirp definition, sample conventions, speed-of-sound handling, and peak-finder interpretation from authoritative source/code.
- Define typed recording/event/channel metadata and dataset manifest schemas.
- Existing code provides generic sine/sweep generation, mono reference matched filtering and configurable peak detection; the paper chirp remains unresolved and must not be guessed.
- A recording/playback adapter and waveform/spectrogram presentation remain future work; any laptop mode is explicitly single-channel exploratory analysis.
- Do not report 3D room reconstruction from this mode. Existing matched filtering accepts mono inputs; channel-wise multichannel acquisition and calibration contracts remain future work.

## Phase 3 — synthetic data and mathematical primitives (forward work implemented)

- Implement reference-consistent image reflection, direct/first-/second-order TOFs, room simulator adapter, and coordinate conventions.
- Establish deterministic synthetic fixtures and hand-computable geometry cases.
- Recover/document cited microphone/source initialization equations and test observability/configuration limits. The design and validation specifications now exist; no inverse algorithm is implemented.

## Phase 4 — initial localization implementation (blocked after timing continuation investigation)

- A deterministic noiseless prototype did not converge within practical iteration budgets under the approved unregularized timing update.
- Gaubitch et al. (2013) Eq. (8) prints a penalty with a current-iterate superscript, while adjacent prose describes minimizing the corrected-matrix norm. A candidate-dependent interpretation was tested as a BatSight proposal; it biased timing estimates and failed the original convergence/recovery criteria. The literal fixed-current-iterate interpretation is an additive constant and cannot affect the update.
- The source does not specify the dependency/indexing and switch threshold sufficiently to accept a unique continuation algorithm. Keep regularization disabled; preserve the approved timing update and convergence criteria. Resolve the source ambiguity or approve a separately justified method before implementation resumes.
- A direct minimization of the discarded singular-value energy was also evaluated as an explicitly BatSight-derived proposal. Although it reached much smaller rank residuals quickly, seeded starts produced badly incorrect timing parameters; rank residual alone is not an adequate timing-identification objective. This method is not accepted for implementation.
- Phase 5C.3 established that the rank-only timing condition is locally non-unique for the exact `M=5,N=13` fixture: its gauge-fixed residual Jacobian has nine independent constraints for 17 timing unknowns, and exact local alternatives were found with positive corrected TOFs. Phase 5C.4 applied the approved Crocco coordinate objective to all three alternatives and the positive zero-start direct-rank candidate: each failed the metric residual gate in deterministic both-branch multi-start searches. The generating truth passed as a positive control. This is not a global search or proof that no alternative satisfies the full constraints; global uniqueness remains open. The scale redundancy in the coordinate-factor design was removed with a scalar log-scale and five-DOF traceless symmetric log-shape, covering all invertible factors up to the explicit condition cap.
- Phase 5C remains blocked: the approved timing procedure still has not met timing recovery criteria. Phase 5C.4 added only an isolated exploratory experiment and documentation; it did not accept a new timing optimizer or add production localization code.
- Phase 5C.5 investigated a separate direct Euclidean TOA joint fit. It recovered the seed-11 solution from the known state and deterministic local perturbations up to `0.5 m / 500 us`, but none of the tested blind coordinate/timing starts recovered it; some blind fits had small residuals with large geometry errors and Jacobian rank/conditioning failures. Planar geometry had rank 50/65, while a flattened nonplanar case remained full rank but was less well conditioned. This remains exploratory and is not accepted as either the paper's initializer or BatSight's standalone initializer. The paper-derived timing stage remains blocked.
- Phase 5C.6 tested blind initializers using only TOAs and sound speed. Zero timing followed by cross-distance rank-3 SVD and Crocco metric fitting repeatedly produced a seed-11 start that the direct TOA fit refined to the generating solution, including deterministic `0.5 m/500 us` perturbation. This is promising but fixture-specific: the noisy minimum-count experiment failed, while random/structured starts were inconsistent. A Gaubitch-derived path reached a distinct machine-precision TOA fit with different coordinates/timing, so global ambiguity is a material risk even when the local Jacobian is full rank. The proposal remains exploratory; no initializer is accepted for production and the approved paper-derived timing stage remains blocked.
- No inverse localization engine has been delivered. Keep the literal 2016 Eq. (13) separate for equation-level auditing.

## Phase 5 — inverse reconstruction (not started; strategy gate required)

- Prioritize a constrained rectangular shoebox estimator as the first release target, without making the general convex-room mode a permanent non-goal.
- Do not start an inverse optimizer until the measurement profile, independent room-dimension information, timing gauges, and echo association assumptions are approved. C17/C18 do not establish a generally reliable blind initializer.
- The existing paper's staged general-plane algorithm remains a separate research track; do not silently replace it with a rectangular method or call the latter a paper reproduction.

## Phase 5E — calibrated audio-to-shoebox experiments (5E.1 implemented; 5E.2 exploratory and not accepted)

- Phase 5E.1 extracts known-reference multichannel direct and unlabeled echo TOAs from synthetic audio. It does not infer wall labels and is not validated for real recordings.
- Phase 5E.2 adds an experimental clutter-aware assignment/consistency loop while preserving Phase 5D.2 and 5D.3. It uses explicit engineering gates and unmatched costs, then the unchanged labeled dimension objective.
- The 24-run synthetic comparison yielded strict dimension recovery in 0/24 for Phase 5D.3 and 0/24 for Phase 5E.2; the post-hoc labeled ceiling passed 18/24. The new loop was slower and did not improve recovery, so it is not approved as a production estimator.
- Review Phase 5E.1 extraction misses and candidate uncertainties, and investigate the 5E.2 failure cases under a predeclared ablation before any real-data or UI integration. Do not infer feasibility or accuracy outside the tested synthetic shoebox profile.
- Phase 5E.3 completed a frozen-observation gate/dummy/strength sensitivity audit without changing the estimators. None of the tested unlabeled settings met the existing recovery screen. Oracle post-hoc labels isolated accurate dimension fits for three sufficiently observed cases; the sparse symmetric case remained insufficient. Keep D5.3 and E5.2 exploratory, preserve the strict acceptance criteria, and review extraction coverage and association ambiguity before real-data work.
- Reproduce paper protocol and report alignment-aware position/plane metrics, inlier definitions, outliers, timing and failures.
- Add model-mismatch discussion and compare initialization against refinement.

## Phase 6 — research dataset evaluation

- Verify dataset source/license/content and ingest without modifying original data.

## Phase 6A — local application and backend foundation (implemented)

- Added a FastAPI application under `src/batsight/application/`, preserving the scientific package layout and existing estimators.
- Added SQLite/SQLAlchemy persistence for projects, WAV recording metadata, experiments, and compact results. Audio bytes remain in a configurable managed directory; upload validation enforces size, WAV parseability, channels, rate, sample count, and duration without resampling.
- Added project, recording, system, and experiment routes. Only the existing forward synthetic shoebox pipeline can currently be run through a threadpool-backed local background task. Output is explicitly marked synthetic and not a room reconstruction.
- Existing chirp/signal, audio loading, matched-filter/peak/TOA, simulation, and reconstruction modules are reached through small application service boundaries. No neural model, new reconstruction method, or frontend was added.
- Validation includes endpoint CRUD, uploads and cleanup, failure/status persistence, synthetic experiment result storage, and compatibility with the existing scientific tests. Phase 6B (frontend work) is not started; this local in-process task lifecycle does not survive server termination.

## Phase 7 — application integration

- Expose versioned FastAPI endpoints around stable engine schemas.
- Build React + TypeScript flows for separate laptop and multichannel research modes, signal plots, geometry view, and experiment reports.
- Add provenance and limitations to exported reports. No accuracy claims beyond measured validation.

## Rectangular-room MVP sequence (proposed; no implementation in this audit)

1. Freeze calibration profiles and data contracts: identify known/unknown positions, emissions, per-channel clocks, sound speed, room dimensions, path orders, associations and missingness.
2. Define one canonical shoebox geometry/parameterization and coordinate/time gauges, reusing the current simulator room model rather than duplicating it.
3. Research and gate an estimation strategy with matched-seed, multi-geometry synthetic competing-solution tests. This is the critical blocker.
4. Only after review, implement a small shoebox estimator with explicit diagnostics and failure outcomes.
5. Validate dimension/position/timing/reflection metrics on multiple synthetic rooms before evaluating real synchronized multichannel recordings.
6. Stabilize engine schemas before FastAPI/React integration. Laptop single-channel signal exploration remains a separate demonstration mode.

See `docs/rectangular_room_mvp_architecture.md`, `docs/rectangular_room_validation_plan.md`, and `docs/reconstruction_modes.md` for assumptions, module reuse and test criteria. No stage in this sequence is being implemented under the current audit.

## Proposed modular layout

The current source tree contains `signals/`, `simulation/shoebox.py`, `datasets/toa.py`, `experiments/pipeline.py`, plus empty `geometry/` and `optimization/` packages. A future least-disruptive target is:

```text
src/batsight/
  signals/                  # existing shared signal processing
  geometry/                 # future shared frame/protocol; shoebox and polyhedral models
  simulation/shoebox.py     # existing forward simulator remains authoritative
  simulation/polyhedral.py  # future only when needed
  datasets/                 # current synthetic TOA plus future recording manifests
  reconstruction/           # future rectangular and general estimators behind shared result types
  optimization/             # currently empty; numerical helpers after method approval
  experiments/              # current forward experiment pipeline
backend/                    # future thin FastAPI boundary
frontend/                   # future React + TypeScript client
experiments/ tests/ data/ research/ docs/
```

Do not create a second shoebox room type or a generic simulator abstraction before a second simulator exists. Preserve the arbitrary polyhedral estimator and research docs as a separate future mode. Packaging and dependencies for current forward modules are already established; no new dependencies are proposed here.

## Phase 5C.7 research status

The seed-11 competing-solution disambiguation study is recorded in `docs/initial_localization_implementation.md` and `experiments/exploratory/phase5c7_results.json`. Unknown convex containment did not discriminate endpoints; ideal first-order echoes were not blind-fit because that would require a latent wall/association solver; count/placement variants showed inconsistent blind recovery despite better local conditioning in some cases. No production optimizer or wall estimation is approved. Before Phase 5C can resume, define a scientifically supportable source of independent information and a test protocol that treats room planes and echo associations as unknown when relevant.


## Phase 5C.8 research status

The isolated unknown-wall reflection fit is documented in `docs/initial_localization_implementation.md` and `experiments/exploratory/phase5c8_results.json`. It fixes each archived direct-TOA endpoint and fits six arbitrary shared planes to ideal unlabeled echo TOA sets. Some runs found bounded enclosures, but none explained the observations to small residual or passed finite-face bounce checks, including the generating endpoint. Optimizer failure prevents any feasibility or disambiguation conclusion. A better validated wall/association optimization study is needed before considering reflection data as a competing-solution discriminator. This exploratory work did not add production wall estimation or start Phase 6.


## Phase 5C.9 research status

C9 identified and documented a source-plane dot-product defect in the isolated C8 predictor; the historical C8 script/results/log remain preserved. The corrected C9 predictor passes the exact oracle test, all deterministic local perturbations, and one generating-endpoint blind PCA start. The competing endpoint remains inadequately optimized, so reflection disambiguation is unresolved. Do not treat C8 residual comparisons as scientific evidence. Any next reflection study must use the corrected equation and solve both endpoints adequately before drawing a distinction. No production module or Phase 6 work was added.


## Phase 5C.10 research status

C10 tested 19 competing-endpoint data-derived starts, longer budgets, parameter scaling, assignment-aware blocks, offset/orientation parameter-block diagnostics, and face-penalty continuation. Some candidates satisfy all convexity and finite-face checks, but reflection residuals remain large. A high-penalty fit reaches all path checks with solver success but has rank `17/18`, condition above `1e20`, and millisecond-scale echo error. The generating endpoint regression remains exact. No competing-endpoint infeasibility or disambiguation conclusion is justified. Continue research on well-conditioned, adequately initialized unknown-wall fits or develop a valid infeasibility certificate before using reflections to distinguish endpoints.


## Phase 5C.11 research status

The isolated joint direct/first-order-reflection experiment is documented in `docs/initial_localization_implementation.md` and `experiments/exploratory/phase5c11_results.json`. It optimized 83 parameters against 455 measurements with equal per-observation distance-scaled residuals and separate physical feasibility checks. A staged, data-derived generating start recovered exact truth; the competing endpoint moved closer under a PCA start but retained millisecond-scale residuals, and blind starts failed physical checks. This neither proves infeasibility of the competing endpoint nor establishes uniqueness. No production module or Phase 6 work was added.


## Phase 5C.12 research status

C12 preserves C11 and validates an analytic echo Jacobian against central finite differences. It agrees to about `1e-10` relative Frobenius error on fixed-association smooth branches; the re-sorted check differs by about `0.85%` at PCA starts because predicted arrivals tie there. Both Jacobian variants recovered the staged reference from all tested deterministic perturbations through `1e-3` scaled per-coordinate RMS. Analytic derivatives improved, but did not solve, the non-exact PCA endpoint fits. Association nonsmoothness is confirmed as a numerical complication, not established as the only cause. The result is fixture-specific and does not establish global uniqueness or a production initializer. No production code or Phase 6 work was added.


## Phase 5C.13 research status

The isolated entropic-transport proposal is documented in `docs/initial_localization_implementation.md` and `experiments/exploratory/phase5c13_results.json`. The balanced transport envelope gradient matched directional finite differences, but the annealing run failed on extreme trial costs before completing the schedule for every start. Smooth-only endpoints were biased. Smooth-then-exact recovered the generating PCA start but not the competing PCA start; 17/18 local perturbations passed versus 18/18 for the exact sorted baseline. The method is not accepted; the competing endpoint remains unresolved. No production module or Phase 6 work was added.


## Phase 5C.14 research status

The exact three archived C11 blind starts were replayed through direct-only, conditional timing, wall-only, sorted joint, and frozen-association diagnostics. The first measurable divergence is at the direct blind seed itself (0.053–0.076 s direct residual and 3.34–3.81 m aligned coordinate RMSE). Direct-only optimization lowered residual by orders of magnitude without geometry recovery; joint fits remained non-exact. PCA wall fitting and frozen association did not isolate a single cause. This supports a coupled initialization/basin difficulty under tested settings, not global non-uniqueness or infeasibility. See `docs/blind_initialization_failure_analysis.md` and the C14 runner/results/log. Next, test controlled coordinate/timing block profiles using the unchanged objective before considering a new initializer. No production module or Phase 6 work was added.


## Phase 5C.15 research status

Timing-only, coordinate-only, and alternating optimization were profiled from the exact C11 blind vectors; the staged generating state served as an oracle positive control. The control stayed at machine precision. Conditional timing lowered the objective but increased timing errors when geometry was held fixed. Coordinate-only updates improved position RMSE to 1.73–2.44 m but did not recover truth. Eight accepted alternating cycles lowered objective by 84.6–92.5%, with final position RMSE 2.93–3.21 m and millisecond-scale timing errors. Assignment changes were concentrated in early coordinate updates. This shows partial objective progress but does not accept alternating blocks as an initializer or establish a universal failure mechanism. See `docs/timing_coordinate_block_analysis.md` and the C15 exploratory artifacts. No production modules or Phase 6 work were added.


## Phase 5C.16 research status

Thirty-six deterministic oracle-centered perturbations (two directions at each of three magnitudes) were evaluated under timing-only, coordinate-only, joint, and four-cycle alternating optimization. The staged reference passed its positive control. In this tested parameterization, pure timing perturbations were recovered through magnitude 0.4 by timing-only and joint fits; joint fits recovered both microphone/source/wall directions through 0.05; at 0.4, joint fits recovered both microphone directions, neither source or combined direction, and one of two wall directions. Alternating geometry updates did not meet the strict recovery thresholds within the cycle budget. This is a local, finite synthetic basin map, not blind recovery, a universal radius, or global uniqueness evidence. Two large-trial overflow warnings were retained. See `docs/local_convergence_basin_analysis.md` and the C16 exploratory artifacts. No production modules or Phase 6 work were added.

## Phase 5C.17 research status

Phase 5C.17 compared the existing zero-timing SVD/Crocco initializer, the existing reference-derived Gaubitch timing plus SVD/Crocco initializer, and the existing direct Euclidean TOA multistart across six deterministic synthetic cases. None recovered the minimum-count noiseless geometry under predeclared strict diagnostic screens. The timing-corrected Crocco route recovered its single larger, well-spread noiseless trial; direct multistart recovered two of five starts in that same case, but neither method generalized to the noisy cases. Low direct residual often coexisted with incorrect aligned geometry/timing, particularly below the cited count and for clustered noisy geometry. Missing TOAs were explicitly rejected because these methods require dense matrices. No initializer is accepted for production; source-count, spatial spread, timing variation, and noise effects are not fully isolated, and global uniqueness remains unproven. See `docs/direct_path_initialization_recovery.md` and the C17 script/results/log. Next, conduct a predetermined factorial study separating counts from placement diversity and timing offsets before selecting any initializer. No production modules or Phase 6 work were added.

## Phase 5C.18 research status

Phase 5C.18 compared the same three C17 methods in a matched-seed one-factor-at-a-time matrix covering microphone/source counts below, at, and above the reference-derived necessary values; uniform, clustered, and planar layouts; four timing levels; and three noise levels. Eight deterministic starts per method/cell used the same 500-evaluation direct-refinement budget. The truth-state gauge-fixed Jacobian had parameter nullity 9 for M4/N13, 3 for M5/N10, and 15 for the planar M5/N13 cell; nondegenerate full-count cases were full column rank locally. Multiple near-exact, substantially different geometries were observed in below-count cases, and the square M5/N13 baseline had a competing direct-fit pair with residuals near 1e-17 s and about 0.465 m pairwise aligned geometry RMSE despite full local rank at truth. Recovery varied by fixed geometry/start and was absent in all noisy cells under the strict screens. No method is accepted for production; no global uniqueness or infeasibility conclusion is made. The report, script, full results, and log are in `docs/direct_path_identifiability_study.md` and `experiments/exploratory/phase5c18_*`. The seed-varying pilot was preserved but excluded after audit because it did not isolate the OAT factors. Next, repeat selected count/layout cells across multiple independent geometry seeds with matched streams. No production modules or Phase 6 work were added.


## Phase 5D.1 — calibrated shoebox forward foundation (implemented)

- Added explicit calibrated inputs: known room-frame microphone/source positions, known emission times, known sound speed, common sample rate and synchronized-clock assertion.
- Added direct, simulator-labeled first-order, and real/unlabeled echo records with explicit uncertainty, missing/invalid states and provenance checks.
- Reused `ShoeboxRoom` as the one dimension/geometry type, exposing derived wall-plane and boundary-clearance helpers rather than adding a duplicate simulator room.
- Exposed a continuous path calculation shared by RIR synthesis and the deterministic direct-plus-six-first-order arrival predictor.
- Added hand-calculated, consistency, multi-event, boundary and observation-contract tests. This remains forward-only: no room-dimension optimizer, association solver or reconstruction claim.

## Phase 5D.2 — calibrated shoebox dimension estimator (implemented)

- Added a bounded three-parameter nonlinear least-squares estimator using only observed, labeled first-order reflection TOAs and the existing image-source predictor.
- Derived lower bounds from known positions and explicit clearance; finite upper bounds are caller-configured because the profile supplies no universal maximum room size.
- Added analytic dimension derivatives, uncertainty-weighted or unweighted timing residuals, per-wall observation accounting, local Jacobian rank/conditioning, optimizer diagnostics, bound flags, and strict interior checks.
- Direct paths and unlabeled echoes are counted and excluded. Missing/invalid labeled records are excluded explicitly. Each axis requires an observed maximum-wall reflection; minimum-wall echoes alone do not constrain dimensions.
- Added deterministic multi-room exact/noisy recovery checks and a reproducible experiment script. Its synthetic measurements are not real-world accuracy evidence.

## Phase 5D.3 — unlabeled first-order echoes (exploratory implementation)

- Added per-microphone/event augmented Hungarian matching between six shared shoebox predictions and unordered detections, with explicit missing-path and false-detection costs and a hard timing gate.
- Alternates inferred assignments with the unchanged Phase 5D.2 bounded dimension fit. Inferred labels carry `estimated_association` provenance; synthetic ground-truth labels remain outside the estimator.
- Added assignment-level ambiguity checks by comparing each selected matching against an alternative with that edge forbidden.
- Deterministic synthetic cases recovered dimensions and all non-ambiguous associations in tested complete, noisy, missing, false-detection, and alternate-layout fixtures. Exact arrival ties are reported as ambiguous; this is synthetic-only evidence and does not establish global uniqueness.
- Historical files and the labeled baseline remain preserved. No frontend/backend or Phase 6 work was added.

## Phase 5E.1 — multichannel audio to unlabeled TOA extraction (implemented)

- Added calibrated-channel matched-filter analysis using the known reference waveform and existing two-stage peak detector.
- Added known-geometry direct-path windows, excess-delay echo candidate windows, local parabolic sub-sample interpolation, robust response-strength diagnostics, duplicate suppression, and a rejection audit.
- Echo candidates remain explicitly unclassified; no first-order identity or wall label is inferred. The adapter preserves detection strength, missing direct states, and synthetic/file provenance without passing simulator labels.
- Added WAV PCM/float input with exact sample-rate validation and no silent resampling.
- Five deterministic synthetic audio cases achieved 100% direct detection. First-order recall was 91.7–95.8% in four broader layouts and 66.7% in a close-arrival case; the dimension fit had errors up to 0.81 m and 1.23 m, respectively. No real-recording support or accuracy claim is made.

### Next review-gated milestone

Review extraction windows, thresholds, candidate audit, and the separation between extraction and reconstruction results before any real-data work. Real calibrated analysis needs synchronized multichannel recordings, known chirp/emission times, surveyed microphone/source positions, sound speed, and independently justified TOA uncertainty. Preserve the general convex-polyhedral research branch.

## Phase 6B — frontend application and Sound Studio (implemented)

- Added the React/TypeScript/Vite/Tailwind application shell with collapsible navigation, live backend status, active-project context, and pages for Overview, Projects, Sound Studio, Signal Analysis, Experiments, Recordings, and Settings.
- Connected the client to the actual project, recording, experiment, health, and system-info endpoints through a centralized API client.
- Added minimal API adapters required by the inspected contracts: generic engineering waveform WAV response, original managed-WAV download, and bounded selected-channel recording analysis using existing signal services. See `docs/api_reference.md` for contracts and limits.
- Sound Studio provides generic sine/sweep generation and download, waveform preview, playback controls, MediaRecorder capture with original-format preservation, explicit decoded WAV-copy export, and WAV upload. It does not silently resample or label single-device recording as synchronized multichannel acquisition.
- Signal Analysis shows actual waveform/spectrogram/correlation data and backend peaks marked unclassified. It does not infer direct-path/echo labels.
- Experiment UI creates/runs only `synthetic_forward`, displays persisted output, and labels it synthetic known ground truth rather than estimated geometry or real-room validation.
- No reconstruction or 3D geometry estimation is included in Phase 6B.
