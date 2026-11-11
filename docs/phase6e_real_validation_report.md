# BatSight Phase 6E — real multichannel recording validation report

**Run date:** 2026-11-11  
**Result class:** `imported_real_multichannel`  
**Scientific status:** restricted real-RIR validation completed; full raw-probe validation remains blocked.

## 1. Executive summary

The paper-linked VGM archive could not be acquired: the published download endpoint returned HTTP 403 and the page does not declare a data reuse license. I therefore inspected an alternate independent real dataset, dEchorate, and evaluated one small measured multichannel RIR subset with provider timing annotations. The included sample contains one source and five microphone channels at 48 kHz.

With the existing Phase 5E.1 analyzer and its unchanged defaults, the direct-path candidate matched all 5 provider direct labels within 0.5 ms. The direct TOA MAE was **0.02564 ms** (**1.23 samples**), median **0.02734 ms**, and 95th percentile **0.04452 ms**. For 30 provider-annotated early echoes, 533 unclassified candidates were emitted; 30 matched within 0.5 ms, giving **100% recall** and **5.63% precision**. The detector did not receive echo or wall labels. The unmatched candidates and very large rejected-peak count show that candidate clutter is substantial on this RIR subset.

This is a positive result for calibrated TOA selection and peak timing on this measured RIR subset. It is **not** an evaluation of the raw ESS recording/reference path: the supplied SOFA file already contains a deconvolved RIR. A unit-impulse reference was supplied to the existing matched filter, so the correlation is the RIR itself. One source/array/configuration is not enough to claim reliability or real-room reconstruction accuracy.

## 2. Dataset acquisition and suitability

The [VGM dataset page](https://vgm.iit.it/datasets/3d-room-reconstruction-with-sound.html) describes 12 microphones, 17 source events, 16 kHz audio and position/room ground truth. The linked archive returned HTTP 403 on 2026-11-11. No actual VGM audio or metadata file was downloaded, and no reuse license is stated on that page. It is not used in the experiment.

The alternate [dEchorate dataset](https://zenodo.org/records/6576203) includes measured multichannel RIRs and early-echo annotations. The paper reports 30 microphones in six 5-microphone arrays, 48 kHz synchronized acquisition, loopback on the acquisition setup, bIPS positions (±2 cm), and manually annotated TOAs/wall identities. The 2021 Zenodo HDF5 record lists a 25.8 GB archive and declares CC BY 4.0 in record API metadata; the inspected SOFA file itself embeds an MIT license statement. Only a 1.76 MB SOFA sample and 30 KB annotation file were downloaded and included. See [dataset suitability](phase6e_dataset_suitability.md) and [sample attribution](../data/raw/dechorate_phase6e/ATTRIBUTION.md).

The inspected SOFA file is `dEchorate_room000000_src1_arr1_mics1-5.sofa`, one measured RIR with 5 channels and 48,000 samples/channel at 48 kHz. It supplies receiver/source positions, room corners and zero per-channel `Data.Delay`. The HDF5 annotations have `echo_toa` and `echo_wall` shapes `(7, 30, 6)`; for source 1 and microphones 1–5, rank 0 is the direct annotation and ranks 1–6 are the provider's early-echo labels.

The JSON output records SHA-256 values for both included source files so the measured-data subset and annotation source can be checked independently.

## 3. Calibration, synchronization, and ground truth

Channel order follows SOFA `ReceiverPosition` order and the filename's microphone range. Source and receiver coordinate variables explicitly declare metres. Room-corner values omit a `Units` attribute; their metre-scale interpretation is consistent with the paper's approximately 6 × 6 × 2.4 m room and is preserved as an interpretation in JSON. Speed of sound was fixed at **346.98 m/s**, the value reported by the dEchorate paper for its documented 24 ±0.5 °C and 80% RH condition; BatSight did not measure conditions for this file. Source emission and RIR recording origin were set to 0 s, consistent with the stored zero `Data.Delay` and RIR convention.

Synchronization classification is **supported by dataset documentation/acquisition protocol**, not independently verified: the paper says microphone channels were synchronously acquired at 48 kHz; all inspected channel delays are zero; raw loopback data are not included in this SOFA file. The result does not claim independently verified hardware synchronization.

Direct and echo reference times and wall labels come from dEchorate's annotation HDF5. The paper describes these annotations as manual peak-finder/GUI annotations initialized against a simulated RIR and subsequently reconciled with geometric-space data. The annotation file supplies no per-label numeric uncertainty; BatSight records uncertainty as unknown. The 0.5 ms match gate is the threshold reported by the dataset paper's goodness-of-match analysis, not an estimate of annotation uncertainty. Full ground-truth values and provenance are in `experiments/phase6e_results/dEchorate_provider_annotations.json`.

## 4. Extractor configuration and protocol

The experiment calls `analyze_multichannel_recording` from Phase 5E.1 without changing its algorithm or configuration. The impulse reference has one sample at amplitude 1.0. The existing matched-filter normalization is reference energy, which makes its output equal to the measured RIR samples. The RIR is treated as a common-origin 48 kHz multichannel signal with source emission time and recording start time zero. Geometry-gated direct candidates use the supplied source/microphone coordinates and paper sound speed.

Frozen Phase 5E.1 settings: direct tolerance 2 ms; echo excess-delay interval 0.2–50 ms; minimum peak separation 0.15 ms; window 8 samples; `thr1=0.9`, `thr2=0.02`; minimum prominence 0; either polarity; no timing-uncertainty override. No threshold was tuned to this subset. External timing scoring is one-to-one with a 0.5 ms tolerance. Direct and echo matches are scored separately; echo detections stay unclassified in the extraction output. No room dimensions are estimated.

## 5. Direct-path results

Across 5 microphone/event pairs, the extractor returned 5 direct candidates. All 5 matched independent provider annotations within 0.5 ms: precision **1.000**, recall **1.000**, 0 false positives, and 0 misses. Absolute TOA error was:

| Metric | Milliseconds | Samples at 48 kHz |
|---|---:|---:|
| Mean absolute error | 0.02564 | 1.231 |
| Median absolute error | 0.02734 | 1.312 |
| 95th percentile absolute error | 0.04452 | 2.137 |
| Maximum absolute error | 0.04877 | 2.341 |

Per-channel signed errors (BatSight minus provider) were mic1 **−0.0276 ms**, mic2 **−0.0075 ms**, mic3 **−0.0171 ms**, mic4 **−0.0488 ms**, and mic5 **+0.0273 ms**. Independently, the geometry-predicted direct time differed from provider direct annotations by **0.01186 ms mean absolute** and **0.01281 ms maximum** over five channels, using the paper's sound speed and supplied positions. Small residuals are consistent with provider annotation, environmental sound-speed, finite-sample, and parabolic peak-estimation differences; they do not override unknown annotation uncertainty.

## 6. Early-echo candidate results

The provider supplies six early-echo annotations for each of the five microphones. The existing extractor emitted 533 unclassified candidates; 30 matched one-to-one within 0.5 ms, and none of the 30 annotations was missed. Precision was **30/533 = 0.0563**, recall **30/30 = 1.000**, with 503 unmatched candidates. For the annotated-first-order task, an unmatched detection is counted as a false positive and an unmatched annotation as a miss. The 503 candidates are not asserted to be physically false: they may include late or higher-order paths absent from the six-label reference, clutter, or peak errors. Matched echo timing MAE was **0.12413 ms** (5.96 samples), maximum **0.30778 ms** (14.77 samples). The per-channel number of candidates was 117, 111, 100, 106 and 99 for mic1–mic5 respectively; each channel recovered all six labeled echoes.

The per-channel echo candidate counts were 117, 111, 100, 106 and 99 for mic1–mic5 respectively. The analysis retained **55,488 peak-audit records** (compressed CSV audit included). The Phase 5E.1 audit list contains selected, suppressed, out-of-window, and threshold-rejected local peaks; it is not a count of verified physical echoes. Its disposition counts are in the JSON. The candidate precision result supports the known clutter limitation. It does not establish that every unmatched detection is a physical reflection: they remain unclassified candidates.

## 7. Robustness and failure cases

Metric denominators: direct precision = direct candidates matched within 0.5 ms / all selected direct candidates; direct recall = matched direct annotations / all five direct annotations. Echo precision = one-to-one matched candidates / all emitted unclassified echo candidates; echo recall = matched first-order annotations / all 30 provider first-order annotations. TOA error summaries use only matched pairs. Thus an unmatched echo candidate contributes to first-order false-positive accounting but is not declared a physically nonexistent echo.

The chosen subset has no provider SNR label, no raw room-tone track, and only one configuration/source/array. SNR, weak-reflection detection, close-arrival robustness, missing-channel robustness, threshold sensitivity, and recording-to-reference variation were not measured. There is no threshold-tuning/test leakage because the defaults were frozen. A representative failure mode is candidate clutter: 503 detected echo candidates were not within 0.5 ms of the six-per-channel provider early-echo labels. The most direct supported explanation is that the peak detector retains many extra peaks under the unchanged defaults. The data do not isolate how much is caused by late reverberation, measurement noise, deconvolution artifacts, or detector thresholds.

## 8. Plots and machine-readable outputs

All plots are labeled as imported real multichannel RIR evidence, not synthetic data.

- [RIR waveform and matched-filter response](../experiments/phase6e_results/real_rir_waveform_and_correlation.svg)
- [Detected versus provider arrival times](../experiments/phase6e_results/real_arrival_comparison.svg)
- [Per-channel direct/echo timing errors](../experiments/phase6e_results/real_channel_errors.svg)
- [Precision and recall](../experiments/phase6e_results/real_precision_recall.svg)
- [Complete metrics and per-channel output](../experiments/phase6e_results/dEchorate_real_rir_validation.json)
- [Provider annotations and source provenance](../experiments/phase6e_results/dEchorate_provider_annotations.json)
- [Peak disposition audit](../experiments/phase6e_results/dEchorate_peak_audit.csv.gz)

## 9. Reproduction

From the project root, install the optional HDF5 reader and run:

```powershell
py -3.14 -m pip install -e ".[phase6e,dev]"
py -3.14 experiments/phase6e_real_multichannel_validation.py
py -3.15 -m pytest -q
```

The research runner does not change the production detector. It recreates JSON, CSV audit, and SVG plots from the included source data. The original 25.8 GB dataset archive is not required.

## 10. Application integration and blockers

No frontend/backend UI was added. The existing Phase 6D recording panel already shows session data provenance, synchronization interpretation, validation state, and that estimated room geometry is unavailable. Phase 6D accepts calibrated raw WAVs and a transmitted reference; this sample is an already-deconvolved SOFA RIR and must not be silently treated as a raw recording session. The report and provenance are directly inspectable as research artifacts. No estimated room geometry is exposed.

Remaining blockers before claiming full real-recording validation:

1. Obtain a properly licensed accessible copy of the VGM raw recordings or a dEchorate raw ESS/microphone/loopback subset.
2. Validate the Phase 5E.1 raw excitation/reference pipeline, including emission and recording-time origins.
3. Evaluate multiple held-out source positions, arrays, room configurations, and channel conditions.
4. Establish timing annotation uncertainty and independently verify channel synchronization or quantify residual clock offsets.
5. Investigate the 503 unmatched echo candidates on additional labeled data, with controlled development/held-out separation.

Phase 6E does not claim system validation, arbitrary room reconstruction, or real-world room-dimension accuracy.

## 11. Software validation

- Backend and project tests: `py -3.15 -m pytest -q --basetemp .pytest-tmp-phase6e-final` — **159 passed**, with one upstream Starlette/AnyIO deprecation warning. The nine new validation tests also pass independently.
- Frontend tests: `npm test` in `frontend/` — **3 files, 11 tests passed**.
- TypeScript and production build: `npm run build` in `frontend/` — passed (`tsc -b` and Vite build). Vite reported the existing large-bundle advisory; no frontend files changed in Phase 6E.
- Experiment: `py -3.14 experiments/phase6e_real_multichannel_validation.py` — completed and regenerated JSON, annotations, compressed audit and SVG plots from the included dEchorate sample.
