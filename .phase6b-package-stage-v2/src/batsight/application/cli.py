"""Command-line launcher honoring local host and port settings."""

import uvicorn

from batsight.application.config import Settings


def main() -> None:
    settings = Settings.from_environment()
    uvicorn.run(
        "batsight.application.main:app",
        host=settings.host,
        port=settings.port,
        reload=False,
    )
