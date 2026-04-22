from __future__ import annotations

from fastapi import Request

from platform_api.core.config import settings
from platform_api.services.metadata_store import MetadataStore
from platform_api.services.security_store import SecurityStore


def metadata_target() -> str | object:
    return getattr(settings, 'metadata_database', getattr(settings, 'metadata_db_path'))


def store() -> MetadataStore:
    return MetadataStore(metadata_target())


def security_store() -> SecurityStore:
    return SecurityStore(metadata_target())


def client_ip(request: Request) -> str | None:
    forwarded = request.headers.get('x-forwarded-for')
    if forwarded:
        return forwarded.split(',', 1)[0].strip()
    return request.client.host if request.client else None
