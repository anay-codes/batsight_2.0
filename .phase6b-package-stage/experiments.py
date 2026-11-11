"""Persisted synthetic experiment management and background execution."""

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from batsight.application.api.schemas.contracts import (
    ExperimentCreate, ExperimentResponse, ExperimentResultResponse, RunAccepted,
)
from batsight.application.api.serializers import utc_datetime
from batsight.application.dependencies import database_session
from batsight.application.models.entities import Experiment, Project

router = APIRouter(prefix="/api/experiments", tags=["experiments"])


def _response(experiment: Experiment) -> ExperimentResponse:
    return ExperimentResponse(
        id=experiment.id, project_id=experiment.project_id, name=experiment.name,
        kind=experiment.kind, status=experiment.status,
        configuration=experiment.configuration, error_message=experiment.error_message,
        created_at=utc_datetime(experiment.created_at), updated_at=utc_datetime(experiment.updated_at),
    )


@router.post("", response_model=ExperimentResponse, status_code=status.HTTP_201_CREATED,
            summary="Create a pending experiment")
def create_experiment(payload: ExperimentCreate, session: Session = Depends(database_session)):
    if session.get(Project, payload.project_id) is None:
        raise HTTPException(404, "Project not found")
    experiment = Experiment(
        project_id=payload.project_id, name=payload.name.strip(), kind=payload.kind,
        status="pending", configuration=payload.configuration,
    )
    if not experiment.name:
        raise HTTPException(422, "Experiment name cannot be blank")
    session.add(experiment)
    session.commit()
    session.refresh(experiment)
    return _response(experiment)


@router.get("", response_model=list[ExperimentResponse], summary="List experiments")
def list_experiments(project_id: int | None = None, session: Session = Depends(database_session)):
    query = select(Experiment).order_by(Experiment.created_at.desc())
    if project_id is not None:
        query = query.where(Experiment.project_id == project_id)
    return [_response(row) for row in session.scalars(query).all()]


@router.get("/{experiment_id}", response_model=ExperimentResponse, summary="Retrieve experiment status")
def get_experiment(experiment_id: int, session: Session = Depends(database_session)):
    experiment = session.get(Experiment, experiment_id)
    if experiment is None:
        raise HTTPException(404, "Experiment not found")
    return _response(experiment)


@router.get("/{experiment_id}/results", response_model=ExperimentResultResponse,
            summary="Retrieve stored experiment results")
def get_experiment_results(experiment_id: int, session: Session = Depends(database_session)):
    experiment = session.get(Experiment, experiment_id)
    if experiment is None:
        raise HTTPException(404, "Experiment not found")
    result = experiment.result.result_json if experiment.result is not None else None
    return ExperimentResultResponse(experiment_id=experiment_id, result=result)


@router.post("/{experiment_id}/run", response_model=RunAccepted, status_code=status.HTTP_202_ACCEPTED,
            summary="Queue a supported synthetic experiment")
def run_experiment(experiment_id: int, background_tasks: BackgroundTasks,
                   request: Request, session: Session = Depends(database_session)):
    experiment = session.get(Experiment, experiment_id)
    if experiment is None:
        raise HTTPException(404, "Experiment not found")
    if experiment.status == "running":
        raise HTTPException(409, "Experiment is already running")
    experiment.status = "running"
    experiment.error_message = None
    session.commit()
    background_tasks.add_task(request.app.state.experiment_service.run_background, experiment_id)
    return RunAccepted(
        experiment_id=experiment_id, status="running",
        message="Synthetic experiment queued for local background execution",
    )
