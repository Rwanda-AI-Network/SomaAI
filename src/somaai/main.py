"""Main entry point for SomaAI."""

import uvicorn

from somaai.app import create_app
from somaai.settings import settings

app = create_app()

if __name__ == "__main__":
    uvicorn.run(
        "somaai.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )
