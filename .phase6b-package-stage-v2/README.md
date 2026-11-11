# BatSight

BatSight is a research-oriented acoustic room reconstruction project. The first working release is prioritized around rectangular shoebox rooms; this is a delivery focus, not a permanent restriction. The broader general convex-polyhedral research mode and its historical artifacts remain preserved. The current checkout includes a narrowly scoped calibrated shoebox-dimension estimator, plus signal-processing and forward synthetic tools. It does not provide the paper's uncalibrated position-and-wall reconstruction pipeline.

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
- `frontend/`: Phase 6B React/TypeScript/Vite local-first UI for projects, Sound Studio, signal analysis, recordings, system status, and the synthetic forward experiment API.
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

The supplied 2016 preprint is archived in `research/Uncalibrated_3D_Room_Reconstruction_from_Sound.pdf`; its record is [arXiv:1606.06258](https://arxiv.org/abs/1606.06258). The related 2017 journal article is separately documented in `docs/research_spec.md`. Its full text was not available from the publisher/repository sources checked, so the preprint and journal article remain distinct references and a complete version reconciliation remains open.

## Status

Phase 2A provides typed signal models, generic engineering waveform generation, reference-based matched filtering, and threshold peak detection. Phase 2B adds a forward-only shoebox image-source simulator. Phase 3 connects these components into reproducible synthetic experiments and TOA comparison reports. Phase 4 adds a forward-only, sampling-independent synthetic dataset for direct-path TOAs with known source and microphone positions, independent emission times and clock offsets, optional timing noise, and missing observations. Phase 5A documented the cited initialization mathematics; Phase 5B specifies a reference-derived general-offset timing and coordinate-recovery design plus a synthetic validation matrix. Phase 5C remains blocked because the paper-derived timing stage has not met recovery criteria. Phase 5C.4 found that three tested positive-TOA rank-only alternatives failed the Crocco metric residual gate, while the generating truth passed on both determinant branches; this finite search does not prove global uniqueness. Phase 5C.5 demonstrated local direct-TOA recovery from truth and nearby perturbations. Phase 5C.6 found a deterministic zero-timing plus cross-distance SVD/Crocco start that repeatedly recovered the seed-11 solution, but noisy minimum-count trials failed and a Gaubitch-derived start reached a distinct machine-precision fit. This remains an exploratory initializer, not a production method or a paper-reproduction claim. Phase 5C.7 independently tested unknown convex-room feasibility, ideal first-order reflection observations, and deterministic count/placement variants against the archived seed-11 competing endpoint. An arbitrary unknown convex enclosure does not disambiguate finite coordinate sets; the reflection check could not be fairly blind-fit without latent wall estimation; added observations changed conditioning and outcomes but did not produce consistent recovery. Phase 5C.8 unknown-wall results were invalidated as an inverse-model test by a source-plane dot-product bug in its predicted image-source calculation; its historical files remain preserved. Phase 5C.9 independently verified the corrected predictor at oracle walls, recovered those walls from deterministic perturbations, and found one blind PCA recovery for the generating endpoint. Phase 5C.10 tested 19 data-derived PCA/offset starts, explicit scaling, assignment-aware blocks and penalty continuation for the competitor. Some candidates pass every geometry check but have large echo residuals; high-penalty fits become severely ill-conditioned. The generating PCA regression still passes, but the competing endpoint remains unresolved and no disambiguation or uniqueness claim is justified. Phase 5C.11 jointly fit direct TOAs, unlabeled first-order echoes, timing, coordinates, and six walls. Phase 5C.12 verified an analytic echo Jacobian away from association ties and measured local recovery through 1e-3 scaled-coordinate perturbations on the seed-11 fixture. PCA starts contain echo-order ties; analytic derivatives improved, but did not eliminate, their non-exact fits. The competing endpoint remains unresolved, and these finite experiments do not establish uniqueness. These are exploratory synthetic results, not global uniqueness evidence. Phase 5C remains blocked. No production inverse localization engine or wall estimator has been delivered. No phase claims exact reproduction of the unresolved 2016 equations or complete paper experiment. No application UI or measured BatSight reconstruction results are included.

Phase 5C.13 investigated balanced entropic transport for unlabeled first-order echoes. Its derivative checks passed at tested checkpoints, but the fixed continuation failed numerically on extreme optimizer trial costs. Smooth-only solutions were biased; smooth-plus-hard refinement recovered the generating PCA case but not the competing PCA case, so the method is not accepted. The competing endpoint remains unresolved. See the Phase 5C.13 report and full exploratory results.

Phase 5C.13 artifacts: [research report](docs/initial_localization_implementation.md), [exploratory solver](experiments/exploratory/phase5c13_smooth_echo_assignment.py), [full results and parameter vectors](experiments/exploratory/phase5c13_results.json), and [run log](experiments/exploratory/phase5c13_run.log).

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
