from fastapi import FastAPI

from platform_api.api.routes import router


def create_app() -> FastAPI:
    app = FastAPI(
        title="Industrial Plugin Platform API",
        version="0.1.0",
        description="Control plane API for plugin package intake and execution metadata.",
    )
    app.include_router(router)
    return app


app = create_app()

