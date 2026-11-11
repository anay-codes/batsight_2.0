# Calibrated shoebox dimension estimation

## Scope and provenance

This is Phase 5D.2's bounded engineering estimator for a fixed, axis-aligned rectangular room. It estimates only `(Lx, Ly, Lz)`. Microphone and source coordinates, emission times, synchronized clocks, and sound speed are supplied by the calibrated Phase 5D.1 profile. Wall labels are required for reflection records. This does not implement the uncalibrated 2016 pipeline, unknown echo association, general polyhedral walls, or Phase 6.

**Measurement-model basis:** the image-source TOA model already implemented by BatSight: an arrival equals known emission time plus image-source propagation distance divided by known sound speed. The Phase 5D.1 predictor shares image-source path generation with the RIR simulator.

**Engineering estimator choices:** bounded SciPy trust-region reflective least squares; analytic dimension Jacobian; finite user-specified upper bounds; explicit interior clearance; uncertainty-standardized residuals when uncertainties are supplied; rank/conditioning and physical diagnostics. These choices are BatSight implementation decisions, not claims about the paper's prescribed reconstruction algorithm.

## Equations and information

For a known source `s_j`, microphone `m_i`, event time `e_j`, and speed `c`, a labeled first-order arrival at wall `k` is

`t_ijk(L) = e_j + ||s'_{j,k}(L) - m_i|| / c`.

For each axis `a`, reflection at the minimum wall has image coordinate `s'_{a}= -s_a`, independent of `L_a`. At the maximum wall, `s'_{a}=2L_a-s_a`; the other two image coordinates equal the source coordinates. Thus minimum-wall TOAs have zero derivative with respect to room dimensions. Direct TOAs also have zero dimension derivative and are excluded from the objective.

For a maximum wall on axis `a`, with distance `d=||s'-m||`,

`∂t/∂L_a = 2(s'_a-m_a)/(c d) > 0`,

because both endpoints are strictly inside the candidate dimension. The residual is defined as measured minus predicted, so its Jacobian entry is the negative of this derivative. Other dimension columns are zero. Consequently, one usable labeled maximum-wall observation per axis is a necessary coverage check for a three-dimensional estimate in this fixed calibrated model. This coverage check is necessary, not a general robustness guarantee. Rank and conditioning are evaluated at the fitted state.

The objective residual is `r_n = t_n^measured - t_n^predicted`. If every used reading supplies a positive standard deviation `σ_n`, residuals are divided by `σ_n`; under independent Gaussian timing errors, this is the conventional standardized least-squares objective. If no uncertainties are supplied, raw seconds are minimized under an unweighted equal-variance engineering model. Mixed specified/missing uncertainty values require an explicit positive `default_uncertainty_s`. Zero uncertainty is rejected because it represents an exact constraint rather than a finite statistical weight.

## Bounds and physical checks

The lower bound for each dimension is the largest coordinate among all known microphones and source events, plus the requested minimum interior clearance and a floating-point safety gap. This origin-at-minimum-corner frame is inherited from `ShoeboxRoom`. The estimator validates all known positions inside each evaluated candidate room.

No universal maximum room size follows from the data model, so callers must supply finite upper bounds. The starting dimensions must be strictly between derived lower and configured upper bounds. A bound-near solution is flagged. A configured bound can influence an estimate; it is reported in the result.

## Observation handling

- Only observed, labeled first-order reflection TOAs enter fitting.
- Missing and invalid labeled reflections are excluded and counted by wall.
- Direct paths and unlabeled echoes are excluded and counted. Unlabeled echoes are not sorted or associated by this estimator.
- Minimum-wall reflections are included in the reported raw residual/objective even though their dimension Jacobian is zero; they can expose model inconsistency but cannot identify dimensions.
- At least one usable maximum-wall reflection on each axis is required. Otherwise the result is `insufficient_information`, with no optimizer invocation.

The `objective_value` is SciPy's `0.5 * ||residual||²`, in squared seconds when unweighted and dimensionless standardized units when weighted. Raw residual statistics are always reported in seconds. Jacobian singular values refer to the residual Jacobian, including the selected weighting. Rank uses the configured relative singular-value threshold. A full-rank Jacobian is local sensitivity evidence only, not proof of global uniqueness.

## Output and failure interpretation

`ShoeboxDimensionEstimate` returns the candidate dimensions, bounds, counts, weighting mode, objective and raw residual statistics, Jacobian rank/spectrum/condition, optimizer termination/evaluation data, boundary clearances, bound proximity, and warnings. `converged` means numerical termination plus rank 3 and requested strict interior validity. It is not an accuracy certification. `optimizer_failed`, `insufficient_information`, and `invalid_physical_solution` are distinct states. Numerical rank below three after fitting is reported as `insufficient_information`, even if the numerical optimizer terminated successfully.

## Synthetic validation

`experiments/shoebox_dimension_recovery.py` creates deterministic labeled synthetic TOAs using the existing forward predictor, then estimates from starts selected independently of each truth. It reports per-case dimension errors, residual statistics, rank/conditioning, exclusions, and optimizer diagnostics. These controlled synthetic checks validate implementation behavior only; they are not real-room accuracy evidence or an exact paper reproduction.

## Limitations and next work

The estimator assumes exact room-frame calibration, exact source emission times, synchronized microphone clocks, known sound speed, axis alignment, a rectangular room, correct first-order wall labels, and the image-source propagation model. It does not estimate positions, timing, sound speed, wall identity, or room pose; it does not model frequency-dependent absorption, detection failures beyond explicit record states, reverberant overlap, or non-rectangular geometry. Before use with real data, independently validate calibration uncertainty, wall labeling, timing uncertainty, and model adequacy. No measured real-world performance is claimed.
