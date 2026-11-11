# Phase 5C.15 — Timing and Coordinate Block Profiling

## Purpose and scope

This exploratory diagnostic asks whether timing or coordinate blocks can improve from the exact three blind starting vectors archived in Phase 5C.11, and whether alternation improves them further. It is not a new initializer or production solver. The original C11 direct and first-order reflection observations are loaded verbatim; the echo matrix is checked for exact equality with the C8 archive. C11–C14 files are unchanged.

The full residual remains the C11/C12 exact sorted direct-plus-unlabeled-first-order-echo residual, with existing distance-unit scaling. The existing gauges are preserved by parameterization: microphone 1 at the origin; microphone 2 on positive x; microphone 3 in xy with positive y; emission time `e0=0`. Parameter blocks are the first 48 scaled coordinate parameters, the next 17 scaled timing parameters (`b_0..b_4`, `e_1..e_12`), and 18 wall parameters. During each requested block solve, the other parameter blocks are held fixed. Walls are fixed for both timing and coordinate profiling.

Optimization uses SciPy TRF, `x_scale="jac"`, the existing C12 analytic Jacobian restricted to the optimized columns, `ftol=xtol=gtol=1e-11`, and at most 80 function evaluations per block. Exact arrival sorting is recomputed in the residual at each evaluation; analytic echo derivatives are the existing piecewise fixed-association derivatives. A proposal is accepted only if the full exact-sorted objective is finite and does not increase by more than `1e-12 * max(1, prior objective)`. This acceptance rule is a BatSight diagnostic convention; it adds no physical prior or penalty. Physical checks are reported but do not change the objective or accept/reject rule. Alternation performs timing then coordinate updates, for up to eight cycles; it stops when cycle objective improvement is no greater than `1e-12 + 1e-10*abs(previous objective)`.

All geometry, timing, plane error, Jacobian, and physical-validity values use known synthetic truth only after each optimizer proposal has been generated. The staged C11 generating solution is the positive control, not a blind start.

## Results

Residual norms are in seconds; the objective is `0.5 * sum(residual_m**2)` in m². Position errors are combined source/microphone RMSE after rigid gauge alignment. The table reports independent block proposals from the original start and the final alternating state.

| Start | Stage | Objective (m²) | Direct norm (s) | Echo norm (s) | Position RMSE (m) | Emission RMSE (s) | Clock RMSE (s) |
|---|---|---:|---:|---:|---:|---:|---:|
| staged reference | initial | ~1.8e-27 | ~8.1e-17 | ~1.6e-16 | ~1.4e-15 | ~2.7e-20 | ~3.0e-21 |
| staged reference | timing-only / coordinate-only / alternating | numerically zero | ~0 | ~0 | ~0 | ~0 | ~0 |
| blind 17 | initial | 2058.21 | 0.05399 | 0.17909 | 3.342 | 0.000403 | 0.000321 |
| blind 17 | timing-only | 765.11 | 0.06424 | 0.09423 | 3.342 | 0.001716 | 0.006858 |
| blind 17 | coordinate-only | 138.51 | 0.01552 | 0.04597 | 1.731 | 0.000403 | 0.000321 |
| blind 17 | alternating, cycle 8 | 153.42 | 0.01956 | 0.04717 | 2.930 | 0.000784 | 0.006774 |
| blind 29 | initial | 2301.11 | 0.07624 | 0.18250 | 3.814 | 0.000403 | 0.000321 |
| blind 29 | timing-only | 840.49 | 0.05805 | 0.10449 | 3.814 | 0.002699 | 0.005925 |
| blind 29 | coordinate-only | 103.96 | 0.01519 | 0.03920 | 2.120 | 0.000403 | 0.000321 |
| blind 29 | alternating, cycle 8 | 187.09 | 0.02812 | 0.04888 | 3.109 | 0.002194 | 0.005746 |
| blind 41 | initial | 1416.61 | 0.05299 | 0.14585 | 3.497 | 0.000403 | 0.000321 |
| blind 41 | timing-only | 588.33 | 0.05199 | 0.08543 | 3.497 | 0.002102 | 0.004229 |
| blind 41 | coordinate-only | 215.61 | 0.02060 | 0.05693 | 2.443 | 0.000403 | 0.000321 |
| blind 41 | alternating, cycle 8 | 218.15 | 0.02384 | 0.05604 | 3.205 | 0.002247 | 0.002958 |

The reference control stayed at machine precision. Both block optimizers terminated after one evaluation at the reference, and the one alternating cycle retained zero echo-order changes. The control passed the convex enclosure and all 390/390 finite-face checks.

All three blind **timing-only** solves terminated on `gtol` (7–8 evaluations). Since the timing block cannot alter positions, position RMSE was unchanged. Its full objective fell, mainly because the echo residual decreased, but the recovered timing moved farther from ground truth: emission RMSE rose from about `0.403 ms` to `1.72–2.70 ms`, and clock RMSE rose from about `0.321 ms` to `4.23–6.86 ms`. The fitted timing terms are therefore conditional compensations for the fixed erroneous geometry, not recovered source times or clock offsets.

The blind **coordinate-only** proposals improved position RMSE to `1.73`, `2.12`, and `2.44 m`, and reduced both residual norms. Timing errors stayed at their initial values because that block was fixed. Their timing/coordinate block Jacobian diagnostics were respectively rank `17/17` with condition `7.92` for timing, and rank `48/48` with conditions `15.72`, `87.39`, and `127.25` for coordinates. Full Jacobian rank remained `83/83` at the configured relative threshold for all recorded states; that local rank does not imply a correct solution. Coordinate solve statuses were `4`, `3`, and `0`; the last reached the 80-evaluation cap despite its proposal being accepted by the objective rule.

Alternation reduced the total objective at each accepted cycle. After eight cycles, objective decreases relative to the starts were about 92.5%, 91.9%, and 84.6%. Position RMSE improved only to `2.93`, `3.11`, and `3.21 m`, respectively. Emission RMSE ranged from `0.784 ms` to `2.247 ms`; clock RMSE ranged from `2.958 ms` to `6.774 ms`. Thus lower objective corresponded to some position improvement, but not recovery. Every proposal was accepted under the monotonic objective rule; no update was rejected. Several coordinate updates hit the 80-evaluation cap. The detailed JSON preserves every before/proposal record, optimizer status, evaluation count, Jacobian, assignments, wall parameters, and physical checks.

The blind initial, independent block-proposal, and all alternating states passed the existing enclosure, positive path, and 390/390 finite-face checks. This is expected for these parameterized synthetic states and does not make them accurate reconstructions.

## Interpretation

### Timing conditional on geometry

Timing parameters can lower the exact objective when geometry is held fixed, but the resulting timing errors worsen substantially. Evidence supports that timing can absorb part of the incorrect geometry/echo fit. It does not support recovering the generating timing from these blind coordinate estimates.

### Coordinates conditional on timing

Coordinate-only optimization improved position RMSE and both residuals more than timing-only optimization. It still landed metres from truth and, for one start, exhausted its evaluation cap. This suggests the fixed initial timing is not by itself enough to prevent coordinate progress, but the coordinate block did not reach the local reference basin.

### Alternating blocks and echo associations

Alternation further lowered objective relative to the initial states but did not recover geometry or timing. Many echo groups changed association in early coordinate updates (57, 61, and 62 groups in the first cycle), followed by fewer changes in later cycles. Timing-only updates preserve each within-group arrival order because all predicted paths for a microphone/source pair receive the same timing shift; observed timing proposals recorded zero assignment-group changes. The association changes coincide with substantial coordinate moves, but this experiment does not prove they cause the remaining error.

### Dependence on starting state and limits

All three blind starts show the same qualitative pattern, but their objective levels, coordinate condition numbers, and final RMSE differ. This supports start dependence within this fixture. Three starts and one synthetic geometry do not establish a general basin boundary, global uniqueness, or infeasibility. These results do not validate alternating blocks as a production initializer.

## Next justified experiment

The most informative follow-up is to profile the same block updates from multiple deterministic points along paths from each archived blind state toward the staged reference, without using the reference to construct the blind optimizer starts. As a diagnostic, prescribe perturbation magnitudes around each archived state and compare the block convergence trends against the known positive control only after each run. Keep the objective and physical checks fixed. This can map which parameter block becomes effective near the local basin without accepting a new initialization method.

## Reproducibility artifacts

- Script: `experiments/exploratory/phase5c15_block_profiling.py`
- Complete records: `experiments/exploratory/phase5c15_results.json`
- Run summary: `experiments/exploratory/phase5c15_run.log`

Run from the project root using `python experiments/exploratory/phase5c15_block_profiling.py`. The script uses the repository's configured NumPy/SciPy environment and downloads no data.
