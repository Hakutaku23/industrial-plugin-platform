from __future__ import annotations

import base64
import hashlib
import secrets
from dataclasses import dataclass
from typing import Callable

from fastapi import Depends, HTTPException, Request, status

from platform_api.core.config import settings
from platform_api.services.security_store import SecurityStore


@dataclass(frozen=True)
class Principal:
    user_id: int | None
    username: str
    display_name: str
    email: str | None
    avatar_url: str | None
    roles: list[str]
    permissions: list[str]
    authenticated: bool

    def can(self, permission: str) -> bool:
        return (not settings.security.enabled) or permission in self.permissions


def _store() -> SecurityStore:
    return SecurityStore(settings.metadata_database)


def make_password_hash(password: str) -> str:
    iterations = settings.security.password_iterations
    salt = secrets.token_bytes(16)
    derived = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, iterations)
    return 'pbkdf2_sha256${iterations}${salt}${digest}'.format(
        iterations=iterations,
        salt=base64.b64encode(salt).decode('ascii'),
        digest=base64.b64encode(derived).decode('ascii'),
    )


def verify_password(password: str, password_hash: str) -> bool:
    try:
        algorithm, iterations_text, salt_text, digest_text = password_hash.split('$', 3)
        if algorithm != 'pbkdf2_sha256':
            return False
        iterations = int(iterations_text)
        salt = base64.b64decode(salt_text.encode('ascii'))
        expected = base64.b64decode(digest_text.encode('ascii'))
    except Exception:
        return False
    candidate = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, iterations)
    return secrets.compare_digest(candidate, expected)


def new_session_token() -> str:
    return secrets.token_urlsafe(32)


def hash_session_token(token: str) -> str:
    return hashlib.sha256(token.encode('utf-8')).hexdigest()


async def get_optional_principal(request: Request) -> Principal:
    if not settings.security.enabled:
        return Principal(
            user_id=None,
            username='local-dev',
            display_name='Local Development',
            email=None,
            avatar_url=None,
            roles=['admin'],
            permissions=[permission for permissions in [] for permission in permissions],
            authenticated=False,
        )

    token = request.cookies.get(settings.security.session_cookie_name)
    if not token:
        return Principal(
            user_id=None,
            username='anonymous',
            display_name='Anonymous',
            email=None,
            avatar_url=None,
            roles=[],
            permissions=[],
            authenticated=False,
        )

    session_user = _store().get_session_user(session_token_hash=hash_session_token(token))
    if session_user is None:
        return Principal(
            user_id=None,
            username='anonymous',
            display_name='Anonymous',
            email=None,
            avatar_url=None,
            roles=[],
            permissions=[],
            authenticated=False,
        )

    return Principal(
        user_id=session_user.user_id,
        username=session_user.username,
        display_name=session_user.display_name,
        email=session_user.email,
        avatar_url=session_user.avatar_url,
        roles=session_user.roles,
        permissions=session_user.permissions,
        authenticated=True,
    )


async def require_authenticated(principal: Principal = Depends(get_optional_principal)) -> Principal:
    if not settings.security.enabled:
        return principal
    if not principal.authenticated:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='authentication required')
    return principal


def require_permission(permission: str) -> Callable[[Principal], Principal]:
    async def dependency(principal: Principal = Depends(require_authenticated)) -> Principal:
        if not settings.security.enabled:
            return principal
        if permission not in principal.permissions:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f'missing permission: {permission}')
        return principal

    return dependency
