"""API routes for calibrated benchmark room reconstructions (e.g. SMARD)."""

from __future__ import annotations

import json
from pathlib import Path
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/reconstructions", tags=["reconstructions"])

PROCESSED_SMARD_DIR = Path("data/processed/smard/0001")


class ErrorMetrics(BaseModel):
    Lx: float
    Ly: float
    Lz: float


class TimingProvenance(BaseModel):
    calibrated_loopback_offset_ms: float = Field(..., description="Systematic hardware loopback latency differential in ms")
    speed_of_sound_mps: float = Field(..., description="Calculated speed of sound at ambient temperature")
    temperature_celsius: float = Field(..., description="Ambient temperature during acquisition")


class ReconstructionDiagnostics(BaseModel):
    residual_rms_ms: float = Field(..., description="Unweighted timing residual RMS in ms")
    jacobian_rank: int = Field(..., description="Rank of the reconstruction Jacobian")
    jacobian_condition_number: float = Field(..., description="Condition number of the Jacobian")
    optimizer_status: str = Field(..., description="Numerical optimizer convergence status")
    function_evaluations: int = Field(..., description="Number of objective function evaluations")
    per_wall_counts: dict[str, int] = Field(..., description="Accepted first-order reflections per wall")
    total_reflections_used: int = Field(..., description="Total first-order reflections entering estimation")
    timing_provenance: TimingProvenance


class DeviceNode(BaseModel):
    channel: int
    name: str
    axis: str | None = None
    position_m: list[float] = Field(..., min_length=3, max_length=3, description="[X=length, Y=width, Z=height] in metres")


class Smard0001ReconstructionResponse(BaseModel):
    dataset: str = "SMARD"
    configuration: str = "0001"
    room_id: str = "B5-108"
    method: str = "BatSight Calibrated Shoebox Dimension Estimator"
    provenance_badge: str = "Estimated (Calibrated Real Data)"
    estimated_dimensions_m: list[float] = Field(..., min_length=3, max_length=3, description="[Lx, Ly, Lz] in metres")
    ground_truth_dimensions_m: list[float] = Field(..., min_length=3, max_length=3, description="[Lx, Ly, Lz] in metres")
    absolute_error_cm: ErrorMetrics
    relative_error_percent: ErrorMetrics
    loudspeaker: DeviceNode
    microphones: list[DeviceNode]
    diagnostics: ReconstructionDiagnostics


@router.get(
    "/smard-0001",
    response_model=Smard0001ReconstructionResponse,
    summary="Get validated SMARD Configuration 0001 calibrated reconstruction",
    description="Returns estimated room dimensions, ground truth, device coordinates, and diagnostic residuals from real SMARD 0001 acoustic data."
)
def get_smard_0001_reconstruction() -> Smard0001ReconstructionResponse:
    recon_path = PROCESSED_SMARD_DIR / "reconstruction_result.json"
    geo_path = PROCESSED_SMARD_DIR / "geometry_metadata.json"
    
    if recon_path.exists() and geo_path.exists():
        try:
            with open(recon_path, "r", encoding="utf-8") as f:
                recon_data = json.load(f)
            with open(geo_path, "r", encoding="utf-8") as f:
                geo_data = json.load(f)

            best_run = recon_data["runs"][0]
            est_dims = [
                best_run["estimated_dimensions_m"]["Lx"],
                best_run["estimated_dimensions_m"]["Ly"],
                best_run["estimated_dimensions_m"]["Lz"],
            ]
            gt_dims = recon_data["ground_truth_dimensions_m"]

            mics_list = []
            for ch_str in sorted(geo_data["microphones"].keys(), key=lambda x: int(x)):
                ch = int(ch_str)
                if ch in (8, 16):
                    continue
                m = geo_data["microphones"][ch_str]
                mics_list.append(DeviceNode(
                    channel=ch,
                    name=m["name"],
                    axis=m.get("axis"),
                    position_m=m["transformed_batsight_coordinates_x_y_z_m"]
                ))

            src = geo_data["source"]
            loudspeaker = DeviceNode(
                channel=src["channel"],
                name=src["name"],
                axis=None,
                position_m=src["transformed_batsight_coordinates_x_y_z_m"]
            )

            diag = ReconstructionDiagnostics(
                residual_rms_ms=best_run["residual_rms_ms"],
                jacobian_rank=best_run["jacobian_rank"],
                jacobian_condition_number=best_run["jacobian_condition_number"],
                optimizer_status=best_run["status"],
                function_evaluations=best_run["function_evaluations"],
                per_wall_counts=recon_data["wall_counts"],
                total_reflections_used=recon_data["total_first_order_observations"],
                timing_provenance=TimingProvenance(
                    calibrated_loopback_offset_ms=-0.353,
                    speed_of_sound_mps=geo_data.get("speed_of_sound_mps", 344.172),
                    temperature_celsius=geo_data.get("temperature_celsius", 21.6)
                )
            )

            return Smard0001ReconstructionResponse(
                dataset="SMARD",
                configuration="0001",
                room_id=geo_data.get("room_name", "B5-108"),
                method="BatSight Calibrated Shoebox Dimension Estimator",
                provenance_badge="Estimated (Calibrated Real Data)",
                estimated_dimensions_m=est_dims,
                ground_truth_dimensions_m=gt_dims,
                absolute_error_cm=ErrorMetrics(
                    Lx=best_run["absolute_error_cm"]["Lx"],
                    Ly=best_run["absolute_error_cm"]["Ly"],
                    Lz=best_run["absolute_error_cm"]["Lz"],
                ),
                relative_error_percent=ErrorMetrics(
                    Lx=best_run["relative_error_percent"]["Lx"],
                    Ly=best_run["relative_error_percent"]["Ly"],
                    Lz=best_run["relative_error_percent"]["Lz"],
                ),
                loudspeaker=loudspeaker,
                microphones=mics_list,
                diagnostics=diag
            )
        except Exception as err:
            raise HTTPException(status_code=500, detail=f"Failed to load SMARD 0001 reconstruction: {err}")

    raise HTTPException(status_code=404, detail="SMARD 0001 reconstruction data not found. Please run scripts/reconstruct_smard_0001.py first.")
