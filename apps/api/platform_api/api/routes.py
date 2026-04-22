from fastapi import APIRouter

from platform_api.api import auth, data_sources, instances, packages, runs, scheduler, system

router = APIRouter()

for module in (
    system,
    auth,
    scheduler,
    packages,
    data_sources,
    instances,
    runs,
):
    router.include_router(module.router)
