# Synthetic shoebox room simulation

This module implements a **forward** image-source simulator for axis-aligned rectangular rooms. Given room dimensions, a known source position, one or more known microphone positions, and an input waveform, it produces synthetic RIRs and convolution recordings. It does not estimate unknown source/microphone positions or room geometry.

## Evidence boundary

The 2016 Crocco et al. paper supports the general image-source construction for convex planar reflectors and defines image sources by reflecting a source across a plane (its Eqs. 2–4). It explicitly models first- and second-order images and describes idealized mirror-like reflections. The shoebox tiling, amplitude convention, duplicate handling, fractional-sample interpolation, and noise procedure below are **BatSight engineering choices**, not claims that they reproduce the paper's full simulation setup or its exact implementation. The paper's unresolved Eq. 10 chirp is not used or implemented here; any `AudioSignal` can be supplied as input.

## Coordinate system and validation

The room's minimum corner is the origin in a right-handed Cartesian system. Dimensions are `(Lx, Ly, Lz)` in metres. Its six planar walls are `x_min`, `x_max`, `y_min`, `y_max`, `z_min`, `z_max`, at coordinates 0 or the corresponding room dimension. Source and microphone coordinates must each satisfy strict interior bounds on all axes; points on a wall or outside are rejected. The configured sound speed is positive and in metres per second (default 343 m/s).

Each wall has a real pressure-amplitude coefficient in `[-1, 1]`. Missing wall entries default to 0.8. A path coefficient is the product of its wall coefficients; the direct path has coefficient 1.

## Image-source mathematics and enumeration

For a point `b=(bx,by,bz)`, reflection across an axis-aligned wall at coordinate `q` on axis `i` maps that coordinate to

`b'_i = 2q - b_i`,

and leaves the other two coordinates unchanged. Thus `x_min` maps x to `-x`, while `x_max` maps x to `2Lx-x` (and similarly for y and z). This is a rectangular-room specialization of the paper's plane-reflection equation.

For an image source `p` and microphone `s`, the simulated path length and TOF are

`d = ||p - s||_2` metres, `tau = d / c` seconds.

The simulator emits direct order 0, six first-order images, then ordered pairs of different wall reflection operators for second order, matching the paper's distinct-wall second-order construction. Operator order is part of the path label and enumeration is deterministic. In an axis-aligned shoebox, reflections in perpendicular walls commute and can produce the same image coordinate. Exactly coordinate-identical images are collapsed, keeping the first lexicographic sequence. Opposite parallel walls yield distinct images and remain distinct. This avoids duplicating an identical image-source path; it does not separately trace or validate bounce-point trajectories. Reflection sequences are the ordered image-construction wall identifiers, not an independently verified physical bounce list.

## RIR amplitude convention

Each image path deposits a discrete impulse with amplitude

`a_path = (product of pressure reflection coefficients) * (1 / d)`.

The factor `1/d` is the selected, frequency-independent geometric spreading convention. The wall coefficient product is kept separate and represents reflection attenuation. This normalized model omits the source-strength, density, frequency, and microphone-sensitivity factors needed for calibrated pressure units; RIR amplitudes are relative with a geometric `1/m` factor. A coincident image/microphone is rejected because `1/d` is singular.

## Fractional-sample arrival placement

The continuous arrival position is `u = tau * fs` samples. By default (`impulse_placement="linear"`) it is not rounded: let `n=floor(u)` and `alpha=u-n`. The path amplitude is split between samples n and n+1 as `a[n] += (1-alpha)*a_path` and `a[n+1] += alpha*a_path`. This preserves the impulse sum and its first temporal moment. The RIR is allocated through the upper sample index of the latest arrival. An alternate `"nearest"` convention deposits the complete impulse at `floor(u+0.5)` and incurs at most `0.5/fs` seconds of quantization error; ties go to the later sample.

Linear splitting is a simple first-order fractional-delay approximation. It introduces a triangular interpolation response and can attenuate high-frequency energy near Nyquist. It is not an ideal bandlimited delay filter. The nearest-sample convention is available when that explicit quantization is desired; it is never applied silently.

## Input waveform, multiple microphones, and noise

`simulate_recordings` convolves a mono supplied waveform with a separately generated RIR for each microphone using full linear convolution. Different channel output lengths are zero-padded to a shared sample-frame length and returned as an `AudioSignal` with shape `(samples, microphones)`. The existing matched filter and peak detector are unchanged.

Optional noise is independent zero-mean Gaussian noise, generated from a NumPy RNG. For each channel, variance is set using its noiseless mean-square power and requested `snr_db`: `noise_power = signal_power / 10^(snr_db/10)`. The optional seed makes output deterministic. A silent channel gets no noise. Finite negative SNR values are accepted. The realized finite-sample SNR will vary around the requested value.

## Assumptions and omissions

This is a low-order, geometric forward model for a convex rectangular enclosure. It includes only direct, first-, and second-order paths. It does not model frequency-dependent absorption or reflection phase, air absorption, diffraction, scattering, diffuse reverberation, furniture/occlusion, wall thickness, source or microphone directivity, microphone/loudspeaker impulse responses, nonlinear distortion, or a calibrated absolute source level. The input waveform can be any caller-supplied samples; its generation is outside this simulator. No accuracy claim or inverse reconstruction capability is implied.

## Verification scope

Tests check hand-computed path lengths, reflection enumeration and duplicate collapse, symmetric path distances, position validation, fractional sample deposition, reflection coefficient scaling, deterministic output, multiple microphone channels, and optional noise behavior. Passing tests verifies these programmed conventions; it does not validate real-room fidelity or reproduce the paper's evaluation.
