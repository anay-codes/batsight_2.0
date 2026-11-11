# Shoebox Geometry and Reflection Model

## One room model, two uses

`batsight.simulation.shoebox.ShoeboxRoom` remains the single source of truth for shoebox dimensions, sound speed, wall names and image-source coordinates. The new `batsight.geometry.shoebox` module adds derived plane and point-validation views; it does not define a duplicate room or a separate reflection model. A candidate set of unknown dimensions for future optimization is represented by constructing the same validated `ShoeboxRoom` value for that candidate. This phase does not optimize those values.

## Frame and dimensions

The coordinate frame is right-handed xyz. The origin is the minimum room corner. Interior points satisfy

`0 < x < Lx`, `0 < y < Ly`, `0 < z < Lz`,

with positive dimensions in metres. There is no room pose in the calibrated profile. Known microphone and source positions are already expressed in this frame. A positive boundary clearance can be required to avoid numerically or physically ambiguous near-wall placements; the clearance is an input-validation margin, not a geometric wall displacement.

## Six wall planes

Planes use outward normal `n` and offset `h`, with the interior half-space

`n dot x <= h`.

| Wall ID | Outward normal | Offset `h` (metres) | Plane |
|---|---|---:|---|
| `x_min` | `(-1,0,0)` | `0` | `x=0` |
| `x_max` | `(1,0,0)` | `Lx` | `x=Lx` |
| `y_min` | `(0,-1,0)` | `0` | `y=0` |
| `y_max` | `(0,1,0)` | `Ly` | `y=Ly` |
| `z_min` | `(0,0,-1)` | `0` | `z=0` |
| `z_max` | `(0,0,1)` | `Lz` | `z=Lz` |

The signed outside distance is `n dot x - h`: negative inside, zero on the plane, positive outside. Wall IDs and their deterministic order are the existing simulator's `WALLS` order.

## Image-source conventions

The shared simulator mirrors a source independently across one named plane. In room-local coordinates, the first-order images are:

- `x_min`: `(-sx, sy, sz)`
- `x_max`: `(2 Lx - sx, sy, sz)`
- `y_min`: `(sx, -sy, sz)`
- `y_max`: `(sx, 2 Ly - sy, sz)`
- `z_min`: `(sx, sy, -sz)`
- `z_max`: `(sx, sy, 2 Lz - sz)`

These are exactly the existing `_reflect_point` conventions, not a newly inferred reflection model. For microphone `m_i`, each path distance and propagation time are

`d_ijk = ||s'_(j,k) - m_i||_2`,

`t_ijk = d_ijk / c`.

The direct path is the unreflected source with `d_ij0=||s_j-m_i||`. `predict_acoustic_paths` is shared by RIR synthesis and the calibrated TOA predictor. It returns continuous distances/times and path labels before any impulse sampling. The calibrated predictor includes the known source event time to produce absolute predicted arrival time `e_j+t_ijk`.

## Deterministic prediction output

`predict_first_order_arrivals` emits, for each source event and microphone, the direct path followed by the six first-order paths in simulator wall order. Each item contains microphone, event, source and optional wall IDs; reflection order; image-source position; propagation distance/time; known emission time; and predicted arrival time. It does not add noise, quantize to samples, assign observed echoes, or estimate dimensions. Sampling frequency is retained in the acquisition contract for later conversion of detected sample indices to seconds.

## Consistency and validation

Tests include hand-computed examples in a `(4,5,3) m` room with source `(1,1,1) m` and microphone `(2,2,1) m`: direct distance `sqrt(2) m`; `x_min` image `(-1,1,1) m` and reflection distance `sqrt(10) m`. They also check all six labels, source/microphone/event indexing, nonzero known emission time, sound-speed conversion, boundary handling, output determinism, and agreement with both `predict_acoustic_paths` and RIR path records.

## Limits and future work

- Dimensions are inputs to the forward predictor, not estimated here.
- No arbitrary room pose or polyhedral wall model is included.
- Real echoes are not supplied with simulator wall labels; real detections use the unlabeled echo contract unless independently annotated.
- No echo association, room-dimension optimizer, missing-data estimator, or confidence model is implemented.
- Existing shoebox waveform/RIR assumptions remain those in `docs/room_simulation.md`; this geometric TOA model does not improve physical acoustic realism.
- A rectangular geometry constraint does not by itself prove that dimensions are identifiable for a given set of paths. Direct paths contain no dimension information in this calibrated profile; reflection data and a validated inverse strategy are required.
