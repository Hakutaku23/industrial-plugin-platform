from fastapi import APIRouter

from platform_api.api import auth, data_sources, instances, internal_scheduler, license, observability, packages, runs, scheduler, system

router = APIRouter()

for module in (
    system,
    auth,
    scheduler,
    observability,
    license,
    packages,
    data_sources,
    instances,
    runs,
    internal_scheduler,
):
    router.include_router(module.router)
