"""Background execution of the existing forward synthetic experiment."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, ValidationError

from batsight.application.database import sessionmaker
from batsight.application.models.entities import Experiment, ExperimentResult
from batsight.application.services.signal_service import SignalProcessingService
from batsight.experiments.pipeline import run_experiment
from batsight.simulation import ShoeboxRoom


class SyntheticForwardConfig(BaseModel):
    room_dimensions_m: tuple[float, float, float]
    source_position_m: tuple[float, float, float]
    microphone_positions_m: list[tuple[float, float, float]] = Field(min_length=1)
    sampling_frequency_hz: float = Field(default=48000.0, gt=0)
    duration_s: float = Field(default=0.01, gt=0, le=2.0)
    waveform: Literal["sine", "linear_sweep"] = "linear_sweep"
    start_frequency_hz: float = Field(default=900.0, ge=0)
    end_frequency_hz: float = Field(default=11000.0, ge=0)
    speed_of_sound_m_s: float = Field(default=343.0, gt=0)
    wall_reflection_coefficients: dict[str, float] = Field(default_factory=dict)
    max_reflection_order: int = Field(default=2, ge=0, le=2)
    snr_db: float | None = None
    random_seed: int | None = None
    impulse_placement: Literal["linear", "nearest"] = "linear"
    peak_window_length_samples: int | None = Field(default=None, ge=1)
    thr1: float = Field(default=0.9, ge=0, le=1)
    thr2: float = Field(default=0.1, ge=0, le=1)
    matching_tolerance_seconds: float | None = Field(default=None, ge=0)


class SyntheticExperimentService:
    SUPPORTED_KIND = "synthetic_forward"

    def __init__(self, session_factory: sessionmaker) -> None:
        self.session_factory = session_factory

    def run_background(self, experiment_id: int) -> None:
        session = self.session_factory()
        try:
            experiment = session.get(Experiment, experiment_id)
            if experiment is None:
                return
            experiment.status = "running"
            experiment.error_message = None
            session.commit()
            if experiment.kind != self.SUPPORTED_KIND:
                raise ValueError(
                    f"Unsupported experiment kind '{experiment.kind}'. "
                    f"Supported kind: '{self.SUPPORTED_KIND}'"
                )
            config = SyntheticForwardConfig.model_validate(experiment.configuration)
            result = self._run(config)
            stored = session.get(Experiment, experiment_id)
            if stored is None:
                return
            if stored.result is not None:
                session.delete(stored.result)
                session.flush()
            stored.result = ExperimentResult(
                result_json={
                    "data_classification": "synthetic_forward_simulation",
                    "geometry_status": "known synthetic ground truth",
                    "is_room_reconstruction": False,
                    "real_world_validation": False,
                    "result": result,
                }
            )
            stored.status = "completed"
            stored.error_message = None
            session.commit()
        except (ValidationError, ValueError, TypeError) as exc:
            session.rollback()
            failed = session.get(Experiment, experiment_id)
            if failed is not None:
                failed.status = "failed"
                failed.error_message = f"{type(exc).__name__}: {exc}"
                session.commit()
        except Exception as exc:  # Persist a safe failure state; details remain server-side.
            session.rollback()
            failed = session.get(Experiment, experiment_id)
            if failed is not None:
                failed.status = "failed"
                failed.error_message = f"Experiment execution failed ({type(exc).__name__})"
                session.commit()
        finally:
            session.close()

    @staticmethod
    def _run(config: SyntheticForwardConfig) -> dict:
        room = ShoeboxRoom(
            config.room_dimensions_m,
            config.speed_of_sound_m_s,
            config.wall_reflection_coefficients,
        )
        signal_service = SignalProcessingService()
        reference = signal_service.generate_reference(
            waveform=config.waveform,
            sample_rate_hz=config.sampling_frequency_hz,
            duration_s=config.duration_s,
            start_frequency_hz=config.start_frequency_hz,
            end_frequency_hz=config.end_frequency_hz,
        )
        result = run_experiment(
            room,
            config.source_position_m,
            config.microphone_positions_m,
            reference.signal,
            max_reflection_order=config.max_reflection_order,
            snr_db=config.snr_db,
            random_seed=config.random_seed,
            impulse_placement=config.impulse_placement,
            peak_window_length_samples=config.peak_window_length_samples,
            thr1=config.thr1,
            thr2=config.thr2,
            matching_tolerance_seconds=config.matching_tolerance_seconds,
        )
        return result.to_dict(include_waveforms=False, include_correlations=False)
