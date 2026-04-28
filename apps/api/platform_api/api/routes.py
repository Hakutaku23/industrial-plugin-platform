from fastapi import APIRouter

from platform_api.api import (
    auth,
    data_sources,
    instances,
    internal_scheduler,
    license,
    model_updates,
    models,
    observability,
    packages,
    runs,
    scheduler,
    system,
    system_settings,
    templates,
    runtime_diagnostics,
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
    model_updates,
    data_sources,
    instances,
    runs,
    system_settings,
    internal_scheduler,
    runtime_diagnostics,
):
    router.include_router(module.router)
