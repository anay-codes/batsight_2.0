# BatSight local API reference

Base URL: `http://127.0.0.1:8000`. Interactive schemas and example payloads are served by `/docs`; OpenAPI JSON is `/openapi.json`. All error responses use FastAPI's JSON `detail` field. IDs are local SQLite integer keys.

## System

| Method/path | Behavior |
|---|---|
| `GET /api/health` | App name/version, backend status, and database connection state. |
| `GET /api/system/info` | Python/version, capabilities, data/recording/export paths, upload limit. |

Capability responses explicitly say that uncalibrated and real-world reconstruction are not implemented or validated.

## 3D workspace path preview

| Method/path | Behavior |
|---|---|
| `POST /api/simulation/paths` | Predict direct, first-order and optionally second-order shoebox image-source paths for an editable visualization scene; validates interior source/microphone coordinates and reports first-order finite-wall bounce points. |

The request provides `room_dimensions_m`, `source_position_m`, one or more `microphone_positions_m`, optional `speed_of_sound_m_s` (default 343), `max_reflection_order` (0–2), and optional wall reflection coefficients. The response includes path length in metres, TOF in seconds, image-source coordinates, reflection order/sequence, first-order bounce validity, and `visualization_only_simulated_prediction_from_editable_scene` provenance. It is an ideal forward geometric prediction, never a measured or estimated path. Second-order sequences are virtual image-source operators; physical finite-bounce trajectories are not validated.

## Projects

| Method/path | Behavior |
|---|---|
| `POST /api/projects` | Create `{ "name": "...", "description": null, "metadata": {} }`; returns 201. |
| `GET /api/projects` | List projects. |
| `GET /api/projects/{project_id}` | Retrieve one project; 404 if absent. |
| `DELETE /api/projects/{project_id}` | Cascade-delete project records and associated managed recording files; returns 204. |

## Recordings

| Method/path | Behavior |
|---|---|
| `POST /api/recordings` | Multipart upload and WAV validation; returns 201 with metadata, never sample bytes. |
| `GET /api/recordings?project_id={id}` | List all recordings or filter by project. |
| `GET /api/recordings/{recording_id}` | Retrieve metadata. |
| `GET /api/recordings/{recording_id}/audio` | Download original managed WAV bytes after validating its storage path. |
| `POST /api/recordings/{recording_id}/analysis` | Run matched filtering, peak detection, and a display spectrogram for one selected channel. |
| `DELETE /api/recordings/{recording_id}` | Remove database record and verified managed WAV; returns 204. |

Upload form fields: `file` (WAV), `name` (required), `description` (optional), `project_id` (optional), and `metadata_json` (optional JSON object string). Unsupported extension/content, invalid WAV, out-of-range sample rate/channel count/duration, and excessive file size are rejected. Size limit returns 413; validation errors return 422; missing project returns 404. No file is silently resampled. The returned metadata has `file_size_bytes`, `sample_rate_hz`, `channel_count`, `sample_count`, `duration_s`, and user-provided acquisition metadata. The original uploaded bytes are retained in generated-name managed storage.

`POST /api/recordings/{recording_id}/analysis` accepts `channel_index`, reference settings (`waveform`, `reference_duration_s`, `start_frequency_hz`, `end_frequency_hz`, `amplitude`), matched-filter `normalization`, peak detector `window_length_samples`, `thr1`, `thr2`, and `spectrogram_nperseg`. The service generates the reference at the recording's original sample rate, rejects out-of-range channel selection, and limits analysis to `BATSIGHT_MAX_ANALYSIS_SAMPLES` (default 2,000,000 frames per channel). Its response includes recording metadata, a decimated spectrogram grid, a decimated signed-lag correlation curve, and detected peaks. Peaks remain unclassified: the endpoint does not distinguish direct paths from echoes, return rejection reasons, infer synchronization, or estimate geometry. Correlation uses `correlate(recording_channel, reference, mode='full')`; positive lag means a delayed reference. The display spectrogram uses SciPy's Hann window and spectrum scaling, with magnitude expressed in dB.

## Signal generation

| Method/path | Behavior |
|---|---|
| `POST /api/signals/waveforms` | Generate a generic sine or linear sweep through BatSight's existing signal generator and return PCM16 WAV bytes. |

Request fields are `waveform` (`sine` or `linear_sweep`), `sample_rate_hz`, `duration_s`, `start_frequency_hz`, `end_frequency_hz`, and `amplitude`. Frequency bounds are checked against Nyquist. Response headers report sample rate, sample count, duration, and the convention `generic_engineering_signal_not_paper_equation_10`. The WAV is PCM16 quantized from the in-memory float signal. The unresolved chirp equation from the 2016 paper is not reproduced.

## Experiments

| Method/path | Behavior |
|---|---|
| `POST /api/experiments` | Create a pending project experiment. |
| `GET /api/experiments?project_id={id}` | List experiments, optionally filtered by project. |
| `GET /api/experiments/{experiment_id}` | Retrieve status/configuration/error. |
| `GET /api/experiments/{experiment_id}/results` | Retrieve stored result or `result: null` before completion. |
| `POST /api/experiments/{experiment_id}/run` | Queue local background execution; returns 202 and running status. |

The initially supported kind is `synthetic_forward`. Its configuration fields are:

The stored result envelope has the canonical provenance contract `data_classification: "synthetic_forward_simulation"`, `geometry_status: "known synthetic ground truth"`, `is_room_reconstruction: false`, and `real_world_validation: false`. This status describes simulator input geometry only; it does not mean an estimate exists. Consumers must reject unrecognized statuses rather than treating geometry as estimated.

```json
{
  "room_dimensions_m": [4.5, 4.1, 3.4],
  "source_position_m": [2.2, 2.0, 1.4],
  "microphone_positions_m": [[1.0, 1.0, 1.2], [3.0, 2.8, 1.5]],
  "sampling_frequency_hz": 48000,
  "duration_s": 0.01,
  "waveform": "linear_sweep",
  "start_frequency_hz": 900,
  "end_frequency_hz": 11000,
  "speed_of_sound_m_s": 343,
  "wall_reflection_coefficients": {"x_min": 0.7},
  "max_reflection_order": 2,
  "snr_db": null,
  "random_seed": 23,
  "impulse_placement": "linear",
  "peak_window_length_samples": null,
  "thr1": 0.9,
  "thr2": 0.1,
  "matching_tolerance_seconds": null
}
```

The sweep is generic engineering input, not a reproduction of the paper's unresolved chirp Equation 10. The result is tagged as synthetic forward simulation; no geometry is estimated. Unsupported experiment kinds fail and persist an error rather than executing another algorithm. Current states are `pending`, `running`, `completed`, `failed`.

## Status/error behavior

- 201 on project/recording/experiment creation.
- 202 on experiment run scheduling.
- 204 on successful deletion.
- 404 for missing records or unknown parent project.
- 409 if an experiment is already running.
- 413 for upload size limit.
- 422 for invalid request or audio content.
- Health returns backend `ok` and `database_status=unavailable` if the DB cannot be queried.

The background mechanism is local and in-process. It does not survive process termination and is not intended for concurrent multi-user service deployment.

## Calibrated multichannel recording sessions (API v1)

See [recording session workflow and metadata contract](recording_sessions.md) for SI units, synchronization semantics, provenance, the complete example, and interpretation limitations. The endpoints import no bytes themselves: first use `POST /api/recordings`, then attach the returned recording ID to a session.

| Method and path | Purpose | Response |
|---|---|---|
| `POST /api/v1/recording-sessions` | Create project-scoped draft with provenance, calibration metadata, and analysis configuration | 201 session |
| `GET /api/v1/recording-sessions?project_id={id}` | List sessions, optionally filtered by project | 200 session array |
| `GET /api/v1/recording-sessions/{session_id}` | Read metadata and attached recording/channel mappings | 200 session |
| `PUT /api/v1/recording-sessions/{session_id}/metadata` | Replace calibration, analysis settings, and provenance | 200 session |
| `POST /api/v1/recording-sessions/{session_id}/recordings` | Attach an imported WAV with common-reference start time, per-channel microphone mapping, optional event IDs | 200 session |
| `POST /api/v1/recording-sessions/{session_id}/validate` | Validate metadata, sample rates, sync assertion/evidence, event references, and channel coverage | 200 validation report |
| `POST /api/v1/recording-sessions/{session_id}/extractions` | Queue existing Phase 5E.1 multichannel TOA extraction; invalid sessions return 422 | 202 job |
| `GET /api/v1/recording-sessions/{session_id}/extractions/{extraction_id}` | Read queued/running/completed/failed job and result | 200 job/result |
| `GET /api/v1/recording-sessions/{session_id}/results` | Read latest extraction, or null before first run | 200 result/null |

WAV sample rates must exactly equal declared session rate. No implicit resampling, channel inference, or clock synchronization is performed. A session can record `laptop_single_device` provenance but validation rejects that mode for calibrated multichannel extraction. `synchronization_interpretation` is always explicit: `asserted_by_metadata_not_independently_verified` or `not_asserted_as_synchronized`. Extraction returns candidates, rejected peaks, and missing direct-path states; no room geometry is estimated.
