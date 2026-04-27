from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import tarfile
import uuid
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

from sqlalchemy import DateTime, Integer, String, Text, UniqueConstraint, create_engine, select
from sqlalchemy.engine import URL
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from platform_api.core.config import settings
from platform_api.services.metadata_store import MetadataStore
from platform_api.services.model_manifest import (
    ModelArtifactManifest,
    ModelManifestError,
    load_checksums,
    load_metrics,
    load_model_manifest,
    validate_artifact_files,
    validate_checksums,
)


class ModelRegistryError(ValueError):
    """Raised when model registry operation fails."""


class Base(DeclarativeBase):
    pass


class ModelRecordModel(Base):
    __tablename__ = "model_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    model_name: Mapped[str] = mapped_column(String(160), unique=True, nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(240), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    owner: Mapped[str] = mapped_column(String(120), nullable=False, default="local-dev")
    family_fingerprint: Mapped[str] = mapped_column(String(240), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="uploaded")
    active_version_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ModelVersionModel(Base):
    __tablename__ = "model_versions"
    __table_args__ = (UniqueConstraint("model_id", "version", name="uq_model_versions_model_version"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    model_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    version: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    artifact_dir: Mapped[str] = mapped_column(Text, nullable=False)
    manifest_json: Mapped[str] = mapped_column(Text, nullable=False)
    artifacts_json: Mapped[str] = mapped_column(Text, nullable=False)
    metrics_json: Mapped[str] = mapped_column(Text, nullable=False)
    checksums_json: Mapped[str] = mapped_column(Text, nullable=False)
    family_fingerprint: Mapped[str] = mapped_column(String(240), nullable=False, index=True)
    metrics_completeness_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="UPLOADED")
    source: Mapped[str] = mapped_column(String(80), nullable=False, default="manual_upload")
    source_job_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ModelBindingModel(Base):
    __tablename__ = "model_bindings"
    __table_args__ = (UniqueConstraint("instance_id", name="uq_model_bindings_instance"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    instance_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    model_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    model_version_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    binding_mode: Mapped[str] = mapped_column(String(40), nullable=False, default="current")
    family_fingerprint: Mapped[str] = mapped_column(String(240), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ModelDeploymentModel(Base):
    __tablename__ = "model_deployments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    model_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    from_version_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    to_version_id: Mapped[int] = mapped_column(Integer, nullable=False)
    activated_by: Mapped[str] = mapped_column(String(120), nullable=False, default="local-dev")
    activated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    rollback_from_deployment_id: Mapped[int | None] = mapped_column(Integer, nullable=True)


@dataclass(frozen=True)
class UploadedModelVersion:
    model_id: int
    version_id: int
    model_name: str
    version: str
    status: str
    digest: str
    manifest: dict[str, Any]


class ModelRegistry:
    def __init__(self, database: str | Path | None = None, storage_root: Path | None = None) -> None:
        self.database = database or settings.metadata_database
        self.storage_root = (storage_root or (settings.project_root / "var/model-store")).resolve()
        self.storage_root.mkdir(parents=True, exist_ok=True)
        self.engine = create_engine(self._engine_target(self.database), future=True)
        self.session_factory = sessionmaker(self.engine, expire_on_commit=False, future=True)

    def initialize(self) -> None:
        Base.metadata.create_all(self.engine)

    def list_models(self) -> list[dict[str, Any]]:
        self.initialize()
        with self.session_factory() as session:
            rows = session.scalars(
                select(ModelRecordModel).order_by(ModelRecordModel.updated_at.desc(), ModelRecordModel.id.desc())
            ).all()
            result: list[dict[str, Any]] = []
            for row in rows:
                active = session.get(ModelVersionModel, row.active_version_id) if row.active_version_id else None
                result.append(self._model_to_dict(row, active_version=active))
            return result

    def get_model(self, model_id: int) -> dict[str, Any] | None:
        self.initialize()
        with self.session_factory() as session:
            row = session.get(ModelRecordModel, model_id)
            if row is None:
                return None
            active = session.get(ModelVersionModel, row.active_version_id) if row.active_version_id else None
            return self._model_to_dict(row, active_version=active)

    def list_versions(self, model_id: int) -> list[dict[str, Any]] | None:
        self.initialize()
        with self.session_factory() as session:
            model = session.get(ModelRecordModel, model_id)
            if model is None:
                return None
            rows = session.scalars(
                select(ModelVersionModel)
                .where(ModelVersionModel.model_id == model_id)
                .order_by(ModelVersionModel.created_at.desc(), ModelVersionModel.id.desc())
            ).all()
            return [self._version_to_dict(row, model) for row in rows]

    def upload_package_bytes(self, *, filename: str, content: bytes, actor: str = "local-dev") -> UploadedModelVersion:
        """Upload a model artifact package.

        The model record is not created manually. It is derived from manifest.yaml:
        model.name, model.version, model.description, and model_family.family_fingerprint.
        """
        self.initialize()
        if not content:
            raise ModelRegistryError("model package body is empty")

        digest = hashlib.sha256(content).hexdigest()
        package_root, staging_dir = self._extract_to_staging(filename=filename, content=content)
        try:
            manifest, checksums, metrics = self._load_and_validate_package(package_root)
            target_dir = self.storage_root / manifest.model.name / "versions" / manifest.model.version
            if target_dir.exists():
                raise ModelRegistryError(f"model version already exists: {manifest.model.name}@{manifest.model.version}")
            target_dir.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(package_root, target_dir)
        except ModelManifestError as exc:
            raise ModelRegistryError(str(exc)) from exc
        finally:
            _remove_child_dir(staging_dir, self.storage_root)

        now = _now()
        with self.session_factory() as session:
            model = session.scalar(select(ModelRecordModel).where(ModelRecordModel.model_name == manifest.model.name))
            if model is None:
                model = ModelRecordModel(
                    model_name=manifest.model.name,
                    display_name=_manifest_display_name(manifest),
                    description=manifest.model.description or "",
                    owner=actor,
                    family_fingerprint=manifest.model_family.family_fingerprint,
                    status="uploaded",
                    active_version_id=None,
                    created_at=now,
                    updated_at=now,
                )
                session.add(model)
                session.flush()
            else:
                if model.family_fingerprint != manifest.model_family.family_fingerprint:
                    raise ModelRegistryError(
                        "manifest family_fingerprint does not match existing model record: "
                        f"{model.family_fingerprint}"
                    )
                model.display_name = _manifest_display_name(manifest)
                model.description = manifest.model.description or model.description
                model.status = "uploaded" if model.active_version_id is None else model.status
                model.updated_at = now

            existing_version = session.scalar(
                select(ModelVersionModel).where(
                    ModelVersionModel.model_id == model.id,
                    ModelVersionModel.version == manifest.model.version,
                )
            )
            if existing_version is not None:
                raise ModelRegistryError(f"model version already exists: {manifest.model.version}")

            version_row = ModelVersionModel(
                model_id=model.id,
                version=manifest.model.version,
                artifact_dir=str(target_dir),
                manifest_json=json.dumps(manifest.model_dump(by_alias=True), ensure_ascii=False, sort_keys=True),
                artifacts_json=json.dumps(manifest.artifacts_json(), ensure_ascii=False, sort_keys=True),
                metrics_json=json.dumps(metrics, ensure_ascii=False, sort_keys=True),
                checksums_json=json.dumps(checksums, ensure_ascii=False, sort_keys=True),
                family_fingerprint=manifest.model_family.family_fingerprint,
                metrics_completeness_json=json.dumps(
                    metrics.get("metrics_completeness", {}),
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                status="UPLOADED",
                source="manual_upload",
                source_job_id=None,
                created_at=now,
                activated_at=None,
                archived_at=None,
            )
            session.add(version_row)
            session.commit()
            return UploadedModelVersion(
                model_id=model.id,
                version_id=version_row.id,
                model_name=model.model_name,
                version=version_row.version,
                status=version_row.status,
                digest=digest,
                manifest=manifest.model_dump(by_alias=True),
            )

    def upload_version_bytes(self, *, model_id: int, filename: str, content: bytes, actor: str = "local-dev") -> UploadedModelVersion:
        """Backward-compatible direct version upload.

        Prefer /api/v1/packages unified upload. This method remains for internal tooling.
        """
        self.initialize()
        if not content:
            raise ModelRegistryError("model package body is empty")

        digest = hashlib.sha256(content).hexdigest()
        with self.session_factory() as session:
            model = session.get(ModelRecordModel, model_id)
            if model is None:
                raise ModelRegistryError(f"model not found: {model_id}")

        package_root, staging_dir = self._extract_to_staging(filename=filename, content=content)
        try:
            manifest, checksums, metrics = self._load_and_validate_package(package_root)
            if manifest.model.name != model.model_name:
                raise ModelRegistryError("manifest model.name does not match target model")
            if manifest.model_family.family_fingerprint != model.family_fingerprint:
                raise ModelRegistryError("manifest family_fingerprint does not match target model")
            target_dir = self.storage_root / model.model_name / "versions" / manifest.model.version
            if target_dir.exists():
                raise ModelRegistryError(f"model version already exists: {manifest.model.version}")
            target_dir.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(package_root, target_dir)
        except ModelManifestError as exc:
            raise ModelRegistryError(str(exc)) from exc
        finally:
            _remove_child_dir(staging_dir, self.storage_root)

        now = _now()
        with self.session_factory() as session:
            model = session.get(ModelRecordModel, model_id)
            if model is None:
                raise ModelRegistryError(f"model not found: {model_id}")
            version_row = ModelVersionModel(
                model_id=model.id,
                version=manifest.model.version,
                artifact_dir=str(target_dir),
                manifest_json=json.dumps(manifest.model_dump(by_alias=True), ensure_ascii=False, sort_keys=True),
                artifacts_json=json.dumps(manifest.artifacts_json(), ensure_ascii=False, sort_keys=True),
                metrics_json=json.dumps(metrics, ensure_ascii=False, sort_keys=True),
                checksums_json=json.dumps(checksums, ensure_ascii=False, sort_keys=True),
                family_fingerprint=manifest.model_family.family_fingerprint,
                metrics_completeness_json=json.dumps(metrics.get("metrics_completeness", {}), ensure_ascii=False, sort_keys=True),
                status="UPLOADED",
                source="manual_upload",
                source_job_id=None,
                created_at=now,
                activated_at=None,
                archived_at=None,
            )
            model.status = "uploaded" if model.active_version_id is None else model.status
            model.updated_at = now
            session.add(version_row)
            session.commit()
            return UploadedModelVersion(
                model_id=model.id,
                version_id=version_row.id,
                model_name=model.model_name,
                version=version_row.version,
                status=version_row.status,
                digest=digest,
                manifest=manifest.model_dump(by_alias=True),
            )

    def validate_version(self, *, model_id: int, version_id: int) -> dict[str, Any]:
        self.initialize()
        with self.session_factory() as session:
            model = session.get(ModelRecordModel, model_id)
            version = session.get(ModelVersionModel, version_id)
            if model is None or version is None or version.model_id != model_id:
                raise ModelRegistryError("model version not found")
            self._validate_version_files(version)
            version.status = "VALIDATED"
            model.status = "validated" if model.active_version_id is None else model.status
            model.updated_at = _now()
            session.commit()
            return self._version_to_dict(version, model)

    def promote_version(self, *, model_id: int, version_id: int, actor: str = "local-dev", reason: str = "manual promote") -> dict[str, Any]:
        self.initialize()
        now = _now()
        with self.session_factory() as session:
            model = session.get(ModelRecordModel, model_id)
            version = session.get(ModelVersionModel, version_id)
            if model is None or version is None or version.model_id != model_id:
                raise ModelRegistryError("model version not found")
            self._validate_version_files(version)
            previous_id = model.active_version_id
            if previous_id and previous_id != version.id:
                previous = session.get(ModelVersionModel, previous_id)
                if previous is not None:
                    previous.status = "ARCHIVED"
                    previous.archived_at = now
            version.status = "ACTIVE"
            version.activated_at = now
            model.active_version_id = version.id
            model.status = "active"
            model.updated_at = now
            deployment = ModelDeploymentModel(
                model_id=model.id,
                from_version_id=previous_id,
                to_version_id=version.id,
                activated_by=actor,
                activated_at=now,
                reason=reason,
                rollback_from_deployment_id=None,
            )
            session.add(deployment)
            session.commit()
            self._write_active_pointer(model=model, version=version, previous_version_id=previous_id, actor=actor)
            return self._model_to_dict(model, active_version=version)

    def rollback(self, *, model_id: int, actor: str = "local-dev", reason: str = "manual rollback") -> dict[str, Any]:
        self.initialize()
        with self.session_factory() as session:
            model = session.get(ModelRecordModel, model_id)
            if model is None:
                raise ModelRegistryError("model not found")
            latest = session.scalars(
                select(ModelDeploymentModel)
                .where(ModelDeploymentModel.model_id == model_id, ModelDeploymentModel.from_version_id.is_not(None))
                .order_by(ModelDeploymentModel.activated_at.desc(), ModelDeploymentModel.id.desc())
                .limit(1)
            ).first()
            if latest is None or latest.from_version_id is None:
                raise ModelRegistryError("no previous deployment available for rollback")
            previous_version_id = int(latest.from_version_id)
        return self.promote_version(model_id=model_id, version_id=previous_version_id, actor=actor, reason=reason)

    def bind_instance(
        self,
        *,
        instance_id: int,
        model_id: int,
        binding_mode: str = "current",
        model_version_id: int | None = None,
    ) -> dict[str, Any]:
        self.initialize()
        metadata_store = MetadataStore(settings.metadata_database)
        instance = metadata_store.get_plugin_instance(int(instance_id))
        if instance is None:
            raise ModelRegistryError(f"plugin instance not found: {instance_id}")

        required_family_fingerprint = self._plugin_required_family_fingerprint(
            metadata_store=metadata_store,
            instance=instance,
        )
        if not required_family_fingerprint:
            raise ModelRegistryError(
                "plugin manifest does not declare modelDependency.familyFingerprint; refuse model binding"
            )

        now = _now()
        binding_mode = binding_mode.strip() or "current"
        if binding_mode not in {"current", "fixed_version"}:
            raise ModelRegistryError("binding_mode must be current or fixed_version")
        with self.session_factory() as session:
            model = session.get(ModelRecordModel, model_id)
            if model is None:
                raise ModelRegistryError("model not found")

            if model.family_fingerprint != required_family_fingerprint:
                raise ModelRegistryError(
                    "model family_fingerprint mismatch: "
                    f"plugin requires {required_family_fingerprint}, model provides {model.family_fingerprint}"
                )

            if binding_mode == "current":
                if model.active_version_id is None:
                    raise ModelRegistryError("model has no active version")
                version_id = model.active_version_id
                version = session.get(ModelVersionModel, int(version_id))
                if version is None or version.model_id != model_id:
                    raise ModelRegistryError("active model version not found")
            else:
                if model_version_id is None:
                    raise ModelRegistryError("fixed_version binding requires model_version_id")
                version = session.get(ModelVersionModel, model_version_id)
                if version is None or version.model_id != model_id:
                    raise ModelRegistryError("model version not found")
                version_id = model_version_id

            if version.family_fingerprint != required_family_fingerprint:
                raise ModelRegistryError(
                    "model version family_fingerprint mismatch: "
                    f"plugin requires {required_family_fingerprint}, version provides {version.family_fingerprint}"
                )

            row = session.scalar(select(ModelBindingModel).where(ModelBindingModel.instance_id == instance_id))
            if row is None:
                row = ModelBindingModel(
                    instance_id=instance_id,
                    model_id=model_id,
                    model_version_id=version_id if binding_mode == "fixed_version" else None,
                    binding_mode=binding_mode,
                    family_fingerprint=model.family_fingerprint,
                    created_at=now,
                    updated_at=now,
                )
                session.add(row)
            else:
                row.model_id = model_id
                row.model_version_id = version_id if binding_mode == "fixed_version" else None
                row.binding_mode = binding_mode
                row.family_fingerprint = model.family_fingerprint
                row.updated_at = now
            session.commit()
            return self._binding_to_dict(
                row,
                model=model,
                plugin_required_family_fingerprint=required_family_fingerprint,
            )

    def get_instance_binding(self, *, instance_id: int) -> dict[str, Any] | None:
        self.initialize()
        required_family_fingerprint = None
        metadata_store = MetadataStore(settings.metadata_database)
        instance = metadata_store.get_plugin_instance(int(instance_id))
        if instance is not None:
            required_family_fingerprint = self._plugin_required_family_fingerprint(
                metadata_store=metadata_store,
                instance=instance,
            )
        with self.session_factory() as session:
            row = session.scalar(select(ModelBindingModel).where(ModelBindingModel.instance_id == instance_id))
            if row is None:
                return None
            model = session.get(ModelRecordModel, row.model_id)
            return self._binding_to_dict(
                row,
                model=model,
                plugin_required_family_fingerprint=required_family_fingerprint,
            )

    def get_instance_model_requirement(self, *, instance_id: int) -> dict[str, Any]:
        metadata_store = MetadataStore(settings.metadata_database)
        instance = metadata_store.get_plugin_instance(int(instance_id))
        if instance is None:
            raise ModelRegistryError(f"plugin instance not found: {instance_id}")
        required_family_fingerprint = self._plugin_required_family_fingerprint(
            metadata_store=metadata_store,
            instance=instance,
        )
        compatible_models = []
        if required_family_fingerprint:
            self.initialize()
            with self.session_factory() as session:
                rows = session.scalars(
                    select(ModelRecordModel)
                    .where(ModelRecordModel.family_fingerprint == required_family_fingerprint)
                    .order_by(ModelRecordModel.updated_at.desc(), ModelRecordModel.id.desc())
                ).all()
                compatible_models = [
                    self._model_to_dict(
                        row,
                        active_version=session.get(ModelVersionModel, row.active_version_id) if row.active_version_id else None,
                    )
                    for row in rows
                ]
        return {
            "instance_id": int(instance_id),
            "package_name": instance.get("package_name"),
            "version": instance.get("version"),
            "required": bool(required_family_fingerprint),
            "family_fingerprint": required_family_fingerprint,
            "compatible_models": compatible_models,
            "message": (
                "plugin manifest declares modelDependency.familyFingerprint"
                if required_family_fingerprint
                else "plugin manifest does not declare modelDependency.familyFingerprint; model binding is refused"
            ),
        }

    def delete_instance_binding(self, *, instance_id: int) -> bool:
        self.initialize()
        with self.session_factory() as session:
            row = session.scalar(select(ModelBindingModel).where(ModelBindingModel.instance_id == instance_id))
            if row is None:
                return False
            session.delete(row)
            session.commit()
            return True

    def resolve_instance_model_context(self, *, instance_id: int) -> dict[str, Any] | None:
        self.initialize()
        with self.session_factory() as session:
            binding = session.scalar(select(ModelBindingModel).where(ModelBindingModel.instance_id == instance_id))
            if binding is None:
                return None
            model = session.get(ModelRecordModel, binding.model_id)
            if model is None:
                return None
            version_id = model.active_version_id if binding.binding_mode == "current" else binding.model_version_id
            if version_id is None:
                return None
            version = session.get(ModelVersionModel, version_id)
            if version is None:
                return None
            return self._runtime_model_context(model=model, version=version, runtime_model_dir="./model")

    def _plugin_required_family_fingerprint(self, *, metadata_store: MetadataStore, instance: dict[str, Any]) -> str | None:
        version_record = metadata_store.get_plugin_version(
            str(instance.get("package_name", "")),
            str(instance.get("version", "")),
        )
        if version_record is None:
            return None
        manifest = version_record.get("manifest") or {}
        if not isinstance(manifest, dict):
            return None
        dependency = self._extract_model_dependency(manifest)
        if not dependency:
            return None
        raw = (
            dependency.get("familyFingerprint")
            or dependency.get("family_fingerprint")
            or dependency.get("modelFamilyFingerprint")
            or dependency.get("model_family_fingerprint")
        )
        value = str(raw or "").strip()
        return value or None

    def _extract_model_dependency(self, manifest: dict[str, Any]) -> dict[str, Any] | None:
        candidates = [
            manifest.get("modelDependency"),
            manifest.get("model_dependency"),
        ]
        spec = manifest.get("spec")
        if isinstance(spec, dict):
            candidates.extend([
                spec.get("modelDependency"),
                spec.get("model_dependency"),
            ])
        for candidate in candidates:
            if isinstance(candidate, dict):
                return candidate
        return None

    def _load_and_validate_package(self, package_root: Path) -> tuple[ModelArtifactManifest, dict[str, Any], dict[str, Any]]:
        manifest = load_model_manifest(package_root / "manifest.yaml")
        validate_artifact_files(package_root, manifest)
        checksums = load_checksums(package_root / "checksums.json")
        validate_checksums(package_root, checksums)
        metrics = load_metrics(package_root / "metrics.json")
        return manifest, checksums, metrics

    def _extract_to_staging(self, *, filename: str, content: bytes) -> tuple[Path, Path]:
        suffix = _archive_suffix(filename)
        if suffix is None:
            raise ModelRegistryError("only .zip and .tar.gz model packages are supported")
        staging_dir = self.storage_root / "_intake" / f"{uuid.uuid4().hex}"
        staging_dir.mkdir(parents=True, exist_ok=False)
        archive_path = staging_dir / f"upload{suffix}"
        archive_path.write_bytes(content)
        extracted_dir = staging_dir / "extracted"
        extracted_dir.mkdir()
        try:
            if suffix == ".zip":
                _extract_zip(archive_path, extracted_dir)
            else:
                _extract_tar_gz(archive_path, extracted_dir)
            return _locate_package_root(extracted_dir), staging_dir
        except Exception:
            _remove_child_dir(staging_dir, self.storage_root)
            raise

    def _validate_version_files(self, version: ModelVersionModel) -> None:
        root = Path(version.artifact_dir).resolve()
        manifest = load_model_manifest(root / "manifest.yaml")
        validate_artifact_files(root, manifest)
        checksums = load_checksums(root / "checksums.json")
        validate_checksums(root, checksums)

    def _write_active_pointer(self, *, model: ModelRecordModel, version: ModelVersionModel, previous_version_id: int | None, actor: str) -> None:
        model_dir = self.storage_root / model.model_name
        model_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "model_name": model.model_name,
            "active_version": version.version,
            "active_version_id": version.id,
            "family_fingerprint": model.family_fingerprint,
            "activated_at": _now().isoformat(),
            "activated_by": actor,
            "previous_version_id": previous_version_id,
        }
        tmp = model_dir / "active.json.tmp"
        target = model_dir / "active.json"
        with tmp.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, target)

    def _model_to_dict(self, row: ModelRecordModel, *, active_version: ModelVersionModel | None) -> dict[str, Any]:
        return {
            "id": row.id,
            "model_name": row.model_name,
            "display_name": row.display_name,
            "description": row.description,
            "owner": row.owner,
            "family_fingerprint": row.family_fingerprint,
            "status": row.status,
            "active_version_id": row.active_version_id,
            "active_version": active_version.version if active_version else None,
            "created_at": row.created_at.isoformat(),
            "updated_at": row.updated_at.isoformat(),
        }

    def _version_to_dict(self, row: ModelVersionModel, model: ModelRecordModel | None = None) -> dict[str, Any]:
        return {
            "id": row.id,
            "model_id": row.model_id,
            "model_name": model.model_name if model else None,
            "version": row.version,
            "artifact_dir": row.artifact_dir,
            "manifest": json.loads(row.manifest_json),
            "artifacts": json.loads(row.artifacts_json),
            "metrics": json.loads(row.metrics_json),
            "checksums": json.loads(row.checksums_json),
            "family_fingerprint": row.family_fingerprint,
            "metrics_completeness": json.loads(row.metrics_completeness_json or "{}"),
            "status": row.status,
            "source": row.source,
            "source_job_id": row.source_job_id,
            "created_at": row.created_at.isoformat(),
            "activated_at": row.activated_at.isoformat() if row.activated_at else None,
            "archived_at": row.archived_at.isoformat() if row.archived_at else None,
        }

    def _binding_to_dict(
        self,
        row: ModelBindingModel,
        *,
        model: ModelRecordModel | None,
        plugin_required_family_fingerprint: str | None = None,
    ) -> dict[str, Any]:
        return {
            "id": row.id,
            "instance_id": row.instance_id,
            "model_id": row.model_id,
            "model_name": model.model_name if model else None,
            "model_version_id": row.model_version_id,
            "binding_mode": row.binding_mode,
            "family_fingerprint": row.family_fingerprint,
            "plugin_required_family_fingerprint": plugin_required_family_fingerprint,
            "fingerprint_match": (
                row.family_fingerprint == plugin_required_family_fingerprint
                if plugin_required_family_fingerprint
                else False
            ),
            "created_at": row.created_at.isoformat(),
            "updated_at": row.updated_at.isoformat(),
        }

    def _runtime_model_context(self, *, model: ModelRecordModel, version: ModelVersionModel, runtime_model_dir: str) -> dict[str, Any]:
        artifacts = json.loads(version.artifacts_json)
        runtime_artifacts: dict[str, Any] = {}
        for key, spec in artifacts.items():
            relative_path = str(spec.get("path", ""))
            runtime_artifacts[key] = {
                **spec,
                "path": f"{runtime_model_dir.rstrip('/')}/{relative_path}",
            }
        manifest = json.loads(version.manifest_json)
        return {
            "model_name": model.model_name,
            "model_version": version.version,
            "model_artifact_id": version.id,
            "model_dir": runtime_model_dir,
            "manifest_path": f"{runtime_model_dir.rstrip('/')}/manifest.yaml",
            "artifacts_dir": f"{runtime_model_dir.rstrip('/')}/artifacts",
            "entry_artifact": manifest.get("model", {}).get("entry_artifact", "model"),
            "family_fingerprint": version.family_fingerprint,
            "artifacts": runtime_artifacts,
        }

    def _engine_target(self, database: str | Path) -> str | URL:
        if isinstance(database, Path):
            return URL.create("sqlite", database=str(database.resolve()))
        if "://" in database:
            return database
        return URL.create("sqlite", database=str(Path(database).resolve()))


def _archive_suffix(filename: str) -> str | None:
    lowered = filename.lower()
    if lowered.endswith(".tar.gz"):
        return ".tar.gz"
    if lowered.endswith(".zip"):
        return ".zip"
    return None


def _assert_safe_member_path(name: str) -> None:
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or name.startswith("\\"):
        raise ModelRegistryError(f"unsafe archive path: {name}")


def _extract_zip(archive_path: Path, output_dir: Path) -> None:
    try:
        with zipfile.ZipFile(archive_path) as archive:
            for member in archive.infolist():
                _assert_safe_member_path(member.filename)
                mode = member.external_attr >> 16
                if stat.S_ISLNK(mode):
                    raise ModelRegistryError(f"symlink is not allowed: {member.filename}")
            archive.extractall(output_dir)
    except zipfile.BadZipFile as exc:
        raise ModelRegistryError("zip model package is invalid") from exc


def _extract_tar_gz(archive_path: Path, output_dir: Path) -> None:
    try:
        with tarfile.open(archive_path, "r:gz") as archive:
            for member in archive.getmembers():
                _assert_safe_member_path(member.name)
                if member.issym() or member.islnk():
                    raise ModelRegistryError(f"link is not allowed: {member.name}")
            archive.extractall(output_dir)
    except tarfile.TarError as exc:
        raise ModelRegistryError("tar.gz model package is invalid") from exc


def _locate_package_root(extracted_dir: Path) -> Path:
    if (extracted_dir / "manifest.yaml").exists():
        return extracted_dir
    entries = [path for path in extracted_dir.iterdir() if path.name not in {"__MACOSX", ".DS_Store"}]
    directories = [path for path in entries if path.is_dir()]
    files = [path for path in entries if path.is_file()]
    if len(directories) == 1 and not files and (directories[0] / "manifest.yaml").exists():
        return directories[0]
    raise ModelRegistryError("manifest not found: expected manifest.yaml at archive root or inside a single top-level directory")


def _remove_child_dir(path: Path, root: Path) -> None:
    root = root.resolve()
    resolved = path.resolve()
    if root == resolved or root not in resolved.parents:
        raise ModelRegistryError(f"refusing to remove path outside model store root: {path}")
    if resolved.exists():
        shutil.rmtree(resolved, ignore_errors=True)


def _manifest_display_name(manifest: ModelArtifactManifest) -> str:
    extra = getattr(manifest.model, "model_extra", {}) or {}
    raw = extra.get("display_name") or extra.get("displayName") or manifest.model.name
    value = str(raw).strip() or manifest.model.name
    return value[:240]


def _now() -> datetime:
    return datetime.now(UTC)
