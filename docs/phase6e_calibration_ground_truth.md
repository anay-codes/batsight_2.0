# Phase 6E calibration, synchronization, and annotation provenance

## Calibration audit

| Item | Evidence | Classification / limit |
|---|---|---|
| Channel-to-microphone map | SOFA filename `mics1-5`; `ReceiverPosition` provides five positions in channel order. | Supplied file mapping; no separate hardware channel audit. |
| Position units | SOFA `SourcePosition` and `ReceiverPosition` explicitly declare metres. `RoomCornerA/B` are present but do not carry a `Units` attribute; their approximately 5.7 × 6.0 × 2.4 values are interpreted in the metre coordinate scale and agree with the paper's roughly 6 × 6 × 2.4 m room. | Source/receiver units are file metadata. Room-corner unit interpretation is documented, not silently treated as explicitly declared. dEchorate paper says bIPS position acquisition had ±2 cm errors. |
| Sample rate | SOFA `Data.SamplingRate` is 48,000 Hz and `Data.IR` has 48,000 samples per channel. | Directly inspected metadata; no resampling. |
| Sound speed | dEchorate paper gives 346.98 m/s at 24 ±0.5 °C and 80% RH. | Published acquisition condition; not a new sample-specific measurement by BatSight. |
| Inter-channel synchronization | Paper states synchronous acquisition at 48 kHz; SOFA `Data.Delay` is zero for all five channels. | **Supported by dataset documentation/acquisition protocol**, not independently verified from raw clock/loopback data. |
| Emission and recording origin | SOFA RIR sample has zero per-channel delay; the RIR convention uses sample zero as origin. | RIR-domain zero reference. The raw emission/loopback track is absent from this file. |
| Hardware/clock offsets | Not included as independently measured offset values in this sample. | Unknown residual offsets; do not estimate them silently. |

## Ground-truth provenance

The experiment uses dEchorate `echo_toa` and `echo_wall` labels. The paper states that array/source positions were acquired with a Beacon indoor positioning system and that a GUI was used to manually tune a peak finder and label echo times and image-source/wall identities. It warns that geometric and signal-space annotations can disagree, and reports a compromise between bIPS positions and MDS-refined TOAs. Accordingly:

- Direct and early-echo times are **provider annotations**, not instrument-verified timestamps and not BatSight detections.
- The annotation file does not provide per-arrival uncertainty. BatSight stores uncertainty as unknown (`null`).
- Position values are provider calibration, not positions surveyed independently by BatSight.
- The metric tolerance is 0.5 ms, matching the threshold used in the dEchorate paper's goodness-of-match comparison. This is an evaluation threshold, not a claim about label uncertainty.
- Wall labels remain scoring-only. Phase 5E.1 sees no wall labels and continues to emit echoes as unclassified candidates.

## Provenance classes and application integration

The result file declares `imported_real_multichannel`. It is never combined with synthetic or laptop-single-device results. No frontend/backend dataset-import workflow was added: Phase 6D's uploaded-session route expects raw calibrated WAV/reference inputs, whereas the inspected artifact is a deconvolved RIR. Reporting it through that route would misstate the measurement type. Existing result provenance should remain visible if a future UI gains an RIR-specific imported-evaluation view. No estimated room geometry is produced.
