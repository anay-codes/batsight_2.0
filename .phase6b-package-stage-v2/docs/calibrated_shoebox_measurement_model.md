# Calibrated Shoebox Measurement Model

## Scope and frozen profile

This document defines the Phase 5D.1 calibrated rectangular-room input and observation contract. Known microphone/source coordinates, synchronized channel clocks, known source emission times and known sound speed are inputs. Only the three box dimensions are the intended future unknowns. This milestone implements these data contracts and forward path prediction; it does not estimate dimensions or claim reconstruction works.

The model uses the axis-aligned room-local frame from the existing `ShoeboxRoom`: right-handed xyz axes, origin at the minimum corner, dimensions `(Lx,Ly,Lz)` in metres, and strict interior source/microphone points. Room pose is not estimated. General clock-offset, unknown-source-position and unknown-emission-time profiles are separate future modes.

## Units and inputs

| Type | Contents | Units/convention |
|---|---|---|
| `CalibratedMicrophone` | Stable microphone/channel ID, known position, optional `RecordingMetadata` | Position in metres in room frame |
| `CalibratedMicrophoneArray` | Non-empty unique microphone set, common `SamplingFrequency`, synchronized clock assertion | Sample rate in Hz; this profile rejects unsynchronized clocks |
| `CalibratedSourceEvent` | Event ID, source ID, known source position, known emission time, optional known reference signal | Metres, seconds; reference sample rate must equal array rate |
| `CalibratedShoeboxInputs` | Array, events, known sound speed | Sound speed in m/s; room dimensions intentionally absent |
| `TOAReading` | Arrival time/status, optional standard uncertainty and invalid reason | Time and uncertainty in seconds relative to common synchronized time origin |
| TOA observation records | Microphone/event IDs and direct, labeled-reflection, or unlabeled-echo reading | IDs are checked against the calibrated inputs |

A missing or invalid reading carries no numeric arrival time. An invalid reading must include a reason. Measurement uncertainty is optional; when present it is finite and nonnegative. These schemas distinguish a valid zero timestamp from a missing measurement.

### Observation label/provenance contract

- `DirectPathTOAObservation`: direct path, no wall association.
- `FirstOrderReflectionTOAObservation`: one explicit wall ID and an explicit label source. Synthetic records must mark `synthetic_ground_truth`; real records can only carry `external_annotation` labels.
- `UnlabeledEchoTOAObservation`: an echo ID and optional first-order hint, with no wall ID. This is the appropriate representation for real detections whose echo-to-wall association is unknown.
- `CalibratedTOAObservationSet.origin` marks a set synthetic or real and rejects synthetic wall labels in a real set unless an external annotation is declared.

The type system does not claim that actual real reflections have known wall identities. A future association algorithm must map unlabeled echo records to candidate paths and preserve ambiguity.

## TOA equations

For microphone `i`, event `j`, known source position `s_j`, microphone position `m_i`, sound speed `c`, known emission time `e_j`, and synchronized channels, the direct arrival is

`tau_ij^(0) = e_j + ||s_j - m_i||_2 / c`.

For wall `k` and the corresponding first-order image source `s'_(j,k)`, the predicted reflected arrival is

`tau_ijk^(1) = e_j + ||s'_(j,k) - m_i||_2 / c`.

Positions and distances are metres; `c` is metres/second; propagation and arrival times are seconds. No microphone clock term appears because the frozen profile asserts synchronized clocks. No source-emission variable is optimized or silently set to zero; the known `e_j` is added to every path. Direct paths contain no room dimension term. With calibrated positions held fixed, direct-path TOAs alone cannot constrain `Lx`, `Ly`, or `Lz`; the box dimensions enter the first-order image-source paths (or must be supplied by independent boundary measurements).

## Coordinate, boundary and input validation

`ShoeboxRoom` remains the single canonical room/dimension model. `geometry.shoebox` exposes its six wall planes, point classification and interior-margin validation without introducing another room class or simulator.

The point convention is strict: points outside or on a wall are not accepted as microphone/source positions. A configurable `minimum_clearance_m` rejects interior points at or within the specified distance of a wall; this margin classifies/validates input and does not move a wall. The default zero-clearance policy preserves existing simulator behavior. `classify_room_point` distinguishes `interior`, `near_boundary`, `on_boundary`, and `outside`.

## Assumptions and limits

- Axis-aligned room frame and minimum-corner origin; no pose parameter.
- Six planar walls form three parallel pairs, with mutually orthogonal axes and positive dimensions.
- Microphone/source positions, sample rate, clock synchronization, emission times, and sound speed are calibrated inputs.
- The forward model uses geometric image-source propagation. The existing RIR model's amplitude, absorption, diffraction and scattering limitations still apply, but amplitudes/noise are outside this TOA predictor.
- Unknown dimensions are not yet inferred. Reflection data-association, false/missed echo modeling, optimizer choice and identifiability are future work.
- This calibrated mode is not the paper's fully uncalibrated setup and does not resolve C17/C18's general localization ambiguity.
- No laptop single-microphone recording is claimed to provide this calibrated spatial input profile.

## Implementation references

- Typed inputs and observations: `src/batsight/datasets/calibrated.py`
- Wall planes and boundary policy: `src/batsight/geometry/shoebox.py`
- Shared continuous path calculation: `src/batsight/simulation/shoebox.py::predict_acoustic_paths`
- Labeled direct/first-order prediction: `src/batsight/simulation/reflections.py::predict_first_order_arrivals`
- Existing synthetic truth-bearing direct-only dataset remains `src/batsight/datasets/toa.py`; it serves a different generator/evaluation contract and was not replaced.
