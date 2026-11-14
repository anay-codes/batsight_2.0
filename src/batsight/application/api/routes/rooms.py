"""API routes for persistent scanned room entities."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from batsight.application.api.schemas.contracts import RoomCreate, RoomResponse, RoomUpdate
from batsight.application.api.serializers import utc_datetime
from batsight.application.dependencies import database_session
from batsight.application.models.entities import Project, Room

router = APIRouter(prefix="/api/rooms", tags=["rooms"])


def _to_response(r: Room) -> RoomResponse:
    return RoomResponse(
        id=r.id,
        project_id=r.project_id,
        name=r.name,
        description=r.description,
        length_x_m=r.length_x_m,
        width_y_m=r.width_y_m,
        height_z_m=r.height_z_m,
        floor_area_m2=r.floor_area_m2,
        room_volume_m3=r.room_volume_m3,
        device_position_m=r.device_position_m or [r.length_x_m / 2, r.width_y_m / 2, 1.0],
        wall_distances=r.wall_distances or {},
        obstacles=r.obstacles or [],
        scan_metadata=r.scan_metadata or {},
        created_at=utc_datetime(r.created_at),
        updated_at=utc_datetime(r.updated_at),
    )


@router.post(
    "",
    response_model=RoomResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create and persist a new scanned room",
)
def create_room(
    payload: RoomCreate,
    session: Session = Depends(database_session),
):
    if payload.project_id is not None:
        project = session.get(Project, payload.project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")

    lx = round(payload.length_x_m, 3)
    ly = round(payload.width_y_m, 3)
    lz = round(payload.height_z_m, 3)
    area = payload.floor_area_m2 or round(lx * ly, 2)
    vol = payload.room_volume_m3 or round(lx * ly * lz, 2)

    room = Room(
        project_id=payload.project_id,
        name=payload.name.strip(),
        description=payload.description,
        length_x_m=lx,
        width_y_m=ly,
        height_z_m=lz,
        floor_area_m2=area,
        room_volume_m3=vol,
        device_position_m=payload.device_position_m,
        wall_distances=payload.wall_distances,
        obstacles=payload.obstacles,
        scan_metadata=payload.scan_metadata,
    )
    session.add(room)
    session.commit()
    session.refresh(room)
    return _to_response(room)


@router.get(
    "",
    response_model=list[RoomResponse],
    summary="List all saved rooms",
)
def list_rooms(
    project_id: int | None = None,
    session: Session = Depends(database_session),
):
    query = select(Room).order_by(Room.created_at.desc())
    if project_id is not None:
        query = query.where(Room.project_id == project_id)
    return [_to_response(row) for row in session.scalars(query).all()]


@router.get(
    "/{room_id}",
    response_model=RoomResponse,
    summary="Retrieve single room details",
)
def get_room(
    room_id: int,
    session: Session = Depends(database_session),
):
    room = session.get(Room, room_id)
    if room is None:
        raise HTTPException(status_code=404, detail="Room not found")
    return _to_response(room)


@router.put(
    "/{room_id}",
    response_model=RoomResponse,
    summary="Update room details, dimensions, or obstacles",
)
def update_room(
    room_id: int,
    payload: RoomUpdate,
    session: Session = Depends(database_session),
):
    room = session.get(Room, room_id)
    if room is None:
        raise HTTPException(status_code=404, detail="Room not found")

    if payload.name is not None:
        room.name = payload.name.strip()
    if payload.description is not None:
        room.description = payload.description
    if payload.length_x_m is not None:
        room.length_x_m = round(payload.length_x_m, 3)
    if payload.width_y_m is not None:
        room.width_y_m = round(payload.width_y_m, 3)
    if payload.height_z_m is not None:
        room.height_z_m = round(payload.height_z_m, 3)
    if payload.device_position_m is not None:
        room.device_position_m = payload.device_position_m
    if payload.wall_distances is not None:
        room.wall_distances = payload.wall_distances
    if payload.obstacles is not None:
        room.obstacles = payload.obstacles

    room.floor_area_m2 = round(room.length_x_m * room.width_y_m, 2)
    room.room_volume_m3 = round(room.length_x_m * room.width_y_m * room.height_z_m, 2)

    session.commit()
    session.refresh(room)
    return _to_response(room)


@router.delete(
    "/{room_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a room",
)
def delete_room(
    room_id: int,
    session: Session = Depends(database_session),
):
    room = session.get(Room, room_id)
    if room is None:
        raise HTTPException(status_code=404, detail="Room not found")
    session.delete(room)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
