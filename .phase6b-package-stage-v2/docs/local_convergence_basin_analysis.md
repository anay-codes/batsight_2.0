# Phase 5C.16 — Local Convergence Basin Mapping

## Scope and experimental provenance

This finite deterministic sweep measures local recovery around the exact staged generating solution archived in C11 and used for the C15 reference. Each run starts from a reproducible perturbation of that reference. These are **oracle-derived basin diagnostics**, never blind initialization, and do not provide evidence that a blind method can find the basin. Ground truth is used only after optimization to align and score results.

The exact 65 direct TOAs and 390 sorted-within-group first-order echo observations are reloaded from C11/C8 and checked for exact agreement. C11–C15 experiment files are not modified. The residual, distance-unit scaling, gauges, wall parameterization, exact sorted objective, C12 analytic Jacobians, and existing convex/finite-face checks are unchanged.

## Recovery criteria set before the sweep

A run counts as recovered only if all of these hold at its final state:

- Direct residual norm ≤ `1e-9 s` and exact sorted echo residual norm ≤ `1e-9 s`.
- Rigidly aligned combined microphone/source coordinate RMSE ≤ `1e-6 m`.
- Emission-time RMSE and microphone clock-offset RMSE each ≤ `1e-9 s`.
- Maximum wall-normal angular error ≤ `1e-4 degrees` and maximum aligned wall-offset error ≤ `1e-6 m`.
- Convex enclosure valid, every image path and corrected TOA positive, and all 390 reflection bounce points on finite faces.

These are BatSight’s numerical recovery thresholds for this exact noiseless fixture. They are intentionally checked in addition to optimizer termination. At the staged control, the starting residuals are approximately `8.1e-17 s` direct and `1.6e-16 s` echo; timing-only, coordinate-only, joint, and alternating controls remain recovered at machine precision.

## Perturbation and optimization protocol

Perturbations use the existing 83-entry optimizer vector with four RMS magnitudes: `0.001`, `0.05`, and `0.4` (three magnitudes; all but the smallest extend beyond the C12 local perturbation range), with two seeded random directions at each magnitude. Each perturbation changes exactly one group, except the combined group:

| Group | Optimizer-vector indices (half-open) | Interpretation |
|---|---:|---|
| Microphone coordinates | `[0, 9)` | Three free microphones’ gauge-fixed parameters |
| Source coordinates | `[9, 48)` | Thirteen source positions |
| Microphone clock offsets | `[48, 53)` | Five clocks |
| Source emission times | `[53, 65)` | Twelve free emissions; `e0=0` remains fixed |
| Wall parameters | `[65, 83)` | Six azimuth/elevation pairs and six log support gaps |
| Combined | `[0, 83)` | Independent perturbations to all entries |

The random direction in each selected block is normalized to unit RMS before multiplying by its listed magnitude. Position variables are scaled by the existing characteristic length, timing variables by the existing timing scale, wall azimuth/elevation are in radians, and wall gaps are represented by log variables. Consequently, magnitudes are comparable within a parameter block but **are not equal physical displacements across different blocks**. In the combined group, equal RMS in native optimizer coordinates is an explicit diagnostic convention.

All modes start from the same complete perturbed vector. A is timing-only (`[48,65)`); B is coordinate-only (`[0,48)`); C is joint (`[0,83)`); D alternates timing then coordinate updates for at most four cycles, holding wall parameters fixed. Each solve uses SciPy TRF, `x_scale="jac"`, existing analytic Jacobian columns, `ftol=xtol=gtol=1e-11`, and at most 80 evaluations. A block proposal is accepted if the full exact-sorted objective is finite and no greater than its predecessor by more than `1e-12 * max(1, objective)`. Alternation stops when cycle objective improvement is at most `1e-12 + 1e-10*abs(previous objective)`. These are documented exploratory controls, not paper parameters.

The wall parameterization expresses each plane offset relative to the current point support plus a positive exponential gap. Therefore, changing microphone/source coordinates while holding the 18 wall variables fixed can still change the implied plane offsets. This model coupling is preserved and is visible in the recorded plane errors; it is not silently treated as independent geometric planes.

## Recovery rates by parameter block and magnitude

Each cell is recovered runs / two deterministic directions under the predeclared full recovery test.

| Perturbed block | Magnitude | Timing-only | Coordinate-only | Joint | Alternating (4-cycle cap) |
|---|---:|---:|---:|---:|---:|
| Microphones | 0.001 | 0/2 | 2/2 | 2/2 | 0/2 |
| Microphones | 0.05 | 0/2 | 2/2 | 2/2 | 0/2 |
| Microphones | 0.4 | 0/2 | 1/2 | 2/2 | 0/2 |
| Sources | 0.001 | 0/2 | 2/2 | 2/2 | 0/2 |
| Sources | 0.05 | 0/2 | 2/2 | 2/2 | 0/2 |
| Sources | 0.4 | 0/2 | 0/2 | 0/2 | 0/2 |
| Emission times | 0.001 | 2/2 | 0/2 | 2/2 | 2/2 |
| Emission times | 0.05 | 2/2 | 0/2 | 2/2 | 2/2 |
| Emission times | 0.4 | 2/2 | 0/2 | 2/2 | 2/2 |
| Clock offsets | 0.001 | 2/2 | 0/2 | 2/2 | 2/2 |
| Clock offsets | 0.05 | 2/2 | 0/2 | 2/2 | 2/2 |
| Clock offsets | 0.4 | 2/2 | 0/2 | 2/2 | 2/2 |
| Wall parameters | 0.001 | 0/2 | 0/2 | 2/2 | 0/2 |
| Wall parameters | 0.05 | 0/2 | 0/2 | 2/2 | 0/2 |
| Wall parameters | 0.4 | 0/2 | 0/2 | 1/2 | 0/2 |
| Combined | 0.001 | 0/2 | 0/2 | 2/2 | 0/2 |
| Combined | 0.05 | 0/2 | 0/2 | 2/2 | 0/2 |
| Combined | 0.4 | 0/2 | 0/2 | 0/2 | 0/2 |

The complete results JSON contains both directions’ exact perturbation vectors, every initial/proposal/cycle state, direct and reflection residual norms and maxima, aligned microphone/source RMSE, timing and wall errors, singular values/rank/condition, optimizer status/message/evaluations/runtime, echo-order changes, enclosure validity, and finite-face counts.

## Findings

### Parameter-block dependence

- **Timing-only and joint solves** recovered all tested pure emission-time and pure clock-offset perturbations through magnitude `0.4`. Because all other state blocks began at the exact solution, these are comparatively favorable conditional tests. Coordinate-only solves did not recover those cases because timing stayed perturbed.
- **Coordinate-only and joint solves** recovered all microphone-coordinate and source-coordinate perturbations at `0.001` and `0.05`. At `0.4`, joint optimization recovered both microphone directions but neither source direction. Coordinate-only recovered one microphone direction and neither source direction. The source-coordinate block is therefore the more fragile of those two blocks in this finite sweep, especially at the largest tested magnitude.
- **Wall-only perturbations** were recovered by joint optimization in both directions through `0.05`, and one of two directions at `0.4`. Timing-only and coordinate-only could not recover the wall parameters they held fixed. Alternating also held walls fixed, so its failure on this group is expected by construction and does not measure its ability to optimize walls.
- **Combined perturbations** were recovered by joint optimization in both directions at `0.001` and `0.05`; no method recovered either `0.4` combined perturbation. This is the clearest tested limit for the local joint solve, but two directions do not establish a basin boundary.

### Joint versus block optimization

Joint optimization was strongest for the tested coordinate, wall, and combined perturbations. Timing-only is sufficient for pure timing perturbations. Coordinate-only can recover pure microphone/source perturbations at small and medium tested magnitudes, but not the large source perturbations. Alternating timing/coordinate updates reached recovery for pure timing perturbations, but none of the coordinate or combined perturbations met the strict thresholds within four cycles. For many of those, residuals and geometry error improved substantially; the cycle cap and occasional 80-evaluation block cap mean this is **failure within the configured budget**, not proof the alternating method cannot converge.

### Direction and optimizer termination

The outcomes depend on direction: at magnitude `0.4`, coordinate-only recovered one microphone direction but neither source direction; joint recovered both microphone directions but neither source direction; joint wall recovery passed one direction; and no combined direction recovered. Optimizer status alone was not sufficient: some runs terminated by `ftol`, `xtol`, or `gtol` without meeting the scientific thresholds, while some successful recovery runs also terminated normally. Full Jacobian ranks, condition numbers, and block-specific diagnostics are recorded for each run; local full rank did not guarantee recovery from the larger starts.

Two overflow warnings (`overflow encountered in exp`) were observed in the inherited C6 microphone-coordinate decoder during high-amplitude trial evaluations. The optimizer was not given clipped replacements. The warning events are retained in the results and run log; their presence is a numerical risk for the largest combined perturbations. Final states were independently scored for finite values and physical checks.

## Limits of inference

This is a single noiseless fixture, with two random directions per parameter block and magnitude. It maps selected rays/blocks from one exact solution, not a volume in the full 83-dimensional space. Magnitudes use mixed native scaled variables, and the wall-offset parameterization is coupled to point support. The results cannot establish a universal convergence radius, global uniqueness, infeasibility, or blind recovery performance. No solver, objective, initializer, or production method is accepted by this experiment.

## Artifacts

- Script: `experiments/exploratory/phase5c16_basin_mapping.py`
- Full machine-readable data: `experiments/exploratory/phase5c16_results.json`
- Run log: `experiments/exploratory/phase5c16_run.log`

Replay with `python experiments/exploratory/phase5c16_basin_mapping.py`. If an interrupted checkpoint exists, the script resumes only missing deterministic cases and rewrites the final log without duplicate checkpoint entries.
