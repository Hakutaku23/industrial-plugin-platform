from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from platform_api.api.routes import router
from platform_api.core.config import settings
from platform_api.middleware import configure_middlewares
from platform_api.services.database_cleanup import database_cleanup_service
from platform_api.services.license_manager import license_manager
from platform_api.services.metadata_store import MetadataStore
from platform_api.services.model_update_scheduler import model_update_scheduler_service
from platform_api.services.run_directory_cleanup import run_directory_cleanup_service
from platform_api.services.scheduler import scheduler
from platform_api.security import make_password_hash
from platform_api.services.security_store import SecurityStore
from platform_api.ui import mount_spa


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Ensure metadata tables exist before any service reads them.
    # This is required when using MySQL or a fresh SQLite database.
    MetadataStore(settings.metadata_database).initialize()

    license_manager.initialize()
    if settings.security.enabled and settings.security.bootstrap_admin_username and settings.security.bootstrap_admin_password:
        SecurityStore(settings.metadata_database).ensure_bootstrap_admin(
            username=settings.security.bootstrap_admin_username,
            display_name=settings.security.bootstrap_admin_display_name,
            email=settings.security.bootstrap_admin_email,
            password_hash=make_password_hash(settings.security.bootstrap_admin_password),
        )
    run_directory_cleanup_service.start()
    database_cleanup_service.start()
    model_update_scheduler_service.start()
    if settings.scheduler.enabled:
        scheduler.start()
    try:
        yield
    finally:
        if settings.scheduler.enabled:
            scheduler.stop()
        model_update_scheduler_service.stop()
        database_cleanup_service.stop()
        run_directory_cleanup_service.stop()


def create_app() -> FastAPI:
    app = FastAPI(
        title='Industrial Plugin Platform API',
        version='0.2.0',
        description='Control plane API for plugin package intake, execution, and administration.',
        lifespan=lifespan,
    )
    configure_middlewares(app)
    app.include_router(router)
    mount_spa(app)
    return app


app = create_app()
