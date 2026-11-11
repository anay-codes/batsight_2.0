# Unlabeled first-order echo association and dimension estimation

## Scope and evidence

Phase 5D.3 adds an exploratory calibrated shoebox method for known microphone/source positions, emission times, synchronized clocks, sound speed, and room frame. It estimates only `(Lx, Ly, Lz)` and assigns unlabeled echoes to the six first-order wall paths. It does not estimate coordinates, clocks, source times, arbitrary wall planes, or higher-order associations.

The forward TOA equations and image-source predictions are reused from Phase 5D.1/5D.2. The estimator does not use ground-truth wall labels. The alternating assignment strategy below is a BatSight engineering proposal; it is not attributed to the 2016 paper. The labeled Phase 5D.2 estimator remains the reference baseline and its residual objective, bounds, analytic Jacobian, and physical checks are unchanged.

## Input and provenance

The estimator consumes `CalibratedTOAObservationSet.unlabeled_echoes`. Each echo provides a microphone/event identifier, measured arrival time, optional positive timing standard deviation, and optional first-order hint. No wall identity is read. Non-observed missing/invalid echo records are counted and excluded; no time is invented for them. A missing echo is represented by the absence of a detected observation. Synthetic ground-truth wall labels are held separately by experiment code for post-run scoring only.

An `estimated_association` label provenance value was added for internal records created after association. This is distinct from `synthetic_ground_truth` and `external_annotation`; the conversion never asserts that the inferred label is true.

## Assignment objective

At candidate dimensions `L`, the shared predictor returns six first-order arrival times `t_hat[w]` for every microphone/event pair. For observed echo `k` with time `t_k`, a gated edge cost is

`c[w,k] = ((t_hat[w] - t_k) / sigma_eff[k])^2`,

where `sigma_eff[k] = max(sigma_k, association_scale_s, max_match_error_s / 3)`, using `association_scale_s` when the record has no standard deviation. Edges with absolute TOA difference greater than `max_match_error_s` are forbidden. The gate/3 scale keeps any admissible single-edge cost at most 9; with default miss and false-detection penalties of 9 each, a feasible match is not rejected solely because its raw residual approaches the configured gate. Penalties are dimensionless cost units.

For each microphone/event pair, a square-augmented linear assignment problem provides a one-to-one matching between up to six predicted wall paths and the detected echoes. Each unmatched predicted path pays `missing_path_penalty`; each unmatched observed echo pays `false_detection_penalty`. The objective sums the selected edge and dummy costs. This prevents duplicate echoes from being assigned to one wall and permits missing and false detections. The problem is solved independently per pair at each iteration; common dimensions couple pairs through the subsequent fit. It does not impose a global arrival ordering, and it never maps “earliest” to a fixed wall.

Ambiguity is flagged by forbidding each selected match edge in turn, resolving that pair's full one-to-one problem, and comparing the alternative assignment cost. A selected echo is marked ambiguous when the best alternative's total pair cost is within `ambiguity_cost_gap`. Since the assignment scale is deliberately broadened to one third of the gate when that exceeds a TOA uncertainty, this is a conservative ambiguity flag under the configured assignment cost; it is not a probability or a proof of exact physical non-identifiability. Results report both all-echo association accuracy and accuracy after excluding these flagged echoes so that this conservative screening does not hide errors.

## Alternating dimension fit

1. Begin from caller-supplied feasible dimensions. Starts must obey the Phase 5D.2 derived lower bounds and finite user-supplied upper bounds.
2. Predict six paths per pair and solve each augmented assignment.
3. Build internal fixed-association records: matched echoes receive `estimated_association` provenance; unassigned paths receive explicit missing states. Unmatched detections are counted as unassigned candidates and excluded from the dimension fit.
4. Call the unchanged Phase 5D.2 dimension estimator on those records.
5. Repeat from the updated dimensions until both the association signature and dimension update stabilize, or a fit fails / iteration limit is reached.

The labeled fit uses its original uncertainty policy: unweighted seconds if matched records have no uncertainty; uncertainty-standardized residuals when all matched records supply standard deviations. Mixed values require the explicit `dimension_default_uncertainty_s` option. The separate assignment cost scaling does not alter the dimension-fit objective.

This alternating method is non-convex and initialization-dependent. It can lock into self-consistent but incorrect wall labels and dimensions. Exact or near-equal arrivals can make associations unidentifiable from one pair; multi-pair geometry may help, but finite experiments do not establish uniqueness. Missing paths and false detections are distinguishable only through timing feasibility and configured penalties. A false detection within the time gate can be assigned to a real path and displace a true echo.

## Diagnostics and evaluation

The returned result includes per-iteration dimensions, matched paths, unassigned echo IDs, the identities of unmatched predicted paths, assignment objective, ambiguity flags, Phase 5D.2 fit diagnostics, changed assignments, termination status, and runtime. Unassigned detections are not automatically called false detections; without truth labels they may also be real echoes that the model failed to match. The estimator deliberately reports `association_accuracy=None`: accuracy requires hidden truth labels and belongs only in the experiment evaluator. The script computes overall association accuracy, accuracy excluding declared ambiguous echoes, false-association rates, dimension errors, TOA residuals, rank/condition, optimizer diagnostics, and physical validity after the estimator returns.

Synthetic evaluation includes complete randomized-order observations, multiple room dimensions/layouts, timing noise, omissions, explicit false detections, and an ambiguous-arrival geometry. A labeled Phase 5D.2 fit runs in parallel as a reference upper bound. Synthetic recovery is software evidence only. It is not real microphone support, measured acoustic accuracy, or reproduction of the paper's uncalibrated algorithm.

## Current limitations

- Correct calibration, known emissions/sound speed, synchronized clocks, axis alignment, and first-order-only detections are assumed.
- No real unlabeled recording has been validated; arrival detector false/missed rates and uncertainty calibration are unknown.
- Wall counts are fixed to six shoebox faces; the method cannot detect a non-rectangular room.
- The hard gate and unmatched penalties are engineering settings. Their suitability depends on TOA uncertainty and initialization scale.
- Convergence and a small residual do not imply correct associations. Inspect ambiguity, post-run label scores on synthetic tests, physical validity, and independent dimension error.
- Global uniqueness is unproven; results apply only to the deterministic tested fixtures.
