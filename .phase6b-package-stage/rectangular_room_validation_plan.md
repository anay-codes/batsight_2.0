# Rectangular-Room MVP — Validation Plan

## Validation boundary

This plan separates checks of the existing forward tools from future inverse-reconstruction claims. The current package has tests for signal processing, a shoebox forward simulator, a forward TOA experiment pipeline and a synthetic direct-path TOA dataset. It has no production inverse estimator. Phase 5C's exploratory direct/echo solvers are not a validation substitute for a released estimator. No test result below is preclaimed.

Synthetic results must be reported as synthetic. Real multichannel validation must be a separate evidence section with recording provenance, synchronization/calibration facts, excitation/reference provenance, and any known ground truth. Do not call laptop-only echo analysis full 3D reconstruction.

## Stage 0 — measurement and data contract

Before inverse testing, freeze the experiment profile for each run:

- `M` microphone channels and `N` emissions, with explicit index mapping and data orientation `[microphone, emission]`.
- Known/unknown room dimensions, room/world pose, microphone/source positions, source emission times, per-microphone clock offsets and sound speed.
- Direct-path versus reflected-path event type, reflection order if known, peak confidence, false/missed detection status and association availability.
- Per-channel sample rate and time origin; measured interchannel skew/drift; calibration provenance.
- Noise estimate and missing-observation mask. Existing `TOAObservationDataset` supports a missing mask for forward synthetic data. Existing exploratory initializers require complete matrices; an inverse MVP must reject missing entries until a mask-aware method has been validated.
- Coordinate and time gauge, axis labeling, reflection/axis-permutation conventions and metric units.

The initial synthetic inverse target should use known `c`, explicitly modeled timing, and complete observations. Other profiles are separate experiments, not silent toggles.

## Stage 1 — preserve forward-model correctness

Reuse the current hand-calculated and deterministic tests as regression gates:

- Hand-check direct, first-order and second-order image-source distance/TOF cases.
- Verify the six wall identifiers, deterministic enumeration, duplicate-image handling and reflection coefficient product.
- Validate source/microphone interior checks and fractional-sample impulse placement.
- Check multichannel convolution, seeded noise, reference-rate checks, matched-filter lag sign and peak thresholds.
- Round-trip direct-path TOA datasets with nonzero independent emission times/clock offsets, noise and masks.
- Run `run_experiment` tests for direct/first-/second-order expected paths, missed/false peaks, CSV and deterministic replay.

These confirm the current forward implementation under its conventions; they do not validate an inverse estimator or full room acoustics.

## Stage 2 — shoebox geometry/parameter tests

Once an estimator-only shoebox parameter model is approved, test:

- At least three room sizes spanning aspect ratios (e.g. compact, near-cubic, and elongated) as engineering fixture choices.
- Axis-aligned canonical boxes first; arbitrary pose only after frame/gauge handling is specified.
- Orthogonality, three opposing parallel face pairs, six-face closure, positive dimensions, finite values, source/mic containment and wall-normal orientation.
- Equivalent boxes under global rigid transforms and box-axis permutations/reflections; expected gauge-equivalent solutions should align under the documented convention.
- Invalid, nearly zero dimensions; points on a wall; near-coplanar or clustered placements; symmetries that make axes indistinguishable.

The test fixtures must not encode a ground-truth room into blind initializers. Oracle configurations are reserved for forward and local optimizer positive controls.

## Stage 3 — direct-path-only diagnostic

Direct paths test localization variables, not room dimensions: `q_ij=e_j+||s_j-m_i||/c+b_i+eta_ij`. The room dimensions do not occur in this equation. Containment in an unknown rectangle is an inequality and cannot by itself identify the box size. Therefore:

- Include a negative/control test showing the direct-only observation Jacobian has no sensitivity to the three dimension parameters if they are included.
- Compare counts below/at/above the reference-derived necessary counts with full-rank, planar, clustered and near-degenerate point placements.
- Report gauge-fixed Jacobian singular values, numerical rank, right near-null parameter-block energy, direct residual and aligned position/timing errors.
- Preserve C18-style competing-solution search: multiple starts, low-residual endpoint comparisons, geometry/timing errors and explicit caution that finite starts do not prove uniqueness.
- Do not report a room-dimension estimate from a direct-only fit unless independent boundary data or reflection observations supply that information.

C17/C18's counts M≥5,N≥13 are cited necessary values for the reference model, not guarantees. Rectangular room constraints do not erase the measurement-model ambiguity automatically.

## Stage 4 — reflection-aided shoebox synthetic tests

Use the existing shoebox image-source simulator to create reproducible, labeled oracle paths first, then a separately evaluated unlabeled observation set. Cover:

| Factor | Suggested test cells |
|---|---|
| Room dimensions | Multiple aspect ratios and absolute scales; fixed `c` and documented scale gauge |
| Microphone/source distribution | 3D spread, boundary-near interior, clustered, planar, symmetric and near-degenerate |
| Timing | Known zero offsets as a unit fixture; known nonzero independent offsets/emissions; unknown timing with explicit gauges; separately calibrated clock profile |
| Reflection order | Direct only (localization diagnostic), direct + first order, then second order after first-order validation |
| Echo associations | Oracle wall labels as equation positive control; unlabeled echo sets with association inferred; ties, crossings, false and missed echoes |
| Noise | Noiseless floating-point control; selected timing-noise levels including 20 and 100 microseconds as BatSight engineering scenarios; waveform noise at declared SNRs |
| Missing observations | Complete baseline; deterministic masks only after a mask-aware objective exists; current behavior is reject, not impute |

For each run retain generating inputs, exact software settings, all initial estimates, optimizer status/evaluations/runtime, predicted and observed path sets, correspondence changes, rejected physical constraints and complete failures. Compare optimizer-positive-control results separately from blind recovery.

### Metrics

- Length, width and height absolute error and relative error, after resolving axis permutation.
- Room pose translation and rotation error only when an external world frame is supplied; otherwise align room-local frames.
- Microphone and source position RMSE after the selected rigid/discrete gauge alignment.
- Emission-time and clock-offset error after applying the documented time gauge.
- Direct and reflection TOA residual norm, RMS and maximum; peak-to-path matched, missed and unmatched counts.
- Wall-plane normal angular error, support offset error, parallel/orthogonality residuals, enclosure convexity and all source/microphone containment checks.
- Positive propagation times, valid image paths and finite-face bounce checks where modeled.
- Gauge-fixed Jacobian rank, scaled singular values, condition and near-null directions.
- Competing-endpoint distances after alignment, including whether multiple geometries satisfy the declared residual criterion.

Measurement fit, physical feasibility and geometric recovery are separate pass/fail columns. Optimizer `success=True` alone never counts as reconstruction success.

### Success criteria

Define thresholds before the blind experiment. Exact synthetic fixtures should use precision-based tolerances verified by an oracle positive control. Noisy thresholds should be tied to declared noise, repeated-seed distributions and the selected scientific use case. Do not import C17's engineering screens as validated application accuracy. Require all of:

1. Correct model/units/gauges and finite parameters.
2. Direct/reflection residuals consistent with the known synthetic noise model.
3. Valid box constraints and all assigned paths physically valid.
4. Room dimensions and positions within preregistered aligned thresholds.
5. Repeatability across multiple deterministic geometries and blind starts.
6. No materially different low-residual geometry left unexplained; report unresolved competitors rather than selecting one by hidden prior.

If known anchors or calibration priors are used, validate them as a separate profile and report them as independent information, not observations recovered by the estimator.

## Stage 5 — real synchronized multichannel validation

Do not begin until a suitable dataset or controlled recording protocol is available. Verify license and metadata before ingest. Required evidence includes:

- At least multiple independently timestamped microphone channels or a documented synchronization calibration.
- Channel geometry if known; otherwise a separately evaluated uncalibrated profile.
- Source-event positions or a declared unknown-source setup, source trigger/emission timestamps if available, and environmental sound-speed estimate.
- Raw samples, channel sample rates/time bases, clipping/gain/device settings, excitation waveform provenance and session metadata.
- Ground truth for room dimensions/pose and sensor/source locations for evaluation, kept out of blind initializers.

Validate channel clock offsets and sample alignment first. Compare measured direct/echo candidates with predictions; report missed/false paths and model mismatch. Use a held-out room/session if enough data exist. Synthetic success must not be presented as real-world accuracy.

## Stage 6 — laptop single-microphone demonstration validation

Use a generic engineering excitation, record the microphone/device chain, display waveform/spectrum/matched-filter output and present threshold peaks as exploratory acoustic observations. Validate sample-rate metadata, clipping, playback/recording latency, noise floors, and repeatability. A single stationary channel does not provide the paper's multi-microphone spatial diversity or calibrated time origins and must not display a complete 3D reconstruction as a validated result. If later using a moving microphone, each pose and clock time needs independent tracking/calibration and a new identifiability analysis.

## General convex-room research mode

Preserve the existing general-room equations, references, open questions, and Phase 5C scripts/results unchanged. It requires its own future suite for arbitrary plane feasibility, reflection association, plane estimation, second-order updates, nonconvex optimizer behavior and real dataset evaluation. Shoebox tests are not evidence for polyhedral performance. Maintain separate validation reports and never silently constrain the general mode to orthogonal walls.
