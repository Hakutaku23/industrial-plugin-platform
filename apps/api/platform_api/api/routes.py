from fastapi import APIRouter

from platform_api.api import (
    auth,
    data_sources,
    instances,
    internal_scheduler,
    license,
    models,
    observability,
    packages,
    runs,
    scheduler,
    system,
    system_settings,
    templates,
)

router = APIRouter()

for module in (
    system,
    auth,
    scheduler,
    observability,
    license,
    packages,
    templates,
    models,
    data_sources,
    instances,
    runs,
    system_settings,
    internal_scheduler,
):
    router.include_router(module.router)
