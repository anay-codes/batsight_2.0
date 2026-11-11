"""Project CRUD routes."""

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from batsight.application.api.schemas.contracts import ProjectCreate, ProjectResponse
from batsight.application.api.serializers import utc_datetime
from batsight.application.dependencies import database_session
from batsight.application.models.entities import Project
from batsight.application.services.recording_service import RecordingService

router = APIRouter(prefix="/api/projects", tags=["projects"])


def _response(project: Project) -> ProjectResponse:
    return ProjectResponse(
        id=project.id, name=project.name, description=project.description,
        metadata=project.project_metadata, created_at=utc_datetime(project.created_at),
        updated_at=utc_datetime(project.updated_at),
    )


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED, summary="Create a project")
def create_project(payload: ProjectCreate, session: Session = Depends(database_session)):
    project = Project(name=payload.name.strip(), description=payload.description,
                      project_metadata=payload.metadata)
    if not project.name:
        raise HTTPException(422, "Project name cannot be blank")
    session.add(project)
    session.commit()
    session.refresh(project)
    return _response(project)


@router.get("", response_model=list[ProjectResponse], summary="List projects")
def list_projects(session: Session = Depends(database_session)):
    return [_response(row) for row in session.query(Project).order_by(Project.created_at.desc()).all()]


@router.get("/{project_id}", response_model=ProjectResponse, summary="Retrieve a project")
def get_project(project_id: int, session: Session = Depends(database_session)):
    project = session.get(Project, project_id)
    if project is None:
        raise HTTPException(404, "Project not found")
    return _response(project)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a project and its records")
def delete_project(project_id: int, request: Request, session: Session = Depends(database_session)):
    project = session.get(Project, project_id)
    if project is None:
        raise HTTPException(404, "Project not found")
    recordings = list(project.recordings)
    file_paths = []
    recording_service = RecordingService(request.app.state.settings)
    try:
        file_paths = [recording_service.safe_managed_path(row) for row in recordings]
    except ValueError as exc:
        raise HTTPException(500, "Project contains an invalid managed recording path") from exc
    session.delete(project)
    session.commit()
    for path in file_paths:
        path.unlink(missing_ok=True)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
