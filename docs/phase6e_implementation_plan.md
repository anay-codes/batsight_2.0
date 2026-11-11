# Phase 6E implementation plan and status

## Validation gates and stages

1. **Dataset gate:** record source URL/DOI, license, actual-file accessibility and inspected format. Require usable multichannel measurements, sample rate, channel/calibration metadata, synchronization evidence, event/reference timing and independent arrival annotations. If any essential condition is absent, report that evaluation mode as blocked; do not synthesize the missing evidence.
2. **Ground-truth contract:** add versioned, provenance-bearing records for dataset/file/event/channel identity and direct/echo annotations. Keep provider annotations distinct from geometry-derived values and manual labels; include uncertainty, ambiguity, and unknown states.
3. **Pure evaluation functions:** deterministic recording/reference matching, one-to-one arrival matching with a declared tolerance, precision/recall/counts, signed/absolute TOA error in seconds/ms/samples, and explicit missing/ambiguous annotation handling. No BatSight detector output may enter reference annotation construction.
4. **Existing extractor adapter:** call the Phase 5E.1 implementation unchanged when the dataset format and its measurement model satisfy the Phase 6D inputs. Preserve parameters, direct/missing states, echo candidates, rejected-peak audit, diagnostics, and provenance. Document any incompatible RIR-only pathway rather than passing it off as raw-audio validation.
5. **Experiments and artifacts:** predeclare a dataset subset and settings before held-out evaluation. Emit machine-readable JSON/CSV and labeled plots for waveform/correlation, detected/reference timing, per-channel errors, and only those precision/recall values supported by independent labels. Separate real, synthetic, and laptop evidence.
6. **Application surface (only if needed):** expose validation provenance/status and real result summaries in the existing Recordings area without geometry output or a broad redesign.
7. **Tests and report:** deterministic tests for parsers, association, metrics, provenance, calibration rejection, missing/ambiguous annotations, and serialization; run existing and new backend/frontend checks. The report records failures and scientific limits as well as any measured results.

## Completed work and result

- Audited the VGM page and attempted its archive endpoint; the endpoint returned HTTP 403 and the page has no reuse license statement.
- Inspected and included one small dEchorate SOFA RIR sample and its compact independent annotation file. The 25.8 GB archive was not downloaded.
- Added provenance-strict metadata/annotation parsing and one-to-one timing metrics in `src/batsight/validation/real_recordings.py`.
- Ran the existing Phase 5E.1 analysis with its unchanged defaults on five channels of one real measured RIR and provider labels. Direct score: 5/5 within 0.5 ms, MAE 0.02564 ms. Echo score: 30/30 labels recalled, 30/533 candidate precision (5.63%). Full rejected-peak audit and plots are archived under `experiments/phase6e_results/`.
- No frontend/backend workflow was changed. The sample is a deconvolved SOFA RIR and does not satisfy Phase 6D's raw-WAV plus transmitted-reference recording contract.
- Validation: 159 Python tests passed; frontend suite 11/11 passed; TypeScript and production build passed with the existing large-chunk advisory. Repeating the experiment produced identical measurements/metrics after excluding runtime (which naturally varies by run).

Detailed evidence: [dataset suitability](phase6e_dataset_suitability.md), [calibration and provenance audit](phase6e_calibration_ground_truth.md), and [validation report](phase6e_real_validation_report.md).

## Current pre-implementation finding

The dEchorate sample is accepted only for a restricted measured-RIR TOA/peak-detection evaluation, not as raw waveform validation. The unresolved acquisition blockers are obtaining accessible raw probe/microphone/loopback data, establishing per-arrival timing uncertainty and independently checking synchronization, and expanding the held-out evaluation across recordings. The VGM source remains blocked by access and license uncertainty.
