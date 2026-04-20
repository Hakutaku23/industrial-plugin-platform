import json
import math
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    event,
    func,
    or_,
    select,
)
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker

from platform_api.services.package_storage import PackageRecord


class Base(DeclarativeBase):
    pass


class PluginPackageModel(Base):
    __tablename__ = "plugin_packages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="validated")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    versions: Mapped[list["PluginVersionModel"]] = relationship(back_populates="package")


class PluginVersionModel(Base):
    __tablename__ = "plugin_versions"
    __table_args__ = (
        UniqueConstraint("package_id", "version", name="uq_plugin_versions_package_version"),
        UniqueConstraint("digest", name="uq_plugin_versions_digest"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    package_id: Mapped[int] = mapped_column(ForeignKey("plugin_packages.id"), nullable=False, index=True)
    version: Mapped[str] = mapped_column(String(80), nullable=False)
    digest: Mapped[str] = mapped_column(String(128), nullable=False)
    package_path: Mapped[str] = mapped_column(Text, nullable=False)
    manifest_json: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="validated")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    package: Mapped[PluginPackageModel] = relationship(back_populates="versions")


class AuditEventModel(Base):
    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_type: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    actor: Mapped[str] = mapped_column(String(120), nullable=False)
    target_type: Mapped[str] = mapped_column(String(80), nullable=False)
    target_id: Mapped[str] = mapped_column(String(120), nullable=False)
    details_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PluginRunModel(Base):
    __tablename__ = "plugin_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(120), unique=True, nullable=False, index=True)
    package_id: Mapped[int] = mapped_column(ForeignKey("plugin_packages.id"), nullable=False, index=True)
    version_id: Mapped[int] = mapped_column(ForeignKey("plugin_versions.id"), nullable=False, index=True)
    instance_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    trigger_type: Mapped[str] = mapped_column(String(60), nullable=False)
    environment: Mapped[str] = mapped_column(String(60), nullable=False)
    status: Mapped[str] = mapped_column(String(60), nullable=False)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    inputs_json: Mapped[str] = mapped_column(Text, nullable=False)
    outputs_json: Mapped[str] = mapped_column(Text, nullable=False)
    metrics_json: Mapped[str] = mapped_column(Text, nullable=False)
    error_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class RunLogModel(Base):
    __tablename__ = "run_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(60), nullable=False)
    level: Mapped[str] = mapped_column(String(20), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class DataSourceModel(Base):
    __tablename__ = "data_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False, index=True)
    connector_type: Mapped[str] = mapped_column(String(40), nullable=False)
    config_json: Mapped[str] = mapped_column(Text, nullable=False)
    read_enabled: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    write_enabled: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="configured")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PluginInstanceModel(Base):
    __tablename__ = "plugin_instances"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False, index=True)
    package_id: Mapped[int] = mapped_column(ForeignKey("plugin_packages.id"), nullable=False, index=True)
    version_id: Mapped[int] = mapped_column(ForeignKey("plugin_versions.id"), nullable=False, index=True)
    input_bindings_json: Mapped[str] = mapped_column(Text, nullable=False)
    output_bindings_json: Mapped[str] = mapped_column(Text, nullable=False)
    config_json: Mapped[str] = mapped_column(Text, nullable=False)
    writeback_enabled: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    schedule_enabled: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    schedule_interval_sec: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    last_scheduled_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_scheduled_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="configured")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class WritebackRecordModel(Base):
    __tablename__ = "writeback_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    output_name: Mapped[str] = mapped_column(String(120), nullable=False)
    data_source_id: Mapped[int] = mapped_column(ForeignKey("data_sources.id"), nullable=False)
    target_tag: Mapped[str] = mapped_column(String(240), nullable=False)
    value_json: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    dry_run: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


@dataclass(frozen=True)
class RegisteredPluginVersion:
    package_id: int
    version_id: int
    audit_event_id: int
    name: str
    version: str
    status: str


@dataclass(frozen=True)
class RegisteredDataSource:
    id: int
    name: str
    connector_type: str
    status: str


@dataclass(frozen=True)
class RegisteredPluginInstance:
    id: int
    name: str
    status: str


@dataclass(frozen=True)
class RecordedRun:
    id: int
    run_id: str
    status: str


class MetadataStore:
    def __init__(self, database: str | Path) -> None:
        self.database = database
        self.sqlite_path = self._sqlite_path(database)
        if self.sqlite_path is not None:
            self.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        self.engine = create_engine(self._engine_target(database), future=True)
        if self._is_sqlite(database):
            self._configure_local_sqlite()
        self.session_factory = sessionmaker(self.engine, expire_on_commit=False, future=True)

    def initialize(self) -> None:
        Base.metadata.create_all(self.engine)
        if self._is_sqlite(self.database):
            self._ensure_local_schema()

    def _engine_target(self, database: str | Path) -> str | URL:
        if isinstance(database, Path):
            return URL.create("sqlite", database=str(database.resolve()))
        if "://" in database:
            return database
        return URL.create("sqlite", database=str(Path(database).resolve()))

    def _is_sqlite(self, database: str | Path) -> bool:
        if isinstance(database, Path):
            return True
        if "://" not in database:
            return True
        return make_url(database).get_backend_name() == "sqlite"

    def _sqlite_path(self, database: str | Path) -> Path | None:
        if isinstance(database, Path):
            return database.resolve()
        if "://" not in database:
            return Path(database).resolve()
        url = make_url(database)
        if url.get_backend_name() != "sqlite":
            return None
        if not url.database:
            return None
        return Path(url.database).resolve()

    def _configure_local_sqlite(self) -> None:
        @event.listens_for(self.engine, "connect")
        def set_local_sqlite_pragmas(dbapi_connection: object, connection_record: object) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=OFF")
            cursor.execute("PRAGMA synchronous=OFF")
            cursor.close()

    def _ensure_local_schema(self) -> None:
        instance_columns = {
            "schedule_enabled": "schedule_enabled INTEGER NOT NULL DEFAULT 0",
            "schedule_interval_sec": "schedule_interval_sec INTEGER NOT NULL DEFAULT 30",
            "last_scheduled_run_at": "last_scheduled_run_at DATETIME",
            "next_scheduled_run_at": "next_scheduled_run_at DATETIME",
        }
        with self.engine.begin() as connection:
            existing = {
                row[1]
                for row in connection.exec_driver_sql("PRAGMA table_info(plugin_instances)").all()
            }
            for name, ddl in instance_columns.items():
                if name not in existing:
                    connection.exec_driver_sql(f"ALTER TABLE plugin_instances ADD COLUMN {ddl}")

            run_columns = {
                "instance_id": "instance_id INTEGER",
            }
            existing_runs = {
                row[1]
                for row in connection.exec_driver_sql("PRAGMA table_info(plugin_runs)").all()
            }
            for name, ddl in run_columns.items():
                if name not in existing_runs:
                    connection.exec_driver_sql(f"ALTER TABLE plugin_runs ADD COLUMN {ddl}")

    # ---------- package / version / audit ----------
    def register_package_upload(
        self,
        record: PackageRecord,
        *,
        actor: str = "local-dev",
    ) -> RegisteredPluginVersion:
        self.initialize()
        now = datetime.now(UTC)
        manifest = record.manifest
        manifest_json = json.dumps(manifest.model_dump(by_alias=True), ensure_ascii=False, sort_keys=True)

        with self.session_factory() as session:
            package = self._get_or_create_package(session, record, now)
            package.display_name = manifest.metadata.display_name
            package.description = manifest.metadata.description
            package.status = "validated"
            package.updated_at = now

            version = session.scalar(
                select(PluginVersionModel).where(
                    PluginVersionModel.package_id == package.id,
                    PluginVersionModel.version == manifest.metadata.version,
                )
            )
            if version is None:
                version = PluginVersionModel(
                    package_id=package.id,
                    version=manifest.metadata.version,
                    digest=record.digest,
                    package_path=str(record.package_dir),
                    manifest_json=manifest_json,
                    status="validated",
                    created_at=now,
                    updated_at=now,
                )
                session.add(version)
                session.flush()
            else:
                version.digest = record.digest
                version.package_path = str(record.package_dir)
                version.manifest_json = manifest_json
                version.status = "validated"
                version.updated_at = now

            audit = AuditEventModel(
                event_type="plugin.package.uploaded",
                actor=actor,
                target_type="plugin_version",
                target_id=str(version.id),
                details_json=json.dumps(
                    {
                        "package": manifest.metadata.name,
                        "version": manifest.metadata.version,
                        "digest": record.digest,
                        "package_path": str(record.package_dir),
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                created_at=now,
            )
            session.add(audit)
            session.commit()

            return RegisteredPluginVersion(
                package_id=package.id,
                version_id=version.id,
                audit_event_id=audit.id,
                name=manifest.metadata.name,
                version=manifest.metadata.version,
                status=version.status,
            )

    def list_audit_events(self) -> list[dict[str, Any]]:
        self.initialize()
        with self.session_factory() as session:
            rows = session.scalars(select(AuditEventModel).order_by(AuditEventModel.id)).all()
            return [
                {
                    "id": row.id,
                    "event_type": row.event_type,
                    "actor": row.actor,
                    "target_type": row.target_type,
                    "target_id": row.target_id,
                    "details": json.loads(row.details_json),
                    "created_at": row.created_at.isoformat(),
                }
                for row in rows
            ]

    def list_plugin_packages(self) -> list[dict[str, Any]]:
        self.initialize()
        with self.session_factory() as session:
            rows = session.execute(
                select(
                    PluginPackageModel,
                    func.count(PluginVersionModel.id).label("version_count"),
                    func.max(PluginVersionModel.updated_at).label("latest_updated_at"),
                )
                .join(PluginVersionModel, PluginVersionModel.package_id == PluginPackageModel.id, isouter=True)
                .group_by(PluginPackageModel.id)
                .order_by(PluginPackageModel.updated_at.desc(), PluginPackageModel.id.desc())
            ).all()

            packages: list[dict[str, Any]] = []
            for package, version_count, latest_updated_at in rows:
                latest_version = session.scalar(
                    select(PluginVersionModel)
                    .where(PluginVersionModel.package_id == package.id)
                    .order_by(PluginVersionModel.updated_at.desc(), PluginVersionModel.id.desc())
                    .limit(1)
                )
                packages.append(
                    {
                        "id": package.id,
                        "name": package.name,
                        "display_name": package.display_name,
                        "description": package.description,
                        "status": package.status,
                        "version_count": int(version_count or 0),
                        "latest_version": latest_version.version if latest_version else None,
                        "latest_version_id": latest_version.id if latest_version else None,
                        "latest_digest": latest_version.digest if latest_version else None,
                        "created_at": package.created_at.isoformat(),
                        "updated_at": package.updated_at.isoformat(),
                        "latest_updated_at": latest_updated_at.isoformat() if latest_updated_at else None,
                    }
                )
            return packages

    def list_plugin_versions(self, package_name: str) -> list[dict[str, Any]] | None:
        self.initialize()
        with self.session_factory() as session:
            package = session.scalar(
                select(PluginPackageModel).where(PluginPackageModel.name == package_name)
            )
            if package is None:
                return None

            versions = session.scalars(
                select(PluginVersionModel)
                .where(PluginVersionModel.package_id == package.id)
                .order_by(PluginVersionModel.updated_at.desc(), PluginVersionModel.id.desc())
            ).all()
            return [
                {
                    "id": version.id,
                    "package_id": version.package_id,
                    "package_name": package.name,
                    "version": version.version,
                    "digest": version.digest,
                    "package_path": version.package_path,
                    "status": version.status,
                    "manifest": json.loads(version.manifest_json),
                    "created_at": version.created_at.isoformat(),
                    "updated_at": version.updated_at.isoformat(),
                }
                for version in versions
            ]

    def delete_plugin_package(self, package_name: str) -> bool:
        self.initialize()
        storage_roots: set[Path] = set()
        with self.session_factory() as session:
            package = session.scalar(
                select(PluginPackageModel).where(PluginPackageModel.name == package_name)
            )
            if package is None:
                return False

            versions = session.scalars(
                select(PluginVersionModel).where(PluginVersionModel.package_id == package.id)
            ).all()
            version_ids = [version.id for version in versions]
            for version in versions:
                try:
                    path = Path(version.package_path).resolve()
                    if len(path.parents) >= 2:
                        storage_roots.add(path.parents[1])
                    else:
                        storage_roots.add(path)
                except OSError:
                    pass

            instances = session.scalars(
                select(PluginInstanceModel).where(PluginInstanceModel.package_id == package.id)
            ).all()
            instance_ids = [instance.id for instance in instances]

            runs = session.scalars(
                select(PluginRunModel).where(PluginRunModel.package_id == package.id)
            ).all()
            run_ids = [run.run_id for run in runs]

            audit_rows = session.scalars(select(AuditEventModel)).all()
            audit_targets = {
                ('plugin_package', str(package.id)),
                ('plugin_package', package.name),
            }
            audit_targets.update(('plugin_version', str(version_id)) for version_id in version_ids)
            audit_targets.update(('plugin_instance', str(instance_id)) for instance_id in instance_ids)
            audit_targets.update(('plugin_run', run_id) for run_id in run_ids)

            for audit in audit_rows:
                if (audit.target_type, audit.target_id) in audit_targets:
                    session.delete(audit)

            if run_ids:
                for row in session.scalars(select(RunLogModel).where(RunLogModel.run_id.in_(run_ids))).all():
                    session.delete(row)
                for row in session.scalars(select(WritebackRecordModel).where(WritebackRecordModel.run_id.in_(run_ids))).all():
                    session.delete(row)

            for run in runs:
                session.delete(run)
            for instance in instances:
                session.delete(instance)
            for version in versions:
                session.delete(version)

            session.delete(package)
            session.add(
                AuditEventModel(
                    event_type='plugin.package.deleted',
                    actor='local-dev',
                    target_type='plugin_package',
                    target_id=package_name,
                    details_json=json.dumps({'package': package_name}, ensure_ascii=False, sort_keys=True),
                    created_at=datetime.now(UTC),
                )
            )
            session.commit()

        for storage_root in storage_roots:
            if storage_root.exists():
                shutil.rmtree(storage_root, ignore_errors=True)

        return True

    def get_plugin_version(self, package_name: str, version: str) -> dict[str, Any] | None:
        self.initialize()
        with self.session_factory() as session:
            row = session.execute(
                select(PluginPackageModel, PluginVersionModel)
                .join(PluginVersionModel, PluginVersionModel.package_id == PluginPackageModel.id)
                .where(
                    PluginPackageModel.name == package_name,
                    PluginVersionModel.version == version,
                )
            ).first()
            if row is None:
                return None

            package, plugin_version = row
            return {
                "id": plugin_version.id,
                "package_id": package.id,
                "package_name": package.name,
                "version": plugin_version.version,
                "digest": plugin_version.digest,
                "package_path": plugin_version.package_path,
                "status": plugin_version.status,
                "manifest": json.loads(plugin_version.manifest_json),
                "created_at": plugin_version.created_at.isoformat(),
                "updated_at": plugin_version.updated_at.isoformat(),
            }

    # ---------- run / logs ----------
    def record_plugin_run(
        self,
        *,
        run_id: str,
        package_id: int,
        version_id: int,
        trigger_type: str,
        environment: str,
        status: str,
        inputs: dict[str, Any],
        outputs: dict[str, Any],
        metrics: dict[str, Any],
        logs: list[dict[str, str]],
        instance_id: int | None = None,
        error: dict[str, Any] | None = None,
        attempt: int = 1,
        started_at: datetime | None = None,
        finished_at: datetime | None = None,
    ) -> RecordedRun:
        self.initialize()
        now = datetime.now(UTC)
        started = started_at or now
        finished = finished_at or now

        with self.session_factory() as session:
            run = PluginRunModel(
                run_id=run_id,
                package_id=package_id,
                version_id=version_id,
                instance_id=instance_id,
                trigger_type=trigger_type,
                environment=environment,
                status=status,
                attempt=attempt,
                inputs_json=json.dumps(inputs, ensure_ascii=False, sort_keys=True),
                outputs_json=json.dumps(outputs, ensure_ascii=False, sort_keys=True),
                metrics_json=json.dumps(metrics, ensure_ascii=False, sort_keys=True),
                error_json=json.dumps(error or {}, ensure_ascii=False, sort_keys=True),
                created_at=now,
                started_at=started,
                finished_at=finished,
            )
            session.add(run)
            session.flush()

            for log in logs:
                session.add(
                    RunLogModel(
                        run_id=run_id,
                        source=log.get("source", "runner"),
                        level=log.get("level", "INFO"),
                        message=log.get("message", ""),
                        created_at=now,
                    )
                )

            session.add(
                AuditEventModel(
                    event_type="plugin.run.completed",
                    actor="local-dev",
                    target_type="plugin_run",
                    target_id=run_id,
                    details_json=json.dumps(
                        {
                            "status": status,
                            "package_id": package_id,
                            "version_id": version_id,
                        },
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                    created_at=now,
                )
            )
            session.commit()

            return RecordedRun(id=run.id, run_id=run.run_id, status=run.status)

    def list_plugin_runs(
        self,
        package_name: str | None = None,
        instance_id: int | None = None,
    ) -> list[dict[str, Any]]:
        self.initialize()
        with self.session_factory() as session:
            statement = (
                select(PluginRunModel, PluginPackageModel, PluginVersionModel)
                .join(PluginPackageModel, PluginPackageModel.id == PluginRunModel.package_id)
                .join(PluginVersionModel, PluginVersionModel.id == PluginRunModel.version_id)
                .order_by(PluginRunModel.created_at.desc(), PluginRunModel.id.desc())
            )
            if package_name:
                statement = statement.where(PluginPackageModel.name == package_name)
            if instance_id is not None:
                statement = statement.where(PluginRunModel.instance_id == instance_id)

            rows = session.execute(statement).all()
            return [
                {
                    "id": run.id,
                    "run_id": run.run_id,
                    "package_id": run.package_id,
                    "version_id": run.version_id,
                    "instance_id": run.instance_id,
                    "package_name": package.name,
                    "version": version.version,
                    "trigger_type": run.trigger_type,
                    "environment": run.environment,
                    "status": run.status,
                    "attempt": run.attempt,
                    "inputs": json.loads(run.inputs_json),
                    "outputs": json.loads(run.outputs_json),
                    "metrics": json.loads(run.metrics_json),
                    "error": json.loads(run.error_json),
                    "created_at": run.created_at.isoformat(),
                    "started_at": run.started_at.isoformat(),
                    "finished_at": run.finished_at.isoformat(),
                }
                for run, package, version in rows
            ]

    def list_run_logs(self, run_id: str) -> list[dict[str, Any]]:
        self.initialize()
        with self.session_factory() as session:
            rows = session.scalars(
                select(RunLogModel).where(RunLogModel.run_id == run_id).order_by(RunLogModel.id)
            ).all()
            return [
                {
                    "id": row.id,
                    "run_id": row.run_id,
                    "source": row.source,
                    "level": row.level,
                    "message": row.message,
                    "created_at": row.created_at.isoformat(),
                }
                for row in rows
            ]

    # ---------- data sources ----------
    def create_data_source(
        self,
        *,
        name: str,
        connector_type: str,
        config: dict[str, Any],
        read_enabled: bool,
        write_enabled: bool,
    ) -> RegisteredDataSource:
        self.initialize()
        now = datetime.now(UTC)
        with self.session_factory() as session:
            existing = session.scalar(select(DataSourceModel).where(DataSourceModel.name == name))
            if existing is not None:
                raise ValueError(f"data source already exists: {name}")

            data_source = DataSourceModel(
                name=name,
                connector_type=connector_type,
                config_json=json.dumps(config, ensure_ascii=False, sort_keys=True),
                read_enabled=1 if read_enabled else 0,
                write_enabled=1 if write_enabled else 0,
                status="configured",
                created_at=now,
                updated_at=now,
            )
            session.add(data_source)
            session.flush()

            session.add(
                AuditEventModel(
                    event_type="data_source.created",
                    actor="local-dev",
                    target_type="data_source",
                    target_id=str(data_source.id),
                    details_json=json.dumps(
                        {"name": name, "connector_type": connector_type},
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                    created_at=now,
                )
            )
            session.commit()
            return RegisteredDataSource(
                id=data_source.id,
                name=data_source.name,
                connector_type=data_source.connector_type,
                status=data_source.status,
            )

    def update_data_source(
        self,
        *,
        data_source_id: int,
        name: str,
        connector_type: str,
        config: dict[str, Any],
        read_enabled: bool,
        write_enabled: bool,
    ) -> RegisteredDataSource | None:
        self.initialize()
        now = datetime.now(UTC)
        with self.session_factory() as session:
            data_source = session.get(DataSourceModel, data_source_id)
            if data_source is None:
                return None

            duplicate = session.scalar(
                select(DataSourceModel).where(
                    DataSourceModel.name == name,
                    DataSourceModel.id != data_source_id,
                )
            )
            if duplicate is not None:
                raise ValueError(f"data source already exists: {name}")

            data_source.name = name
            data_source.connector_type = connector_type
            data_source.config_json = json.dumps(config, ensure_ascii=False, sort_keys=True)
            data_source.read_enabled = 1 if read_enabled else 0
            data_source.write_enabled = 1 if write_enabled else 0
            data_source.status = "configured"
            data_source.updated_at = now

            session.add(
                AuditEventModel(
                    event_type="data_source.updated",
                    actor="local-dev",
                    target_type="data_source",
                    target_id=str(data_source.id),
                    details_json=json.dumps(
                        {"name": name, "connector_type": connector_type},
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                    created_at=now,
                )
            )
            session.commit()
            return RegisteredDataSource(
                id=data_source.id,
                name=data_source.name,
                connector_type=data_source.connector_type,
                status=data_source.status,
            )

    def upsert_data_source(
        self,
        *,
        name: str,
        connector_type: str,
        config: dict[str, Any],
        read_enabled: bool,
        write_enabled: bool,
    ) -> RegisteredDataSource:
        self.initialize()
        now = datetime.now(UTC)
        with self.session_factory() as session:
            data_source = session.scalar(select(DataSourceModel).where(DataSourceModel.name == name))
            if data_source is None:
                data_source = DataSourceModel(
                    name=name,
                    connector_type=connector_type,
                    config_json=json.dumps(config, ensure_ascii=False, sort_keys=True),
                    read_enabled=1 if read_enabled else 0,
                    write_enabled=1 if write_enabled else 0,
                    status="configured",
                    created_at=now,
                    updated_at=now,
                )
                session.add(data_source)
                session.flush()
            else:
                data_source.connector_type = connector_type
                data_source.config_json = json.dumps(config, ensure_ascii=False, sort_keys=True)
                data_source.read_enabled = 1 if read_enabled else 0
                data_source.write_enabled = 1 if write_enabled else 0
                data_source.status = "configured"
                data_source.updated_at = now

            session.add(
                AuditEventModel(
                    event_type="data_source.configured",
                    actor="local-dev",
                    target_type="data_source",
                    target_id=str(data_source.id),
                    details_json=json.dumps(
                        {"name": name, "connector_type": connector_type},
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                    created_at=now,
                )
            )
            session.commit()
            return RegisteredDataSource(
                id=data_source.id,
                name=data_source.name,
                connector_type=data_source.connector_type,
                status=data_source.status,
            )

    def list_data_sources(self) -> list[dict[str, Any]]:
        self.initialize()
        with self.session_factory() as session:
            rows = session.scalars(select(DataSourceModel).order_by(DataSourceModel.id)).all()
            return [self._data_source_to_dict(row) for row in rows]

    def delete_data_source(self, data_source_id: int) -> bool:
        self.initialize()
        with self.session_factory() as session:
            row = session.get(DataSourceModel, data_source_id)
            if row is None:
                return False

            now = datetime.now(UTC)
            session.delete(row)
            session.add(
                AuditEventModel(
                    event_type="data_source.deleted",
                    actor="local-dev",
                    target_type="data_source",
                    target_id=str(data_source_id),
                    details_json=json.dumps({"id": data_source_id}, ensure_ascii=False, sort_keys=True),
                    created_at=now,
                )
            )
            session.commit()
            return True

    def get_data_source(self, data_source_id: int) -> dict[str, Any] | None:
        self.initialize()
        with self.session_factory() as session:
            row = session.get(DataSourceModel, data_source_id)
            return self._data_source_to_dict(row) if row else None

    def update_data_source_config(self, data_source_id: int, config: dict[str, Any]) -> None:
        self.initialize()
        with self.session_factory() as session:
            row = session.get(DataSourceModel, data_source_id)
            if row is None:
                return
            row.config_json = json.dumps(config, ensure_ascii=False, sort_keys=True)
            row.updated_at = datetime.now(UTC)
            session.commit()

    # ---------- instances ----------
    def upsert_plugin_instance(
        self,
        *,
        name: str,
        package_name: str,
        version: str,
        input_bindings: list[dict[str, Any]],
        output_bindings: list[dict[str, Any]],
        config: dict[str, Any],
        writeback_enabled: bool,
        schedule_enabled: bool = False,
        schedule_interval_sec: int = 30,
    ) -> RegisteredPluginInstance | None:
        self.initialize()
        now = datetime.now(UTC)
        with self.session_factory() as session:
            version_row = session.execute(
                select(PluginPackageModel, PluginVersionModel)
                .join(PluginVersionModel, PluginVersionModel.package_id == PluginPackageModel.id)
                .where(
                    PluginPackageModel.name == package_name,
                    PluginVersionModel.version == version,
                )
            ).first()
            if version_row is None:
                return None

            package, plugin_version = version_row
            normalized_interval = self._normalize_schedule_interval(schedule_interval_sec)
            instance = session.scalar(select(PluginInstanceModel).where(PluginInstanceModel.name == name))
            if instance is None:
                instance = PluginInstanceModel(
                    name=name,
                    package_id=package.id,
                    version_id=plugin_version.id,
                    input_bindings_json=json.dumps(input_bindings, ensure_ascii=False, sort_keys=True),
                    output_bindings_json=json.dumps(output_bindings, ensure_ascii=False, sort_keys=True),
                    config_json=json.dumps(config, ensure_ascii=False, sort_keys=True),
                    writeback_enabled=1 if writeback_enabled else 0,
                    schedule_enabled=1 if schedule_enabled else 0,
                    schedule_interval_sec=normalized_interval,
                    next_scheduled_run_at=self._next_schedule_time(now, schedule_enabled, normalized_interval),
                    status="scheduled" if schedule_enabled else "configured",
                    created_at=now,
                    updated_at=now,
                )
                session.add(instance)
                session.flush()
            else:
                instance.package_id = package.id
                instance.version_id = plugin_version.id
                instance.input_bindings_json = json.dumps(input_bindings, ensure_ascii=False, sort_keys=True)
                instance.output_bindings_json = json.dumps(output_bindings, ensure_ascii=False, sort_keys=True)
                instance.config_json = json.dumps(config, ensure_ascii=False, sort_keys=True)
                instance.writeback_enabled = 1 if writeback_enabled else 0
                instance.schedule_enabled = 1 if schedule_enabled else 0
                instance.schedule_interval_sec = normalized_interval
                instance.next_scheduled_run_at = self._next_schedule_time(now, schedule_enabled, normalized_interval)
                instance.status = "scheduled" if schedule_enabled else "configured"
                instance.updated_at = now

            session.add(
                AuditEventModel(
                    event_type="plugin.instance.configured",
                    actor="local-dev",
                    target_type="plugin_instance",
                    target_id=str(instance.id),
                    details_json=json.dumps(
                        {"name": name, "package": package_name, "version": version},
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                    created_at=now,
                )
            )
            session.commit()
            return RegisteredPluginInstance(id=instance.id, name=instance.name, status=instance.status)

    def update_plugin_instance(
        self,
        *,
        instance_id: int,
        name: str,
        package_name: str,
        version: str,
        input_bindings: list[dict[str, Any]],
        output_bindings: list[dict[str, Any]],
        config: dict[str, Any],
        writeback_enabled: bool,
        schedule_enabled: bool = False,
        schedule_interval_sec: int = 30,
    ) -> RegisteredPluginInstance | None:
        self.initialize()
        now = datetime.now(UTC)
        with self.session_factory() as session:
            instance = session.get(PluginInstanceModel, instance_id)
            if instance is None:
                return None

            version_row = session.execute(
                select(PluginPackageModel, PluginVersionModel)
                .join(PluginVersionModel, PluginVersionModel.package_id == PluginPackageModel.id)
                .where(
                    PluginPackageModel.name == package_name,
                    PluginVersionModel.version == version,
                )
            ).first()
            if version_row is None:
                return None

            package, plugin_version = version_row
            normalized_interval = self._normalize_schedule_interval(schedule_interval_sec)
            instance.name = name
            instance.package_id = package.id
            instance.version_id = plugin_version.id
            instance.input_bindings_json = json.dumps(input_bindings, ensure_ascii=False, sort_keys=True)
            instance.output_bindings_json = json.dumps(output_bindings, ensure_ascii=False, sort_keys=True)
            instance.config_json = json.dumps(config, ensure_ascii=False, sort_keys=True)
            instance.writeback_enabled = 1 if writeback_enabled else 0
            instance.schedule_enabled = 1 if schedule_enabled else 0
            instance.schedule_interval_sec = normalized_interval
            instance.next_scheduled_run_at = self._next_schedule_time(now, schedule_enabled, normalized_interval)
            instance.status = "scheduled" if schedule_enabled else "configured"
            instance.updated_at = now

            session.add(
                AuditEventModel(
                    event_type="plugin.instance.updated",
                    actor="local-dev",
                    target_type="plugin_instance",
                    target_id=str(instance.id),
                    details_json=json.dumps(
                        {"name": name, "package": package_name, "version": version},
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                    created_at=now,
                )
            )
            session.commit()
            return RegisteredPluginInstance(id=instance.id, name=instance.name, status=instance.status)

    def list_plugin_instances(self) -> list[dict[str, Any]]:
        self.initialize()
        with self.session_factory() as session:
            rows = session.execute(
                select(PluginInstanceModel, PluginPackageModel, PluginVersionModel)
                .join(PluginPackageModel, PluginPackageModel.id == PluginInstanceModel.package_id)
                .join(PluginVersionModel, PluginVersionModel.id == PluginInstanceModel.version_id)
                .order_by(PluginInstanceModel.id)
            ).all()
            return [
                self._plugin_instance_to_dict(instance, package, version)
                for instance, package, version in rows
            ]

    def get_plugin_instance(self, instance_id: int) -> dict[str, Any] | None:
        self.initialize()
        with self.session_factory() as session:
            row = session.execute(
                select(PluginInstanceModel, PluginPackageModel, PluginVersionModel)
                .join(PluginPackageModel, PluginPackageModel.id == PluginInstanceModel.package_id)
                .join(PluginVersionModel, PluginVersionModel.id == PluginInstanceModel.version_id)
                .where(PluginInstanceModel.id == instance_id)
            ).first()
            if row is None:
                return None
            instance, package, version = row
            return self._plugin_instance_to_dict(instance, package, version)

    def delete_plugin_instance(self, instance_id: int) -> bool:
        self.initialize()
        with self.session_factory() as session:
            row = session.get(PluginInstanceModel, instance_id)
            if row is None:
                return False

            now = datetime.now(UTC)
            session.delete(row)
            session.add(
                AuditEventModel(
                    event_type="plugin.instance.deleted",
                    actor="local-dev",
                    target_type="plugin_instance",
                    target_id=str(instance_id),
                    details_json=json.dumps({"id": instance_id}, ensure_ascii=False, sort_keys=True),
                    created_at=now,
                )
            )
            session.commit()
            return True

    def set_plugin_instance_schedule(
        self,
        *,
        instance_id: int,
        enabled: bool,
        interval_sec: int | None = None,
    ) -> dict[str, Any] | None:
        self.initialize()
        now = datetime.now(UTC)
        with self.session_factory() as session:
            row = session.get(PluginInstanceModel, instance_id)
            if row is None:
                return None

            if interval_sec is not None:
                row.schedule_interval_sec = self._normalize_schedule_interval(interval_sec)
            row.schedule_enabled = 1 if enabled else 0
            row.next_scheduled_run_at = self._next_schedule_time(now, enabled, row.schedule_interval_sec)
            row.status = "scheduled" if enabled else "stopped"
            row.updated_at = now
            session.add(
                AuditEventModel(
                    event_type="plugin.instance.schedule_updated",
                    actor="local-dev",
                    target_type="plugin_instance",
                    target_id=str(instance_id),
                    details_json=json.dumps(
                        {
                            "enabled": enabled,
                            "interval_sec": row.schedule_interval_sec,
                        },
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                    created_at=now,
                )
            )
            session.commit()
            refreshed = session.execute(
                select(PluginInstanceModel, PluginPackageModel, PluginVersionModel)
                .join(PluginPackageModel, PluginPackageModel.id == PluginInstanceModel.package_id)
                .join(PluginVersionModel, PluginVersionModel.id == PluginInstanceModel.version_id)
                .where(PluginInstanceModel.id == instance_id)
            ).one()
            instance, package, version = refreshed
            return self._plugin_instance_to_dict(instance, package, version)

    def claim_due_scheduled_instances(self, *, now: datetime, limit: int = 10) -> list[dict[str, Any]]:
        self.initialize()
        with self.session_factory() as session:
            rows = session.scalars(
                select(PluginInstanceModel)
                .where(
                    PluginInstanceModel.schedule_enabled == 1,
                    PluginInstanceModel.status != "running",
                    or_(
                        PluginInstanceModel.next_scheduled_run_at.is_(None),
                        PluginInstanceModel.next_scheduled_run_at <= now,
                    ),
                )
                .order_by(PluginInstanceModel.next_scheduled_run_at, PluginInstanceModel.id)
                .limit(limit)
            ).all()
            claimed: list[dict[str, Any]] = []
            for row in rows:
                row.status = "running"
                row.updated_at = now
                claimed.append(
                    {
                        "id": row.id,
                        "name": row.name,
                        "schedule_interval_sec": row.schedule_interval_sec,
                        "scheduled_at": row.next_scheduled_run_at.isoformat() if row.next_scheduled_run_at else None,
                    }
                )
            session.commit()
            return claimed

    def finish_scheduled_instance_run(self, *, instance_id: int, finished_at: datetime) -> None:
        self.initialize()
        with self.session_factory() as session:
            row = session.get(PluginInstanceModel, instance_id)
            if row is None:
                return

            interval = self._normalize_schedule_interval(row.schedule_interval_sec)
            previous_due = row.next_scheduled_run_at
            row.last_scheduled_run_at = previous_due or finished_at
            if row.schedule_enabled:
                row.next_scheduled_run_at = self._advance_schedule_time(
                    previous_due=previous_due,
                    reference=finished_at,
                    interval_sec=interval,
                )
                row.status = "scheduled"
            else:
                row.next_scheduled_run_at = None
                row.status = "stopped"
            row.updated_at = finished_at
            session.commit()

    def record_audit_event(
        self,
        *,
        event_type: str,
        target_type: str,
        target_id: str,
        details: dict[str, Any],
        actor: str = "local-dev",
    ) -> None:
        self.initialize()
        with self.session_factory() as session:
            session.add(
                AuditEventModel(
                    event_type=event_type,
                    actor=actor,
                    target_type=target_type,
                    target_id=target_id,
                    details_json=json.dumps(details, ensure_ascii=False, sort_keys=True),
                    created_at=datetime.now(UTC),
                )
            )
            session.commit()

    def record_writeback(
        self,
        *,
        run_id: str,
        output_name: str,
        data_source_id: int,
        target_tag: str,
        value: Any,
        status: str,
        reason: str,
        dry_run: bool,
    ) -> None:
        self.initialize()
        with self.session_factory() as session:
            session.add(
                WritebackRecordModel(
                    run_id=run_id,
                    output_name=output_name,
                    data_source_id=data_source_id,
                    target_tag=target_tag,
                    value_json=json.dumps(value, ensure_ascii=False, sort_keys=True),
                    status=status,
                    reason=reason,
                    dry_run=1 if dry_run else 0,
                    created_at=datetime.now(UTC),
                )
            )
            session.commit()

    def list_writeback_records(self, run_id: str | None = None) -> list[dict[str, Any]]:
        self.initialize()
        with self.session_factory() as session:
            statement = select(WritebackRecordModel).order_by(WritebackRecordModel.id)
            if run_id:
                statement = statement.where(WritebackRecordModel.run_id == run_id)
            rows = session.scalars(statement).all()
            return [
                {
                    "id": row.id,
                    "run_id": row.run_id,
                    "output_name": row.output_name,
                    "data_source_id": row.data_source_id,
                    "target_tag": row.target_tag,
                    "value": json.loads(row.value_json),
                    "status": row.status,
                    "reason": row.reason,
                    "dry_run": bool(row.dry_run),
                    "created_at": row.created_at.isoformat(),
                }
                for row in rows
            ]

    # ---------- helpers ----------
    def _get_or_create_package(
        self,
        session: Session,
        record: PackageRecord,
        now: datetime,
    ) -> PluginPackageModel:
        manifest = record.manifest
        package = session.scalar(
            select(PluginPackageModel).where(PluginPackageModel.name == manifest.metadata.name)
        )
        if package is not None:
            return package

        package = PluginPackageModel(
            name=manifest.metadata.name,
            display_name=manifest.metadata.display_name,
            description=manifest.metadata.description,
            status="validated",
            created_at=now,
            updated_at=now,
        )
        session.add(package)
        session.flush()
        return package

    def _data_source_to_dict(self, row: DataSourceModel) -> dict[str, Any]:
        return {
            "id": row.id,
            "name": row.name,
            "connector_type": row.connector_type,
            "config": json.loads(row.config_json),
            "read_enabled": bool(row.read_enabled),
            "write_enabled": bool(row.write_enabled),
            "status": row.status,
            "created_at": row.created_at.isoformat(),
            "updated_at": row.updated_at.isoformat(),
        }

    def _plugin_instance_to_dict(
        self,
        instance: PluginInstanceModel,
        package: PluginPackageModel,
        version: PluginVersionModel,
    ) -> dict[str, Any]:
        return {
            "id": instance.id,
            "name": instance.name,
            "package_id": package.id,
            "version_id": version.id,
            "package_name": package.name,
            "version": version.version,
            "input_bindings": json.loads(instance.input_bindings_json),
            "output_bindings": json.loads(instance.output_bindings_json),
            "config": json.loads(instance.config_json),
            "writeback_enabled": bool(instance.writeback_enabled),
            "schedule_enabled": bool(instance.schedule_enabled),
            "schedule_interval_sec": instance.schedule_interval_sec,
            "last_scheduled_run_at": instance.last_scheduled_run_at.isoformat()
            if instance.last_scheduled_run_at
            else None,
            "next_scheduled_run_at": instance.next_scheduled_run_at.isoformat()
            if instance.next_scheduled_run_at
            else None,
            "status": instance.status,
            "created_at": instance.created_at.isoformat(),
            "updated_at": instance.updated_at.isoformat(),
        }

    def _normalize_schedule_interval(self, interval_sec: int) -> int:
        return max(5, int(interval_sec or 30))

    def _next_schedule_time(
        self,
        now: datetime,
        schedule_enabled: bool,
        interval_sec: int,
    ) -> datetime | None:
        if not schedule_enabled:
            return None
        return self._align_to_interval_boundary(now, self._normalize_schedule_interval(interval_sec))

    def _align_to_interval_boundary(self, reference: datetime, interval_sec: int) -> datetime:
        reference = self._as_db_time(reference)
        interval = self._normalize_schedule_interval(interval_sec)
        ts = reference.timestamp()
        next_ts = math.floor(ts / interval) * interval + interval
        return datetime.fromtimestamp(next_ts, tz=UTC).replace(tzinfo=None)

    def _advance_schedule_time(
        self,
        *,
        previous_due: datetime | None,
        reference: datetime,
        interval_sec: int,
    ) -> datetime:
        reference = self._as_db_time(reference)
        previous_due = self._as_db_time(previous_due) if previous_due else None
        interval = timedelta(seconds=self._normalize_schedule_interval(interval_sec))
        next_due = previous_due or self._align_to_interval_boundary(reference, interval_sec)
        while next_due <= reference:
            next_due += interval
        return next_due

    def _as_db_time(self, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value
        return value.astimezone(UTC).replace(tzinfo=None)
