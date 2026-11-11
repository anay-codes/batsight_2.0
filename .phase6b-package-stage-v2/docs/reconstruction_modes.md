# BatSight Reconstruction Modes

BatSight's room-shape choice is an explicit mode. Rectangular is the first-release priority; it does not replace the project's general convex-polyhedral research direction. At present both are architectural modes, not production reconstruction capabilities. The checkout contains forward shoebox simulation and signal/TOA analysis, but no production inverse geometry estimator.

| Mode | Target | Expected inputs | May support when implemented | Cannot currently claim |
|---|---|---|---|---|
| **1. Rectangular Room** | First-release constrained room geometry | Synthetic multichannel runs; or suitable synchronized real multichannel recordings; known waveform/reference and explicit timing/calibration metadata. Unknowns must be declared for each experiment. | Estimate a shoebox's dimensions and selected source/microphone/timing variables only after an identifiable observation profile and estimator pass synthetic validation. | No current reconstruction; rectangular constraints do not automatically identify room dimensions or remove TOA competing solutions. |
| **2. General Convex Polyhedral Room** | Future research and implementation mode | Multi-mic, multi-source observations and a declared face-count/measurement model; data provenance and calibration facts | Preserve general wall planes, reflection modeling, and the paper-derived research direction as a distinct estimator. | No current production polyhedral estimator, no claim that the unresolved paper initialization is solved, and no automatic reuse of rectangular orthogonality assumptions. |
| **3. Laptop Single-Microphone Demonstration** | Signal exploration, not room-shape reconstruction | One laptop speaker/microphone or supplied mono audio, known engineering reference, device/sample-rate metadata | Generate/record generic test signals, show waveform/spectrum/correlation and exploratory echo candidates after a recording adapter is built. | Cannot claim the paper's full uncalibrated multichannel 3D reconstruction or a complete room estimate from one stationary microphone. |

## Mode 1: rectangular room

### Geometry and gauge

A shoebox has six planar faces forming three opposing parallel pairs with mutually orthogonal normals. It is described by positive length, width and height and a right-handed frame. For unanchored reconstruction, use the room frame as the coordinate gauge: internal room origin at the minimum corner and axes aligned with the three dimensions. This avoids estimating a redundant room pose. An optional world transform is only meaningful when the world frame is independently calibrated.

The room may have unknown dimensions. Direct-path TOA equations contain no box dimensions; only boundary/reflection observations or independent measurements inform those dimensions. Interior containment by itself only supplies inequalities. Microphone/source locations, per-source emission times and per-channel clock offsets may be known or unknown by experiment. Sound speed should be declared and treated as known in the first estimator study. Do not set emission times or offsets to zero without evidence or calibration.

### Inputs and staged capability

- **Synthetic multichannel:** supported as a forward path today through shoebox simulation, signal processing, experiment results, and separate direct-TOA observation generation. The simulator knows the box and paths; these truths must not be passed into a blind estimator.
- **Real synchronized multichannel:** not currently ingested. The VGM landing page lists a 12-channel, 16 kHz, 17-event dataset and ground-truth files, but the archive endpoint returned 403 in the recorded audit and no license is stated; no data was downloaded. A future path needs confirmed access/reuse terms, per-channel sample/time-base metadata, reference waveform provenance, clock characterization, sensor/source calibration facts, and licensed data or controlled recording. If channels are unsynchronized, their offsets must be estimated or supplied with uncertainty.
- **Laptop single channel:** useful for signal and echo visualization only. A stationary one-mic record lacks the synchronized spatial measurements needed for the uncalibrated 3D problem. Moving the microphone does not solve this unless poses and clock times are independently measured.

### Implementation gate

Before an estimator is implemented, select which variables are known and unknown, what independent information constrains the box, and how unlabeled/missed/false echoes are handled. Compare candidate approaches on deterministic multi-geometry synthetic fixtures with competing-solution diagnostics. Phase 5C.18 shows that full local rank can coexist with substantially different near-exact fits; this must remain visible in result schemas and UI copy.

## Mode 2: general convex polyhedron

This remains a preserved research mode. The reference model permits arbitrary shared convex wall planes under its stated face-count and measurement setup; it is not equivalent to a shoebox. Keep its reference equations, discrepancies, assumptions, literature crosswalk, optimizer experiments, and historical results. The repository currently contains these in documents and `experiments/exploratory/phase5c*`, not in production geometry/estimator modules. General polyhedral estimation remains blocked by timing/localization initialization, echo association, conditioning and validation questions. Rectangular MVP work may share signal models, TOA schemas, experiment provenance, optimizer diagnostics and metric utilities, but it must not overwrite or reinterpret general-room equations.

## Shared components and boundaries

Reuse `AudioSignal`, `SamplingFrequency`, recording metadata, generic waveform generation, matched filtering, peak detection, the existing shoebox forward simulator, direct-path TOA generator and experiment/CSV result machinery. Keep signal processing independent of geometry. Keep the current shoebox simulator authoritative until a reviewed extraction establishes a shared geometry type; avoid parallel ShoeboxRoom definitions. Store estimator-specific unknowns and diagnostics separately from immutable simulation ground truth. Preserve synthetic, real multichannel, and laptop single-channel as different acquisition profiles, with provenance and capability labels in outputs.

See [MVP architecture audit](rectangular_room_mvp_architecture.md) and [mode-specific validation plan](rectangular_room_validation_plan.md) for details.
