"""Integration tests for calibrated multichannel session persistence and TOA extraction."""

from __future__ import annotations

from io import BytesIO

import numpy as np
from fastapi.testclient import TestClient
from scipy.io import wavfile

from batsight.application.config import Settings
from batsight.application.main import create_app
from batsight.application.services.signal_service import SignalProcessingService


def _session_client(tmp_path):
    app = create_app(Settings(data_dir=tmp_path / "sessions"))
    return TestClient(app)


def _project(client):
    response = client.post("/api/projects", json={"name": "session test", "description": None, "metadata": {}})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _calibration(sample_rate=16000, *, synchronized=True, positions=True):
    return {
        "schema_version": "1.0",
        "coordinate_frame": "corner_origin_x_length_y_width_z_height",
        "position_unit": "m", "time_unit": "s", "time_reference": "test-clock-origin",
        "sample_rate_hz": sample_rate, "speed_of_sound_m_s": 343.0,
        "synchronization": {
            "status": "synchronized" if synchronized else "unknown",
            "evidence_description": "shared synthetic sample clock" if synchronized else None,
        },
        "microphones": [
            {"microphone_id": "mic-a", "position_m": [1.1, 1.0, 1.0] if positions else None},
            {"microphone_id": "mic-b", "position_m": [1.0, 1.2, 1.0] if positions else None},
        ],
        "events": [{
            "event_id": "event-a", "source_id": "source-a", "position_m": [1.0, 1.0, 1.0],
            "emission_time_s": 0.02,
            "reference_signal": {"waveform": "linear_sweep", "duration_s": 0.01,
                                 "start_frequency_hz": 1000, "end_frequency_hz": 3000, "amplitude": 0.7},
        }],
    }


def _synthetic_multichannel_wav():
    fs = 16000
    start_s = 0.01
    reference = SignalProcessingService().generate_reference(
        waveform="linear_sweep", sample_rate_hz=fs, duration_s=0.01,
        start_frequency_hz=1000, end_frequency_hz=3000, amplitude=0.7,
    ).signal.samples
    source = np.array([1.0, 1.0, 1.0])
    microphones = (np.array([1.1, 1.0, 1.0]), np.array([1.0, 1.2, 1.0]))
    emission = 0.02
    samples = np.zeros((int(0.25 * fs), 2), dtype=np.float64)
    for channel, mic in enumerate(microphones):
        direct_s = emission + float(np.linalg.norm(source - mic)) / 343.0
        direct_index = round((direct_s - start_s) * fs)
        echo_index = direct_index + round(0.008 * fs)
        samples[direct_index:direct_index + len(reference), channel] += reference
        samples[echo_index:echo_index + len(reference), channel] += 0.35 * reference
    stream = BytesIO()
    wavfile.write(stream, fs, np.clip(np.rint(samples * 32767), -32768, 32767).astype(np.int16))
    return stream.getvalue()


def _upload(client, project_id, body=None, *, rate=16000):
    if body is None:
        body = _synthetic_multichannel_wav()
    stream = BytesIO(body)
    response = client.post("/api/recordings", data={"name": "two channel synthetic", "project_id": str(project_id), "metadata_json": "{}"},
                           files={"file": ("two-channel.wav", stream.getvalue(), "audio/wav")})
    assert response.status_code == 201, response.text
    return response.json()


def _create_session(client, project_id, calibration=None, provenance="synthetic"):
    response = client.post("/api/v1/recording-sessions", json={
        "project_id": project_id, "name": "known synthetic test", "provenance": provenance,
        "calibration": calibration or _calibration(), "analysis_configuration": {},
    })
    assert response.status_code == 201, response.text
    return response.json()


def test_session_import_map_validate_extract_and_retrieve_end_to_end(tmp_path):
    with _session_client(tmp_path) as client:
        project_id = _project(client)
        recording = _upload(client, project_id)
        session = _create_session(client, project_id)
        session_id = session["session_id"]
        attached = client.post(f"/api/v1/recording-sessions/{session_id}/recordings", json={
            "recording_id": recording["id"], "recording_start_time_s": 0.01,
            "channel_mapping": [{"channel_index": 0, "microphone_id": "mic-a"},
                                {"channel_index": 1, "microphone_id": "mic-b"}],
            "event_ids": ["event-a"],
        })
        assert attached.status_code == 200, attached.text
        assert attached.json()["recordings"][0]["channel_mapping"][1]["microphone_id"] == "mic-b"
        validation = client.post(f"/api/v1/recording-sessions/{session_id}/validate")
        assert validation.status_code == 200, validation.text
        assert validation.json()["valid"] is True
        assert validation.json()["synchronization_interpretation"] == "asserted_by_metadata_not_independently_verified"

        queued = client.post(f"/api/v1/recording-sessions/{session_id}/extractions")
        assert queued.status_code == 202, queued.text
        job = client.get(f"/api/v1/recording-sessions/{session_id}/extractions/{queued.json()['extraction_id']}")
        assert job.status_code == 200, job.text
        assert job.json()["status"] == "completed", job.json()
        result = job.json()["result"]
        assert result["data_provenance"] == "synthetic"
        assert result["estimated_room_geometry_available"] is False
        assert result["synchronization"]["interpretation"] == "asserted_by_metadata_not_independently_verified"
        assert result["summary"]["microphone_event_pairs"] == 2
        assert len(result["recordings"][0]["waveform_preview"]["channels"]) == 2
        pairs = result["pair_results"]
        assert {pair["microphone_id"] for pair in pairs} == {"mic-a", "mic-b"}
        assert all(pair["direct_status"] == "observed" for pair in pairs)
        assert all(abs(pair["direct_arrival"]["arrival_time_s"] - pair["expected_direct_time_s"]) < 0.001 for pair in pairs)
        assert all(item["classification"] == "unclassified_echo_candidate" for pair in pairs for item in pair["echo_candidates"])
        assert all("rejected_peaks" in pair for pair in pairs)
        assert sum(len(pair["echo_candidates"]) for pair in pairs) >= 1
        assert all("wall_id" not in item for pair in pairs for item in pair["echo_candidates"])
        assert all(item["recording_provenance"] == "synthetic" for item in result["toa_observations"])
        assert client.get(f"/api/v1/recording-sessions/{session_id}/results").json()["extraction_id"] == queued.json()["extraction_id"]


def test_session_validation_reports_missing_positions_and_bad_channel_map(tmp_path):
    with _session_client(tmp_path) as client:
        project_id = _project(client)
        recording = _upload(client, project_id)
        calibration = _calibration(positions=False)
        session = _create_session(client, project_id, calibration)
        session_id = session["session_id"]
        attached = client.post(f"/api/v1/recording-sessions/{session_id}/recordings", json={
            "recording_id": recording["id"], "recording_start_time_s": 0.01,
            "channel_mapping": [{"channel_index": 0, "microphone_id": "mic-a"},
                                {"channel_index": 1, "microphone_id": "mic-b"}],
        })
        assert attached.status_code == 200
        validation = client.post(f"/api/v1/recording-sessions/{session_id}/validate").json()
        assert "microphone_position_missing" in {issue["code"] for issue in validation["errors"]}

        bad_session = _create_session(client, project_id)
        response = client.post(f"/api/v1/recording-sessions/{bad_session['session_id']}/recordings", json={
            "recording_id": recording["id"], "recording_start_time_s": 0.01,
            "channel_mapping": [{"channel_index": 0, "microphone_id": "mic-a"},
                                {"channel_index": 2, "microphone_id": "mic-b"}],
        })
        assert response.status_code == 200
        issues = client.post(f"/api/v1/recording-sessions/{bad_session['session_id']}/validate").json()["errors"]
        assert "channel_mapping_incomplete" in {issue["code"] for issue in issues}


def test_session_rejects_laptop_mode_unknown_sync_and_invalid_event_reference(tmp_path):
    with _session_client(tmp_path) as client:
        project_id = _project(client)
        recording = _upload(client, project_id)
        session = _create_session(client, project_id, _calibration(synchronized=False), "laptop_single_device")
        attached = client.post(f"/api/v1/recording-sessions/{session['session_id']}/recordings", json={
            "recording_id": recording["id"], "recording_start_time_s": 0.01,
            "channel_mapping": [{"channel_index": 0, "microphone_id": "mic-a"},
                                {"channel_index": 1, "microphone_id": "mic-b"}], "event_ids": ["not-known"],
        })
        assert attached.status_code == 200
        issues = client.post(f"/api/v1/recording-sessions/{session['session_id']}/validate").json()["errors"]
        codes = {issue["code"] for issue in issues}
        assert {"single_device_not_array", "synchronization_not_asserted", "unknown_event_reference"} <= codes
        run = client.post(f"/api/v1/recording-sessions/{session['session_id']}/extractions")
        assert run.status_code == 422


def test_session_rejects_sample_rate_mismatch_without_resampling(tmp_path):
    with _session_client(tmp_path) as client:
        project_id = _project(client)
        first = _upload(client, project_id)
        second_body = BytesIO()
        wavfile.write(second_body, 44100, np.zeros((4410, 2), dtype=np.int16))
        second = _upload(client, project_id, second_body.getvalue())
        session = _create_session(client, project_id)
        for recording in (first, second):
            attached = client.post(f"/api/v1/recording-sessions/{session['session_id']}/recordings", json={
                "recording_id": recording["id"], "recording_start_time_s": 0.01,
                "channel_mapping": [{"channel_index": 0, "microphone_id": "mic-a"},
                                    {"channel_index": 1, "microphone_id": "mic-b"}],
            })
            assert attached.status_code == 200, attached.text
        validation = client.post(f"/api/v1/recording-sessions/{session['session_id']}/validate").json()
        assert {issue["code"] for issue in validation["errors"]} >= {"sample_rate_mismatch", "calibration_sample_rate_mismatch"}


def test_session_preserves_missing_direct_and_rejected_peak_audit(tmp_path):
    with _session_client(tmp_path) as client:
        project_id = _project(client)
        recording = _upload(client, project_id)
        session_response = client.post("/api/v1/recording-sessions", json={
            "project_id": project_id, "name": "threshold audit", "provenance": "synthetic",
            "calibration": _calibration(), "analysis_configuration": {"minimum_peak_prominence": 10.0},
        })
        assert session_response.status_code == 201, session_response.text
        session_id = session_response.json()["session_id"]
        attached = client.post(f"/api/v1/recording-sessions/{session_id}/recordings", json={
            "recording_id": recording["id"], "recording_start_time_s": 0.01,
            "channel_mapping": [{"channel_index": 0, "microphone_id": "mic-a"},
                                {"channel_index": 1, "microphone_id": "mic-b"}],
        })
        assert attached.status_code == 200
        assert client.post(f"/api/v1/recording-sessions/{session_id}/validate").json()["valid"]
        queued = client.post(f"/api/v1/recording-sessions/{session_id}/extractions")
        assert queued.status_code == 202, queued.text
        job = client.get(f"/api/v1/recording-sessions/{session_id}/extractions/{queued.json()['extraction_id']}").json()
        assert job["status"] == "completed", job
        pairs = job["result"]["pair_results"]
        assert all(pair["direct_status"] == "missing" for pair in pairs)
        assert all(pair["direct_arrival"] is None for pair in pairs)
        assert any(pair["rejected_peaks"] for pair in pairs)
