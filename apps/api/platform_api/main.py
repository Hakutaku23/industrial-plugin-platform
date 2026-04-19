from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from platform_api.api.routes import router
from platform_api.core.config import settings
from platform_api.services.scheduler import scheduler


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    if settings.scheduler.enabled:
        scheduler.start()
    try:
        yield
    finally:
        if settings.scheduler.enabled:
            scheduler.stop()


def create_app() -> FastAPI:
    app = FastAPI(
        title="Industrial Plugin Platform API",
        version="0.1.0",
        description="Control plane API for plugin package intake and execution metadata.",
        lifespan=lifespan,
    )
    app.include_router(router)
    return app


app = create_app()
