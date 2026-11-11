"""Local application API integration tests with isolated SQLite/filesystem state."""

from __future__ import annotations

from io import BytesIO

import numpy as np
import pytest
from fastapi.testclient import TestClient
from scipy.io import wavfile
from sqlalchemy import inspect

from batsight.application.config import Settings
from batsight.application.main import create_app
from batsight.application.models.entities import Experiment, Project, Recording


@pytest.fixture
def client(tmp_path):
    settings = Settings(
        data_dir=tmp_path / "app-data",
        max_upload_size_bytes=2_000_000,
    )
    app = create_app(settings)
    with TestClient(app) as test_client:
        yield test_client


def _wav_bytes(sample_rate=16000, channels=1, sample_count=1600):
    stream = BytesIO()
    samples = np.zeros((sample_count, channels), dtype=np.int16) if channels > 1 else np.zeros(sample_count, dtype=np.int16)
    wavfile.write(stream, sample_rate, samples)
    return stream.getvalue()


def _create_project(client):
    response = client.post("/api/projects", json={
        "name": "Lab room", "description": "test project", "metadata": {"site": "synthetic"}
    })
    assert response.status_code == 201
    return response.json()


def _upload(client, *, filename="capture.wav", content=None, project_id=None, name="Capture"):
    fields = {"name": name, "metadata_json": '{"device":"test"}'}
    if project_id is not None:
        fields["project_id"] = str(project_id)
    return client.post(
        "/api/recordings", data=fields,
        files={"file": (filename, content if content is not None else _wav_bytes(), "audio/wav")},
    )


def test_startup_health_openapi_and_database_initialization(client):
    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["application"] == "BatSight"
    assert health.json()["backend_status"] == "ok"
    assert health.json()["database_status"] == "connected"
    assert client.get("/api/system/info").status_code == 200
    assert client.get("/openapi.json").status_code == 200
    assert client.get("/docs").status_code == 200
    assert client.get("/redoc").status_code == 200
    assert set(inspect(client.app.state.engine).get_table_names()) >= {
        "projects", "recordings", "experiments", "experiment_results"
    }


def test_project_crud_and_project_filtering(client):
    project = _create_project(client)
    assert project["metadata"] == {"site": "synthetic"}
    assert project["created_at"].endswith(("+00:00", "Z"))
    assert client.get(f"/api/projects/{project['id']}").json()["name"] == "Lab room"
    assert len(client.get("/api/projects").json()) == 1
    assert client.get(f"/api/projects/{project['id'] + 100}").status_code == 404


def test_recording_upload_metadata_and_original_bytes_are_preserved(client):
    project = _create_project(client)
    raw = _wav_bytes(sample_rate=16000, channels=2, sample_count=2400)
    response = _upload(client, filename="..\\unsafe\\audio.wav", content=raw, project_id=project["id"])
    assert response.status_code == 201, response.text
    item = response.json()
    assert item["original_filename"] == "audio.wav"
    assert item["sample_rate_hz"] == 16000
    assert item["channel_count"] == 2
    assert item["sample_count"] == 2400
    assert item["duration_s"] == pytest.approx(0.15)
    assert item["created_at"].endswith(("+00:00", "Z"))
    assert item["metadata"]["device"] == "test"
    with client.app.state.session_factory() as session:
        row = session.get(Recording, item["id"])
        assert open(row.file_path, "rb").read() == raw
        assert row.managed_filename.endswith(".wav")
    assert len(client.get(f"/api/recordings?project_id={project['id']}").json()) == 1
    downloaded = client.get(f"/api/recordings/{item['id']}/audio")
    assert downloaded.status_code == 200
    assert downloaded.content == raw


def test_recording_rejects_non_wav_malformed_wav_and_invalid_sample_rate(client):
    assert _upload(client, filename="not-audio.txt").status_code == 422
    assert _upload(client, content=b"not a wave").status_code == 422
    low_rate = _upload(client, content=_wav_bytes(sample_rate=4000))
    assert low_rate.status_code == 422
    assert "not resampled" in low_rate.json()["detail"]
    too_many_channels = _upload(client, content=_wav_bytes(sample_rate=16000, channels=65))
    assert too_many_channels.status_code == 422
    assert _upload(client, name="   ").status_code == 422


def test_waveform_endpoint_returns_generic_pcm_wav_and_rejects_nyquist(client):
    response = client.post("/api/signals/waveforms", json={
        "waveform": "linear_sweep", "sample_rate_hz": 16000, "duration_s": 0.02,
        "start_frequency_hz": 500, "end_frequency_hz": 7000, "amplitude": 0.5,
    })
    assert response.status_code == 200, response.text
    rate, samples = wavfile.read(BytesIO(response.content))
    assert rate == 16000
    assert samples.shape == (320,)
    assert samples.dtype == np.int16
    assert response.headers["x-waveform-convention"] == "generic_engineering_signal_not_paper_equation_10"
    sine = client.post("/api/signals/waveforms", json={
        "waveform": "sine", "sample_rate_hz": 16000, "duration_s": 0.01,
        "start_frequency_hz": 1000, "end_frequency_hz": 12000,
    })
    assert sine.status_code == 200, sine.text
    assert client.post("/api/signals/waveforms", json={
        "sample_rate_hz": 16000, "start_frequency_hz": 1000, "end_frequency_hz": 8000,
    }).status_code == 422


def test_recording_analysis_uses_existing_peak_pipeline_and_reports_unclassified_candidates(client):
    sample_rate = 16000
    t = np.arange(2400) / sample_rate
    ref = np.sin(2 * np.pi * 1000 * np.arange(160) / sample_rate)
    signal = np.zeros(2400, dtype=np.float64)
    signal[400:560] += ref
    signal[1200:1360] += 0.6 * ref
    stream = BytesIO()
    wavfile.write(stream, sample_rate, np.rint(signal * 32767).astype(np.int16))
    uploaded = _upload(client, content=stream.getvalue())
    recording_id = uploaded.json()["id"]
    response = client.post(f"/api/recordings/{recording_id}/analysis", json={
        "channel_index": 0, "waveform": "sine", "reference_duration_s": 0.01,
        "start_frequency_hz": 1000, "normalization": "reference_energy",
        "window_length_samples": 400, "thr1": 0.8, "thr2": 0.2,
        "spectrogram_nperseg": 256,
    })
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["sample_rate_hz"] == sample_rate
    assert result["channel_count"] == 1
    assert result["matched_filter"]["correlation_convention"].startswith("full correlate")
    assert result["matched_filter"]["direct_or_echo_classification_available"] is False
    assert result["matched_filter"]["peaks"]
    assert all(peak["classification"] == "unclassified_correlation_peak" for peak in result["matched_filter"]["peaks"])
    assert any(abs(peak["lag_seconds"] - 400 / sample_rate) < 1 / sample_rate for peak in result["matched_filter"]["peaks"])
    assert client.post(f"/api/recordings/{recording_id}/analysis", json={"channel_index": 4}).status_code == 422


def test_recording_size_limit_and_file_delete(client, tmp_path):
    # Exercise a separate small-limit app without changing the fixture's app.
    settings = Settings(data_dir=tmp_path / "small", max_upload_size_bytes=64)
    with TestClient(create_app(settings)) as small_client:
        too_big = _upload(small_client)
        assert too_big.status_code == 413

    response = _upload(client)
    recording_id = response.json()["id"]
    with client.app.state.session_factory() as session:
        path = session.get(Recording, recording_id).file_path
    assert client.delete(f"/api/recordings/{recording_id}").status_code == 204
    assert not __import__("pathlib").Path(path).exists()
    assert client.get(f"/api/recordings/{recording_id}").status_code == 404


def _experiment_config():
    return {
        "room_dimensions_m": [4.0, 3.5, 2.8],
        "source_position_m": [2.0, 1.6, 1.4],
        "microphone_positions_m": [[1.0, 0.8, 1.0], [3.0, 2.5, 1.5]],
        "sampling_frequency_hz": 16000,
        "duration_s": 0.01,
        "start_frequency_hz": 500.0,
        "end_frequency_hz": 7000.0,
        "max_reflection_order": 1,
        "random_seed": 17,
    }


def test_experiment_creation_background_execution_and_result_persistence(client):
    project = _create_project(client)
    created = client.post("/api/experiments", json={
        "project_id": project["id"], "name": "Forward check", "kind": "synthetic_forward",
        "configuration": _experiment_config(),
    })
    assert created.status_code == 201, created.text
    experiment_id = created.json()["id"]
    assert created.json()["status"] == "pending"
    queued = client.post(f"/api/experiments/{experiment_id}/run")
    assert queued.status_code == 202, queued.text
    experiment = client.get(f"/api/experiments/{experiment_id}").json()
    assert experiment["status"] == "completed"
    result = client.get(f"/api/experiments/{experiment_id}/results").json()["result"]
    assert result["data_classification"] == "synthetic_forward_simulation"
    assert result["is_room_reconstruction"] is False
    assert result["real_world_validation"] is False
    assert result["result"]["overall_metrics"]
    assert client.get(f"/api/experiments?project_id={project['id']}").json()[0]["id"] == experiment_id
    with client.app.state.session_factory() as session:
        row = session.get(Experiment, experiment_id)
        assert row.result is not None
        assert row.result.result_json["data_classification"] == "synthetic_forward_simulation"


def test_experiment_failure_is_persisted_and_reported(client):
    project = _create_project(client)
    created = client.post("/api/experiments", json={
        "project_id": project["id"], "name": "Unsupported", "kind": "unknown_method",
        "configuration": {},
    })
    assert created.status_code == 201
    experiment_id = created.json()["id"]
    assert client.post(f"/api/experiments/{experiment_id}/run").status_code == 202
    state = client.get(f"/api/experiments/{experiment_id}").json()
    assert state["status"] == "failed"
    assert "Unsupported experiment kind" in state["error_message"]
    assert client.get(f"/api/experiments/{experiment_id}/results").json()["result"] is None
    assert client.post(f"/api/experiments/{experiment_id}/run").status_code == 202


def test_project_delete_cascades_experiments_and_managed_files(client):
    project = _create_project(client)
    recording = _upload(client, project_id=project["id"]).json()
    exp = client.post("/api/experiments", json={
        "project_id": project["id"], "name": "Pending", "kind": "synthetic_forward",
        "configuration": {},
    }).json()
    with client.app.state.session_factory() as session:
        file_path = session.get(Recording, recording["id"]).file_path
    assert client.delete(f"/api/projects/{project['id']}").status_code == 204
    assert not __import__("pathlib").Path(file_path).exists()
    with client.app.state.session_factory() as session:
        assert session.get(Project, project["id"]) is None
        assert session.get(Recording, recording["id"]) is None
        assert session.get(Experiment, exp["id"]) is None


def test_missing_project_rejected_for_child_resources(client):
    assert client.post("/api/experiments", json={
        "project_id": 999, "name": "Orphan", "kind": "synthetic_forward", "configuration": {}
    }).status_code == 404
    assert _upload(client, project_id=999).status_code == 404
