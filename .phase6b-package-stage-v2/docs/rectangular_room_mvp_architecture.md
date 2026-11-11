# Rectangular-Room MVP — Architecture and Scope Audit

## Decision and boundary

The shoebox mode is a first-release prioritization, not a change to BatSight's broader research purpose. The implementation target is a constrained rectangular-room pipeline. Arbitrary convex polyhedral rooms remain a separate future research mode. Nothing in this audit claims that the unresolved uncalibrated localization problem has been solved, that any C17/C18 initializer is production-ready, or that a rectangular constraint makes TOA reconstruction identifiable.

This is a source audit of the current checkout. No production algorithm was modified.

## Existing project inventory and reuse map

| Area | Current implementation | MVP use and limits |
|---|---|---|
| `src/batsight/signals/models.py` | Immutable `AudioSignal`, `SamplingFrequency`, `RecordingMetadata`, `KnownReferenceSignal`, `DetectedArrivalTime`; explicit sample/time conversion | Shared signal and time types. Audio amplitudes are caller-defined; metadata is optional. |
| `src/batsight/signals/generation.py` | Sine and generic linear sweep generators | Engineering excitation fixtures. The sweep explicitly is not the unresolved Eq. 10 waveform. No playback/recording device adapter exists. |
| `src/batsight/signals/matched_filter.py` | Full correlation of a mono recording against supplied mono reference; positive lag convention; optional reference-energy normalization | Reuse per channel. This estimates one strongest arrival through its convenience method; it does not itself label multiple room paths. No GCC-PHAT. |
| `src/batsight/signals/peaks.py` | Two-stage local/global threshold peak detector with timestamps | Reuse as current configurable peak picker; its thresholds are not probabilistic false-alarm guarantees. |
| `src/batsight/simulation/shoebox.py` | `ShoeboxRoom`, deterministic six-wall image-source enumeration through order two, sparse RIR deposition, multichannel convolution, optional seeded Gaussian noise | Existing forward shoebox infrastructure. Room is axis-aligned, origin at minimum corner, dimensions known, and source/microphones must be strictly inside. Not an inverse solver or complete physical acoustics model. |
| `src/batsight/datasets/toa.py` | Direct-path synthetic TOA equation, source and mic truth, independent emissions/clock offsets, noise and missing mask, JSON round-trip | Synthetic forward observations and test fixtures. Dataset includes ground truth by design. It is not a real observation loader or masked inverse estimator. |
| `src/batsight/experiments/pipeline.py` | Orchestrates one excitation/source with multiple microphones: simulation, matched filtering, peak detection, arrival matching, metrics, structured output and CSV | Reuse for forward regression and later signal-to-arrival evaluation. Existing expected path labels are simulator-known; real echo association is not solved. |
| `src/batsight/geometry/` | Only `__init__.py`; no room geometry types or estimators | Empty package boundary, not existing shoebox or polyhedral support. |
| `src/batsight/optimization/` | Only `__init__.py`; no production optimizer | Empty package boundary. Do not imply a shared or accepted inverse optimizer exists. |
| `experiments/exploratory/phase5c4`–`phase5c18` | Historical equations, direct TOA, reflection, Jacobian, convergence and identifiability experiments plus result JSON/logs | Preserve as research artifacts. They are exploratory, not stable runtime APIs. C18 found start-dependent recovery and distinct near-exact geometries; no general production initializer is accepted. |
| `tests/` | 72 existing tests for signals, shoebox forward simulation, forward experiment orchestration, and synthetic direct TOA generation/serialization | Useful baseline coverage; there are no estimator/reconstruction tests because no production estimator exists. |
| `backend/`, `frontend/` | Boundary README files only | No FastAPI app, React app, live capture flow, visualizer or API schema exists. |
| `data/raw/`, `data/processed/` | `.gitkeep` placeholders | No real multichannel recording or external research dataset is present in the checkout. |
| `pyproject.toml` | Python package config with NumPy/SciPy; pytest optional dev dependency | Minimal existing numerical stack. No new dependency is justified by this architecture phase. |


## Explicit component classification

### A. Shared infrastructure already present

- Signal/value layer: `signals/models.py`, generic waveform generation, matched filtering and peak detection.
- Forward acoustic foundation: typed simulation path/RIR/recording results in `simulation/shoebox.py`.
- Experiment/data foundation: `experiments/pipeline.py`, direct-path `datasets/toa.py`, JSON/CSV outputs and seeded metrics.
- NumPy/SciPy/pytest packaging and current forward tests.

These components are reusable foundations; they do not imply that a microphone recording adapter, general multichannel acquisition workflow or inverse optimization framework exists.

### B. Rectangular-room support present or required

Present: `ShoeboxRoom` is an axis-aligned rectangular room with six named walls, interior validation, per-wall pressure coefficients and image-source simulation through second order. It is a **known-geometry forward simulator**. Present tests verify hand distances, path ordering, fractional samples, reflection coefficients, multichannel convolution and deterministic noise.

Absent: a room pose, unknown-dimension state, shoebox parameter estimator, room-boundary inference, microphone/source reconstruction, real echo association, or a rectangular inverse reconstruction result. The `geometry/` and `optimization/` package directories are empty placeholders. Any rectangular estimator is future work and needs a prior identifiability/strategy gate.

### C. General-room research preserved

The broader arbitrary convex-polyhedral direction remains in `research/`, the paper equation/assumption/design docs, and exploratory Phase 5C scripts/results/logs. C5C7–C5C18 are finite synthetic research experiments, including unknown-wall and direct/echo fitting diagnostics; they are not a production polyhedral geometry library or estimator. Keep their math, discrepancies, limitations and archived outcomes unchanged. Do not retrofit their general plane variables into shoebox-specific optimizer code or describe them as solved.
The detailed paper equations, unresolved Eq. 13/20 issues, timing update questions and historical experimental outcomes remain in the existing research documents linked from README. The research audit reports that the VGM landing page is available and lists 12 microphones, 17 source events, 16 kHz signals and ground-truth files, but its archive endpoint returned 403 and the page states no explicit dataset license. No dataset is in `data/raw/`; access and reuse permission remain unresolved. This audit does not rewrite those conclusions.

## Geometry modes

### Mode 1 — Rectangular Room (first-release priority)

Represent a rectangular cuboid with positive length, width and height `(Lx,Ly,Lz)`, a room frame, and six faces in three opposing parallel pairs. The three face-pair normals are mutually orthogonal; floor and ceiling are parallel and planar. Microphones and sources lie in the interior, subject to a documented boundary tolerance.

For a gauge-fixed internal representation, take the room frame as right-handed and aligned to xyz, with the room origin at the minimum corner. This is consistent with the current `ShoeboxRoom` simulator and avoids carrying a free rigid room pose when no external world reference exists. If users supply world-calibrated coordinates, expose an optional rigid transform `T_world_room=(R,t)`; do not estimate that pose redundantly alongside an unconstrained global coordinate gauge. Room dimensions remain unknown unless explicitly supplied.

A rectangular room has nine geometric degrees of freedom when embedded in an external frame: three for orientation, three for translation, and three dimensions. Six arbitrary planes have eighteen continuous degrees of freedom (unit normal direction and offset per plane). Constructing planes from a common orthogonal frame and three dimensions enforces the parallel/orthogonal constraints by parameterization and reduces the room shape's independent geometry to nine degrees of freedom. With a room-fixed gauge, pose is removed from the internal unknowns and the three dimensions remain.

### Mode 2 — General Convex Polyhedral Room (future research mode)

Retain the broader problem: a convex polyhedron with a specified face count and general plane orientations, shared across source/microphone observations. Do not replace general planes with orthogonal pairs or force a shoebox prior in this mode. Existing papers, derivations and Phase 5C artifacts remain its research record. The checkout currently has no production polyhedral geometry or estimator implementation; compatibility is an architectural requirement, not a claim of current functionality.

## Parameter and observation model

For direct path from source `j` to microphone `i`:

`q_ij = e_j + ||s_j - m_i|| / c + b_i + eta_ij`.

For a reflected path with image source `s'_j,k`:

`q_ij,k = e_j + ||s'_j,k - m_i|| / c + b_i + eta_ij,k`.

Here positions/distances are metres, times are seconds, `c` is m/s, and the noise terms are measurement errors. The second equation is a forward-model statement; it does not solve the path-to-wall association problem. Image-source coordinates are generated by reflecting the source across room planes, as already implemented for an axis-aligned shoebox through second order.

| Quantity | Known-input options | Unknown-estimation options | Important caveat |
|---|---|---|---|
| Room dimensions | User-measured dimensions or simulator truth | Three positive values | Direct paths alone contain no room-plane/dimension term. Containment inequalities alone cannot identify an enclosing box's size. Reflection observations or independent boundary information are required. |
| Room pose | Known room/world transform | Optional rigid pose in a world frame | If all coordinates are relative and otherwise free, pose is a gauge. Fix one frame or provide calibrated world anchors. |
| Microphone positions | Calibrated array positions | Per-mic 3D coordinates | A common rigid scene transform is unobservable without a gauge. Array calibration is valuable independent information. |
| Source positions | Tracked/known positions | Per-event 3D coordinates | TOA-only fits can have competing solutions; C18 contains finite synthetic examples. |
| Emission times | Trigger timestamps / known launch times | One per source event | Fix a time-origin gauge (e.g. first emission) when all are unknown. |
| Microphone clock offsets | Synchronized hardware with verified residual skew | One offset per channel | Do not silently assume synchronization. Relative clock drift may require a time-varying model; none exists now. |
| Sound speed | Calibrated/assumed environmental value | Optional estimate in future | MVP should treat `c` as known and record its source. Estimating it with geometry/timing adds scale/conditioning questions. |
| Reflection order/identity | Known in simulation/oracle diagnostics | Unknown for measured echoes | In real data, false/missed peaks and unknown wall association are discrete nuisance variables. |
| Wall reflection coefficients | Simulator configuration | Optional amplitude parameters | Current echo timing objective does not require amplitudes, but signal detectability depends on them. Frequency-dependent absorption is not modeled. |

With the room frame fixed, a fully unknown box/direct-path model would have `3M+3N+M+(N-1)+3 = 4M+4N+2` continuous unknowns (mic/source coordinates, offsets, emission times after one time gauge, and dimensions). For direct-only TOAs, the three dimension columns are absent from the measurement equations; adding room containment does not create direct measurement information about those dimensions. This simple count is not a sufficient identifiability test for any reflection-based setup. Reflection associations, valid image paths, spatial diversity and gauge removal all affect observability.

### Calibration profiles to keep explicit

1. **Synthetic oracle profile:** all geometry and timings known to the generator; use only to validate the forward model and recovery metrics, never as a blind start.
2. **Array-calibrated profile:** microphone coordinates and clock synchronization independently measured; source positions and/or room dimensions may be estimated under a separately specified experiment. Calibration uncertainty must be recorded.
3. **Uncalibrated multichannel profile:** multiple microphone channels, multiple source events, known or detected emissions, and independently estimated per-channel clock offsets. Requires a defensible initializer and reflection association strategy; C17/C18 show these are unresolved.
4. **Laptop single-channel demonstration:** one recording channel can show waveform, spectrum, matched-filter trace and exploratory echo candidates. It does not have the spatially diverse synchronized observations required to claim the paper's full uncalibrated 3D reconstruction. A moving laptop would need independently tracked positions and timing; neither is implemented.

## Proposed least-disruptive software structure

Keep existing forward and signal modules as the single source of truth while the estimator is researched:

```text
src/batsight/
  signals/                  # existing shared audio/time/filter/peak code
  datasets/
    toa.py                  # existing direct-path synthetic dataset
    recordings.py           # future real recording manifest/loader, after data contract
  geometry/
    base.py                 # future geometry protocol and frame conventions
    shoebox.py              # future unknown-dimension parameter state/constraints
    polyhedral.py           # future general plane representation; research mode
  simulation/
    shoebox.py              # existing forward image-source/RIR implementation
    polyhedral.py           # future only if a general forward simulator is required
  reconstruction/
    base.py                 # future common inputs/results and estimator protocol
    shoebox.py              # future rectangular estimator
    polyhedral.py           # future general estimator; not MVP
  optimization/             # currently empty; shared numerical helpers only after method approval
  experiments/              # existing forward experiment utilities remain reusable
backend/                    # currently a placeholder; future versioned FastAPI adapter
frontend/                   # currently a placeholder; future React + TypeScript client
```

Do not create a second `ShoeboxRoom` type just to match this diagram. For the first implementation milestone, either keep the current `ShoeboxRoom` canonical and add an estimator-only parameter/result type, or perform a reviewed extraction with compatibility re-exports so the simulator and estimator share one definition. Avoid a generic `simulation/base.py` until a second simulator exists. Keep the arbitrary-polyhedron interface narrow and mode-specific; do not over-generalize the first shoebox solver.

## Proposed milestones and effort estimate

Estimates are engineering person-days for one experienced Python/scientific-computing engineer, excluding review latency, real-data acquisition, hardware setup and frontend work. They are planning ranges, not commitments.

| Milestone | Work and exit condition | Estimate | Dependency/risk |
|---|---|---:|---|
| 0. Measurement contract and mode schemas | Specify channel/source indices, known/unknown variables, timing gauges, direct/reflection event representation, clock calibration metadata and missing-data policy | 2–3 days | Required before comparing estimators |
| 1. Rectangular geometry parameterization | Canonical box frame, positive dimensions, optional world pose, containment, wall/image path invariants; maintain simulator compatibility | 2–4 days | Low risk; current simulator is axis-aligned only |
| 2. Estimation strategy gate | Compare constrained shoebox hypotheses on synthetic fixtures; establish independent information/anchors and a repeatable blind initialization under competing-solution checks | 5–10 days research | **Critical blocker:** C17/C18 do not establish a general blind initializer or uniqueness |
| 3. MVP shoebox estimator | Implement only after milestone 2 approval; explicit unknown-variable profiles, residual/Jacobian diagnostics, failure reporting | 6–12 days | High; unknown echo associations and timing coupling may extend this |
| 4. Synthetic validation | Multiple dimensions/distributions, timing, reflection order, noise and supported missingness; metrics and seeded regression suite | 4–7 days | Depends on estimator and frozen success criteria |
| 5. Real multichannel ingest/validation | Recording manifest, channel/timebase validation, known reference association, clock characterization, real-data reports | 4–8 days | Requires suitable licensed data or synchronized recording hardware |
| 6. API integration preparation | Stable estimator schemas and a thin FastAPI boundary; no algorithm in API | 2–4 days | After engine schema is stable; outside current authorization |

A constrained synthetic MVP might take about 19–36 engineering days through synthetic validation, **after** the strategy gate succeeds. Real-data work and UI are additional. The range is wide because the core inverse method is not established. No production implementation should start by assuming that box constraints solve the C18 ambiguity.

## Open architecture/research questions

- Which experiment profile is the first reconstruction target: calibrated array, unknown array, or unknown source positions too?
- Which observations constrain the box: direct paths, first-order echoes, second-order echoes, known boundary measurements, or a combination?
- What is the accepted echo association and missed/false detection model?
- Are recording channels actually synchronized; what independent clock-calibration evidence is available?
- What room-pose/coordinate gauge and discrete axis/sign/permutation convention will exported results use?
- How will degeneracy and competing low-residual reconstructions be reported to users?
- Which paper-derived components are intended for a rectangular variant, and which are replaced by a clearly named constrained engineering method?
- Where is the real multichannel dataset, what is its license, and are per-channel timestamps, device geometry and source events available?

The immediate review gate is to approve an explicit calibration/unknown-variable profile and evidence source before implementation. The architecture keeps the rectangular MVP small while preserving the general polyhedral research path.

