# Signal-processing foundation

This module provides signal containers, generic waveform generation, matched filtering against a caller-supplied reference, and a configurable two-stage peak picker. It does not estimate room geometry or implement any part of the reconstruction pipeline.

## Paper-derived behavior and engineering choices

| Component | Source-supported behavior | BatSight engineering implementation |
|---|---|---|
| Reference / matched filtering | The 2016 paper describes correlating with a time-reversed transmitted signal whose spectrum is normalized by spectrum magnitude (generalized correlation / PHAT-like weighting). | `matched_filter` uses ordinary full discrete correlation against an explicitly supplied waveform, normalized by reference energy by default. It deliberately does not apply spectral whitening or PHAT weighting. It is a conventional matched filter with a documented convention, not a claim to reproduce paper Eq. 11. |
| Generic waveform generation | Paper Eq. 10's chirp expression and frequency convention remain unresolved in the research audit. | Sine and linear sweep generators are generic engineering test signals. The linear sweep uses phase `2*pi*(f_start*t + 0.5*k*t^2)` where `k=(f_end-f_start)/duration`; this does not claim paper fidelity. |
| Peak detection | Paper Algorithm 1 uses a forward sliding window with local threshold `thr1`, then a global threshold `thr2`. The paper's exact sample-level peak extraction/boundary handling is underspecified. | Candidate peaks are local maxima of absolute correlation magnitude, endpoints are considered when they exceed their sole neighbor, the forward window is truncated at the end of input, and threshold comparisons are inclusive. Returned amplitude keeps its sign. See below. |

These engineering conventions are intentionally explicit and should be revisited if the journal article, errata, or authors' implementation clarifies the original definitions.

## Data models and units

- `SamplingFrequency.hertz`: samples per second (Hz), finite and strictly positive.
- `AudioSignal.samples`: finite `float64` samples, shape `(sample_count,)` for mono or `(sample_count, channel_count)` for multichannel audio. Amplitude units are caller-defined, commonly normalized full scale. Inputs are copied and marked read-only.
- `AudioSignal.duration_seconds`: sample-frame duration `sample_count / sampling_frequency_hz`. The last sample occurs at `(sample_count - 1) / fs`.
- `RecordingMetadata`: optional recording/source/device identifiers and attributes.
- `KnownReferenceSignal`: an explicitly known mono waveform.
- `DetectedArrivalTime`: zero-based sample index, time coordinate in seconds, and signed amplitude. The time coordinate can be negative for lag-array analysis; physical TOAs are expected to be non-negative in the acquisition's time origin.

Sample index conversion uses `t = index / fs`. Time-to-index conversion rounds to the nearest sample, with half-sample ties upward. Conversion does not clamp indices to a particular signal's duration. Signal generation chooses `N = round(duration * fs)` samples and returns times `n/fs` for `n = 0 ... N-1`; the requested duration is therefore a sample-frame duration and its endpoint is not sampled.

## Generic signal generation

`generate_sine_wave` and `generate_linear_sweep` accept SI-valued frequency (Hz), duration (seconds), sampling frequency (Hz), amplitude, and optional initial phase (radians). Frequencies must be non-negative and below Nyquist. These are synthetic test signals only. No signal generator currently claims to reproduce Crocco et al. (2016), Eq. 10.

## Matched filter convention

For recording `x[n]` and reference `r[n]`, the module computes SciPy's full discrete correlation `correlate(x, r, mode="full")`, associated with lag values from `correlation_lags(len(x), len(r), mode="full")`. A delayed copy `x[n] = a*r[n-d]` peaks at positive lag `+d`. A negative lag means the reference's sample-zero alignment lies later than the recording's. Output length is `len(x) + len(r) - 1`.

By default, values are divided by reference energy `E_r = sum_n r[n]^2`. For an exact noiseless, gain-scaled copy, the peak becomes the signed gain `a`. This is not coefficient normalization by the recording segment's energy. `normalization="none"` returns the raw correlation sum. A zero-energy reference is rejected.

The matched-filter statistic is optimal under the conventional known-waveform, additive white Gaussian noise model with a suitable signal model. The implementation does not estimate noise covariance, whiten colored noise, correct a propagation channel, or deconvolve source/microphone responses. Arrival selection defaults to largest absolute correlation to tolerate polarity inversion; choosing `polarity="positive"` assumes matching polarity. The returned score is signed either way. In noisy or multi-arrival recordings the largest match can be a false peak or a stronger later reflection; use peak detection and inspect outputs rather than treating one maximum as a guaranteed direct path.

No GCC-PHAT or alternative generalized cross-correlation weighting is silently applied. Implementing the paper's specific matched filter needs resolution of its spectrum-normalization and discrete-transform conventions.

## Two-stage peak picker

`detect_peaks(values, fs, window_length_samples, thr1, thr2)` first finds local maxima in magnitude. For each candidate at `i`, its local maximum is measured over forward interval `[i, i+T)`, clipped at the input end. Stage one retains the candidate when `|x[i]| >= thr1 * local_max`; this suppresses a smaller local maximum when a stronger candidate follows within T samples. Stage two retains it when `|x[i]| >= thr2 * global_max`. `thr1` and `thr2` are dimensionless fractions in `[0,1]`; window length is an integer number of samples; timestamps use seconds and `fs` in Hz.

This choice follows the forward iteration in the paper's pseudocode. The paper does not fully specify whether peaks are signed or magnitude-valued, how exact plateaus or endpoints are selected, or how a surviving run of nonzero samples maps to one peak index. BatSight uses absolute magnitude, SciPy local maxima, explicit endpoint handling, and returns one index per candidate. `start_time_seconds` shifts timestamps without changing returned sample indices and supports signed correlation-lag arrays. All threshold comparisons are inclusive. An all-zero input returns no peaks.

## Validation status

The tests use deterministic fixtures and seeds for sample conversion, waveform duration/frequency behavior, delayed and inverted references, additive noise, multiple arrivals, threshold behavior, edges, and invalid/numerically degenerate input. Passing these checks verifies implementation behavior only; it does not establish paper reproduction, echo-detection accuracy in real rooms, or any reconstruction performance.
