"""Thin forward-simulation service facade."""

from collections.abc import Sequence

from batsight.signals import AudioSignal
from batsight.simulation import ShoeboxRoom, simulate_recordings


class SimulationService:
    def simulate(self, room: ShoeboxRoom, source_position_m: Sequence[float],
                 microphone_positions_m: Sequence[Sequence[float]],
                 excitation: AudioSignal, *, max_reflection_order: int = 2,
                 random_seed: int | None = None, snr_db: float | None = None):
        return simulate_recordings(
            room, source_position_m, microphone_positions_m, excitation,
            max_reflection_order=max_reflection_order,
            random_seed=random_seed, snr_db=snr_db,
        )
