# Initial localization: open mathematical questions

This register isolates details that block a faithful implementation of Section 4.2 in Crocco, Trucco & Del Bue (2016). It uses the archived preprint as the controlling source and cited works [7] and [28] only for operations those works explicitly establish. See [the derivation and equation crosswalk](initial_localization_derivation.md).

## Blocking questions

| ID | Question | Evidence | Status | Required resolution / safe interim treatment |
|---|---|---|---|---|
| Q1 | What is the exact definition and indexing of the 2016 matrix `D` in Eq. (13)? | As printed: `D_{n,m}=(d^a_{m,n})²-(d^a_{m,1})²-(d^a_{1,n})²`; Eq. (14) immediately asserts a rank-3 bilinear factorization. Reference [28]’s factorization comes from a four-term double difference with `+d^2_{11}` and centered point coordinates. | **Unresolved and blocking.** Without the fourth term/reference-centering convention, the asserted factorization does not generally follow from Euclidean squared distances. | Obtain erratum/source code/author clarification or confirm visually against a corrected authoritative version. Do not silently add the baseline term. |
| Q2 | What exact correction matrix `phi(e,o)` is intended in the 2016 `Dhat=D+phi`? | 2016 describes `phi` only as a function of emission and offset times. Reference [7] gives `A(p)+Gamma` for the double-difference matrix `T`. | **Partially recoverable, mapping unresolved.** [7]’s formula applies to a specific complete double-difference construction; Eq. (13) in 2016 differs as printed. | Document any derived phi as an explicitly labeled variant, pending confirmation of Q1. |
| Q3 | Why does 2016 Algorithm 2 specify a linear least-squares timing update for arbitrary independent offsets? | Reference [7], Eq. (8) and Sec. 3.1: full unequal-delay case requires nonlinear LS because `Gamma_ij=2(o_i-o_1)e_j`; the pseudoinverse update is for equal internal delays where `Gamma=0`. | **Unresolved and blocking.** | Clarify whether 2016 assumes equal offsets, linearizes the bilinear term, omits it, or intended nonlinear LS. Do not assume synchronized clocks or equal offsets. |
| Q4 | How is `phi` initialized, and what timing initial values/regularization are used? | Algorithm 2 says initialize `phi`; no values/rule. Reference [7] experiments used random p initialization, lambda 0.7, then annealed lambda. | **Unresolved for 2016.** [7] experimental settings are not 2016 settings. | No exact reproduction claim. If a BatSight experiment later chooses these, mark as a design deviation and compare alternatives. |
| Q5 | What exact convergence threshold, maximum iteration count, and stopping rule does 2016 use? | Algorithm 2 says `||E||_F` below a threshold but gives no numeric value. Reference [7] reports a change criterion and an experiment threshold `10^-12`. | **Partially recoverable, numeric 2016 setting unavailable.** | Do not transfer `10^-12` without explicit engineering label. |
| Q6 | Which coordinate-recovery objective and gauge from [28] did 2016 actually use? | 2016 says “suitable cost function” from [28] and solve for `Q`. [28] has general nine-parameter nonlinear LS, optional unknown first-event x-coordinate, and a special co-located source/microphone closed-form branch. | **Partially recoverable.** 2016 does not state its selected branch, initialization, solver, or constraints. | Do not use the co-location solution; it requires an assumption absent from 2016. Specify the general branch only as a candidate design pending confirmation. |
| Q7 | How are missing direct-path TOAs handled during initialization? | 2016 uses the first detected peak for every microphone/source pair. [7] forms a dense matrix and applies ordinary SVD. | **Unresolved.** No incomplete-matrix objective or imputation procedure is given. | Preserve the mask and report the method as unavailable for incomplete matrices until a documented extension is approved. |
| Q8 | How are false early peaks, outliers, negative corrected TOFs, and inconsistent timing assignments rejected? | 2016 assumes earliest detected peak corresponds to direct path; Eq. (12) turns that time into apparent distance. Robust peak-to-wall matching appears later, not in this initialization. [7] uses ordinary Frobenius least squares under Gaussian noise. | **Unresolved.** | Do not add clipping, reassignment, robust losses, or outlier pruning without labeling them as extensions. |
| Q9 | Are [7]’s `M≥5`, `N≥13` counts sufficient for the 2016 formulation? | [7] derives them from a degrees-of-freedom count and says event locations must differ. | **Necessary count for [7]’s stated model, not sufficient in degenerate geometry.** The 2016 preprint itself does not state a minimum. | Treat as a reference-based lower bound only; require rank and geometry conditioning checks as future engineering safeguards, clearly marked as such. |
| Q10 | Which geometric reflection/sign solution is intended after [28] factor recovery? | [28]’s triangular-factor reconstruction has sign ambiguities with eight possible configurations; it says extra information may select one. 2016 does not specify a branch rule. | **Unresolved.** | Report coordinate equivalence up to orthogonal transforms; do not claim room-frame orientation or handedness from TOAs alone. |

## What can be implemented later without overclaiming

The following components are mathematically supported but do not constitute a faithful end-to-end implementation by themselves:

- Given a complete and correctly identified direct-path TOA matrix, convert TOAs to distance units with known `c`.
- Build a *clearly specified* double-centered squared-distance matrix and verify its rank numerically.
- Compute its best rank-3 approximation by truncated SVD.
- Parameterize the remaining factor ambiguity and fit Euclidean coordinate constraints using the general reference [28] objective.
- Compare a timing-update implementation against [7]’s exact equations while labeling any choice made to reconcile the 2016 discrepancy.

An implementation of those items must say it follows the reference [7]/[28] formulation or is a BatSight variant. Until Q1–Q8 are resolved, it should not be labeled an exact implementation of 2016 Algorithm 2.

## Source references

- 2016 archived paper, Section 4.2, Eqs. (12)–(15), Algorithm 2: [arXiv record](https://arxiv.org/abs/1606.06258), [HTML full text](https://arxiv.org/html/1606.06258), local archived copy at `research/Uncalibrated_3D_Room_Reconstruction_from_Sound.pdf`.
- Reference [7], Gaubitch, Kleijn & Heusdens, ICASSP 2013, Eqs. (1), (3)–(10), Algorithm 1: [author-hosted PDF](https://www.commsp.ee.ic.ac.uk/~ndg/papers/Gaubitch2013.pdf).
- Reference [28], Crocco, Del Bue, Bustreo & Murino, ICASSP 2012, Eqs. (3)–(20): [conference proceedings PDF](https://dihana.cps.unizar.es/proceedings/ICASSP/2012/pdfs/0002597.pdf).
