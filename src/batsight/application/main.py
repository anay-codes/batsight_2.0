"""FastAPI app factory for the local BatSight backend."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from batsight.application.api.routes import experiments, projects, recordings, recording_sessions, signals, simulation, system
from batsight.application.config import Settings
from batsight.application.database import Base, create_database
from batsight.application.models import entities as _entities  # noqa: F401 - register tables
from batsight.application.services.synthetic_experiment_service import SyntheticExperimentService


def create_app(settings: Settings | None = None) -> FastAPI:
    app_settings = settings or Settings.from_environment()
    engine, session_factory = create_database(app_settings.resolved_database_url)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app_settings.ensure_directories()
        Base.metadata.create_all(bind=engine)
        yield
        engine.dispose()

    application = FastAPI(
        title=app_settings.app_name,
        version=app_settings.version,
        description=(
            "Local research application for synthetic acoustic experiments. "
            "Current API outputs are not validated room reconstructions."
        ),
        lifespan=lifespan,
    )
    application.state.settings = app_settings
    application.state.engine = engine
    application.state.session_factory = session_factory
    application.state.experiment_service = SyntheticExperimentService(session_factory)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Content-Type"],
        expose_headers=["X-Audio-Sample-Rate-Hz", "X-Audio-Sample-Count", "X-Audio-Duration-S", "X-Waveform-Convention"],
    )
    for route_module in (system, projects, recordings, recording_sessions, experiments, signals, simulation):
        application.include_router(route_module.router)
    return application


app = create_app()
