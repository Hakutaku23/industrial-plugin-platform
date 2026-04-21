from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import Response as RawResponse
from pydantic import BaseModel, Field

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
from platform_api.services.execution import (
    PluginExecutionError,
    execute_plugin_instance_locked,
    execute_plugin_version,
)
from platform_api.services.metadata_store import MetadataStore
from platform_api.services.package_storage import PackageStorage, PackageStorageError
from platform_api.services.plugin_template import build_python_function_template_archive
from platform_api.services.scheduler import scheduler
from platform_api.services.security_store import SecurityStore
from platform_api.ui import frontend_is_available

router = APIRouter(prefix='/api/v1')


def _metadata_target() -> str | object:
    return getattr(settings, 'metadata_database', getattr(settings, 'metadata_db_path'))


def _store() -> MetadataStore:
    return MetadataStore(_metadata_target())


def _security_store() -> SecurityStore:
    return SecurityStore(_metadata_target())


def _client_ip(request: Request) -> str | None:
    forwarded = request.headers.get('x-forwarded-for')
    if forwarded:
        return forwarded.split(',', 1)[0].strip()
    return request.client.host if request.client else None


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


def _guard_single_admin_create(*, roles: list[str], security_store: SecurityStore) -> None:
    normalized = {str(role).strip().lower() for role in roles if str(role).strip()}
    if 'admin' not in normalized:
        return
    if _admin_user_ids(security_store.list_users()):
        raise HTTPException(status_code=409, detail='系统仅允许一个管理员用户，当前已存在管理员。')


def _guard_single_admin_status_update(
    *,
    target_user: dict[str, Any],
    next_status: str | None,
    actor_user_id: int | None,
    security_store: SecurityStore,
) -> None:
    if next_status is None or next_status == 'active':
        return

    users = security_store.list_users()
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
    security_store: SecurityStore,
) -> None:
    normalized = [str(role).strip().lower() for role in roles if str(role).strip()]
    requested_admin = 'admin' in normalized

    users = security_store.list_users()
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


class RunRequest(BaseModel):
    inputs: dict[str, Any] = Field(default_factory=dict)
    config: dict[str, Any] = Field(default_factory=dict)


class DataSourceRequest(BaseModel):
    name: str
    connector_type: str = Field(pattern='^(mock|redis|tdengine)$')
    config: dict[str, Any] = Field(default_factory=dict)
    read_enabled: bool = True
    write_enabled: bool = False


class PluginInstanceRequest(BaseModel):
    name: str
    package_name: str
    version: str
    input_bindings: list[dict[str, Any]] = Field(default_factory=list)
    output_bindings: list[dict[str, Any]] = Field(default_factory=list)
    config: dict[str, Any] = Field(default_factory=dict)
    writeback_enabled: bool = False
    schedule_enabled: bool = False
    schedule_interval_sec: int = Field(default=30, ge=5, le=86400)


class InstanceScheduleRequest(BaseModel):
    enabled: bool
    interval_sec: int | None = Field(default=None, ge=5, le=86400)


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


@router.get('/health')
def health() -> dict[str, str]:
    return {'status': 'ok'}


@router.get('/security/status')
def security_status() -> dict[str, Any]:
    return {
        'enabled': settings.security.enabled,
        'auth_mode': 'local-session',
        'session_cookie_name': settings.security.session_cookie_name,
    }


@router.get('/system/runtime')
def system_runtime(principal: Principal = Depends(require_permission('system.read'))) -> dict[str, Any]:
    return {
        'environment': settings.environment,
        'security_enabled': settings.security.enabled,
        'auth_mode': 'local-session' if settings.security.enabled else 'disabled',
        'ui_mode': 'static-dist' if frontend_is_available() else 'vite-dev',
        'scheduler_enabled': settings.scheduler.enabled,
    }


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
def update_my_profile(payload: UpdateProfileRequest, request: Request, principal: Principal = Depends(get_optional_principal)) -> dict[str, Any]:
    if settings.security.enabled and not principal.authenticated:
        raise HTTPException(status_code=401, detail='authentication required')
    if principal.user_id is None:
        raise HTTPException(status_code=400, detail='local development mode does not support profile editing')

    security_store = _security_store()
    auth_user = security_store.get_auth_user(principal.username)
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

    updated = security_store.update_user(**profile_kwargs)
    if updated is None:
        raise HTTPException(status_code=404, detail='user not found')

    _store().record_audit_event(
        event_type='security.user.profile_updated',
        target_type='user',
        target_id=str(principal.user_id),
        actor=principal.username,
        details={'ip': _client_ip(request)},
    )
    return updated


@router.get('/auth/me/permissions')
def my_permissions(principal: Principal = Depends(get_optional_principal)) -> dict[str, Any]:
    if settings.security.enabled and not principal.authenticated:
        raise HTTPException(status_code=401, detail='authentication required')

    security_store = _security_store()
    owned = set(principal.permissions)
    all_permissions = security_store.list_permissions()
    return {
        'owned': [item for item in all_permissions if item['code'] in owned],
        'missing': [item for item in all_permissions if item['code'] not in owned],
        'all': all_permissions,
    }


@router.post('/auth/login')
def auth_login(request: Request, payload: LoginRequest, response: Response) -> dict[str, Any]:
    if not settings.security.enabled:
        raise HTTPException(status_code=400, detail='security is disabled')

    user = _security_store().get_auth_user(payload.username.strip())
    if user is None or user['status'] != 'active' or not verify_password(payload.password, user.get('password_hash', '')):
        _store().record_audit_event(
            event_type='security.login.failed',
            target_type='user',
            target_id=payload.username.strip(),
            actor=payload.username.strip() or 'anonymous',
            details={'ip': _client_ip(request), 'user_agent': request.headers.get('user-agent', '')},
        )
        raise HTTPException(status_code=401, detail='invalid username or password')

    session_token = new_session_token()
    _security_store().create_session(
        user_id=int(user['id']),
        session_token_hash=hash_session_token(session_token),
        ttl_sec=settings.security.session_ttl_sec,
        ip_address=_client_ip(request),
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
    _store().record_audit_event(
        event_type='security.login.succeeded',
        target_type='user',
        target_id=str(user['id']),
        actor=user['username'],
        details={'ip': _client_ip(request), 'user_agent': request.headers.get('user-agent', '')},
    )
    return {'ok': True}


@router.post('/auth/logout')
def auth_logout(request: Request, response: Response, principal: Principal = Depends(get_optional_principal)) -> dict[str, Any]:
    token = request.cookies.get(settings.security.session_cookie_name)
    if token and settings.security.enabled:
        _security_store().revoke_session(session_token_hash=hash_session_token(token))
    response.delete_cookie(key=settings.security.session_cookie_name, path='/')
    if principal.authenticated:
        _store().record_audit_event(
            event_type='security.logout',
            target_type='user',
            target_id=str(principal.user_id),
            actor=principal.username,
            details={'ip': _client_ip(request), 'user_agent': request.headers.get('user-agent', '')},
        )
    return {'ok': True}


@router.get('/roles')
def list_roles(principal: Principal = Depends(require_permission('role.read'))) -> dict[str, Any]:
    return {'items': _security_store().list_roles()}


@router.get('/users')
def list_users(principal: Principal = Depends(require_permission('user.read'))) -> dict[str, Any]:
    return {'items': _security_store().list_users()}


@router.post('/users', status_code=status.HTTP_201_CREATED)
def create_user(payload: CreateUserRequest, request: Request, principal: Principal = Depends(require_permission('user.create'))) -> dict[str, Any]:
    security_store = _security_store()
    _guard_single_admin_create(roles=payload.roles, security_store=security_store)
    try:
        user = security_store.create_user(
            username=payload.username.strip(),
            display_name=payload.display_name.strip(),
            email=payload.email.strip() if payload.email else None,
            password_hash=make_password_hash(payload.password),
            roles=payload.roles,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    _store().record_audit_event(
        event_type='security.user.created',
        target_type='user',
        target_id=str(user['id']),
        actor=principal.username,
        details={'username': user['username'], 'roles': user['roles'], 'ip': _client_ip(request)},
    )
    return user


@router.patch('/users/{user_id}')
def update_user(user_id: int, payload: UpdateUserRequest, request: Request, principal: Principal = Depends(require_permission('user.update'))) -> dict[str, Any]:
    security_store = _security_store()
    current = security_store.get_user(user_id)
    if current is None:
        raise HTTPException(status_code=404, detail=f'user not found: {user_id}')

    _guard_single_admin_status_update(
        target_user=current,
        next_status=payload.status,
        actor_user_id=principal.user_id,
        security_store=security_store,
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
        updated = security_store.update_user(**update_kwargs)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    if updated is None:
        raise HTTPException(status_code=404, detail=f'user not found: {user_id}')
    if payload.status and payload.status != 'active':
        security_store.revoke_user_sessions(user_id=user_id)
    _store().record_audit_event(
        event_type='security.user.updated',
        target_type='user',
        target_id=str(user_id),
        actor=principal.username,
        details={'status': updated['status'], 'roles': updated['roles'], 'ip': _client_ip(request)},
    )
    return updated


@router.post('/users/{user_id}/roles')
def assign_user_roles(user_id: int, payload: AssignRolesRequest, request: Request, principal: Principal = Depends(require_permission('user.assign_roles'))) -> dict[str, Any]:
    security_store = _security_store()
    current = security_store.get_user(user_id)
    if current is None:
        raise HTTPException(status_code=404, detail=f'user not found: {user_id}')

    _guard_single_admin_role_assignment(
        target_user=current,
        roles=payload.roles,
        actor_user_id=principal.user_id,
        security_store=security_store,
    )

    try:
        updated = security_store.set_user_roles(user_id=user_id, roles=payload.roles)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if updated is None:
        raise HTTPException(status_code=404, detail=f'user not found: {user_id}')
    security_store.revoke_user_sessions(user_id=user_id)
    _store().record_audit_event(
        event_type='security.user.roles_updated',
        target_type='user',
        target_id=str(user_id),
        actor=principal.username,
        details={'roles': updated['roles'], 'ip': _client_ip(request)},
    )
    return updated


@router.get('/scheduler/status')
def scheduler_status(principal: Principal = Depends(require_permission('system.read'))) -> dict[str, object]:
    return {
        'enabled': settings.scheduler.enabled,
        **scheduler.status_snapshot(),
    }


@router.get('/scheduler/locks')
def scheduler_locks(principal: Principal = Depends(require_permission('system.read'))) -> dict[str, object]:
    return {
        'items': scheduler.lock_snapshot(),
    }


@router.get('/templates/python-function-package.zip')
def download_python_function_template(principal: Principal = Depends(require_permission('package.read'))) -> RawResponse:
    archive = build_python_function_template_archive()
    headers = {
        'Content-Disposition': 'attachment; filename="python-function-plugin-template.zip"',
        'Cache-Control': 'no-store',
    }
    return RawResponse(content=archive, media_type='application/zip', headers=headers)


@router.post('/packages', status_code=status.HTTP_201_CREATED)
async def upload_package(
    request: Request,
    filename: str = Query(..., min_length=1),
    principal: Principal = Depends(require_permission('package.upload')),
) -> dict[str, object]:
    content = await request.body()
    if not content:
        raise HTTPException(status_code=400, detail='package body is empty')

    storage = PackageStorage(settings.package_storage_dir)
    try:
        record = storage.add_archive_bytes(filename=filename, content=content)
    except PackageStorageError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    registration = _store().register_package_upload(record)
    _store().record_audit_event(
        event_type='security.package.uploaded',
        target_type='plugin_version',
        target_id=str(registration.version_id),
        actor=principal.username,
        details={'filename': filename, 'package': record.manifest.metadata.name, 'version': record.manifest.metadata.version},
    )

    return {
        'package_id': registration.package_id,
        'version_id': registration.version_id,
        'audit_event_id': registration.audit_event_id,
        'name': record.manifest.metadata.name,
        'version': record.manifest.metadata.version,
        'status': registration.status,
        'digest': record.digest,
        'package_dir': str(record.package_dir),
        'manifest': record.manifest.model_dump(by_alias=True),
    }


@router.get('/packages')
def list_packages(principal: Principal = Depends(require_permission('package.read'))) -> dict[str, object]:
    return {'items': _store().list_plugin_packages()}


@router.get('/packages/{package_name}/versions')
def list_package_versions(package_name: str, principal: Principal = Depends(require_permission('package.read'))) -> dict[str, object]:
    versions = _store().list_plugin_versions(package_name)
    if versions is None:
        raise HTTPException(status_code=404, detail=f'plugin package not found: {package_name}')
    return {'items': versions}


@router.delete('/packages/{package_name}', status_code=status.HTTP_204_NO_CONTENT)
def delete_package(package_name: str, request: Request, principal: Principal = Depends(require_permission('package.delete'))) -> None:
    deleted = _store().delete_plugin_package(package_name)
    if not deleted:
        raise HTTPException(status_code=404, detail=f'plugin package not found: {package_name}')
    _store().record_audit_event(
        event_type='security.package.deleted',
        target_type='plugin_package',
        target_id=package_name,
        actor=principal.username,
        details={'package': package_name, 'ip': _client_ip(request)},
    )


@router.post('/data-sources', status_code=status.HTTP_201_CREATED)
def create_data_source(request: DataSourceRequest, principal: Principal = Depends(require_permission('datasource.create'))) -> dict[str, object]:
    try:
        result = _store().create_data_source(
            name=request.name,
            connector_type=request.connector_type,
            config=request.config,
            read_enabled=request.read_enabled,
            write_enabled=request.write_enabled,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    _store().record_audit_event(
        event_type='security.datasource.created',
        target_type='data_source',
        target_id=str(result.id),
        actor=principal.username,
        details={'name': result.name, 'connector_type': result.connector_type},
    )
    return {
        'id': result.id,
        'name': result.name,
        'connector_type': result.connector_type,
        'status': result.status,
    }


@router.put('/data-sources/{data_source_id}')
def update_data_source(
    data_source_id: int,
    request: DataSourceRequest,
    principal: Principal = Depends(require_permission('datasource.update')),
) -> dict[str, object]:
    try:
        result = _store().update_data_source(
            data_source_id=data_source_id,
            name=request.name,
            connector_type=request.connector_type,
            config=request.config,
            read_enabled=request.read_enabled,
            write_enabled=request.write_enabled,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=404, detail=f'data source not found: {data_source_id}')
    _store().record_audit_event(
        event_type='security.datasource.updated',
        target_type='data_source',
        target_id=str(result.id),
        actor=principal.username,
        details={'name': result.name, 'connector_type': result.connector_type},
    )
    return {
        'id': result.id,
        'name': result.name,
        'connector_type': result.connector_type,
        'status': result.status,
    }


@router.get('/data-sources')
def list_data_sources(principal: Principal = Depends(require_permission('datasource.read'))) -> dict[str, object]:
    return {'items': _store().list_data_sources()}


@router.delete('/data-sources/{data_source_id}', status_code=status.HTTP_204_NO_CONTENT)
def delete_data_source(data_source_id: int, request: Request, principal: Principal = Depends(require_permission('datasource.delete'))) -> None:
    deleted = _store().delete_data_source(data_source_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f'data source not found: {data_source_id}')
    _store().record_audit_event(
        event_type='security.datasource.deleted',
        target_type='data_source',
        target_id=str(data_source_id),
        actor=principal.username,
        details={'ip': _client_ip(request)},
    )


@router.post('/instances', status_code=status.HTTP_201_CREATED)
def upsert_plugin_instance(request: PluginInstanceRequest, principal: Principal = Depends(require_permission('instance.create'))) -> dict[str, object]:
    result = _store().upsert_plugin_instance(
        name=request.name,
        package_name=request.package_name,
        version=request.version,
        input_bindings=request.input_bindings,
        output_bindings=request.output_bindings,
        config=request.config,
        writeback_enabled=request.writeback_enabled,
        schedule_enabled=request.schedule_enabled,
        schedule_interval_sec=request.schedule_interval_sec,
    )
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f'plugin version not found: {request.package_name}@{request.version}',
        )
    _store().record_audit_event(
        event_type='security.instance.created',
        target_type='plugin_instance',
        target_id=str(result.id),
        actor=principal.username,
        details={'name': result.name, 'package': request.package_name, 'version': request.version},
    )
    return {'id': result.id, 'name': result.name, 'status': result.status}


@router.put('/instances/{instance_id}')
def update_plugin_instance(instance_id: int, request: PluginInstanceRequest, principal: Principal = Depends(require_permission('instance.update'))) -> dict[str, object]:
    result = _store().update_plugin_instance(
        instance_id=instance_id,
        name=request.name,
        package_name=request.package_name,
        version=request.version,
        input_bindings=request.input_bindings,
        output_bindings=request.output_bindings,
        config=request.config,
        writeback_enabled=request.writeback_enabled,
        schedule_enabled=request.schedule_enabled,
        schedule_interval_sec=request.schedule_interval_sec,
    )
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f'plugin instance or version not found: {instance_id}',
        )
    _store().record_audit_event(
        event_type='security.instance.updated',
        target_type='plugin_instance',
        target_id=str(result.id),
        actor=principal.username,
        details={'name': result.name, 'package': request.package_name, 'version': request.version},
    )
    return {'id': result.id, 'name': result.name, 'status': result.status}


@router.get('/instances')
def list_plugin_instances(principal: Principal = Depends(require_permission('instance.read'))) -> dict[str, object]:
    return {'items': _store().list_plugin_instances()}


@router.patch('/instances/{instance_id}/schedule')
def update_plugin_instance_schedule(
    instance_id: int,
    request: InstanceScheduleRequest,
    principal: Principal = Depends(require_permission('instance.schedule.update')),
) -> dict[str, object]:
    result = _store().set_plugin_instance_schedule(
        instance_id=instance_id,
        enabled=request.enabled,
        interval_sec=request.interval_sec,
    )
    if result is None:
        raise HTTPException(status_code=404, detail=f'plugin instance not found: {instance_id}')
    _store().record_audit_event(
        event_type='security.instance.schedule_updated',
        target_type='plugin_instance',
        target_id=str(instance_id),
        actor=principal.username,
        details={'enabled': request.enabled, 'interval_sec': request.interval_sec},
    )
    return result


@router.delete('/instances/{instance_id}', status_code=status.HTTP_204_NO_CONTENT)
def delete_plugin_instance(instance_id: int, principal: Principal = Depends(require_permission('instance.delete'))) -> None:
    deleted = _store().delete_plugin_instance(instance_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f'plugin instance not found: {instance_id}')
    _store().record_audit_event(
        event_type='security.instance.deleted',
        target_type='plugin_instance',
        target_id=str(instance_id),
        actor=principal.username,
        details={},
    )


@router.post('/instances/{instance_id}/runs', status_code=status.HTTP_201_CREATED)
def run_plugin_instance(instance_id: int, principal: Principal = Depends(require_permission('instance.run'))) -> dict[str, object]:
    try:
        result = execute_plugin_instance_locked(instance_id=instance_id)
    except PluginExecutionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _store().record_audit_event(
        event_type='security.instance.run_triggered',
        target_type='plugin_instance',
        target_id=str(instance_id),
        actor=principal.username,
        details={'run_id': result.get('run_id'), 'status': result.get('status')},
    )
    return result


@router.post('/packages/{package_name}/versions/{version}/runs', status_code=status.HTTP_201_CREATED)
def run_package_version(package_name: str, version: str, request: RunRequest, principal: Principal = Depends(require_permission('instance.run'))) -> dict[str, object]:
    try:
        result = execute_plugin_version(
            package_name=package_name,
            version=version,
            inputs=request.inputs,
            config=request.config,
        )
    except PluginExecutionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _store().record_audit_event(
        event_type='security.package_version.run_triggered',
        target_type='plugin_version',
        target_id=f'{package_name}@{version}',
        actor=principal.username,
        details={'run_id': result.get('run_id'), 'status': result.get('status')},
    )
    return result


@router.get('/runs')
def list_runs(package_name: str | None = None, instance_id: int | None = None, principal: Principal = Depends(require_permission('run.read'))) -> dict[str, object]:
    return {
        'items': _store().list_plugin_runs(
            package_name=package_name,
            instance_id=instance_id,
        )
    }


@router.get('/runs/{run_id}/logs')
def list_run_logs(run_id: str, principal: Principal = Depends(require_permission('run.read'))) -> dict[str, object]:
    return {'items': _store().list_run_logs(run_id)}


@router.get('/writeback-records')
def list_writeback_records(run_id: str | None = None, principal: Principal = Depends(require_permission('run.read'))) -> dict[str, object]:
    return {'items': _store().list_writeback_records(run_id)}


@router.get('/audit-events')
def list_audit_events(principal: Principal = Depends(require_permission('audit.read'))) -> dict[str, object]:
    return {'items': _store().list_audit_events()}
