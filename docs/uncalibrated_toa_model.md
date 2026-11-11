# Uncalibrated TOA observation dataset

This module generates a **forward-only synthetic observation dataset** for the direct-path timing model. It starts from known room, source, and microphone geometry. It does not estimate positions, infer walls, or reproduce the complete reconstruction method in the 2016 paper.

## Observation equation

For microphone `i` and source emission `j`:

\[
\widehat{t}_{ij}=e_j+\frac{\|\mathbf{s}_j-\mathbf{m}_i\|_2}{c}+b_i+\eta_{ij}.
\]

| Symbol | Meaning | Unit |
|---|---|---|
| `s_j` | Ground-truth position of source event `j` | m |
| `m_i` | Ground-truth position of microphone `i` | m |
| `e_j` | Source emission time for event `j` | s |
| `c` | Configured speed of sound | m/s |
| `d_ij = ||s_j - m_i||₂` | True direct-path geometric distance | m |
| `d_ij / c` | Ideal direct-path propagation time | s |
| `b_i` | Microphone clock offset | s |
| `eta_ij` | Timing measurement error | s |
| `t_hat_ij` | Measured time of arrival | s |

The arrays use `[microphone_index, source_index]` order. The dataset retains `d_ij`, propagation time, ideal TOA (`e_j + d_ij/c + b_i`), timing noise, measured TOA, and the missing mask separately. A missing measured TOA is represented internally as NaN and in JSON as `null`; its ideal TOA and generated noise remain recorded.

## Time and coordinate conventions

Coordinates are metres in a right-handed Cartesian `x,y,z` system. The room origin is its minimum corner, and every source and microphone must be strictly inside the rectangular room. The same configured `c` is used for all pairs.

Emission times are the event times in the chosen common reference timeline. Clock offset `b_i` is additive: a positive value makes microphone `i` report a later timestamp by that amount. Emission times and offsets may be nonzero and may be signed where a chosen time origin makes that appropriate. The generated ideal and measured timestamps are not constrained to be positive; callers choose the experiment's time origin.

There is no sample rate or sample-index quantization in this dataset. It is a continuous-time, sampling-independent observation model.

## Noise and missing observations

When `timing_noise_std_seconds = sigma`, each pair receives an independent draw `eta_ij ~ Normal(0, sigma^2)` in seconds. With zero sigma, noise is exactly zero. `random_seed` initializes NumPy's generator so noise and random missingness are repeatable for the same inputs and package behavior.

Random missingness uses independent Bernoulli draws: each pair is marked missing with the configured `missing_probability`. Alternatively, callers can supply an explicit Boolean mask. An explicit mask and nonzero random missing probability cannot be combined. Missingness affects only the measured TOA field; geometry, ideal times, and generated noise are retained. This simple missing-at-random model does not represent signal-dependent detection failures.

## Evidence and engineering choices

**Paper-derived concept:** the 2016 work formulates direct-path arrival timing using unknown source and microphone locations, source emission times, microphone timing offsets, and propagation distance divided by sound speed. This module uses that forward relation with known ground truth to create observations. It does not implement the paper's initialization procedure or optimization.

**Engineering choices:** independent Gaussian timing errors, independent Bernoulli missingness, strict interior validation, the `[microphone, source]` array order, NaN/null missing values, JSON schema, and seeded NumPy random generation are dataset design choices. They are not claimed as the paper's noise, missingness, or data serialization protocol.

## Future use and limits

The dataset can later exercise code that estimates source and microphone positions or timing nuisance variables from incomplete pairwise TOAs, with ground truth available for evaluation. It does not contain reflections, waveform detection, frequency-dependent propagation, measured sensor data, or paper-specific experiment metadata. A generated dataset is not evidence of successful localization or a reproduction of the full paper experiment. The paper's unresolved initialization details (including the phi correction, timing update, rank-3 projection, quadratic constraints, and stopping criteria) remain unresolved and are intentionally not inferred here.
