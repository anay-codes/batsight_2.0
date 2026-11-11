# Validation plan

No validation run or BatSight performance claim is made in Phase 1. The following plan defines evidence required before claims are made.

## Scientific unit checks

- Check plane reflection `IM(b,r)` by confirming the reflected point lies on the opposite side at equal signed distance and the midpoint-to-plane relationship holds.
- Check direct, first-order, and ordered second-order path lengths against manually calculated examples; check distinct-plane index handling.
- Check TOA decomposition into propagation, emission time, and microphone offset; test sign and unit conventions.
- Check matched-filter delay recovery with known synthetic delays and the exact paper chirp once its formula is resolved.
- Check peak detector behavior for isolated pulse, sidelobes, close arrivals, weak peaks, noise, and boundaries; report misses/false detections rather than tuning against reconstruction outcomes alone.

## Synthetic end-to-end validation

- Recreate the paper's six-face perturbed convex-room distribution, source/microphone counts (20 sources; 8 and 12 microphones), 5 s 3–6 kHz chirp, image-method RIR, and SNR cases 14, 6, 0, -6, -14 dB.
- Use the paper's peak thresholds, grid resolution, score floor/width, and matching threshold only after formula/unit issues are confirmed. Store exact random seeds, sound speed, grid bounds, and solver settings; report any differences from unavailable paper details.
- Evaluate after Procrustes alignment. Report position errors, plane-normal angle and offset errors, inlier definitions, outlier rate, distributions across trials, runtime by stage, failed cases, and sensitivity to initialization.
- Compare greedy initialization to global refinement. Report both so refinement does not hide a poor or unstable initialization.

## Real dataset validation

- First verify the cited VGM dataset URL, license, files, channels, emitted signal, sampling/timing metadata, coordinate system, and ground-truth registration. Do not fabricate or reconstruct missing channels/data.
- Reproduce the paper's 12-microphone, 17-source setup and account for clock/signal alignment as documented.
- Evaluate source/microphone positions after registration/alignment and planes by normal angle and signed/absolute offset with consistent plane correspondence.
- Compare against paper Tables 1–3 and explicitly flag the Table 1 prose/table label discrepancy and vaulted-ceiling mismatch.
- Preserve dataset-provided splits/recordings and never tune thresholds on evaluation results without labeling that as tuning.

## Product mode checks

- Single-laptop mode must display channel count and label outputs waveform/spectrogram/echo or TOA exploration. It must not enable or claim the paper's complete multichannel uncalibrated 3D result.
- Research mode must expose required microphones, sources, timing assumptions, known signal, face count, and convexity assumption before running.
- Experiment exports must state paper version, algorithm/configuration, dataset provenance, units, alignment method, metrics, failures, and which numbers are paper-reported versus BatSight-measured.
