# Initial microphone/source localization: evidence-based derivation

## Scope and notation

This note analyzes only the direct-path initialization in Section 4.2 of the archived 2016 preprint. It does not implement the algorithm. It distinguishes what the preprint prints from material that can be recovered from references [7] and [28]. The full source equations are cited so readers can compare typography and indexing.

**Primary sources**

1. Crocco, Trucco & Del Bue, 2016 preprint, Section 4.2, Eqs. (1), (5), (12)–(15), Algorithm 2: [arXiv HTML](https://arxiv.org/html/1606.06258), [archived PDF in this project](../research/Uncalibrated_3D_Room_Reconstruction_from_Sound.pdf).
2. Gaubitch, Kleijn & Heusdens, “Auto-localization in ad-hoc microphone arrays,” ICASSP 2013, Sections 2–3, Eqs. (1), (3)–(10), Algorithm 1: [author-hosted paper PDF](https://www.commsp.ee.ic.ac.uk/~ndg/papers/Gaubitch2013.pdf).
3. Crocco, Del Bue, Bustreo & Murino, “A closed form solution to the microphone position self-calibration problem,” ICASSP 2012, Sections 2.1–2.2, Eqs. (3)–(20): [conference paper PDF](https://dihana.cps.unizar.es/proceedings/ICASSP/2012/pdfs/0002597.pdf).

Throughout this note, use `M` microphones indexed by `i` and `N` source events indexed by `j`. The 2016 preprint calls source positions `b^n` and microphone positions `s_m`; reference [7] uses event positions `s_j` and microphone positions `r_i`; reference [28] uses event positions `a_j` and microphone positions `x_i`. We retain those symbols only when explaining each source and use distinct names in explanatory prose to reduce collisions.

## 1. Measurement model and direct-path selection

**2016, Eqs. (1), (5):** geometric direct-path time is distance divided by sound speed. Measured arrival time is geometric propagation time plus event emission time and microphone sampling/clock offset. In consistent notation,

\[
t_{ij}=\frac{\|\mathbf r_i-\mathbf s_j\|_2}{c}+e_j+o_i+\nu_{ij}.
\]

Here `r_i,s_j` are unknown 3D coordinates in metres; `c` is the assumed sound speed in m/s; `e_j,o_i,t_ij,nu_ij` are seconds. The equation itself and the two timing nuisance terms are directly in the paper. The equation above combines its notation with [7]’s measurement-noise term; that noise term is not printed in the 2016 Eq. (5).

**2016, Section 4.2:** the first detected TOA for each microphone/event pair is designated as direct path because the direct path is shortest, and is expected to be detected because it is likely strongest. This is an assumption about detection. It does not protect against a missed direct path or a spurious early peak.

Set `a_ij` to the selected direct-path measured TOA. Eq. (12) defines `d^a_ij = c a_ij`. These are apparent distances, not geometric distances when `e_j` and `o_i` are unknown. There are `MN` such values only if all pairs have an available direct-path detection.

## 2. Rank structure when timing is known or removed

Let `R` be the `M × 3` microphone coordinate matrix, row `i` equal to `r_i^T`; let `S` be `N × 3`, row `j` equal to `s_j^T`. In a synchronized, noiseless model with true distances `d_ij=||r_i-s_j||`, squared distances obey

\[
d_{ij}^2=\|r_i\|^2+\|s_j\|^2-2r_i^T s_j.
\]

Subtracting a reference row and column removes the two norm-only terms. Define the **double-centered** matrix, for `i=2..M`, `j=2..N`,

\[
G_{i-1,j-1}=d_{ij}^2-d_{i1}^2-d_{1j}^2+d_{11}^2
=-2(r_i-r_1)^T(s_j-s_1).
\]

Then `G` has shape `(M-1) × (N-1)` and rank at most 3; if the centered configurations span three dimensions, its rank is 3. Let `Rbar` have rows `(r_i-r_1)^T`, and `Sbar` have rows `(s_j-s_1)^T`. Then `G=-2 Rbar Sbar^T`.

**Source status:** the derivation is the standard expansion explicitly shown in [28] Eqs. (3)–(5), and the factorization is [28] Eq. (7). In the 2016 preprint, Eqs. (13)–(14) state a rank-3 product `B^T S`, but the printed Eq. (13) is `D_{j,i}=(d^a_{ij})²-(d^a_{i1})²-(d^a_{1j})²` and does **not** display `+ (d^a_{11})²`; it also describes `B,S` as containing the unqualified source and microphone coordinates. As printed, that expression is not the double difference above and does not generally factor as a bilinear product of absolute coordinates. The exact intended indexing, reference term, and centered-versus-absolute coordinate convention are unresolved. This note does not silently alter Eq. (13).

## 3. Timing correction recoverable from reference [7]

Reference [7] starts from a complete `M × N` measured TOA matrix `T0=[t_ij]` with `t_ij=||r_i-s_j||/c+o_i+e_j` (plus noise in its stated model). Its derivation sets `c=1` and fixes event-time gauge `e_1=0`. It forms a double difference over rows/microphones and columns/events. With time quantities in seconds and actual sound speed retained, define the time-squared matrix

\[
T_{ij}=a_{ij}^2-a_{1j}^2-a_{i1}^2+a_{11}^2,
\quad i=2,\ldots,M,\ j=2,\ldots,N.
\]

It is `(M-1) × (N-1)`. Reference [7] then defines the correction through its Eqs. (4)–(6). Written elementwise in [7]’s notation (device delay `o_i`, emission time `e_j`), the linear timing terms are

\[
A_{ij}(o,e)=-2o_i(a_{ij}-a_{i1})+2o_1(a_{1j}-a_{11})-2e_j(a_{ij}-a_{1j}),
\]

and its bilinear term is

\[
\Gamma_{ij}(o,e)=2(o_i-o_1)e_j.
\]

These are in seconds squared. Reference [7] writes `A(p)=C^{-1}{Wp}` using a column-stacking operator `C^{-1}` (not the arbitrary 3×3 matrix named `C` in [28]); `p=[o_1,\ldots,o_M,e_2,\ldots,e_N]^T`. Its `W` is the linear coefficient matrix whose row for pair `(i,j)` has coefficients `-2(a_ij-a_i1)` for `o_i`, `+2(a_1j-a_11)` for `o_1`, and `-2(a_ij-a_1j)` for `e_j`, with zero coefficients for other timing variables. Its prose describes `W` by these TOA differences but does not print a fully expanded sparse matrix. `Gamma` contains the remaining products.

The corrected relation is

\[
-2\bar R\bar S^T=c^2\{T+A(o,e)+\Gamma(o,e)\}.
\]

Reference [7] sets `c=1`, so it omits the outer `c²`. This is a unit conversion when moving its timing-domain equations into the 2016 distance-squared representation. Under its `c=1` convention the right-hand side itself is denoted the corrected TOF matrix. Thus the conceptual `phi` for a proper distance-squared double difference is `c²(A+Gamma)`, while the base term must be the double-difference `c²T`; **this is a reference-based mapping, not an explicit Eq. (13) formula supplied by 2016**. Because the 2016 printed `D` does not match the same double difference, the exact identity `D + phi = corrected rank-3 matrix` cannot be uniquely reconstructed from the preprint as typeset.

### Timing iteration in reference [7]

At iteration `k`, let `X^(k)=T+A(p^(k))+Gamma(p^(k))`, shape `(M-1)×(N-1)`. Its closest rank-3 approximation is obtained from `X=U Sigma V^T` by retaining the three largest singular values:

\[
X_3^{(k)}=U_{(:,1:3)}\,\mathrm{diag}(\sigma_1,\sigma_2,\sigma_3)\,V_{(:,1:3)}^T.
\]

Then `E^(k)=X_3^(k)-T` (reference [7], Eqs. (8)–(9)). Update timing variables by minimizing the mismatch between `E^(k)` and timing correction terms. In full generality, because `Gamma` is bilinear in offsets and event times, [7] says this step requires nonlinear least squares. The paper gives a linear pseudoinverse update only for its special equal-internal-delay case, where `Gamma=0`; that is not the general independent-clock-offset problem. Reference [7] also adds a temporary regularization `lambda ||X^(k)||_F²` to keep values in a “reasonable” range, then sets `lambda=0` once the norm change is below a threshold. This is a continuation heuristic from [7], not explicitly specified in 2016 Algorithm 2.

The 2016 Algorithm 2 instead says “estimate `e_j,o_i` from `E` by linear least squares.” This is not justified for arbitrary independent offsets by [7] as published: [7]’s bilinear `Gamma` prevents a single linear least-squares update in the general case. Whether 2016 assumes an approximation, omits `Gamma`, or intended a nonlinear update is unresolved.

## 4. Rank-3 projection and SVD coordinate factorization

For a complete, corrected double-difference matrix `G` of shape `(M-1) × (N-1)`, compute `G=U Sigma V^T`. Retain three singular triplets; the rank-3 approximation minimizes Frobenius error among rank-at-most-3 matrices (Eckart–Young–Mirsky). This operation is directly specified by [7] and 2016 Algorithm 2, Steps 3–4, though the exact matrix and its indexing differ as noted above. With Gaussian independent additive matrix-entry noise, this is the least-squares low-rank fit; missing entries are not handled by ordinary truncated SVD.

If `G=U_3 Sigma_3 V_3^T`, then a family of factors is

\[
\bar R=U_3 C,\qquad -2\bar S^T=C^{-1}\Sigma_3 V_3^T,
\]

for any invertible `3×3` matrix `C` (reference [7], Eqs. (11)–(14); reference [28] Eqs. (8)–(9) with its own factor names). The SVD provides coordinates only up to this arbitrary invertible transformation. It does not by itself produce Euclidean coordinates.

## 5. Quadratic coordinate recovery from reference [28]

Reference [28] uses microphone anchor `x_1=0` and rotational gauge that places the first event on the x-axis, `a_1=(a_11,0,0)^T`. For `i=2..M` and `j=2..N`, subtracting the reference distance equations gives the quadratic relation

\[
\|x_i\|^2-2x_i^T a_j=d_{ij}^2-d_{1j}^2.
\]

After inserting SVD factors parameterized by `C`, this yields [28] Eq. (12), a nonlinear least-squares objective over the nine entries of `C`; the anchor coordinate `a_11` is another quantity to initialize or optimize. Reference [28] suggests deriving `a_11` from the first microphone/source distance under the chosen gauge, or fixing it if noise is low. It does not give a universal initialization or global-optimum guarantee. It states residual local minima remain possible.

Reference [28] also linearizes a *different* route by lifting six quadratic combinations of a triangular factor into a vector `f`, fitting a linear least-squares system `P f ≈ k` (Eqs. (15)–(20)). Recovering the triangular-factor entries from `f` requires square roots and sign choices, leading to multiple reflected configurations. Its especially simple closed-form solution assumes one source coincides with one microphone; the 2016 problem does not make that assumption, so that special-case result cannot be imported as the general BatSight procedure.

**2016 statement:** it says “a suitable cost function exploiting the quadratic relations obtained squaring the relations in (4) is described in [28]” and then says estimate coordinates “solving for `Q`.” It does not print that cost function, state the anchor/gauge used, define `Q`’s relation to reference [28]’s factor, state how any extra anchor coordinate is treated, or say which [28] branch (general nonlinear LS versus co-location closed form) it uses. The recoverable mathematical family is clear; the exact 2016 coordinate recovery is not.

## 6. Initialization, stopping and data conditions

| Item | What the sources specify | Status for a faithful 2016 design |
|---|---|---|
| Initial timing vector `p^(0)` | [7] says initialize; its experiments use random non-informative values and `lambda=0.7`. 2016 Algorithm 2 says initialize `phi` but gives no rule. | **Unresolved.** [7]’s experimental choice is not identified as the 2016 setting. |
| Rank projection | Truncated SVD retaining the top 3 singular values. | **Recoverable from [7], directly stated in 2016 Algorithm 2.** |
| Timing update | [7] full independent-delay case nonlinear LS; linear pseudoinverse only for equal delays (`Gamma=0`). 2016 says linear LS. | **Contradictory/under-specified** for arbitrary offsets. |
| Stopping | 2016: stop when `||E||_F` is below a threshold, with no numeric threshold. [7]: iterative norm criterion; its experiment exits when change in Frobenius norm is `< 10^-12` and anneals `lambda` to zero after a change threshold. | **Partially recoverable.** The form is known; the 2016 threshold and `lambda` schedule are not. Do not transfer `10^-12` without labeling it an extension. |
| Data completeness | 2016 chooses the first TOA for every mic/source pair. [7] forms a dense complete TOA matrix and uses ordinary SVD. | **Missing data unresolved.** No mask-aware rank approximation or treatment of absent direct arrivals is specified in these steps. |
| Noise | [7] motivates low-rank Frobenius fitting as maximum likelihood under Gaussian measurement noise. 2016 acknowledges peak errors but does not give robust weighting for this initialization. | **Partially recoverable.** Ordinary SVD handles dense noise by least squares, not outliers. |
| Outlier/invalid timing values | 2016 assumes the first detected peak is direct path; it gives no rejection or consistency repair inside initialization. | **Unresolved.** No clipping, reassignment, or robust loss is specified. |
| Minimum measurement count | [7] counts degrees of freedom and derives `M≥5` and `N≥13` as its minimum configuration. It also requires events at different spatial locations. | **Recoverable as [7]’s necessary identifiability count** under its model. It is not a guarantee for degenerate or poorly spread geometry, nor does the 2016 preprint independently restate this minimum. |

## 7. Gauges and coordinate ambiguities

Distance-only localization has a global translation and orthogonal transformation ambiguity: applying the same translation/rotation/reflection to every source and microphone leaves distances unchanged. Since distances are metric after multiplying TOA by known `c`, there is no global scale ambiguity in the noiseless, correctly timed model. The factorized matrix additionally admits a general invertible `C` ambiguity; the quadratic Euclidean distance constraints are what restrict it back to Euclidean geometry. Reflection/sign ambiguities can remain. Reference [28] fixes translation with one microphone at the origin and rotation by putting one source on the x-axis, while its triangular-factor recovery admits eight sign/reflection branches; additional information is needed to select a branch if handedness matters.

There is also a timing-origin gauge: adding a constant `q` to every `e_j` and subtracting `q` from every `o_i` leaves all measured TOAs unchanged. Reference [7] fixes `e_1=0`. This convention does not mean the clocks are synchronized and does not set each offset to zero. Coordinate gauge choices are arbitrary representations, not known physical positions.

## 8. Line-by-line crosswalk to the 2016 initialization

| 2016 text/equation | Operation actually stated | Cross-check and classification |
|---|---|---|
| Section 4.2 first detected peak | Select first TOA as direct path. | **Directly specified.** Conditional on correct detection and direct path being earliest. |
| Eq. (12) | Multiply selected TOA by `c` to form apparent distance. | **Directly specified.** Does not remove emission/clock terms. |
| Eq. (13) | Form `N×M` matrix from three squared apparent distances. | **Directly printed, but ambiguous/inconsistent.** As typeset it lacks the fourth baseline term present in a proper double difference. |
| Eq. (14) | Assert rank-3 factorization using source/microphone coordinate matrices. | **Directly asserted.** Its exact compatibility with printed Eq. (13) and absolute-vs-centered coordinates is unresolved. The centered product is recoverable from [28]. |
| Text after Eq. (14) | Use left/right singular vectors, truncate at third singular value. | **Directly specified / recoverable from [7], [28].** Full factor dimensions should use `(M-1)×(N-1)` only for the referenced centered formulation. |
| Text before Algorithm 2 | Unknown timing changes require additive `phi(e,o)` so corrected matrix is rank 3. | **Concept directly specified; exact 2016 `phi` unresolved.** [7] supplies an explicit correction for its double-differenced TOA matrix. Mapping it to the 2016 printed Eq. (13) is not exact due the matrix-definition mismatch. |
| Algorithm 2 steps 1–2 | Initialize `phi`, set `Dhat=D+phi`. | **Directly stated, initialization rule unresolved.** |
| Steps 3–4 | Closest rank-3 approximation; residual `E=Dhat3-Dhat`. | **Directly specified.** Standard truncated SVD is supported by [7]. |
| Step 5 | Estimate emission times and offsets from `E` by linear LS. | **Directly stated but conflicts with general [7].** Linear update holds in [7] only under equal offsets; otherwise [7] says nonlinear LS. |
| Steps 6–8 | Update correction; repeat until Frobenius residual below threshold. | **Directly stated.** Numeric threshold, initialization and maximum iterations are absent. [7] gives related but distinct convergence/regularization choices. |
| Step 9 | Recover coordinates by solving for `Q` from rank-3 matrix. | **Directly stated at high level.** Quadratic factor recovery from [28] is available, but the exact objective, gauge and solver choice in 2016 are omitted. |
| Eq. (15) | Subtract estimated emission/offset from observed TOA for later TOF use. | **Directly specified.** This is downstream of initialization and depends on estimated timing parameters. |

## 9. Classification summary

1. **Directly specified by the paper:** choose first detected direct TOA; `d^a=c t_a`; rank-3 corrected matrix concept; SVD truncation; residual-driven timing loop; threshold stopping form; final coordinate recovery via a `Q` solve; TOF subtraction.
2. **Recoverable from cited references:** explicit double-difference correction structure and its linear/bilinear timing terms, timing gauges, full-rank projection and [7]’s distinction between equal-offset linear LS and general nonlinear LS; SVD arbitrary-factor ambiguity and quadratic constraints for coordinate recovery from [28].
3. **Engineering interpretation:** translating [7]’s `c=1` equations to physical SI units with `c²`; naming the correction `phi`; choosing a concrete data structure or matrix indexing; applying validity filters or a missing-data solver.
4. **Unresolved:** how 2016 Eq. (13) is reconciled with double differencing; exact 2016 phi initialization/formula and matrix orientation; why Algorithm 2 calls general timing update linear; exact coordinate cost/gauge/initialization/solver; numerical stopping criterion; treatment of absent, missed, outlier, or invalid direct TOAs.

No implementation should claim exact reproduction until the unresolved items are settled by an authoritative correction, author-provided source, or a deliberately documented engineering variant.
