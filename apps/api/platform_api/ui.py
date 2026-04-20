from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

from platform_api.core.config import settings


def frontend_dist_root() -> Path:
    return settings.ui.dist_dir


def frontend_is_available() -> bool:
    dist_root = frontend_dist_root()
    return settings.ui.serve_dist and dist_root.exists() and (dist_root / settings.ui.index_file).exists()


def mount_spa(app: FastAPI) -> None:
    if not frontend_is_available():
        return

    dist_root = frontend_dist_root()
    index_file = dist_root / settings.ui.index_file

    @app.get('/', include_in_schema=False)
    async def spa_index() -> FileResponse:
        return FileResponse(index_file)

    @app.get('/{full_path:path}', include_in_schema=False)
    async def spa_fallback(full_path: str):
        if full_path.startswith('api/'):
            raise HTTPException(status_code=404, detail='not found')
        candidate = (dist_root / full_path).resolve()
        if dist_root.resolve() in candidate.parents or candidate == dist_root.resolve():
            if candidate.exists() and candidate.is_file():
                return FileResponse(candidate)
        return FileResponse(index_file)
