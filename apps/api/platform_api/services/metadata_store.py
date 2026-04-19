import json
from dataclasses import dataclass
from datetime import UTC, datetime
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
    select,
)
from sqlalchemy.engine import URL
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
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        database_url = URL.create("sqlite", database=str(self.db_path.resolve()))
        self.engine = create_engine(database_url, future=True)
        self._configure_local_sqlite()
        self.session_factory = sessionmaker(self.engine, expire_on_commit=False, future=True)

    def initialize(self) -> None:
        Base.metadata.create_all(self.engine)

    def _configure_local_sqlite(self) -> None:
        @event.listens_for(self.engine, "connect")
        def set_local_sqlite_pragmas(dbapi_connection: object, connection_record: object) -> None:
            cursor = dbapi_connection.cursor()
            # The current Windows workspace rejects SQLite journal file writes.
            # This keeps the local MVP usable; production should use PostgreSQL.
            cursor.execute("PRAGMA journal_mode=OFF")
            cursor.execute("PRAGMA synchronous=OFF")
            cursor.close()

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

    def list_plugin_runs(self, package_name: str | None = None) -> list[dict[str, Any]]:
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

            rows = session.execute(statement).all()
            return [
                {
                    "id": run.id,
                    "run_id": run.run_id,
                    "package_id": run.package_id,
                    "version_id": run.version_id,
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
                    status="configured",
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
                instance.status = "configured"
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
            "status": instance.status,
            "created_at": instance.created_at.isoformat(),
            "updated_at": instance.updated_at.isoformat(),
        }
