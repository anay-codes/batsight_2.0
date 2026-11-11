# Phase 5C.18 — Direct-Path Identifiability Study

## Scope

This is a deterministic, exploratory one-factor-at-a-time (OAT) study of the three existing C17 approaches. It adds no production initializer and changes neither the TOA model nor the objective. The archived 2016 printed Equation 13 remains distinct from the reference-derived four-term formulation used by SVD/Crocco. This report does not describe the latter as a literal correction or reproduction of the printed equation.

## Mathematical formulation retained

For microphone `i` and source event `j`, the forward model is

`q_ij = e_j + ||s_j - m_i||/c + b_i + eta_ij`,

where `q,e,b,eta` are seconds, positions and distances are metres, and sound speed `c` is m/s. The time-origin gauge is `e_1=0`; microphone offsets remain independent. The direct-fit coordinate gauge fixes microphone 1 at the origin, microphone 2 on positive x, and microphone 3 in xy with positive y. Evaluation uses rigid alignment (allowing the discrete reflection) before position RMSE. This removes continuous translation/rotation and time-origin gauges; it does not guarantee identifiability of the remaining variables.

The reference-derived centered double difference for complete data is

`G_ij = d_ij^2 - d_i1^2 - d_1j^2 + d_11^2 = -2 (r_i-r_1)^T (s_j-s_1)`,

with `d_ij=c(q_ij-e_j-b_i)`, shape `(M-1) x (N-1)`, and rank at most three for exact Euclidean 3D. The timing stage uses the existing C6 `T+A(p)+Gamma(p)` implementation and general bilinear correction, followed by rank-3 SVD and Crocco's general quadratic metric constraints. Both determinant-sign branches remain in its coordinate fitter. Rank-3 consistency alone is not a Euclidean metric fit. Method C minimizes the existing direct Euclidean TOA residual. No equations or solver models were changed.

The gauge-fixed direct-fit unknown count is `4M+4N-7`; its Jacobian is built from the analytic derivatives of the original measurement residual. The generating-state Jacobian is diagnostic evaluation only. For a `(MN) x P` Jacobian, `rank` uses relative singular-value cutoff `1e-8`. Reported condition is the largest divided by smallest *reported nonzero row-space singular value*; parameter nullity `P-rank` is reported separately. The Jacobian is evaluated with the implementation's scaled parameter vector and residual (`length_scale`, `time_scale` from TOAs), so condition values are scale- and threshold-dependent. Weak right-singular directions are summarized by energy in microphone, source, clock, and emission parameter blocks. Local rank is not a global uniqueness test.

## Factorial design and protocol

The corrected run uses 12 fixed cells. Every cell shares independent random streams for microphone positions (seed 51800), source positions (51801), emission times (51802), clock offsets (51803), and measurement noise (91800). Thus count changes preserve prefixes of the corresponding point arrays; timing and noise contrasts reuse the same standardized draws. The room dimensions `(8,7,5) m` are generator-only and are not supplied to any initializer. The generator fixes `c=343 m/s`.

| Cell | M | N | Spatial distribution | Clock/emission standard deviation | TOA noise standard deviation |
|---|---:|---:|---|---:|---:|
| Baseline | 5 | 13 | Uniform 3D | 0.5 ms / 0.5 ms | 0 |
| Microphones below | 4 | 13 | Uniform 3D | baseline | 0 |
| Microphones above | 7 | 13 | Uniform 3D | baseline | 0 |
| Sources below | 5 | 10 | Uniform 3D | baseline | 0 |
| Sources above | 5 | 17 | Uniform 3D | baseline | 0 |
| Clustered | 5 | 13 | Clustered 3D, sigma 0.30 m | baseline | 0 |
| Planar | 5 | 13 | Coplanar microphones and sources | baseline | 0 |
| Timing zero | 5 | 13 | Uniform 3D | 0 / 0 | 0 |
| Timing low | 5 | 13 | Uniform 3D | 0.10 ms / 0.10 ms | 0 |
| Timing high | 5 | 13 | Uniform 3D | 4 ms / 4 ms | 0 |
| Noise low | 5 | 13 | Uniform 3D | baseline | 20 us |
| Noise high | 5 | 13 | Uniform 3D | baseline | 100 us |

These levels compare below/at/above the reference-derived necessary-count values `M>=5,N>=13`; those counts are not claimed sufficient. Each factor cell changes only its named factor from the baseline. The fixed streams mitigate random realization changes but do not make spatial distribution a causal population study; each distribution has one deterministic realization.

For each method/cell, eight deterministic starts were attempted. Methods A/B use eight deterministic Crocco-fit seeds; method B's timing vector is obtained once per cell by the existing 100-outer-iteration Gaubitch-derived timing stage. Method C uses three existing deterministic Halton starts and five fixed-seed random-coordinate starts. Every direct Euclidean refinement uses the same existing TRF least-squares objective, analytic direct-path Jacobian, `x_scale='jac'`, tolerance settings inherited from C6, and `max_nfev=500`. Initializer-stage work differs by method and is not equal wall-clock cost; all direct-refinement budgets are equal. Rejected candidates and optimizer failures remain in the results.

Initializers receive only measured `q`, `c`, counts, derived scales, their fixed/candidate timing vector, and deterministic seed. The truth-bearing object is only used by the post-fit evaluator. The script creates it separately from a blind problem object used by method C's start generator.

Recovery screens reuse C17's declared engineering criteria, not paper tolerances: noiseless residual norm `<=1e-8 s`, aligned coordinate RMSE `<=1e-3 m`, and emission/clock RMSE `<=1e-7 s`; noisy residual norm `<=3 sigma sqrt(MN)`, coordinate RMSE `<=max(1e-3 m,5c sigma)`, and each timing RMSE `<=max(1e-7 s,5 sigma)`. Fit and recovery pass rates are separate. Start successes are counted before refinement separately from recovery after refinement.

## Results

Each cell has 8 external start attempts per method. Some starts were rejected before a direct refinement (including invalid/nonpositive corrected TOAs or invalid coordinate states). The table gives **measurement-fit passes / completed refinements; geometry-and-timing recoveries / completed refinements**.

| Cell | A zero timing SVD/Crocco | B Gaubitch + SVD/Crocco | C direct TOA multistart | Truth Jacobian rank / P; condition |
|---|---:|---:|---:|---:|
| Baseline M5,N13 | 1/8; 1/8 | 0/8; 0/8 | 3/7; 2/7 | 65/65; 8.95e3 |
| M4,N13 | 8/8; 0/8 | 8/8; 0/8 | 6/8; 0/8 | 52/61; 2.01e2; nullity 9 |
| M7,N13 | 0/8; 0/8 | 0/8; 0/8 | 4/8; 4/8 | 73/73; 7.35e2 |
| M5,N10 | 0/8; 0/8 | 0/8; 0/8 | 4/8; 0/8 | 50/53; 1.96e3; nullity 3 |
| M5,N17 | 0/8; 0/8 | 0/7; 0/7 (1 rejected) | 3/8; 3/8 | 81/81; 3.85e3 |
| Clustered 3D | 0/0; 0/0 (8 rejected) | 0/0; 0/0 (8 rejected) | 0/6; 0/6 (2 rejected) | 65/65; 8.93e3 |
| Planar | 0/7; 0/7 (1 rejected) | 0/8; 0/8 | 0/8; 0/8 | 50/65; 1.58e16; nullity 15 |
| Zero timing | 0/8; 0/8 | 0/8; 0/8 | 3/8; 2/8 | 65/65; 8.91e3 |
| Low timing | 0/8; 0/8 | 0/8; 0/8 | 3/8; 2/8 | 65/65; 8.91e3 |
| High timing | 0/0; 0/0 (8 rejected) | 0/0; 0/0 (8 rejected) | 4/8; 3/8 | 65/65; 9.70e3 |
| 20 us noise | 0/8; 0/8 | 0/8; 0/8 | 5/7; 0/7 (1 rejected) | 65/65; 8.96e3 |
| 100 us noise | 7/8; 0/8 | 0/8; 0/8 | 7/8; 0/8 | 65/65; 8.99e3 |

No raw blind initialization met both strict geometry and timing thresholds before direct refinement in these cells. Direct refinement produced recoveries on the baseline, M7, M5/N17, zero/low/high timing cells, but results depended strongly on the configuration and start. In particular, direct multistart recovered 4/8 for the fixed M7 cell and 3/8 for M5/N17, while it recovered none in M4/N13, M5/N10, planar, clustered, or noisy cells. The two Crocco variants did not match those outcomes consistently. At the M5/N13 baseline, the zero-timing route recovered one of eight refinements; Gaubitch+Crocco recovered none; direct multistart recovered two of seven completed refinements.

### Local observability and competing fits

The generating-state Jacobian was full column rank in the nonplanar, nondegenerate cells at the stated cutoff, including the square 65/65 baseline. This is local observability at the generating state under this parameterization; it does not rule out distant solutions. For M4/N13 and M5/N10, the Jacobian has 9 and 3 parameter null directions respectively, matching the observation/parameter deficits. The planar cell has rank 50/65, nullity 15, and a very large condition number, supporting a local degeneracy/conditioning explanation for its failures. The clustered cell remained full rank in this one sampled configuration and had a condition (`8.93e3`) comparable to the baseline (`8.95e3`); this one draw does not establish a universal clustered-geometry effect.

Several optimizer endpoints had low residuals but differed substantially after rigid alignment. At M4/N13, a pair from method A had residual norms `1.32e-13 s` and `1.62e-13 s` with pairwise aligned geometry RMSE `70.5 m`; method C also had alternatives with `1.52 m` pairwise RMSE and residuals below `1.3e-13 s`. The underdetermined measurement system therefore exhibits widely different near-exact solutions in these finite trials. At the square M5/N13 baseline, two direct multistart endpoints had residuals `1.46e-17 s` and `1.49e-17 s`, but differed by `0.465 m` aligned geometry RMSE; their emission-vector difference was `1.55 ms` and clock-vector difference `0.853 ms`. This is a numerical competing-solution example from the tested starts despite a full-rank Jacobian at truth. It is evidence against treating that local rank result as global uniqueness; it is not proof that the two endpoints are exact mathematical solutions in infinite precision or that all configurations are non-unique.

For noisy cells, residual-fit passes did not coincide with geometry/timing recovery. The C method had 5/7 fit passes at 20 us and 7/8 at 100 us, but zero recovery at both levels. The loose residual screen scales with noise and permits fit endpoints with materially different geometry; the full results include coordinate, timing, optimizer and Jacobian diagnostics for each. This is not evidence that increasing noise improves fitting: the standardized observation noise changes while the threshold also grows, and outcomes are start-dependent.

## Interpretation and limitations

- **Counts and information:** below-count cells show exact/near-exact competing fits and numerical null directions. Above-count cells remove the simple observation-count deficit, but recovery remains initializer-dependent. Count sufficiency is not established by this study.
- **Spatial distribution:** the planar fixture has rank loss and extreme conditioning, consistent with failure caused by geometric degeneracy. Clustered placement caused initialization rejection in this sample, though its truth Jacobian was full rank; the study cannot separate algorithmic basin effects from practical conditioning for the population.
- **Timing:** the high-timing cell made the two rank/Crocco starts reject all candidates because corrected TOAs were nonpositive for the tested initialization, while direct multistart still recovered 3/8. This is a start-construction failure for A/B, not proof that timing parameters are unidentifiable.
- **Noise:** both noise levels produced zero strict geometry/timing recoveries despite frequent fit-screen passes. Competing low-residual solutions and timing/geometry compensation are documented per pair in the JSON.
- **Local versus global:** Jacobian rank and near-null directions describe local behavior at the generating state only. Competing minima from finite deterministic starts demonstrate practical ambiguity, but neither a finite multistart nor full local rank establishes global uniqueness or infeasibility.
- **No production recommendation:** none of A/B/C is reliable across all tested conditions. No method is promoted to a production initializer.
- **Study limits:** one matched geometry realization per OAT cell; eight starts; fixed diagnostic thresholds inherited from C17; timing and noise levels are selected engineering values, not paper parameters; no missing-data case because the methods require complete matrices; no reflections or wall constraints; no exhaustive basin/global search.

The first seed-varying pilot was retained as `phase5c18_seedvarying_pilot_results.json` and its log. It is excluded from conclusions because each factor cell used a different random seed. The primary C18 results use the corrected shared independent streams.

## Next research step

Before selecting an initializer, repeat the informative count and geometry cells across multiple independent **geometry seeds**, keeping matched streams within each seed and fixed start protocol. Include the baseline, M4/N13, M7/N13, M5/N10, M5/N17, and planar configurations. For each converged low-residual endpoint, report measurement residual, aligned geometry/timing error, and full Jacobian spectrum. Use this to estimate repeatability across geometries, while maintaining that finite runs cannot prove global uniqueness. No Phase 6 work is part of this proposal.

## Reproducibility artifacts

- Runner: `experiments/exploratory/phase5c18_identifiability.py`
- Full primary results: `experiments/exploratory/phase5c18_results.json`
- Run log: `experiments/exploratory/phase5c18_run.log`
- Excluded seed-varying pilot: `experiments/exploratory/phase5c18_seedvarying_pilot_results.json` and `phase5c18_seedvarying_pilot_run.log`


