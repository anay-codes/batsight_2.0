"""FastAPI dependencies shared by route modules."""

from collections.abc import Iterator

from fastapi import Request
from sqlalchemy.orm import Session


def database_session(request: Request) -> Iterator[Session]:
    session = request.app.state.session_factory()
    try:
        yield session
    finally:
        session.close()
