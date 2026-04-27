from fastapi import APIRouter

from platform_api.api import auth, data_sources, instances, internal_scheduler, license, models, observability, packages, runs, scheduler, system

router = APIRouter()

for module in (
    system,
    auth,
    scheduler,
    observability,
    license,
    packages,
    models,
    data_sources,
    instances,
    runs,
    internal_scheduler,
):
    router.include_router(module.router)
