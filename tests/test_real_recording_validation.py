import pytest

from batsight.validation.real_recordings import (
    associate_annotations,
    match_arrivals,
    parse_imported_recording_metadata,
    parse_provider_annotations,
    score_arrivals,
)


def _metadata(**updates):
    value = {
        "recording_id": "rir-a.sofa",
        "dataset": "dEchorate",
        "provenance": "imported_real_multichannel",
        "sample_rate_hz": 48000,
        "channel_count": 2,
        "microphone_ids": ["mic1", "mic2"],
        "synchronization_status": "documented_protocol",
        "time_origin_s": 0,
    }
    value.update(updates)
    return value


def test_parse_imported_multichannel_metadata_and_reject_synthetic():
    parsed = parse_imported_recording_metadata(_metadata())
    assert parsed.sample_rate_hz == 48000
    assert parsed.microphone_ids == ("mic1", "mic2")
    with pytest.raises(ValueError, match="only imported_real_multichannel"):
        parse_imported_recording_metadata(_metadata(provenance="synthetic"))


def test_metadata_rejects_bad_mapping_sync_and_rate():
    with pytest.raises(ValueError, match="channel order"):
        parse_imported_recording_metadata(_metadata(microphone_ids=["mic1"]))
    with pytest.raises(ValueError, match="synchronization status"):
        parse_imported_recording_metadata(_metadata(synchronization_status="synchronized_guess"))
    with pytest.raises(ValueError, match="invalid"):
        parse_imported_recording_metadata(_metadata(sample_rate_hz=float("nan")))


def test_parse_provider_annotations_and_reject_detector_self_ground_truth():
    payload = {
        "annotation_provenance": "independent_provider_annotation",
        "annotation_method": "manual provider labels",
        "arrivals": [{
            "recording_id": "rir-a.sofa", "microphone_id": "mic1", "event_id": "src1",
            "kind": "echo", "arrival_time_s": 0.01, "source": "provider",
            "wall_label": "north", "uncertainty_s": None,
        }],
    }
    parsed = parse_provider_annotations(payload)
    assert parsed[0].wall_label == "north"
    with pytest.raises(ValueError, match="independent provider"):
        parse_provider_annotations({**payload, "annotation_provenance": "batsight_detector"})


def test_associate_annotations_uses_recording_event_and_channel_identity():
    metadata = parse_imported_recording_metadata(_metadata())
    annotations = parse_provider_annotations({
        "annotation_provenance": "independent_provider_annotation",
        "annotation_method": "manual",
        "arrivals": [
            {"recording_id": "rir-a.sofa", "microphone_id": "mic1", "event_id": "src1", "kind": "direct", "arrival_time_s": 0.01, "source": "provider"},
            {"recording_id": "other.sofa", "microphone_id": "mic2", "event_id": "src1", "kind": "direct", "arrival_time_s": 0.02, "source": "provider"},
        ],
    })
    assert len(associate_annotations(metadata, annotations, event_id="src1")) == 1
    with pytest.raises(ValueError, match="no provider annotations"):
        associate_annotations(metadata, annotations, event_id="src2")


def test_one_to_one_matching_and_hand_calculated_metrics():
    # Two references, one in-tolerance candidate, and one false detection.
    refs = [0.010, 0.020]
    detections = [0.0102, 0.035]
    matches = match_arrivals(refs, detections, tolerance_s=0.001)
    assert [(item.reference_index, item.detection_index) for item in matches] == [(0, 0)]
    metrics = score_arrivals(refs, detections, tolerance_s=0.001)
    assert (metrics.true_positive, metrics.false_positive, metrics.false_negative) == (1, 1, 1)
    assert metrics.precision == pytest.approx(0.5)
    assert metrics.recall == pytest.approx(0.5)
    assert metrics.f1 == pytest.approx(0.5)
    assert metrics.mean_absolute_error_s == pytest.approx(0.0002)
    assert metrics.median_absolute_error_s == pytest.approx(0.0002)
    assert metrics.p95_absolute_error_s == pytest.approx(0.0002)


def test_matching_is_maximum_cardinality_not_greedy_nearest_pair():
    # The 1st detection is close to both references; the 2nd only matches ref 2.
    matches = match_arrivals([0.0, 0.0015], [0.0007, 0.0024], tolerance_s=0.001)
    assert len(matches) == 2
    assert [(item.reference_index, item.detection_index) for item in matches] == [(0, 0), (1, 1)]


def test_empty_annotations_are_not_scored_as_perfect_recall():
    metrics = score_arrivals([], [0.1], tolerance_s=0.01)
    assert metrics.precision == 0.0
    assert metrics.recall is None
    assert metrics.false_positive == 1


def test_equal_distance_ambiguity_is_resolved_deterministically():
    first = match_arrivals([0.0], [-0.0001, 0.0001], tolerance_s=0.001)
    second = match_arrivals([0.0], [-0.0001, 0.0001], tolerance_s=0.001)
    assert first == second
    assert len(first) == 1
    assert first[0].detection_index == 0


def test_evaluation_metrics_are_reproducible_for_fixed_inputs():
    first = score_arrivals([0.1, 0.2], [0.101, 0.4], tolerance_s=0.005)
    second = score_arrivals([0.1, 0.2], [0.101, 0.4], tolerance_s=0.005)
    assert first == second
    assert (first.true_positive, first.false_positive, first.false_negative) == (1, 1, 1)
