# End-to-end synthetic acoustic experiments

The `batsight.experiments` package connects the forward shoebox simulator to the existing matched filter and peak detector. It measures how known simulated arrivals appear in processed recordings. It does not estimate unknown room geometry or perform inverse reconstruction.

## Pipeline

For each configured experiment:

1. Validate room, source, microphone positions, mono excitation, and sample-rate agreement. No resampling is performed.
2. Generate a forward shoebox RIR for every microphone with the selected maximum reflection order and impulse placement convention.
3. Convolve the supplied excitation with each RIR. Optionally add seeded Gaussian noise at the requested nominal SNR.
4. For each recording channel, call the existing full-correlation `matched_filter` using the exact supplied excitation waveform as reference. Its existing default reference-energy normalization, full-correlation lag convention, and polarity behavior remain unchanged.
5. Run the existing two-stage `detect_peaks` on the correlation values. Peak indices are local to the full correlation array; their time coordinate is shifted by the first signed correlation lag so detected times are directly comparable with non-negative propagation TOFs.
6. Compare sorted detected peak times against sorted simulator path TOFs, retaining all ground truth, all detections, matched pairs, missed paths, unmatched peaks, and errors.

The default peak window is 1 ms (`round(0.001 * fs)` samples, minimum 1), `thr1=0.9`, and `thr2=0.1`. These are visible parameters and can be changed in the run configuration. The default matching tolerance is one sample period (`1/fs` seconds); it is a deterministic engineering choice that accounts for sample-grid peak timing, not a tolerance established by the paper. Set `matching_tolerance_seconds` explicitly for controlled comparisons.

## Arrival matching and metrics

Matching is chronological and one-to-one. Expected arrivals and detected peaks are sorted by their time, with stable original order for ties. A two-pointer pass pairs the earliest remaining entries if their absolute difference is at most the configured tolerance; otherwise it marks the earlier entry missed/unmatched and advances it. No detected peak can explain multiple paths, and no out-of-tolerance pair is forced. The rule is deterministic and does not infer echo labels or wall identities from the signal.

For each accepted pair `i`, the absolute TOA error is `e_i = |t_detected,i - t_expected,i|`. Mean absolute error and root mean square error are computed over accepted matches only:

`MAE = mean(e_i)`; `RMSE = sqrt(mean(e_i^2))`.

Counts of matched, missed expected, and unmatched detected arrivals are reported separately. If no pair is accepted, MAE and RMSE are `null`/`None`, not zero. Overall metrics aggregate accepted pairs across microphones; per-microphone metrics remain available.

## Results and export

`ExperimentResult.to_dict()` returns JSON-compatible experiment settings, room and microphone metadata, ground-truth paths, detections, matches, missed/unmatched items, and metrics. To include raw excitation, multichannel recordings, RIR arrays, or full correlation traces, call `to_dict(include_waveforms=True, include_correlations=True)`; these arrays can be large. The configuration stores the excitation sample count, rate, and SHA-256 hash so callers can identify the exact waveform. `write_csv(path_or_text_stream)` writes one row for each matched path, missed expected arrival, or unmatched peak. Unmatched items receive separate rows instead of synthetic matches.

Run fixed-seed examples from the repository root after installing the package:

```powershell
python experiments/synthetic_examples.py
```

The examples cover order 0, order 1, order 2, two microphones, noiseless runs, and 20, 10, and 0 dB noise settings. They use a generic configured linear sweep and make no claim to reproduce the paper's unresolved Eq. 10.

## What the results mean

- **Simulator ground truth** is the generated image-source path set and continuous geometric TOFs under the configured shoebox model.
- Geometric paths remain in the expected set even when their configured reflection coefficient is zero; such a path has no simulated energy and is expected to be missed. Its coefficient remains visible in path metadata so this case is not mistaken for a peak-detector failure.
- **Detected measurements** are sample-grid peaks after full matched filtering and threshold peak detection. They can include sidelobes or noise peaks and can miss weak or closely spaced paths.
- **Engineering metrics** describe only tolerance-accepted pairs in this simulator. The matching tolerance, threshold parameters, waveform, and noise seed are part of the recorded configuration.
- These results test orchestration and forward-simulation/TOA measurement behavior. They are not real-room measurements, do not validate the paper's complete reconstruction, and are not evidence of accuracy for unknown geometry.

## Assumptions and limitations

The experiment inherits the shoebox simulator's axis-aligned convex-room model, low-order ideal image sources, `1/d` spreading, frequency-independent scalar wall coefficients, and linear/nearest impulse placement options. It omits frequency-dependent absorption, diffraction, scattering, directivity, device responses, and calibrated source/microphone units. The matched filter uses the existing ordinary reference-energy-normalized correlation, not a new GCC-PHAT implementation. Peak detection preserves its existing forward-window and global-threshold semantics. Finite-sample Gaussian noise yields approximate, not exact, realized SNR.

The waveform hash identifies samples but is not a substitute for storing the waveform. For fully portable reruns, retain the excitation samples and use the recorded room, positions, thresholds, noise seed, sample rate, impulse placement, and matching tolerance.
