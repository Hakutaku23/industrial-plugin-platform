from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, create_engine, select
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker


DEFAULT_ROLE_PERMISSIONS: dict[str, list[str]] = {
    'viewer': [
        'system.read',
        'package.read',
        'instance.read',
        'datasource.read',
        'run.read',
    ],
    'operator': [
        'system.read',
        'package.read',
        'instance.read',
        'datasource.read',
        'run.read',
        'instance.run',
        'instance.schedule.update',
    ],
    'developer': [
        'system.read',
        'package.read',
        'package.upload',
        'instance.read',
        'instance.create',
        'instance.update',
        'instance.run',
        'datasource.read',
        'run.read',
    ],
    'auditor': [
        'system.read',
        'package.read',
        'instance.read',
        'datasource.read',
        'run.read',
        'audit.read',
    ],
    'admin': [
        'system.read',
        'package.read',
        'package.upload',
        'package.delete',
        'instance.read',
        'instance.create',
        'instance.update',
        'instance.delete',
        'instance.run',
        'instance.schedule.update',
        'datasource.read',
        'datasource.create',
        'datasource.update',
        'datasource.delete',
        'run.read',
        'audit.read',
        'user.read',
        'user.create',
        'user.update',
        'user.assign_roles',
        'role.read',
    ],
}


class Base(DeclarativeBase):
    pass


class UserModel(Base):
    __tablename__ = 'security_users'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(120), unique=True, nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[str | None] = mapped_column(String(240), nullable=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default='active')
    auth_source: Mapped[str] = mapped_column(String(40), nullable=False, default='local')
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    assignments: Mapped[list['UserRoleModel']] = relationship(back_populates='user', cascade='all, delete-orphan')


class RoleModel(Base):
    __tablename__ = 'security_roles'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    is_system: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    permissions: Mapped[list['RolePermissionModel']] = relationship(back_populates='role', cascade='all, delete-orphan')


class PermissionModel(Base):
    __tablename__ = 'security_permissions'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(160), unique=True, nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    module: Mapped[str] = mapped_column(String(80), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class RolePermissionModel(Base):
    __tablename__ = 'security_role_permissions'
    __table_args__ = (UniqueConstraint('role_id', 'permission_id', name='uq_security_role_permission'),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    role_id: Mapped[int] = mapped_column(ForeignKey('security_roles.id'), nullable=False, index=True)
    permission_id: Mapped[int] = mapped_column(ForeignKey('security_permissions.id'), nullable=False, index=True)

    role: Mapped[RoleModel] = relationship(back_populates='permissions')


class UserRoleModel(Base):
    __tablename__ = 'security_user_roles'
    __table_args__ = (UniqueConstraint('user_id', 'role_id', name='uq_security_user_role'),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('security_users.id'), nullable=False, index=True)
    role_id: Mapped[int] = mapped_column(ForeignKey('security_roles.id'), nullable=False, index=True)

    user: Mapped[UserModel] = relationship(back_populates='assignments')
    role: Mapped[RoleModel] = relationship()


class SessionModel(Base):
    __tablename__ = 'security_sessions'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('security_users.id'), nullable=False, index=True)
    session_token_hash: Mapped[str] = mapped_column(String(200), unique=True, nullable=False, index=True)
    ip_address: Mapped[str | None] = mapped_column(String(120), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


@dataclass(frozen=True)
class SessionUser:
    session_id: int
    user_id: int
    username: str
    display_name: str
    email: str | None
    status: str
    roles: list[str]
    permissions: list[str]
    expires_at: datetime


class SecurityStore:
    def __init__(self, database: str | Path) -> None:
        self.database = database
        self.engine = create_engine(self._engine_target(database), future=True)
        self.session_factory = sessionmaker(self.engine, expire_on_commit=False, future=True)

    def _engine_target(self, database: str | Path) -> str | URL:
        if isinstance(database, Path):
            return URL.create('sqlite', database=str(database.resolve()))
        if '://' in database:
            return database
        return URL.create('sqlite', database=str(Path(database).resolve()))

    def initialize(self) -> None:
        Base.metadata.create_all(self.engine)
        self._seed_system_security()

    def _seed_system_security(self) -> None:
        now = datetime.now(UTC)
        with self.session_factory() as session:
            permission_by_code: dict[str, PermissionModel] = {}
            for role_name, permission_codes in DEFAULT_ROLE_PERMISSIONS.items():
                for code in permission_codes:
                    if code in permission_by_code:
                        continue
                    permission = session.scalar(select(PermissionModel).where(PermissionModel.code == code))
                    if permission is None:
                        module = code.split('.', 1)[0]
                        permission = PermissionModel(
                            code=code,
                            description=f'{code} permission',
                            module=module,
                            created_at=now,
                            updated_at=now,
                        )
                        session.add(permission)
                        session.flush()
                    permission_by_code[code] = permission

            for role_name, permission_codes in DEFAULT_ROLE_PERMISSIONS.items():
                role = session.scalar(select(RoleModel).where(RoleModel.name == role_name))
                if role is None:
                    role = RoleModel(
                        name=role_name,
                        description=f'{role_name} system role',
                        is_system=1,
                        created_at=now,
                        updated_at=now,
                    )
                    session.add(role)
                    session.flush()
                existing_permission_ids = {
                    item.permission_id
                    for item in session.scalars(
                        select(RolePermissionModel).where(RolePermissionModel.role_id == role.id)
                    ).all()
                }
                for code in permission_codes:
                    permission_id = permission_by_code[code].id
                    if permission_id in existing_permission_ids:
                        continue
                    session.add(RolePermissionModel(role_id=role.id, permission_id=permission_id))
            session.commit()

    def count_users(self) -> int:
        self.initialize()
        with self.session_factory() as session:
            return len(session.scalars(select(UserModel.id)).all())

    def ensure_bootstrap_admin(
        self,
        *,
        username: str,
        display_name: str,
        email: str | None,
        password_hash: str,
    ) -> dict[str, Any]:
        self.initialize()
        now = datetime.now(UTC)
        with self.session_factory() as session:
            user = session.scalar(select(UserModel).where(UserModel.username == username))
            if user is None:
                user = UserModel(
                    username=username,
                    display_name=display_name,
                    email=email,
                    password_hash=password_hash,
                    status='active',
                    auth_source='local',
                    created_at=now,
                    updated_at=now,
                )
                session.add(user)
                session.flush()
            else:
                user.display_name = display_name
                user.email = email
                user.password_hash = password_hash
                user.status = 'active'
                user.updated_at = now

            admin_role = session.scalar(select(RoleModel).where(RoleModel.name == 'admin'))
            assert admin_role is not None
            assigned = session.scalar(
                select(UserRoleModel).where(UserRoleModel.user_id == user.id, UserRoleModel.role_id == admin_role.id)
            )
            if assigned is None:
                session.add(UserRoleModel(user_id=user.id, role_id=admin_role.id))
            session.commit()
            return self._serialize_user(session.get(UserModel, user.id))

    def get_user_by_username(self, username: str) -> dict[str, Any] | None:
        self.initialize()
        with self.session_factory() as session:
            user = session.scalar(select(UserModel).where(UserModel.username == username))
            return self._serialize_user(user) if user else None


    def get_auth_user(self, username: str) -> dict[str, Any] | None:
        self.initialize()
        with self.session_factory() as session:
            user = session.scalar(select(UserModel).where(UserModel.username == username))
            if user is None:
                return None
            payload = self._serialize_user(user)
            assert payload is not None
            payload['password_hash'] = user.password_hash
            return payload

    def get_user(self, user_id: int) -> dict[str, Any] | None:
        self.initialize()
        with self.session_factory() as session:
            user = session.get(UserModel, user_id)
            return self._serialize_user(user) if user else None

    def list_roles(self) -> list[dict[str, Any]]:
        self.initialize()
        with self.session_factory() as session:
            rows = session.scalars(select(RoleModel).order_by(RoleModel.name)).all()
            return [self._serialize_role(session, row) for row in rows]

    def list_users(self) -> list[dict[str, Any]]:
        self.initialize()
        with self.session_factory() as session:
            rows = session.scalars(select(UserModel).order_by(UserModel.id)).all()
            return [self._serialize_user(row) for row in rows]

    def create_user(
        self,
        *,
        username: str,
        display_name: str,
        email: str | None,
        password_hash: str,
        roles: list[str],
    ) -> dict[str, Any]:
        self.initialize()
        now = datetime.now(UTC)
        normalized_roles = self._normalize_roles(roles)
        with self.session_factory() as session:
            exists = session.scalar(select(UserModel).where(UserModel.username == username))
            if exists is not None:
                raise ValueError(f'user already exists: {username}')
            user = UserModel(
                username=username,
                display_name=display_name,
                email=email,
                password_hash=password_hash,
                status='active',
                auth_source='local',
                created_at=now,
                updated_at=now,
            )
            session.add(user)
            session.flush()
            self._replace_user_roles(session, user.id, normalized_roles)
            session.commit()
            return self._serialize_user(session.get(UserModel, user.id))

    def update_user(
        self,
        *,
        user_id: int,
        display_name: str | None = None,
        email: str | None = None,
        password_hash: str | None = None,
        status: str | None = None,
    ) -> dict[str, Any] | None:
        self.initialize()
        with self.session_factory() as session:
            user = session.get(UserModel, user_id)
            if user is None:
                return None
            if display_name is not None:
                user.display_name = display_name
            if email is not None:
                user.email = email
            if password_hash is not None:
                user.password_hash = password_hash
            if status is not None:
                user.status = status
            user.updated_at = datetime.now(UTC)
            session.commit()
            return self._serialize_user(session.get(UserModel, user.id))

    def set_user_roles(self, *, user_id: int, roles: list[str]) -> dict[str, Any] | None:
        self.initialize()
        normalized_roles = self._normalize_roles(roles)
        with self.session_factory() as session:
            user = session.get(UserModel, user_id)
            if user is None:
                return None
            self._replace_user_roles(session, user_id, normalized_roles)
            user.updated_at = datetime.now(UTC)
            session.commit()
            return self._serialize_user(session.get(UserModel, user.id))

    def create_session(
        self,
        *,
        user_id: int,
        session_token_hash: str,
        ttl_sec: int,
        ip_address: str | None,
        user_agent: str | None,
    ) -> dict[str, Any]:
        self.initialize()
        now = datetime.now(UTC)
        expires_at = now + timedelta(seconds=ttl_sec)
        with self.session_factory() as session:
            record = SessionModel(
                user_id=user_id,
                session_token_hash=session_token_hash,
                ip_address=ip_address,
                user_agent=user_agent,
                expires_at=expires_at,
                last_seen_at=now,
                revoked_at=None,
                created_at=now,
            )
            session.add(record)
            user = session.get(UserModel, user_id)
            assert user is not None
            user.last_login_at = now
            user.updated_at = now
            session.commit()
            return {
                'session_id': record.id,
                'expires_at': record.expires_at,
            }

    def get_session_user(self, *, session_token_hash: str) -> SessionUser | None:
        self.initialize()
        now = datetime.now(UTC)
        with self.session_factory() as session:
            record = session.scalar(select(SessionModel).where(SessionModel.session_token_hash == session_token_hash))
            if record is None or record.revoked_at is not None or _as_utc(record.expires_at) <= now:
                return None
            user = session.get(UserModel, record.user_id)
            if user is None or user.status != 'active':
                return None
            permissions = self._permissions_for_user(session, user.id)
            roles = self._roles_for_user(session, user.id)
            record.last_seen_at = now
            session.commit()
            return SessionUser(
                session_id=record.id,
                user_id=user.id,
                username=user.username,
                display_name=user.display_name,
                email=user.email,
                status=user.status,
                roles=roles,
                permissions=permissions,
                expires_at=_as_utc(record.expires_at),
            )

    def revoke_session(self, *, session_token_hash: str) -> None:
        self.initialize()
        with self.session_factory() as session:
            record = session.scalar(select(SessionModel).where(SessionModel.session_token_hash == session_token_hash))
            if record is None or record.revoked_at is not None:
                return
            record.revoked_at = datetime.now(UTC)
            session.commit()

    def revoke_user_sessions(self, *, user_id: int) -> None:
        self.initialize()
        now = datetime.now(UTC)
        with self.session_factory() as session:
            rows = session.scalars(select(SessionModel).where(SessionModel.user_id == user_id, SessionModel.revoked_at.is_(None))).all()
            for row in rows:
                row.revoked_at = now
            session.commit()

    def _normalize_roles(self, roles: list[str]) -> list[str]:
        normalized = []
        seen: set[str] = set()
        for role in roles:
            name = str(role).strip().lower()
            if not name or name in seen:
                continue
            seen.add(name)
            normalized.append(name)
        if not normalized:
            normalized.append('viewer')
        return normalized

    def _replace_user_roles(self, session, user_id: int, roles: list[str]) -> None:
        requested_roles = session.scalars(select(RoleModel).where(RoleModel.name.in_(roles))).all()
        found_names = {row.name for row in requested_roles}
        missing = [role for role in roles if role not in found_names]
        if missing:
            raise ValueError(f'unknown role(s): {", ".join(missing)}')
        existing = session.scalars(select(UserRoleModel).where(UserRoleModel.user_id == user_id)).all()
        for row in existing:
            session.delete(row)
        session.flush()
        for role in requested_roles:
            session.add(UserRoleModel(user_id=user_id, role_id=role.id))

    def _roles_for_user(self, session, user_id: int) -> list[str]:
        rows = session.scalars(select(UserRoleModel).where(UserRoleModel.user_id == user_id)).all()
        names = []
        for row in rows:
            role = session.get(RoleModel, row.role_id)
            if role is not None:
                names.append(role.name)
        return sorted(set(names))

    def _permissions_for_user(self, session, user_id: int) -> list[str]:
        codes: set[str] = set()
        for role_name in self._roles_for_user(session, user_id):
            role = session.scalar(select(RoleModel).where(RoleModel.name == role_name))
            if role is None:
                continue
            links = session.scalars(select(RolePermissionModel).where(RolePermissionModel.role_id == role.id)).all()
            for link in links:
                permission = session.get(PermissionModel, link.permission_id)
                if permission is not None:
                    codes.add(permission.code)
        return sorted(codes)

    def _serialize_user(self, user: UserModel | None) -> dict[str, Any] | None:
        if user is None:
            return None
        with self.session_factory() as session:
            user_row = session.get(UserModel, user.id)
            assert user_row is not None
            return {
                'id': user_row.id,
                'username': user_row.username,
                'display_name': user_row.display_name,
                'email': user_row.email,
                'status': user_row.status,
                'auth_source': user_row.auth_source,
                'last_login_at': user_row.last_login_at.isoformat() if user_row.last_login_at else None,
                'created_at': user_row.created_at.isoformat(),
                'updated_at': user_row.updated_at.isoformat(),
                'roles': self._roles_for_user(session, user_row.id),
                'permissions': self._permissions_for_user(session, user_row.id),
            }

    def _serialize_role(self, session, role: RoleModel) -> dict[str, Any]:
        links = session.scalars(select(RolePermissionModel).where(RolePermissionModel.role_id == role.id)).all()
        codes: list[str] = []
        for link in links:
            permission = session.get(PermissionModel, link.permission_id)
            if permission is not None:
                codes.append(permission.code)
        return {
            'id': role.id,
            'name': role.name,
            'description': role.description,
            'is_system': bool(role.is_system),
            'permissions': sorted(set(codes)),
            'created_at': role.created_at.isoformat(),
            'updated_at': role.updated_at.isoformat(),
        }


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
