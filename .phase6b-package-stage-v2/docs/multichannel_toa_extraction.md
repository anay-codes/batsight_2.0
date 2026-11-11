# Phase 5E.1 — multichannel audio to unlabeled TOA observations

## Scope and scientific separation

This module accepts synchronized multichannel recordings, a known transmitted waveform, and calibrated microphone/source/event inputs. It performs matched filtering and produces direct-path candidates plus unlabeled echo candidates. It does not estimate wall identities, and it does not guarantee that every echo candidate is a first-order reflection. Candidates may include true first-order paths, higher-order paths, waveform sidelobes, noise peaks, or false detections.

The phase reuses BatSight's full discrete matched-filter correlation and two-stage local/global peak detector. The input chirp can be any caller-supplied known waveform. The generic engineering sweep used in synthetic experiments is not a reproduction of the unresolved 2016 paper chirp equation.

## Input contract and time convention

`analyze_multichannel_recording` accepts an `AudioSignal` with samples-by-channel layout. Channel index must equal the microphone order in `CalibratedMicrophoneArray`. Recording, calibration, and reference sample rates must match exactly; no resampling, channel permutation, filtering, or gain normalization is applied. Optional metadata declarations for sample rate/channel count are checked against the signal object.

`recording_start_time_s` gives the common-clock timestamp of recording sample zero. Each event's expected direct arrival is calculated using known source/microphone coordinates, emission time, and sound speed:

`t_direct = t_emission + ||source - microphone|| / c`.

Matched-filter lags are relative to the recording's first sample and are converted back to the common timestamp by adding `recording_start_time_s`. Events must share synchronized clocks and known emission times, as required by the calibrated observation model.

The file loader currently supports WAV PCM integer and WAV floating-point data through SciPy. Integer PCM is converted to dimensionless floating-point full scale; unsigned PCM is midpoint-centered. Floating data is passed through. The loader records encoding, sample rate, and channel count. An optional expected rate rejects mismatch; the loader never resamples. Other audio file formats require a separate explicit decoder adapter.

## Matched filtering and peak audit

For each event/microphone pair, the reference-energy normalized matched filter computes full correlation `correlate(recording, reference, mode="full") / sum(reference**2)`. Positive lag indicates delayed reference onset. Detection uses absolute correlation by default (`polarity="either"`) and the existing `thr1` forward-window local threshold and `thr2` global threshold. This is not GCC-PHAT, and it is not a probabilistic detector.

All local maxima are audited. Peaks rejected by local/global thresholds, the prominence floor, direct timing gate, candidate delay window, or duplicate suppression retain a `RejectedPeak` with a reason, lag/time, amplitude, and prominence. A direct peak selected for the direct output is also marked `selected_direct` in that audit to distinguish it from echo candidates. Threshold-rejected maxima can be numerous on noise-rich records; the audit is for traceability, not a calibrated false-alarm model.

Prominence is computed on absolute matched-filter output. `peak_to_noise_ratio` divides absolute peak response by a robust MAD-derived scale over the full correlation sequence. It is a descriptive strength diagnostic, not a probability or calibrated SNR. Endpoint maxima use absolute height as a prominence fallback.

## Direct path and echo candidates

Among threshold-accepted peaks within `direct_tolerance_s` of the known-geometry direct prediction, the nearest TOA is selected; amplitude breaks exact timing ties. If none passes, a direct observation with missing status is emitted by the adapter. Other peaks in the direct gate are audited as not selected.

Echo candidates are accepted peaks inside
`[t_direct + minimum_echo_excess_delay_s, t_direct + maximum_echo_excess_delay_s]`.
The maximum excess delay is a caller-selected analysis window, not an inferred room bound. Candidates closer than `minimum_peak_separation_s` are clustered; the member with greatest prominence (then absolute response) is retained and the rest are recorded as duplicates.

Every emitted echo is marked `unclassified_echo_candidate`; its adapter record has no wall label and no first-order hint. The extraction window cannot distinguish first-order from higher-order paths without additional information. No candidate is silently labeled or removed due to an assumed arrival ordering. The Phase 5D.3 estimator may still accept higher-order/false candidates as assignment competitors; this is one cause of degraded dimension estimates and must be considered separately from extraction recall.

## Sub-sample estimates and uncertainty

The integer correlation maximum is refined by a three-point parabolic interpolation of the absolute correlation magnitude. The offset is clipped to half a sample. This is a local interpolation engineering approximation, not a bandlimited delay estimator. `fractional_sample_index` and `arrival_time_s` preserve the refined value; `integer_peak_index` is the matched-filter lag sample.

No uncertainty is inferred from prominence or MAD. By default, TOA `uncertainty_s` is `None`. If a caller supplies `timing_uncertainty_s`, that value is copied to readings as an externally chosen standard deviation; the code does not validate its statistical calibration. Users should leave it unset until justified by repeated measurements or a separate noise/delay study.

## Observation adapter and provenance

`recording_analysis_to_observations` creates one direct-path record per microphone/event pair and one `UnlabeledEchoTOAObservation` per accepted echo candidate. It preserves TOA, explicit missing direct states, detection strength, provenance, and the unclassified-candidate marker. Synthetic adapter use is marked `synthetic_audio`; real-file use is marked `multichannel_file`. It never transfers simulator wall labels. Rejected peak audit records remain in `RecordingAnalysisResult`, not the estimator's observation set.

## Synthetic validation and measured outcome

`experiments/shoebox_audio_toa_recovery.py` uses the existing image-source RIR simulator and generic linear sweep to create multi-event/multichannel audio, including seeded post-mix Gaussian noise. Ground-truth path times and wall labels are held only in the experiment scorer. The result JSON includes direct detection, first-order candidate recall, timing errors in microseconds and samples, unmatched/duplicate candidate metrics, rejection reasons, and separate Phase 5D.3 dimension recovery diagnostics.

In the deterministic run, direct detection was 100% in all five cases. Four broader-layout cases had first-order recall about 0.917–0.958; an explicit close-arrival symmetry case fell to 0.667. Between 0.673 and 0.846 of emitted unlabeled echo candidates did not match a first-order truth path (including higher-order paths and false peaks). The Phase 5D.3 dimension fit converged numerically, but dimension error reached about 0.81 m in the broad-layout cases and 1.23 m in the close-arrival case. This demonstrates why extraction and reconstruction metrics must be reported separately: convergence and high first-order recall did not imply correct room dimensions. These are synthetic results only.

## Real multichannel prerequisites and limits

Real calibrated reconstruction input requires a known transmitted chirp/reference, sample-accurate common clock and recording start, synchronized microphone channels with known channel order, calibrated microphone and source positions, known emission times, known sound speed, and adequate recording duration. The current checks cannot establish physical synchronization, emission-time truth, microphone calibration, or whether an observed peak is a room reflection. A laptop single-microphone demo is a separate waveform/spectrogram/echo-analysis mode and does not satisfy this multichannel calibrated reconstruction contract.
