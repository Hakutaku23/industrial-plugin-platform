from __future__ import annotations

import uuid

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.httpsredirect import HTTPSRedirectMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from platform_api.core.config import settings


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        content_length = request.headers.get('content-length')
        if content_length and int(content_length) > settings.security.max_request_body_bytes:
            return Response('request body too large', status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE)

        request_id = request.headers.get('x-request-id') or uuid.uuid4().hex
        response = await call_next(request)
        response.headers['X-Request-Id'] = request_id
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        return response


class CacheControlMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        if request.url.path.startswith('/api/v1/auth'):
            response.headers['Cache-Control'] = 'no-store'
        return response



def configure_middlewares(app: FastAPI) -> None:
    if settings.security.trusted_hosts:
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.security.trusted_hosts)
    if settings.security.https_redirect:
        app.add_middleware(HTTPSRedirectMiddleware)
    app.add_middleware(CacheControlMiddleware)
    app.add_middleware(RequestContextMiddleware)
