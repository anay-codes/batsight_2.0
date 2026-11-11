"""Known-coordinate calibrated shoebox TOA model and predictor tests."""

import numpy as np
import pytest

from batsight.datasets import (
    CalibratedMicrophone,
    CalibratedMicrophoneArray,
    CalibratedShoeboxInputs,
    CalibratedSourceEvent,
    CalibratedTOAObservationSet,
    DirectPathTOAObservation,
    FirstOrderReflectionTOAObservation,
    TOAReading,
    UnlabeledEchoTOAObservation,
)
from batsight.signals import (
    AudioSignal,
    KnownReferenceSignal,
    RecordingMetadata,
    SamplingFrequency,
)
from batsight.simulation import (
    ShoeboxRoom,
    generate_rir,
    predict_acoustic_paths,
    predict_first_order_arrivals,
)


def make_inputs(*, microphones=None, events=None, speed=340.0):
    microphone_items = microphones or (
        CalibratedMicrophone("mic-a", (2.0, 2.0, 1.0), RecordingMetadata(device="array-a")),
    )
    event_items = events or (CalibratedSourceEvent("event-a", "source-a", (1.0, 1.0, 1.0), 0.01),)
    array = CalibratedMicrophoneArray(tuple(microphone_items), SamplingFrequency(48_000.0))
    return CalibratedShoeboxInputs(array, tuple(event_items), speed)


def test_predictor_direct_and_x_min_reflection_by_hand():
    room = ShoeboxRoom((4.0, 5.0, 3.0), speed_of_sound_m_s=340.0)
    predictions = predict_first_order_arrivals(make_inputs(), room)
    direct = next(item for item in predictions if item.reflection_order == 0)
    x_min = next(item for item in predictions if item.wall_id == "x_min")

    assert direct.propagation_distance_m == pytest.approx(np.sqrt(2.0))
    assert direct.propagation_time_s == pytest.approx(np.sqrt(2.0) / 340.0)
    assert direct.arrival_time_s == pytest.approx(0.01 + np.sqrt(2.0) / 340.0)
    assert x_min.image_source_position_m == pytest.approx((-1.0, 1.0, 1.0))
    assert x_min.propagation_distance_m == pytest.approx(np.sqrt(10.0))
    assert x_min.arrival_time_s == pytest.approx(0.01 + np.sqrt(10.0) / 340.0)
    assert direct.wall_id is None
    assert direct.source_id == x_min.source_id == "source-a"


def test_predicts_exactly_direct_and_all_six_named_first_order_paths():
    room = ShoeboxRoom((4.0, 5.0, 3.0), speed_of_sound_m_s=340.0)
    predictions = predict_first_order_arrivals(make_inputs(), room)
    assert len(predictions) == 7
    assert [p.wall_id for p in predictions] == [
        None, "x_min", "x_max", "y_min", "y_max", "z_min", "z_max"
    ]
    assert all(p.reflection_order == 1 for p in predictions[1:])


def test_multiple_sources_and_microphones_and_known_emissions():
    microphones = (
        CalibratedMicrophone("mic-a", (2.0, 2.0, 1.0)),
        CalibratedMicrophone("mic-b", (3.0, 2.0, 1.0)),
    )
    events = (
        CalibratedSourceEvent("event-a", "src-a", (1.0, 1.0, 1.0), 0.01),
        CalibratedSourceEvent("event-b", "src-b", (1.0, 2.0, 1.0), 0.03),
    )
    room = ShoeboxRoom((4.0, 5.0, 3.0), speed_of_sound_m_s=340.0)
    predictions = predict_first_order_arrivals(make_inputs(microphones=microphones, events=events), room)
    assert len(predictions) == 2 * 2 * 7
    assert {(p.event_id, p.microphone_id) for p in predictions} == {
        ("event-a", "mic-a"), ("event-a", "mic-b"),
        ("event-b", "mic-a"), ("event-b", "mic-b"),
    }
    for p in predictions:
        assert p.arrival_time_s == pytest.approx(p.emission_time_s + p.propagation_time_s)
    event_b_mic_a_direct = next(
        p for p in predictions if p.event_id == "event-b" and p.microphone_id == "mic-a" and p.wall_id is None
    )
    assert event_b_mic_a_direct.emission_time_s == pytest.approx(0.03)


def test_prediction_reuses_existing_image_source_and_path_conventions():
    room = ShoeboxRoom((4.0, 5.0, 3.0), speed_of_sound_m_s=340.0)
    inputs = make_inputs()
    predicted = predict_first_order_arrivals(inputs, room)
    paths = predict_acoustic_paths(room, (1.0, 1.0, 1.0), (2.0, 2.0, 1.0), max_reflection_order=1)
    rir = generate_rir(room, (1.0, 1.0, 1.0), (2.0, 2.0, 1.0), SamplingFrequency(48_000.0), max_reflection_order=1)
    assert [(p.reflection_order, p.reflection_sequence, p.propagation_distance_m) for p in paths] == [
        (p.reflection_order, p.reflection_sequence, p.propagation_distance_m) for p in rir.paths
    ]
    assert [p.wall_id for p in predicted] == [None if not p.reflection_sequence else p.reflection_sequence[0] for p in paths]
    assert [p.propagation_distance_m for p in predicted] == pytest.approx([p.propagation_distance_m for p in paths])


def test_predictor_is_deterministic_and_adds_no_noise():
    room = ShoeboxRoom((4.0, 5.0, 3.0), speed_of_sound_m_s=340.0)
    inputs = make_inputs()
    first = predict_first_order_arrivals(inputs, room)
    second = predict_first_order_arrivals(inputs, room)
    assert first == second
    assert all(p.arrival_time_s == p.emission_time_s + p.propagation_time_s for p in first)


def test_room_candidate_sound_speed_and_boundary_clearance_are_checked():
    inputs = make_inputs()
    with pytest.raises(ValueError, match="same known sound speed"):
        predict_first_order_arrivals(inputs, ShoeboxRoom((4.0, 5.0, 3.0), speed_of_sound_m_s=343.0))
    near_inputs = make_inputs(microphones=(CalibratedMicrophone("mic-a", (1e-4, 2.0, 1.0)),))
    with pytest.raises(ValueError, match="farther"):
        predict_first_order_arrivals(near_inputs, ShoeboxRoom((4.0, 5.0, 3.0), speed_of_sound_m_s=340.0), boundary_tolerance_m=1e-3)
    with pytest.raises(ValueError, match="boundary_tolerance"):
        predict_first_order_arrivals(inputs, ShoeboxRoom((4.0, 5.0, 3.0), speed_of_sound_m_s=340.0), boundary_tolerance_m=-1.0)


def test_invalid_calibrated_positions_and_dimensions_are_rejected_by_candidate_room():
    inputs = make_inputs(microphones=(CalibratedMicrophone("mic-a", (4.1, 2.0, 1.0)),))
    with pytest.raises(ValueError, match="inside the room"):
        predict_first_order_arrivals(inputs, ShoeboxRoom((4.0, 5.0, 3.0), speed_of_sound_m_s=340.0))
    with pytest.raises(ValueError):
        ShoeboxRoom((-4.0, 5.0, 3.0), speed_of_sound_m_s=340.0)


def test_calibrated_measurement_contract_tracks_observed_missing_and_invalid_records():
    inputs = make_inputs()
    dataset = CalibratedTOAObservationSet(
        inputs,
        "synthetic",
        direct_paths=(
            DirectPathTOAObservation("mic-a", "event-a", TOAReading(0.02, 2e-5)),
        ),
        labeled_first_order_reflections=(
            FirstOrderReflectionTOAObservation(
                "mic-a", "event-a", "x_min", TOAReading(0.03), "synthetic_ground_truth"
            ),
            FirstOrderReflectionTOAObservation(
                "mic-a", "event-a", "y_min", TOAReading(None, status="missing"), "synthetic_ground_truth"
            ),
            FirstOrderReflectionTOAObservation(
                "mic-a", "event-a", "z_max", TOAReading(None, status="invalid", reason="clipped"), "synthetic_ground_truth"
            ),
        ),
    )
    assert dataset.direct_paths[0].reading.uncertainty_s == pytest.approx(2e-5)
    assert dataset.labeled_first_order_reflections[1].reading.status == "missing"
    assert dataset.labeled_first_order_reflections[2].reading.reason == "clipped"


def test_unlabeled_echo_contract_does_not_assign_a_wall_to_real_data():
    inputs = make_inputs()
    echo = UnlabeledEchoTOAObservation("mic-a", "event-a", "echo-17", TOAReading(0.04), 1)
    records = CalibratedTOAObservationSet(inputs, "real", unlabeled_echoes=(echo,))
    assert records.unlabeled_echoes[0].echo_id == "echo-17"
    with pytest.raises(ValueError, match="external annotation"):
        CalibratedTOAObservationSet(
            inputs,
            "real",
            labeled_first_order_reflections=(
                FirstOrderReflectionTOAObservation(
                    "mic-a", "event-a", "x_min", TOAReading(0.03), "synthetic_ground_truth"
                ),
            ),
        )
    allowed_annotation = FirstOrderReflectionTOAObservation(
        "mic-a", "event-a", "x_min", TOAReading(0.03), "external_annotation"
    )
    CalibratedTOAObservationSet(inputs, "real", labeled_first_order_reflections=(allowed_annotation,))


def test_contract_rejects_unsynchronized_clocks_bad_ids_times_and_references():
    mic = CalibratedMicrophone("mic-a", (1.0, 1.0, 1.0))
    with pytest.raises(ValueError, match="synchronized"):
        CalibratedMicrophoneArray((mic,), SamplingFrequency(48_000.0), clocks_synchronized=False)
    with pytest.raises(ValueError, match="unique"):
        CalibratedMicrophoneArray((mic, mic), SamplingFrequency(48_000.0))
    with pytest.raises(ValueError, match="finite seconds"):
        CalibratedSourceEvent("event-a", "src-a", (1.0, 1.0, 1.0), np.nan)
    with pytest.raises(ValueError, match="finite"):
        TOAReading(np.inf)
    with pytest.raises(ValueError, match="require a reason"):
        TOAReading(None, status="invalid")
    with pytest.raises(ValueError, match="non-negative"):
        TOAReading(0.1, uncertainty_s=-1.0)
    with pytest.raises(ValueError, match="sampling frequency"):
        CalibratedShoeboxInputs(
            CalibratedMicrophoneArray((mic,), SamplingFrequency(48_000.0)),
            (CalibratedSourceEvent("event-a", "src-a", (1.0, 1.0, 1.0), 0.0,
                KnownReferenceSignal(AudioSignal(np.ones(8), SamplingFrequency(44_100.0)))),),
            343.0,
        )
