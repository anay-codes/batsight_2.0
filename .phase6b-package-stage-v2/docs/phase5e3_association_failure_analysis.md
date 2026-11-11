# Phase 5E.3 — Association failure analysis and parameter sensitivity

## Purpose and preservation

This diagnostic investigates the Phase 5D.3 Hungarian association and Phase 5E.2 clutter-aware association while preserving both implementations and the Phase 5D.2 dimension fitter. No estimator code or historical results were changed. The runner is `experiments/phase5e3_parameter_sensitivity.py`; its complete 92-fit output and four oracle fits are in `experiments/phase5e3_parameter_sensitivity_results.json`.

All experiments are synthetic. Ground-truth path order and wall labels are applied only after each unlabeled fit to score results. The separate oracle dimension fit uses post-hoc labels explicitly to isolate the extractor plus dimension fitter; those labels are never passed to either unlabeled method.

## Assignment objective audit

For one microphone/event pair, let (W=6) be the possible walls and (E) the observed echo candidates. The augmented one-to-one assignment has real wall/detection edges and dummy choices for an unmatched predicted wall and an unassigned detection.

**Phase 5D.3.** A valid edge has

\[
c_{we}=\left(\frac{t_w-\hat t_e}{\sigma_e^*}\right)^2,
\quad \sigma_e^*=\max(\sigma_e,\sigma_{assoc},g/3),
\]

where (g) is the hard timing gate. Invalid edges outside (|t_w-\hat t_e|\le g) receive `missing_path_penalty + false_detection_penalty + 1e12`. A missing wall costs `missing_path_penalty`; an unassigned detection costs `false_detection_penalty`; dummy-to-dummy costs zero. The matching therefore compares a real edge against the combined cost of leaving both endpoints unmatched. The measurement uncertainty affects only the unchanged Phase 5D.2 fit; the assignment scale is floored at (g/3).

**Phase 5E.2.** The valid edge uses the same squared normalized timing residual, with σ floored by `max(reading uncertainty, association_scale_s, gate/3)`. A forbidden edge or edge outside the hard gate gets a prohibitive cost. Dummy costs are `missing_path_penalty` and `clutter_penalty`. When enabled, the edge additionally pays `strength_weight * (1 - quality_e)`, where `quality_e` is min/max-normalized `log1p` detection strength within that mic/event pair. Missing strengths receive a neutral quality value of 0.5. After fitting dimensions, an assignment edge whose residual exceeds `max(consistency_gate_s, 3 sigma)` is forbidden for later iterations. This is persistent edge deletion, not a soft penalty.

The assignment has a useful cost identity. If (k) matches are made, the dummy part of the objective is ((W-k)P_{miss}+(E-k)P_{clutter}). Thus the match-count tradeoff depends on the **sum** (P_{miss}+P_{clutter}); swapping unequal costs while holding their sum fixed does not change the optimum in this complete augmented assignment. The values still allocate reported objective cost between miss and clutter, but do not express different behavior by themselves. This explains why `(1,9)` and `(9,1)` produced identical assignments in the tested cases.

At the common 6 ms gate, σ floor is 2 ms, so an edge exactly at the hard gate has timing cost (3^2=9), before strength penalty. With 9+9 dummy costs, it is far cheaper to match than leave both endpoints unmatched. Even at 25+25, however, the tests rarely changed selected assignments because relevant valid edges had costs below the combined dummy cost and the hard gate/iteration history dominated. At low 1+1 penalties, real matches become less competitive when edge cost exceeds 2; this can create more misses. No penalty was selected based on dimension error.

## Experimental design

The script creates each audio/TOA dataset once, then holds it fixed across parameter variations. Four Phase 5E.2 scenario profiles are used at seed 17 with the first predetermined start `(4.7, 4.6, 4.0) m`, bounds `(8.5, 8.0, 7.0) m`, 48 kHz sample rate, a 10 ms generic 900 Hz–11 kHz sweep, second-order simulated RIRs, and the unchanged Phase 5E.1 extractor. The generic sweep is an engineering signal, not the paper's unresolved chirp.

| Case | Room dimensions for scoring | Noise | Reflection coefficient | Placement/clutter characteristic |
|---|---:|---:|---:|---|
| Nominal asymmetric | (4.5, 4.2, 3.6) m | noiseless | 0.70 | Four microphones, three events |
| Noisy asymmetric | (5.4, 4.8, 3.8) m | 30 dB SNR | 0.70 | Alternate calibrated layout, two events |
| Weak reflections | (4.8, 4.4, 3.7) m | 18 dB SNR | 0.16 | Four microphones, three events |
| Close-arrival symmetric | (4.0, 4.0, 3.0) m | noiseless | 0.70 | One microphone and one event; deliberately low information |

Each recording includes simulator paths through reflection order two. The extractor determines omissions and candidates. Two false TOAs per case are injected with no strength metadata. Higher-order echoes and extractor artifacts remain unlabeled candidates. Thus missing first-order paths are represented by audio-extraction misses; no missing path is imputed.

The 92 fits comprise, for both D5.3 and E5.2, four gates at fixed 9/9 dummy penalties; six dummy-cost pairs at a fixed 6 ms gate; and, for E5.2 only, three strength weights. That is 23 fits per case. The four oracle labeled fits use only extracted candidates post-hoc matched to first-order simulator paths. The matching and geometry estimators receive no truth labels.

Fixed method settings: `association_scale_s=1e-4`, E5.2 `consistency_gate_s=5e-4`, ambiguity gap 1, 20 association iterations, 400 dimension-fit evaluations. Gates are 2, 6, 12, and 25 ms. Missing/clutter penalty pairs are (1,1), (3,3), (9,9), (25,25), (1,9), and (9,1). E5.2 strength weights are 0, 0.25, and 1.

The original recovery screen is unchanged: optimizer status must be `converged`, physical validity must pass, maximum axis error must be ≤ 0.05 m, and every axis percentage error must be ≤ 2%.

## Metric definitions

- **First-order detection recall** = candidate TOAs post-hoc matched to true first-order paths / all simulated first-order paths. Extraction timing mismatch or an absent peak reduces this value.
- **Association precision** = correctly assigned detected first-order candidates / all assigned detection-wall pairs.
- **Association recall (conditional)** = correctly assigned detected first-order candidates / detected candidates mapped post-hoc to first-order paths. This is conditional on extraction; use detection recall separately to see end-to-end misses.
- **Association accuracy (classified detections)** = correct first-order wall assignments plus known clutter candidates left unassigned / all detections with a post-hoc class (first-order, higher-order, or injected false). Candidates not confidently mapped to a simulator path are excluded; classification coverage is also recorded. The many clutter negatives can make accuracy appear high, so precision and recall are more informative.
- **False assignment rate** = (all assignments minus correct first-order wall assignments) / all assignments. Unknown-class detections assigned to a wall count as false for this diagnostic.
- **Missed first-order path count** = all simulated first-order paths minus correctly associated detected first-order paths. It includes extractor misses and association misses.
- **Unassigned detection count** is the number of extracted/injected observed echo candidates the estimator left unmatched. **Unmatched predicted wall count** is the estimator's count of possible wall paths left without a candidate (D5.3 reports its corresponding count).
- Dimension errors are post-run estimate-minus-truth quantities only. The report includes mean absolute axis error, max axis error, and per-axis percentage errors. Truth dimensions are not estimator inputs.
- TOA residual is the dimension fitter's RMS residual on its assigned observations, not an association correctness metric. A low residual does not show the correct wall labels.

## Comparison at the existing 6 ms operating point

For D5.3, use 6 ms, 9/9 penalties. For E5.2, use 6 ms, 9/9, strength weight 0.25, matching the Phase 5E.2 default. The oracle is a separate D5.2 dimension fit with post-hoc detected-first-order labels.

| Scenario | Extracted first-order recall | D5.2 oracle status / max axis error | D5.3 max axis error / association P / conditional R | E5.2 max axis error / association P / conditional R | E5.2 status |
|---|---:|---:|---:|---:|---|
| Nominal asymmetric | 0.708 | converged / 0.0016 m | 0.441 m / 0.333 / 0.471 | 0.963 m / 0.338 / 0.471 | max iterations |
| Noisy asymmetric | 0.854 | converged / 0.00085 m | 0.547 m / 0.333 / 0.390 | 2.291 m / 0.511 / 0.585 | max iterations |
| Weak reflections | 0.292 | converged / 0.00115 m | 0.183 m / 0.225 / 0.762 | 1.335 m / 0.259 / 0.714 | max iterations |
| Close-arrival symmetric | 0.333 | insufficient information / n/a | 0.935 m / 0.167 / 0.500 | 0.935 m / 0.167 / 0.500 | converged |

Across these four matched cases, none of the three methods passes the strict recovery screen at its default unlabeled setting; the oracle labeled diagnostic fits three cases closely and finds the symmetric one under-observed (two labeled echoes). D5.3 reports convergence in all four despite large geometry errors. E5.2 converges in one case and reaches the iteration cap in three. Mean max-axis error is 0.527 m for D5.3 and 1.381 m for E5.2 at weight 0.25. Both estimates are physically valid under the estimator's box constraints in these runs, showing that physical validity alone is insufficient.

At that operating point, across cases, D5.3 has mean association precision 0.265, conditional recall 0.531, false-assignment rate 0.735, TOA RMS 0.241 ms, and runtime 0.14 s/run. E5.2 at strength weight 0.25 has precision 0.318, conditional recall 0.568, false-assignment rate 0.682, TOA RMS 0.780 ms, and runtime 0.48 s/run. Mean first-order detection recall is 0.547 across four audio scenarios. Each average covers only four fixed synthetic cases; runtime is machine-specific.

## Timing gate sensitivity

Each row averages the same four recordings with penalties fixed at 9/9 and E5.2 strength set to zero, isolating the gate. All 16 fits converged for D5.3; E5.2 converged in one of four cases at each gate. No setting passed room recovery.

| Method | Gate | Mean max-axis error | Precision | Conditional recall | False assignment rate | Mean unmatched predicted paths |
|---|---:|---:|---:|---:|---:|---:|
| D5.3 | 2 ms | 0.494 m | 0.280 | 0.578 | 0.720 | 0.5 |
| D5.3 | 6 ms | 0.527 m | 0.265 | 0.531 | 0.735 | 0.25 |
| D5.3 | 12 ms | 0.527 m | 0.265 | 0.531 | 0.735 | 0.25 |
| D5.3 | 25 ms | 0.527 m | 0.265 | 0.531 | 0.735 | 0.25 |
| E5.2 | 2 ms | 0.679 m | 0.301 | 0.527 | 0.699 | 5.25 |
| E5.2 | 6 ms | 1.490 m | 0.274 | 0.482 | 0.726 | 4.0 |
| E5.2 | 12 ms | 1.662 m | 0.286 | 0.530 | 0.714 | 3.0 |
| E5.2 | 25 ms | 1.677 m | 0.267 | 0.485 | 0.733 | 3.25 |

Tightening to 2 ms modestly improved average dimension error for both methods but still missed the strict criterion in every case. The D5.3 results beyond 6 ms were identical at the aggregate level because the additional allowance did not change selected assignments on these observations. E5.2 became worse on average as the gate widened, while missed-wall count fell; assigning more questionable candidates is consistent with the increased error but does not establish a causal mechanism.

## Dummy penalty sensitivity

The table is the 6 ms gate sweep. Cost pairs are `missing, clutter`; all estimates failed the strict recovery screen. D5.3 assignments and outcomes were identical across the tested penalties. E5.2 varied because edge banning and refitting feed back across iterations.

| Method | Missing/clutter pair | Sum | Mean max-axis error | Precision | Conditional recall | Mean unassigned detections | Mean unmatched predicted paths |
|---|---:|---:|---:|---:|---:|---:|---:|
| D5.3 | 1/1 | 2 | 0.527 m | 0.265 | 0.531 | 158.5 | 0.2 |
| D5.3 | 3/3 | 6 | 0.527 m | 0.265 | 0.531 | 158.5 | 0.2 |
| D5.3 | 1/9 or 9/1 | 10 | 0.527 m | 0.265 | 0.531 | 158.5 | 0.2 |
| D5.3 | 9/9 | 18 | 0.527 m | 0.265 | 0.531 | 158.5 | 0.2 |
| D5.3 | 25/25 | 50 | 0.527 m | 0.265 | 0.531 | 158.5 | 0.2 |
| E5.2 | 1/1 | 2 | 0.722 m | 0.297 | 0.518 | 165.0 | 6.8 |
| E5.2 | 3/3 | 6 | 1.287 m | 0.279 | 0.527 | 161.0 | 2.8 |
| E5.2 | 1/9 or 9/1 | 10 | 1.384 m | 0.282 | 0.506 | 162.0 | 3.8 |
| E5.2 | 9/9 | 18 | 1.490 m | 0.274 | 0.482 | 162.2 | 4.0 |
| E5.2 | 25/25 | 50 | 1.490 m | 0.274 | 0.482 | 162.2 | 4.0 |

Lower dummy totals made E5.2 leave more paths unmatched and marginally improved the dimension error average, but not enough to pass. Raising the total above 18 had no measurable effect in these fixtures. The identical 1/9 and 9/1 results are predicted by the dummy-cost identity, not evidence that misses and clutter have identical physical meaning.

## Strength evidence sensitivity

Only E5.2 uses this optional term. The weight multiplies an uncalibrated, within-pair log-strength rank penalty on a proposed match; it is neither a probability nor part of the Phase 5D.2 dimension objective. The injected false detections have no strength field and receive the implementation's neutral quality treatment.

| Strength weight | Mean max-axis error | Precision | Conditional recall | False assignment rate | Recovery passes |
|---:|---:|---:|---:|---:|---:|
| 0 | 1.490 m | 0.274 | 0.482 | 0.726 | 0/4 |
| 0.25 | 1.381 m | 0.318 | 0.568 | 0.682 | 0/4 |
| 1 | 1.628 m | 0.352 | 0.610 | 0.648 | 0/4 |

Larger weight raised precision/conditional recall on these four cases but did not recover dimensions; at weight 1 the average dimension error worsened relative to 0.25. Post-hoc median detection strength was higher for first-order than higher-order candidates in all four cases, but absolute scales varied by orders of magnitude with signal/noise conditions. Within first-order paths, the strongest median wall differed: z-min for nominal and weak-reflection, z-max for noisy alternate, and only two walls had detected examples in the symmetric case. This is insufficient for a universal wall-strength rule. The 25th/75th percentile summaries are in the JSON; percentile overlap and per-pair variation mean a stronger candidate is not a reliable wall identity.

## Failure decomposition

### A. Audio extraction

First-order detection recall ranged from 0.292 (weak reflections) to 0.854 (noisy alternate), with mean 0.547. The close-arrival symmetric case detected only 2 first-order paths out of the 6 possible. In the explicit oracle diagnostic, the detected first-order labels let the unchanged dimension fitter estimate the first three rooms within 1.7 mm maximum-axis error. It returned `insufficient_information` on the symmetric case with only two labeled observations. This supports an extraction/observation-coverage limitation in that case, while showing that extraction alone does not explain the other failures.

### B. Association

At the default operating points, D5.3 precision averaged 0.265 and E5.2 precision 0.318. False assignment fractions were 0.735 and 0.682. Many detections remain unmatched because the audio extractor also captures higher-order and other candidates; yet the subset actually assigned still contains substantial wrong or clutter assignments. Changing the hard gate can move this tradeoff but did not produce correct room dimensions. D5.3's assignment ambiguity diagnostic averaged 47.25 flagged candidates in these runs; E5.2 averaged 38.25. These are assignment-level warnings, not probabilities.

### C. Geometry fitting

Three post-hoc oracle-label fits converged and were accurate to millimetres using the exact same Phase 5D.2 objective. Unlabeled fits frequently converged with much larger dimension errors (D5.3 four of four; E5.2 one of four at its default settings). This isolates bad associations as a major contributor in the identifiable cases. The close-arrival case remains underdetermined even with oracle labels, so it is an information/configuration limitation as well. The oracle test only labels detected first-order candidates and does not restore paths missed by extraction.

### D. Ambiguity and alternating rejection

The close-arrival symmetric configuration has one microphone and one event, so wall arrivals are sparse and symmetric; its oracle fit is insufficient. E5.2's post-fit edge bans created unmatched paths (mean four at default vs 0.25 for D5.3) and reached `max_iterations` in three of four cases. The bans can remove a questionable edge, but the experiment does not show they consistently lead to a better assignment; they can instead produce cycling/reassignment and geometry drift. This behavior is observed, but the finite sweep does not isolate whether gate rejection, assignment ambiguity, or poor starting dimensions is causal.

## Conclusion and limitations

The strongest evidence points to (1) missing/low-quality first-order candidates in weak-reflection and close-arrival audio, (2) substantial wrong correspondence among candidates that are assigned, and (3) an alternating E5.2 feedback loop that often fails to stabilize. The original D5.2 fitter is accurate on three oracle-labeled detected sets, so incorrect associations—not simply optimizer termination—explain much of the dimension error in those cases. In the symmetric sparse case, correct associations are still insufficient.

No parameter sweep setting satisfies the predeclared room recovery screen. Gate 2 ms and lower E5.2 dummy costs are diagnostic tradeoffs, not recommendations; selecting them because their mean error is lower would be tuning on four evaluation cases. Reflection strength offers a modest association signal in this experiment, but it is not calibrated, wall-specific, or adequate alone. These results do not establish global uniqueness, infeasibility, or real-world accuracy.

## Reproduction

From the project root:

```powershell
$env:PYTHONPATH = 'src;experiments'
python experiments/phase5e3_parameter_sensitivity.py
python -m pytest -q --basetemp=.pytest-tmp-phase5e3
```

The experiment writes the full per-run metrics (dimension errors, association scores and denominators, path counts, TOA residuals, rank/condition, physical validity, statuses, evaluations, ambiguities, and runtime) to the adjacent JSON. No estimator, baseline, or recovery threshold is modified.
