from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field

from platform_api.api.common import client_ip, security_store, store
from platform_api.core.config import settings
from platform_api.security import (
    Principal,
    get_optional_principal,
    hash_session_token,
    make_password_hash,
    new_session_token,
    require_permission,
    verify_password,
)
from platform_api.services.security_store import SecurityStore

router = APIRouter(prefix='/api/v1', tags=['auth'])


class LoginRequest(BaseModel):
    username: str
    password: str


class CreateUserRequest(BaseModel):
    username: str
    display_name: str
    email: str | None = None
    password: str = Field(min_length=8)
    roles: list[str] = Field(default_factory=lambda: ['viewer'])


class UpdateUserRequest(BaseModel):
    display_name: str | None = None
    email: str | None = None
    password: str | None = Field(default=None, min_length=8)
    status: str | None = Field(default=None, pattern='^(active|disabled|locked)$')


class AssignRolesRequest(BaseModel):
    roles: list[str] = Field(default_factory=list)


class UpdateProfileRequest(BaseModel):
    display_name: str | None = None
    email: str | None = None
    avatar_url: str | None = None
    current_password: str | None = None
    new_password: str | None = Field(default=None, min_length=8)


def _admin_user_ids(users: list[dict[str, Any]]) -> list[int]:
    admin_ids: list[int] = []
    for user in users:
        roles = user.get('roles', [])
        if isinstance(roles, list) and 'admin' in roles:
            admin_ids.append(int(user['id']))
    return admin_ids


def _sole_admin_user_id(users: list[dict[str, Any]]) -> int | None:
    admin_ids = _admin_user_ids(users)
    return admin_ids[0] if len(admin_ids) == 1 else None


def _guard_single_admin_create(*, roles: list[str], security_store_: SecurityStore) -> None:
    normalized = {str(role).strip().lower() for role in roles if str(role).strip()}
    if 'admin' not in normalized:
        return
    if _admin_user_ids(security_store_.list_users()):
        raise HTTPException(status_code=409, detail='系统仅允许一个管理员用户，当前已存在管理员。')


def _guard_single_admin_status_update(
    *,
    target_user: dict[str, Any],
    next_status: str | None,
    actor_user_id: int | None,
    security_store_: SecurityStore,
) -> None:
    if next_status is None or next_status == 'active':
        return

    users = security_store_.list_users()
    sole_admin_id = _sole_admin_user_id(users)
    target_user_id = int(target_user['id'])
    target_roles = target_user.get('roles', [])
    target_is_admin = isinstance(target_roles, list) and 'admin' in target_roles

    if target_is_admin and sole_admin_id == target_user_id:
        if actor_user_id == target_user_id:
            detail = '管理员不能将自己的账号状态修改为 disabled 或 locked，否则会导致系统管理权限丢失。'
        else:
            detail = '当前系统仅有一个管理员，不能将其账号状态修改为 disabled 或 locked。'
        raise HTTPException(status_code=409, detail=detail)


def _guard_single_admin_role_assignment(
    *,
    target_user: dict[str, Any],
    roles: list[str],
    actor_user_id: int | None,
    security_store_: SecurityStore,
) -> None:
    normalized = [str(role).strip().lower() for role in roles if str(role).strip()]
    requested_admin = 'admin' in normalized

    users = security_store_.list_users()
    admin_ids = _admin_user_ids(users)
    sole_admin_id = _sole_admin_user_id(users)
    target_user_id = int(target_user['id'])
    current_roles = target_user.get('roles', [])
    target_is_admin = isinstance(current_roles, list) and 'admin' in current_roles

    if requested_admin and admin_ids and target_user_id not in admin_ids:
        raise HTTPException(status_code=409, detail='系统仅允许一个管理员用户，不能再将其他用户设置为管理员。')

    if target_is_admin and sole_admin_id == target_user_id and not requested_admin:
        if actor_user_id == target_user_id:
            detail = '管理员不能移除自己的管理员角色，否则会导致系统管理权限丢失。'
        else:
            detail = '当前系统仅有一个管理员，不能移除其管理员角色。'
        raise HTTPException(status_code=409, detail=detail)


@router.get('/auth/me')
def auth_me(principal: Principal = Depends(get_optional_principal)) -> dict[str, Any]:
    return {
        'authenticated': principal.authenticated or not settings.security.enabled,
        'security_enabled': settings.security.enabled,
        'user': {
            'id': principal.user_id,
            'username': principal.username,
            'display_name': principal.display_name,
            'email': principal.email,
            'avatar_url': principal.avatar_url,
            'roles': principal.roles,
            'permissions': principal.permissions,
        } if (principal.authenticated or not settings.security.enabled) else None,
    }


@router.patch('/auth/me')
def update_my_profile(
    payload: UpdateProfileRequest,
    request: Request,
    principal: Principal = Depends(get_optional_principal),
) -> dict[str, Any]:
    if settings.security.enabled and not principal.authenticated:
        raise HTTPException(status_code=401, detail='authentication required')
    if principal.user_id is None:
        raise HTTPException(status_code=400, detail='local development mode does not support profile editing')

    security_store_ = security_store()
    auth_user = security_store_.get_auth_user(principal.username)
    if auth_user is None:
        raise HTTPException(status_code=404, detail='user not found')

    password_hash: str | object = None
    if payload.new_password:
        current_password = (payload.current_password or '').strip()
        if not current_password:
            raise HTTPException(status_code=400, detail='current password is required when changing password')
        if not verify_password(current_password, auth_user.get('password_hash', '')):
            raise HTTPException(status_code=400, detail='current password is incorrect')
        password_hash = make_password_hash(payload.new_password)

    profile_kwargs: dict[str, Any] = {'user_id': int(principal.user_id)}
    if payload.display_name is not None:
        profile_kwargs['display_name'] = payload.display_name.strip()
    if payload.email is not None:
        profile_kwargs['email'] = payload.email.strip() or None
    if payload.avatar_url is not None:
        profile_kwargs['avatar_url'] = payload.avatar_url.strip() or None
    if payload.new_password:
        profile_kwargs['password_hash'] = password_hash

    updated = security_store_.update_user(**profile_kwargs)
    if updated is None:
        raise HTTPException(status_code=404, detail='user not found')

    store().record_audit_event(
        event_type='security.user.profile_updated',
        target_type='user',
        target_id=str(principal.user_id),
        actor=principal.username,
        details={'ip': client_ip(request)},
    )
    return updated


@router.get('/auth/me/permissions')
def my_permissions(principal: Principal = Depends(get_optional_principal)) -> dict[str, Any]:
    if settings.security.enabled and not principal.authenticated:
        raise HTTPException(status_code=401, detail='authentication required')

    security_store_ = security_store()
    owned = set(principal.permissions)
    all_permissions = security_store_.list_permissions()
    return {
        'owned': [item for item in all_permissions if item['code'] in owned],
        'missing': [item for item in all_permissions if item['code'] not in owned],
        'all': all_permissions,
    }


@router.post('/auth/login')
def auth_login(request: Request, payload: LoginRequest, response: Response) -> dict[str, Any]:
    if not settings.security.enabled:
        raise HTTPException(status_code=400, detail='security is disabled')

    user = security_store().get_auth_user(payload.username.strip())
    if user is None or user['status'] != 'active' or not verify_password(payload.password, user.get('password_hash', '')):
        store().record_audit_event(
            event_type='security.login.failed',
            target_type='user',
            target_id=payload.username.strip(),
            actor=payload.username.strip() or 'anonymous',
            details={'ip': client_ip(request), 'user_agent': request.headers.get('user-agent', '')},
        )
        raise HTTPException(status_code=401, detail='invalid username or password')

    session_token = new_session_token()
    security_store().create_session(
        user_id=int(user['id']),
        session_token_hash=hash_session_token(session_token),
        ttl_sec=settings.security.session_ttl_sec,
        ip_address=client_ip(request),
        user_agent=request.headers.get('user-agent', ''),
    )
    response.set_cookie(
        key=settings.security.session_cookie_name,
        value=session_token,
        httponly=True,
        secure=settings.security.session_cookie_secure,
        samesite=settings.security.session_cookie_samesite,
        max_age=settings.security.session_ttl_sec,
        path='/',
    )
    store().record_audit_event(
        event_type='security.login.succeeded',
        target_type='user',
        target_id=str(user['id']),
        actor=user['username'],
        details={'ip': client_ip(request), 'user_agent': request.headers.get('user-agent', '')},
    )
    return {'ok': True}


@router.post('/auth/logout')
def auth_logout(
    request: Request,
    response: Response,
    principal: Principal = Depends(get_optional_principal),
) -> dict[str, Any]:
    token = request.cookies.get(settings.security.session_cookie_name)
    if token and settings.security.enabled:
        security_store().revoke_session(session_token_hash=hash_session_token(token))
    response.delete_cookie(key=settings.security.session_cookie_name, path='/')
    if principal.authenticated:
        store().record_audit_event(
            event_type='security.logout',
            target_type='user',
            target_id=str(principal.user_id),
            actor=principal.username,
            details={'ip': client_ip(request), 'user_agent': request.headers.get('user-agent', '')},
        )
    return {'ok': True}


@router.get('/roles')
def list_roles(principal: Principal = Depends(require_permission('role.read'))) -> dict[str, Any]:
    return {'items': security_store().list_roles()}


@router.get('/users')
def list_users(principal: Principal = Depends(require_permission('user.read'))) -> dict[str, Any]:
    return {'items': security_store().list_users()}


@router.post('/users', status_code=status.HTTP_201_CREATED)
def create_user(
    payload: CreateUserRequest,
    request: Request,
    principal: Principal = Depends(require_permission('user.create')),
) -> dict[str, Any]:
    security_store_ = security_store()
    _guard_single_admin_create(roles=payload.roles, security_store_=security_store_)
    try:
        user = security_store_.create_user(
            username=payload.username.strip(),
            display_name=payload.display_name.strip(),
            email=payload.email.strip() if payload.email else None,
            password_hash=make_password_hash(payload.password),
            roles=payload.roles,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    store().record_audit_event(
        event_type='security.user.created',
        target_type='user',
        target_id=str(user['id']),
        actor=principal.username,
        details={'username': user['username'], 'roles': user['roles'], 'ip': client_ip(request)},
    )
    return user


@router.patch('/users/{user_id}')
def update_user(
    user_id: int,
    payload: UpdateUserRequest,
    request: Request,
    principal: Principal = Depends(require_permission('user.update')),
) -> dict[str, Any]:
    security_store_ = security_store()
    current = security_store_.get_user(user_id)
    if current is None:
        raise HTTPException(status_code=404, detail=f'user not found: {user_id}')

    _guard_single_admin_status_update(
        target_user=current,
        next_status=payload.status,
        actor_user_id=principal.user_id,
        security_store_=security_store_,
    )

    update_kwargs: dict[str, Any] = {'user_id': user_id}
    if payload.display_name is not None:
        update_kwargs['display_name'] = payload.display_name.strip()
    if payload.email is not None:
        update_kwargs['email'] = payload.email.strip() or None
    if payload.password is not None:
        update_kwargs['password_hash'] = make_password_hash(payload.password)
    if payload.status is not None:
        update_kwargs['status'] = payload.status

    try:
        updated = security_store_.update_user(**update_kwargs)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    if updated is None:
        raise HTTPException(status_code=404, detail=f'user not found: {user_id}')
    if payload.status and payload.status != 'active':
        security_store_.revoke_user_sessions(user_id=user_id)
    store().record_audit_event(
        event_type='security.user.updated',
        target_type='user',
        target_id=str(user_id),
        actor=principal.username,
        details={'status': updated['status'], 'roles': updated['roles'], 'ip': client_ip(request)},
    )
    return updated


@router.post('/users/{user_id}/roles')
def assign_user_roles(
    user_id: int,
    payload: AssignRolesRequest,
    request: Request,
    principal: Principal = Depends(require_permission('user.assign_roles')),
) -> dict[str, Any]:
    security_store_ = security_store()
    current = security_store_.get_user(user_id)
    if current is None:
        raise HTTPException(status_code=404, detail=f'user not found: {user_id}')

    _guard_single_admin_role_assignment(
        target_user=current,
        roles=payload.roles,
        actor_user_id=principal.user_id,
        security_store_=security_store_,
    )

    try:
        updated = security_store_.set_user_roles(user_id=user_id, roles=payload.roles)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if updated is None:
        raise HTTPException(status_code=404, detail=f'user not found: {user_id}')
    security_store_.revoke_user_sessions(user_id=user_id)
    store().record_audit_event(
        event_type='security.user.roles_updated',
        target_type='user',
        target_id=str(user_id),
        actor=principal.username,
        details={'roles': updated['roles'], 'ip': client_ip(request)},
    )
    return updated
