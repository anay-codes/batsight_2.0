"""Forward acoustic simulation utilities."""

from typing import TYPE_CHECKING

from .shoebox import (
    AcousticPath,
    ImageSource,
    RIRSimulation,
    ShoeboxRoom,
    SimulatedRecordings,
    generate_rir,
    image_sources,
    predict_acoustic_paths,
    simulate_recordings,
)

if TYPE_CHECKING:
    from batsight.datasets.calibrated import CalibratedShoeboxInputs
    from .reflections import PredictedArrival


def predict_first_order_arrivals(
    inputs: "CalibratedShoeboxInputs",
    candidate_room: ShoeboxRoom,
    *,
    boundary_tolerance_m: float = 0.0,
) -> tuple["PredictedArrival", ...]:
    """Lazily predict calibrated direct and first-order shoebox arrivals."""
    from .reflections import predict_first_order_arrivals as _predict

    return _predict(inputs, candidate_room, boundary_tolerance_m=boundary_tolerance_m)

__all__ = [
    "AcousticPath",
    "ImageSource",
    "RIRSimulation",
    "ShoeboxRoom",
    "SimulatedRecordings",
    "generate_rir",
    "image_sources",
    "predict_acoustic_paths",
    "predict_first_order_arrivals",
    "simulate_recordings",
]
