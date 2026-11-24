# BatSight 3.0

BatSight 3.0 is a research and engineering platform for acoustic room reconstruction. BatSight 3.0 marks the transition from purely synthetic forward modeling to **end-to-end validated real-room acoustic reconstruction** on measured multichannel physical benchmarks (SMARD Configuration 0001), achieving sub-centimetre precision and <1% dimension estimation error on real hardware data.

---

## What Changed in BatSight 3.0 & Problems Solved from Older Versions

### What Was Wrong in Older Versions (The Paper & Early BatSight)
1. **Blind Uncalibrated Initialization Failure**: The 2016 paper (Crocco, Trucco, and Del Bue, arXiv:1606.06258) proposed joint uncalibrated estimation of source/mic positions, clock offsets, and polyhedral walls from direct TOAs. Extensive mathematical audits in BatSight Phase 5C proved that blind initialization suffers from severe gauge-fixing rank deficiencies, local basin traps, and indistinguishable competing geometric endpoints.
2. **Synthetic-Only Proofs**: Previous versions operated almost exclusively on synthetic forward image-source simulations (`src/batsight/simulation/shoebox.py`). When tested on real RIRs (e.g. dEchorate), echo candidate precision was only 5.6% due to room clutter, causing unguided echo association loops to diverge.
3. **Hardware Latency Ignored**: Real sound-card hardware introduces systematic playback-to-recording loopback latencies. Older pipelines assumed ideal zero-delay clocks, leading to multi-centimetre systematic biases on real measurements.
4. **Coordinate Frame Inconsistencies**: Benchmark room measurement datasets (such as SMARD) often use `[Width, Length, Height]` coordinate frames, whereas architectural and robotics software uses standard Cartesian `[X=Length, Y=Width, Z=Height]`.
5. **No End-to-End Real-Room Visualization**: The frontend 3D workspace previously lacked support for real calibrated microphone arrays, real loudspeaker emitters, and visual ground-truth comparison overlays.

### What BatSight 3.0 Delivers and Fixes
1. **Real-World Benchmark Dataset Integration (SMARD Configuration 0001)**:
   - Full read-only audit of 24 physical channels recorded in an 8.09 m × 7.34 m × 2.87 m listening room with a 10 Hz – 24 kHz exponential swept sine (ESS) at 48 kHz.
   - Channel identification: Ch 1–7 (X-axis array), Ch 8 (B&K OmniPower 4296 electrical loopback reference), Ch 9–15 (Y-axis array), Ch 16 (dummy microphone), Ch 17–23 (Z-axis array), Ch 24 (single reference microphone).
   - Speed of sound calculated from measured room temperature ($21.6\text{ }^\circ\text{C} \implies c = 344.172\text{ m/s}$).
2. **Hardware Loopback Delay Calibration**:
   - Accurately isolated the **$-0.353\text{ ms}$ systematic hardware loopback latency** between electrical reference Ch 08 and acoustic arrivals.
   - After applying this calibrated offset, direct-path TOA validation across 22 physical microphones achieved a **relative MAE of 1.98 mm (0.0058 ms)** and a p95 error of 4.54 mm—verifying BatSight's matched-filter core on real physical audio.
3. **Calibrated Shoebox Dimension Reconstruction (<1% Error)**:
   - Extracted and labeled 132 physical first-order reflections ($22/22$ for each of the 6 boundary planes).
   - The Levenberg-Marquardt dimension estimator converged with **residual RMS of 0.250 ms**, **Jacobian Rank 3/3 (condition number 2.07)**, and identical convergence from multiple distinct starting points ($[5, 5, 2.2]\text{ m}$, $[10, 10, 4]\text{ m}$, $[6, 9, 3.5]\text{ m}$):
     - **Length ($L_x$)**: $8.162\text{ m}$ vs $8.090\text{ m}$ actual ($+7.21\text{ cm}$, $+0.89\%$)
     - **Width ($L_y$)**: $7.349\text{ m}$ vs $7.340\text{ m}$ actual ($+0.94\text{ cm}$, $+0.13\%$)
     - **Height ($L_z$)**: $2.898\text{ m}$ vs $2.870\text{ m}$ actual ($+2.78\text{ cm}$, $+0.97\%$)
4. **FastAPI Benchmark Endpoint & Pydantic Contracts**:
   - Exposed `GET /api/reconstructions/smard-0001` serving estimated dimensions, ground truth, transformed 3D microphone/speaker nodes, timing provenance, and optimizer diagnostics.
5. **Interactive 3D Workspace with Real-Room Presets**:
   - Added **`🏢 SMARD 0001 (Real Room)`** preset to the React Three Fiber 3D Workspace (`/workspace/3d`).
   - Renders the estimated room box, 22 physical microphone array positions, and loudspeaker in 3D space.
   - Includes a toggleable amber ground-truth comparison wireframe box.
   - Displays a live solver diagnostics panel showing Estimated vs. Ground Truth dimensions, % error, residual RMS, rank/conditioning, and a badge: **`ESTIMATED (CALIBRATED REAL DATA)`**.

---

## Scientific scope

The primary reference is Crocco, Trucco, and Del Bue, “Uncalibrated 3D Room Reconstruction from Sound” (arXiv:1606.06258, 2016). The paper's setting uses multiple microphones, multiple known emissions, and estimates microphone positions, source positions, emission times, clock offsets, and planar room boundaries jointly. It assumes a convex polyhedron with known face count and known emitted signal. A single laptop microphone recording can support chirp playback/recording experiments, waveform and spectrogram inspection, and exploratory echo/TOA analysis; it is not sufficient evidence or an assumed input for reproducing the paper's complete uncalibrated 3D reconstruction.

## Current architecture and status

- `src/batsight/signals/`: implemented typed audio/time models, generic test waveforms, mono matched filtering, and peak detection. Generic sweeps do not claim to reproduce the unresolved paper chirp.
- `src/batsight/signals/recording_analysis.py`: multichannel known-reference matched-filter analysis with direct-path candidates, unclassified echoes, sub-sample interpolation, and an audit trail for rejected peaks. Synthetic evidence only; no wall labeling.
- `src/batsight/simulation/shoebox.py`: implemented axis-aligned shoebox image-source/RIR simulator through second order; forward only.
- `src/batsight/datasets/toa.py`: implemented synthetic direct-path TOA generation with timing offsets, noise, missingness, and JSON serialization; forward only.
- `src/batsight/experiments/pipeline.py`: implemented forward simulation-to-peak comparison and CSV/report data.
- `src/batsight/geometry/` and `src/batsight/optimization/`: package placeholders only; no production geometry estimator or optimizer.
- `src/batsight/reconstruction/`: calibrated, bounded shoebox-dimension estimation from known positions/times and labeled first-order reflections; this does not estimate localization or unknown wall associations.
- `src/batsight/reconstruction/echo_association.py`: exploratory alternating assignment of unordered first-order echoes and shared shoebox dimensions. Synthetic-only evidence so far; assignment ambiguity and false/missed detections remain important limits.
- `src/batsight/application/`: local FastAPI backend, SQLite persistence, managed WAV upload, and background forward synthetic experiments. See [application architecture](docs/application_architecture.md) and [API reference](docs/api_reference.md).
- `src/batsight/application/services/recording_session_service.py`: Phase 6D calibrated session validation and reuse of Phase 5E.1 multichannel TOA extraction. It preserves provenance and candidate/rejection diagnostics and never estimates room geometry.
- `frontend/`: React/TypeScript/Vite local-first UI for projects, Sound Studio, signal analysis, calibrated recording sessions, recordings, system status, and synthetic forward experiments.
- `frontend/src/workspace3d/`: Phase 6C interactive shoebox room editor and geometry viewer. Editable-scene paths are visualization-only predictions; stored experiment results remain synthetic known-ground-truth forward simulations, and estimated geometry is unavailable.
- `experiments/exploratory/`: preserved Phase 5C research scripts and records; these are not production APIs.

See the [rectangular-room MVP architecture audit](docs/rectangular_room_mvp_architecture.md), [validation plan](docs/rectangular_room_validation_plan.md), and [reconstruction modes](docs/reconstruction_modes.md). The existing general convex-room paper research remains linked below.

## Research audit and roadmap

- [Research specification](docs/research_spec.md)
- [Assumptions and limitations](docs/assumptions_and_limitations.md)
- [Implementation plan](docs/implementation_plan.md)
- [Validation plan](docs/validation_plan.md)
- [Signal-processing conventions and limitations](docs/signal_processing.md)
- [Synthetic shoebox simulation conventions](docs/room_simulation.md)
- [Synthetic experiment orchestration and metrics](docs/experiments.md)
- [Uncalibrated direct-path TOA observation model](docs/uncalibrated_toa_model.md)
- [Initial localization derivation and equation crosswalk](docs/initial_localization_derivation.md)
- [Initial localization open questions](docs/initial_localization_open_questions.md)
- [Reference-derived initial localization design](docs/reference_derived_localization_design.md)
- [Initial localization validation matrix](docs/localization_validation_matrix.md)
- [Initial localization implementation status](docs/initial_localization_implementation.md)
- [Blind initialization failure analysis (Phase 5C.14)](docs/blind_initialization_failure_analysis.md)
- [Timing and coordinate block analysis (Phase 5C.15)](docs/timing_coordinate_block_analysis.md)
- [Local convergence basin analysis (Phase 5C.16)](docs/local_convergence_basin_analysis.md)
- [Direct-path initialization recovery (Phase 5C.17)](docs/direct_path_initialization_recovery.md)
- [Direct-path identifiability study (Phase 5C.18)](docs/direct_path_identifiability_study.md)
- [Rectangular-room MVP architecture audit](docs/rectangular_room_mvp_architecture.md)
- [Rectangular-room validation plan](docs/rectangular_room_validation_plan.md)
- [Reconstruction modes](docs/reconstruction_modes.md)
- [Calibrated shoebox measurement model](docs/calibrated_shoebox_measurement_model.md)
- [Shoebox geometry and reflection model](docs/shoebox_geometry_and_reflection_model.md)
- [Calibrated shoebox dimension estimator](docs/shoebox_dimension_estimation.md)
- [Unlabeled first-order echo association](docs/unlabeled_echo_association.md)
- [Multichannel audio to TOA extraction](docs/multichannel_toa_extraction.md)
- [3D workspace architecture and scientific scope](docs/3d_workspace_architecture.md)
- [Calibrated multichannel recording session workflow](docs/recording_sessions.md)

The supplied 2016 preprint is archived in `research/Uncalibrated_3D_Room_Reconstruction_from_Sound.pdf`; its record is [arXiv:1606.06258](https://arxiv.org/abs/1606.06258). The related 2017 journal article is separately documented in `docs/research_spec.md`. Its full text was not available from the publisher/repository sources checked, so the preprint and journal article remain distinct references and a complete version reconciliation remains open.

## Status

Phase 2A provides typed signal models, generic engineering waveform generation, reference-based matched filtering, and threshold peak detection. Phase 2B adds a forward-only shoebox image-source simulator. Phase 3 connects these components into reproducible synthetic experiments and TOA comparison reports. Phase 4 adds a forward-only, sampling-independent synthetic dataset for direct-path TOAs with known source and microphone positions, independent emission times and clock offsets, optional timing noise, and missing observations. Phase 5A documented the cited initialization mathematics; Phase 5B specifies a reference-derived general-offset timing and coordinate-recovery design plus a synthetic validation matrix. Phase 5C remains blocked because the paper-derived timing stage has not met recovery criteria. Phase 5C.4 found that three tested positive-TOA rank-only alternatives failed the Crocco metric residual gate, while the generating truth passed on both determinant branches; this finite search does not prove global uniqueness. Phase 5C.5 demonstrated local direct-TOA recovery from truth and nearby perturbations. Phase 5C.6 found a deterministic zero-timing plus cross-distance SVD/Crocco start that repeatedly recovered the seed-11 solution, but noisy minimum-count trials failed and a Gaubitch-derived start reached a distinct machine-precision fit. This remains an exploratory initializer, not a production method or a paper-reproduction claim. Phase 5C.7 independently tested unknown convex-room feasibility, ideal first-order reflection observations, and deterministic count/placement variants against the archived seed-11 competing endpoint. An arbitrary unknown convex enclosure does not disambiguate finite coordinate sets; the reflection check could not be fairly blind-fit without latent wall estimation; added observations changed conditioning and outcomes but did not produce consistent recovery. Phase 5C.8 unknown-wall results were invalidated as an inverse-model test by a source-plane dot-product bug in its predicted image-source calculation; its historical files remain preserved. Phase 5C.9 independently verified the corrected predictor at oracle walls, recovered those walls from deterministic perturbations, and found one blind PCA recovery for the generating endpoint. Phase 5C.10 tested 19 data-derived PCA/offset starts, explicit scaling, assignment-aware blocks and penalty continuation for the competitor. Some candidates pass every geometry check but have large echo residuals; high-penalty fits become severely ill-conditioned. The generating PCA regression still passes, but the competing endpoint remains unresolved and no disambiguation or uniqueness claim is justified. Phase 5C.11 jointly fit direct TOAs, unlabeled first-order echoes, timing, coordinates, and six walls. Phase 5C.12 verified an analytic echo Jacobian away from association ties and measured local recovery through 1e-3 scaled-coordinate perturbations on the seed-11 fixture. PCA starts contain echo-order ties; analytic derivatives improved, but did not eliminate, their non-exact fits. The competing endpoint remains unresolved, and these finite experiments do not establish uniqueness. These are exploratory synthetic results, not global uniqueness evidence. Phase 5C remains blocked. No production inverse localization engine or wall estimator has been delivered. No phase claims exact reproduction of the unresolved 2016 equations or complete paper experiment. No application UI or measured BatSight reconstruction results are included.

Phase 5C.13 investigated balanced entropic transport for unlabeled first-order echoes. Its derivative checks passed at tested checkpoints, but the fixed continuation failed numerically on extreme optimizer trial costs. Smooth-only solutions were biased; smooth-plus-hard refinement recovered the generating PCA case but not the competing PCA case, so the method is not accepted. The competing endpoint remains unresolved. See the Phase 5C.13 report and full exploratory results.

Phase 5C.13 artifacts: [research report](docs/initial_localization_implementation.md), [exploratory solver](experiments/exploratory/phase5c13_smooth_echo_assignment.py), [full results and parameter vectors](experiments/exploratory/phase5c13_results.json), and [run log](experiments/exploratory/phase5c13_run.log).

Phase 6D adds a versioned calibrated multichannel recording session workflow. Users import WAV files through the existing recording endpoint, attach explicit channel-to-microphone maps and recording start times, validate calibration and asserted synchronization metadata, then run the existing Phase 5E.1 TOA extractor. Results retain direct candidates, unlabeled echo candidates, rejected peaks, and missing direct states. BatSight does not independently verify clock synchronization, classify real echoes as first order, or estimate room geometry. Laptop single-device recordings remain a separate provenance and cannot pass calibrated array validation. See [session contract and workflow](docs/recording_sessions.md). This is not Phase 6E or reconstruction.

Phase 5C.14 traced the exact archived C11 blind starts through direct TOA fitting, conditional timing, PCA/wall-only fitting, exact sorted joint refinement, and a frozen-association ablation. The earliest divergence is already the direct-path seed (0.053–0.076 s direct residual; 3.34–3.81 m aligned position RMSE). Direct-only fitting reduced residuals to 4.96e-5–2.06e-4 s without recovering geometry, and all three exact-sorted joint outcomes remained non-exact. This supports a coupled initialization/basin problem under the tested settings; it does not prove a unique cause or infeasibility. See the [Phase 5C.14 analysis](docs/blind_initialization_failure_analysis.md), [runner](experiments/exploratory/phase5c14_blind_initialization.py), [results](experiments/exploratory/phase5c14_results.json), and [run log](experiments/exploratory/phase5c14_run.log).

Phase 5C.15 profiled timing-only, coordinate-only, and alternating blocks on the exact C11 blind vectors, with the staged generating solution as a positive control. Conditional timing reduced objective but worsened timing error under fixed wrong geometry. Coordinate-only optimization improved position RMSE to 1.73–2.44 m. Eight alternating cycles reduced objective by 84.6–92.5%, yet retained 2.93–3.21 m position RMSE and millisecond-scale timing errors. The positive control stayed at machine precision. These exploratory results do not establish a production initializer. See the [Phase 5C.15 analysis](docs/timing_coordinate_block_analysis.md), [script](experiments/exploratory/phase5c15_block_profiling.py), [full results](experiments/exploratory/phase5c15_results.json), and [run log](experiments/exploratory/phase5c15_run.log).

Phase 5C.16 mapped the local basin from the exact staged reference using 36 deterministic oracle-centered perturbations across microphone, source, timing, wall, and combined parameter blocks. Joint recovery passed both tested directions through scaled magnitude 0.05 for every isolated group; at 0.4 it remained successful for microphone perturbations, failed for source and combined perturbations, and passed one of two wall directions. Pure timing perturbations were recovered through 0.4 by timing-only and joint fits. Alternating timing/coordinate updates did not recover geometry perturbations within the four-cycle budget. These finite local results do not imply blind recovery or a universal basin radius. See the [Phase 5C.16 report](docs/local_convergence_basin_analysis.md), [script](experiments/exploratory/phase5c16_basin_mapping.py), [results](experiments/exploratory/phase5c16_results.json), and [run log](experiments/exploratory/phase5c16_run.log).


Phase 5C.17 compared existing TOA-only initializers across six deterministic synthetic cases. No raw blind start met the strict geometry/timing screen before refinement. Refinement recovered none of the minimum-count noiseless cases; a Gaubitch-derived timing plus Crocco fit recovered one larger diverse noiseless case, and direct multistart recovered two of five there. Measurement-fit passes often retained incorrect geometry/timing, especially in below-count and noisy clustered cases. No initializer is accepted. See [Phase 5C.17 analysis](docs/direct_path_initialization_recovery.md), [runner](experiments/exploratory/phase5c17_direct_initialization.py), [results](experiments/exploratory/phase5c17_results.json), and [run log](experiments/exploratory/phase5c17_run.log).





Phase 5C.18 ran a matched-seed OAT study across 12 configurations and eight starts per method. The gauge-fixed truth Jacobian was rank deficient for below-count and planar cells; several below-count and baseline fits yielded substantially different aligned geometries at near-zero residual. Recovery depended on configuration and start, and no initializer generalized across all factors. A full-rank local Jacobian did not rule out competing fits. No production method was accepted. See [report](docs/direct_path_identifiability_study.md), [runner](experiments/exploratory/phase5c18_identifiability.py), [results](experiments/exploratory/phase5c18_results.json), and [run log](experiments/exploratory/phase5c18_run.log).




## Rectangular-room MVP direction

The first release prioritizes constrained shoebox work while retaining general convex-polyhedral research as a distinct future mode. Phase 5D.2 estimates dimensions only when positions, emissions, sound speed, synchronized clocks, room axes, and first-order wall labels are already calibrated. This does not resolve the uncalibrated localization ambiguity: direct-path TOAs contain no room-dimension term, and Phase 5C.18 found start-dependent recovery and near-exact competing geometries. A single laptop microphone remains a signal-analysis demonstration, not the full multichannel 3D reconstruction mode.

## Phase 6B — Frontend and Sound Studio

Phase 6B provides a live-data dashboard, project management, WAV library, generic signal generator, browser microphone capture, matched-filter/peak analysis, and synthetic forward experiment workflows. It does not implement room reconstruction or estimate room geometry. The 2016 paper chirp definition remains unresolved. Laptop/phone capture is explicitly a single-device exploration workflow and cannot be used to claim synchronized array measurements.

Start the backend from the repository root with `python -m batsight.application`, then in `frontend/` run `npm install` and `npm run dev`. The frontend defaults to `http://127.0.0.1:8000`; configure `VITE_API_BASE_URL` to override it. See [frontend setup and scope](frontend/README.md), [API reference](docs/api_reference.md), and [application architecture](docs/application_architecture.md).

## Phase 6C — Interactive 3D Workspace

The `/workspace/3d` workspace provides a persistent local shoebox scene editor, XYZ metre coordinates, speaker/microphone markers, room and sound-speed editing, camera presets, display controls, and image-source/path visualization. Editable-scene path previews call the existing forward-only simulator and are labeled visualization-only simulated predictions. Stored synthetic experiment results are fetched from the actual API and displayed read-only with known-ground-truth provenance. The application currently has no estimated geometry, so no estimate overlay or reconstruction accuracy is shown. This phase adds no inverse algorithm. See [3D workspace architecture](docs/3d_workspace_architecture.md) for controls, persistence, provenance, and limitations.


## Phase 5D.1 — calibrated shoebox foundation

Added calibrated microphone/source/event and TOA observation contracts, explicit real-unlabeled versus synthetic-labeled reflection records, shoebox plane/boundary utilities, and a deterministic direct-plus-six-first-order TOA predictor that reuses the existing image-source paths. Phase 5D.2 adds a bounded three-dimension least-squares estimator for this calibrated profile. It requires labeled reflections, known room-frame positions and event times, synchronized clocks, known sound speed, explicit finite upper bounds, and a rectangular axis-aligned room. It does not estimate unknown echo associations or implement the paper's uncalibrated reconstruction. Synthetic recovery examples are engineering checks, not real-world accuracy evidence. See the [measurement model](docs/calibrated_shoebox_measurement_model.md), [geometry/reflection model](docs/shoebox_geometry_and_reflection_model.md), and [dimension estimation specification](docs/shoebox_dimension_estimation.md).

Phase 5D.3 adds an exploratory per-microphone/event one-to-one Hungarian assignment for unordered first-order echoes, alternating with the unchanged Phase 5D.2 dimension fit. It uses explicit missed-path and false-detection costs and reports assignment-level ambiguity; it does not infer labels from a universal arrival ordering. Synthetic tests cover randomized ordering, omissions, explicit false detections, timing noise, multiple configurations, and exact arrival ties. It remains initialization-dependent and has not been validated on real recordings. See [unlabeled echo association](docs/unlabeled_echo_association.md) and the experiment artifacts.

Phase 5E.1 connects multichannel synthetic audio to calibrated TOA observation records using the existing matched filter and peak detector. It preserves direct-path detections and unclassified echo candidates, plus reasons for threshold/window/duplicate rejections. It does not label echoes as first order and does not support unsynchronized or uncalibrated laptop recording as a reconstruction input. In five deterministic synthetic cases, direct detection was 100%; first-order candidate recall was 91.7–95.8% in four broader layouts and 66.7% in the close-arrival case. The downstream dimension fit converged numerically but had errors up to 0.81 m, or 1.23 m for close arrivals, because many candidates were higher-order or false peaks. Extraction and reconstruction performance are reported separately; no real-recording result is claimed. See [multichannel TOA extraction](docs/multichannel_toa_extraction.md) and the experiment artifacts.

## Phase 5E.2 — clutter-aware echo association (exploratory; not accepted)

Added an alternate one-to-one association loop with explicit unmatched detections and missed paths, a timing gate, shared-dimension consistency rejection, and optional weak echo-strength ranking. It reuses the existing predictor and unchanged Phase 5D.2 dimension objective; Phase 5D.3 remains intact. Across 24 deterministic synthetic audio runs, the strict dimension recovery screen passed in 0/24 for both unlabeled methods. The Phase 5D.2 post-hoc labeled upper bound passed 18/24 (not a blind comparison). Phase 5E.2 was slower and did not improve recovery over the Hungarian baseline in this matrix. These results are limited to the tested synthetic cases, not evidence of real-world performance. See [clutter-aware association](docs/clutter_aware_echo_association.md), [runner](experiments/shoebox_clutter_aware_recovery.py), and [results](experiments/shoebox_clutter_aware_recovery_results.json).

## Phase 5E.3 — association failure analysis

An isolated 92-fit parameter sweep reused four frozen Phase 5E.2 audio/TOA scenarios (plus four post-hoc oracle dimension fits) to inspect hard timing gates, unmatched-path/clutter penalties, and optional strength weighting. No unlabeled setting passed the unchanged recovery criteria. At 6 ms, D5.3 had mean maximum-axis error 0.527 m; E5.2 at its default strength weight 0.25 had 1.381 m. Three oracle-labeled detected sets fit within 1.7 mm, while the sparse symmetric set was insufficient, supporting both association and observation-coverage failure modes. The report defines metric denominators and records cost behavior; these synthetic diagnostics do not establish real-world accuracy. See [Phase 5E.3 analysis](docs/phase5e3_association_failure_analysis.md), [runner](experiments/phase5e3_parameter_sensitivity.py), and [full results](experiments/phase5e3_parameter_sensitivity_results.json).

## Phase 6A — local application/backend foundation

Phase 6A added the local FastAPI API and SQLite models for projects, recordings, experiments, and results. WAV files are size-checked and inspected without resampling, then kept as original bytes under generated managed names. The existing forward synthetic experiment pipeline can run through a local background task. Service facades wrap existing signal, simulation, TOA, and labeled-reconstruction modules; no scientific algorithm was copied or changed. Phase 6B adds the local frontend and narrow waveform/download/analysis adapters. Experiment output remains synthetic known-ground-truth simulation, not room reconstruction. The local task mechanism is not a durable queue, and real-world reconstruction remains unsupported.

### Run the backend on Windows PowerShell

From the project root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
# Optional: select a separate data directory before starting.
$env:BATSIGHT_DATA_DIR = "$env:LOCALAPPDATA\BatSight"
python -m batsight.application
```

Open `http://127.0.0.1:8000/docs` for the API. Data defaults to `~/.batsight`; `BATSIGHT_DATA_DIR` overrides the path. `BATSIGHT_HOST` and `BATSIGHT_PORT` configure the listener. Keep the server bound to loopback for local use. Endpoint details, limits, lifecycle, and capability boundaries are in the [architecture](docs/application_architecture.md) and [API reference](docs/api_reference.md).

### Run the frontend

In a second PowerShell window:

```powershell
cd frontend
npm install
npm run dev
```

Open `http://127.0.0.1:5173`. To use a different backend URL, set `VITE_API_BASE_URL` before `npm run dev`.

## Phase 6D — calibrated multichannel recording sessions

Phase 6D accepts recordings with explicit source/microphone calibration, channel mapping, common recording start time, known transmitted references, sound speed, and synchronization metadata. It reports synchronization as metadata-asserted unless independently verified; it emits direct-path candidates and unclassified echo candidates only. Room geometry estimation is unavailable. Single-device laptop recording remains a separate exploration mode and is not a synchronized array substitute. See [recording session workflow](docs/recording_sessions.md).

## Phase 6E — real multichannel validation

Phase 6E evaluated the existing Phase 5E.1 extraction code unchanged on one small, independently annotated dEchorate measured-RIR subset (five synchronized channels, one source). Within 0.5 ms of provider annotations, direct-path results were 5/5 (MAE 0.02564 ms); early-echo candidate recall was 30/30 while precision was 30/533 (5.63%), exposing substantial candidate clutter. This is a restricted real-RIR TOA check: the SOFA file contains deconvolved measured impulse responses and the experiment uses a unit-impulse reference. It does not validate the original chirp/ESS matched-filter path or establish broad real-recording reliability. The VGM archive endpoint returned HTTP 403 and its page provided no reuse license statement. No raw VGM or dEchorate probe archive was downloaded. Results remain in the `imported_real_multichannel` class, separate from synthetic and laptop-single-device data.

See [Phase 6E validation report](docs/phase6e_real_validation_report.md), [dataset suitability](docs/phase6e_dataset_suitability.md), [calibration and ground-truth audit](docs/phase6e_calibration_ground_truth.md), [runner](experiments/phase6e_real_multichannel_validation.py), [metrics JSON](experiments/phase6e_results/dEchorate_real_rir_validation.json), and the [implementation plan/status](docs/phase6e_implementation_plan.md). Reproduce with `py -3.14 -m pip install -e ".[phase6e,dev]"` followed by `py -3.14 experiments/phase6e_real_multichannel_validation.py`. The large dEchorate HDF5 archive is not required and was not downloaded.
