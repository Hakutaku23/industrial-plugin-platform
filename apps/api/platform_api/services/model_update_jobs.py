from __future__ import annotations

import json
import os
import shutil
import time
import uuid
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import Boolean, DateTime, Integer, String, Text, create_engine, inspect, select, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from platform_api.core.config import settings
from platform_api.services.execution import PluginExecutionError, execute_plugin_version
from platform_api.services.input_binding_resolver import InputBindingResolverError, resolve_input_bindings
from platform_api.services.metadata_store import MetadataStore
from platform_api.services.model_registry import ModelRegistry, ModelRegistryError


class ModelUpdateJobError(ValueError):
    """Raised when a model update job cannot be configured or executed."""


class Base(DeclarativeBase):
    pass


class ModelUpdateJobModel(Base):
    __tablename__ = "model_update_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    model_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    trainer_package_name: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    trainer_package_version: Mapped[str] = mapped_column(String(80), nullable=False)
    trainer_instance_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    input_bindings_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    schedule_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    schedule_interval_sec: Mapped[int] = mapped_column(Integer, nullable=False, default=86400)
    promote_mode: Mapped[str] = mapped_column(String(40), nullable=False, default="manual")
    metric_policy_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    config_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="configured")
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ModelUpdateRunModel(Base):
    __tablename__ = "model_update_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    run_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(60), nullable=False)
    trigger_type: Mapped[str] = mapped_column(String(60), nullable=False, default="manual")
    current_model_version_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    candidate_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    inputs_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    metrics_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    error_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ModelUpdateCandidateModel(Base):
    __tablename__ = "model_update_candidates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    run_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    model_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    version: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    version_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    candidate_dir: Mapped[str] = mapped_column(Text, nullable=False)
    manifest_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    artifacts_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    metrics_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="GENERATED")
    reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    promoted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


@dataclass(frozen=True)
class JobExecutionResult:
    job: dict[str, Any]
    run: dict[str, Any]
    candidate: dict[str, Any] | None


class FileLock:
    def __init__(self, path: Path, *, stale_after_sec: int = 24 * 60 * 60) -> None:
        self.path = path
        self.stale_after_sec = stale_after_sec
        self.acquired = False

    def __enter__(self) -> "FileLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists() and time.time() - self.path.stat().st_mtime > self.stale_after_sec:
            try:
                self.path.unlink()
            except OSError:
                pass
        try:
            fd = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(json.dumps({"pid": os.getpid(), "created_at": datetime.now(UTC).isoformat()}))
            self.acquired = True
            return self
        except FileExistsError as exc:
            raise ModelUpdateJobError(f"model update lock is already held: {self.path.name}") from exc

    def __exit__(self, exc_type, exc, tb) -> None:
        if self.acquired:
            try:
                self.path.unlink()
            except OSError:
                pass


class ModelUpdateJobStore:
    def __init__(self, database: str | Path | None = None) -> None:
        self.database = database or settings.metadata_database
        self.engine = create_engine(self._engine_target(self.database), future=True)
        self.session_factory = sessionmaker(self.engine, expire_on_commit=False, future=True)

    def initialize(self) -> None:
        Base.metadata.create_all(self.engine)
        self._ensure_compat_columns()

    def list_jobs(self) -> list[dict[str, Any]]:
        self.initialize()
        with self.session_factory() as session:
            rows = session.scalars(select(ModelUpdateJobModel).order_by(ModelUpdateJobModel.updated_at.desc(), ModelUpdateJobModel.id.desc())).all()
            return [self._job_to_dict(row) for row in rows]

    def get_job(self, job_id: int) -> dict[str, Any] | None:
        self.initialize()
        with self.session_factory() as session:
            row = session.get(ModelUpdateJobModel, job_id)
            return self._job_to_dict(row) if row else None

    def create_job(self, payload: dict[str, Any], *, actor: str = "local-dev") -> dict[str, Any]:
        self.initialize()
        now = datetime.now(UTC)
        model_id = int(payload.get("model_id"))
        package_name = str(payload.get("trainer_package_name") or "").strip()
        package_version = str(payload.get("trainer_package_version") or "").strip()
        if not package_name or not package_version:
            raise ModelUpdateJobError("trainer_package_name and trainer_package_version are required")

        self._validate_trainer_and_model(
            model_id=model_id,
            trainer_package_name=package_name,
            trainer_package_version=package_version,
        )

        interval = max(60, int(payload.get("schedule_interval_sec") or 86400))
        schedule_enabled = bool(payload.get("schedule_enabled", False))
        next_run_at = now if schedule_enabled else None
        row = ModelUpdateJobModel(
            name=str(payload.get("name") or f"model-update-{model_id}").strip(),
            model_id=model_id,
            trainer_package_name=package_name,
            trainer_package_version=package_version,
            trainer_instance_id=payload.get("trainer_instance_id"),
            input_bindings_json=_json_dumps(payload.get("input_bindings") or []),
            schedule_enabled=schedule_enabled,
            schedule_interval_sec=interval,
            promote_mode=str(payload.get("promote_mode") or "manual"),
            metric_policy_json=_json_dumps(payload.get("metric_policy") or {}),
            config_json=_json_dumps(payload.get("config") or {}),
            status="configured",
            last_run_at=None,
            next_run_at=next_run_at,
            created_at=now,
            updated_at=now,
        )
        with self.session_factory() as session:
            session.add(row)
            session.commit()
            session.refresh(row)
            self._audit("model.update.job.created", "model_update_job", str(row.id), actor, self._job_to_dict(row))
            return self._job_to_dict(row)

    def update_job(self, job_id: int, payload: dict[str, Any], *, actor: str = "local-dev") -> dict[str, Any]:
        self.initialize()
        with self.session_factory() as session:
            row = session.get(ModelUpdateJobModel, job_id)
            if row is None:
                raise ModelUpdateJobError(f"model update job not found: {job_id}")

            if "model_id" in payload:
                row.model_id = int(payload["model_id"])
            if "trainer_package_name" in payload and payload["trainer_package_name"]:
                row.trainer_package_name = str(payload["trainer_package_name"]).strip()
            if "trainer_package_version" in payload and payload["trainer_package_version"]:
                row.trainer_package_version = str(payload["trainer_package_version"]).strip()
            if "name" in payload:
                row.name = str(payload["name"] or row.name).strip()
            if "input_bindings" in payload:
                row.input_bindings_json = _json_dumps(payload.get("input_bindings") or [])
            if "config" in payload:
                row.config_json = _json_dumps(payload.get("config") or {})
            if "metric_policy" in payload:
                row.metric_policy_json = _json_dumps(payload.get("metric_policy") or {})
            if "promote_mode" in payload:
                row.promote_mode = str(payload.get("promote_mode") or "manual")
            if "schedule_enabled" in payload:
                row.schedule_enabled = bool(payload.get("schedule_enabled"))
            if "schedule_interval_sec" in payload:
                row.schedule_interval_sec = max(60, int(payload.get("schedule_interval_sec") or row.schedule_interval_sec))
            row.next_run_at = self._compute_next_run_at(row, from_time=datetime.now(UTC)) if row.schedule_enabled else None
            row.updated_at = datetime.now(UTC)

            self._validate_trainer_and_model(
                model_id=row.model_id,
                trainer_package_name=row.trainer_package_name,
                trainer_package_version=row.trainer_package_version,
            )
            session.commit()
            session.refresh(row)
            result = self._job_to_dict(row)
            self._audit("model.update.job.updated", "model_update_job", str(row.id), actor, result)
            return result

    def delete_job(self, job_id: int, *, actor: str = "local-dev") -> bool:
        self.initialize()
        with self.session_factory() as session:
            row = session.get(ModelUpdateJobModel, job_id)
            if row is None:
                return False
            payload = self._job_to_dict(row)
            session.delete(row)
            session.commit()
            self._audit("model.update.job.deleted", "model_update_job", str(job_id), actor, payload)
            return True

    def list_runs(self, job_id: int | None = None, *, limit: int = 100) -> list[dict[str, Any]]:
        self.initialize()
        stmt = select(ModelUpdateRunModel)
        if job_id is not None:
            stmt = stmt.where(ModelUpdateRunModel.job_id == job_id)
        stmt = stmt.order_by(ModelUpdateRunModel.started_at.desc(), ModelUpdateRunModel.id.desc()).limit(max(1, min(limit, 500)))
        with self.session_factory() as session:
            return [self._run_to_dict(row) for row in session.scalars(stmt).all()]

    def list_candidates(self, job_id: int | None = None, *, limit: int = 100) -> list[dict[str, Any]]:
        self.initialize()
        stmt = select(ModelUpdateCandidateModel)
        if job_id is not None:
            stmt = stmt.where(ModelUpdateCandidateModel.job_id == job_id)
        stmt = stmt.order_by(ModelUpdateCandidateModel.created_at.desc(), ModelUpdateCandidateModel.id.desc()).limit(max(1, min(limit, 500)))
        with self.session_factory() as session:
            return [self._candidate_to_dict(row) for row in session.scalars(stmt).all()]

    def get_candidate(self, candidate_id: int) -> dict[str, Any] | None:
        self.initialize()
        with self.session_factory() as session:
            row = session.get(ModelUpdateCandidateModel, candidate_id)
            return self._candidate_to_dict(row) if row else None

    def promote_candidate(self, candidate_id: int, *, actor: str = "local-dev", reason: str = "manual promote candidate") -> dict[str, Any]:
        self.initialize()
        with self.session_factory() as session:
            row = session.get(ModelUpdateCandidateModel, candidate_id)
            if row is None:
                raise ModelUpdateJobError(f"candidate not found: {candidate_id}")
            if row.status == "PROMOTED":
                return self._candidate_to_dict(row)
            if row.status == "REJECTED":
                raise ModelUpdateJobError("rejected candidate cannot be promoted")
            if row.version_id is None:
                raise ModelUpdateJobError("candidate has no model version id")

            promoted = ModelRegistry().promote_version(model_id=row.model_id, version_id=int(row.version_id), actor=actor, reason=reason)
            row.status = "PROMOTED"
            row.promoted_at = datetime.now(UTC)
            row.reason = reason
            session.commit()
            session.refresh(row)
            payload = self._candidate_to_dict(row)
            payload["promoted_model"] = promoted
            self._audit("model.update.candidate.promoted", "model_update_candidate", str(candidate_id), actor, payload)
            return payload

    def reject_candidate(self, candidate_id: int, *, actor: str = "local-dev", reason: str = "manual reject candidate") -> dict[str, Any]:
        self.initialize()
        with self.session_factory() as session:
            row = session.get(ModelUpdateCandidateModel, candidate_id)
            if row is None:
                raise ModelUpdateJobError(f"candidate not found: {candidate_id}")
            if row.status == "PROMOTED":
                raise ModelUpdateJobError("promoted candidate cannot be rejected; use model rollback instead")
            row.status = "REJECTED"
            row.rejected_at = datetime.now(UTC)
            row.reason = reason
            session.commit()
            session.refresh(row)
            payload = self._candidate_to_dict(row)
            self._audit("model.update.candidate.rejected", "model_update_candidate", str(candidate_id), actor, payload)
            return payload

    def list_due_jobs(self, *, limit: int = 10) -> list[dict[str, Any]]:
        self.initialize()
        now = datetime.now(UTC)
        stmt = (
            select(ModelUpdateJobModel)
            .where(ModelUpdateJobModel.schedule_enabled == True)  # noqa: E712
            .where(ModelUpdateJobModel.status != "running")
            .where((ModelUpdateJobModel.next_run_at == None) | (ModelUpdateJobModel.next_run_at <= now))  # noqa: E711
            .order_by(text("CASE WHEN next_run_at IS NULL THEN 0 ELSE 1 END"), ModelUpdateJobModel.next_run_at.asc(), ModelUpdateJobModel.id.asc())
            .limit(max(1, min(limit, 100)))
        )
        with self.session_factory() as session:
            return [self._job_to_dict(row) for row in session.scalars(stmt).all()]

    def run_due_jobs(self, *, limit: int = 5, actor: str = "scheduler") -> dict[str, Any]:
        due = self.list_due_jobs(limit=limit)
        results: list[dict[str, Any]] = []
        for job in due:
            try:
                results.append(self.execute_job(int(job["id"]), trigger_type="model_update_schedule", actor=actor))
            except Exception as exc:  # noqa: BLE001
                results.append({"job_id": job.get("id"), "status": "FAILED", "error": {"message": str(exc)}})
        return {"due_count": len(due), "results": results}

    def execute_job(self, job_id: int, *, trigger_type: str = "model_update_manual", actor: str = "local-dev") -> dict[str, Any]:
        self.initialize()
        job = self.get_job(job_id)
        if job is None:
            raise ModelUpdateJobError(f"model update job not found: {job_id}")

        lock_root = Path(settings.run_storage_dir) / ".model-update-locks"
        with FileLock(lock_root / f"job-{job_id}.lock"), FileLock(lock_root / f"model-{job['model_id']}.lock"):
            return self._execute_job_unlocked(job=job, trigger_type=trigger_type, actor=actor)

    def _execute_job_unlocked(self, *, job: dict[str, Any], trigger_type: str, actor: str) -> dict[str, Any]:
        started_at = datetime.now(UTC)
        run_row_id: int | None = None
        candidate_row_id: int | None = None
        run_record: dict[str, Any] | None = None
        error_payload: dict[str, Any] = {}
        metrics: dict[str, Any] = {}
        resolved_inputs: dict[str, Any] = {}
        model_version_id: int | None = None
        plugin_run_id: str | None = None

        with self.session_factory() as session:
            row = session.get(ModelUpdateJobModel, int(job["id"]))
            if row is None:
                raise ModelUpdateJobError(f"model update job not found: {job['id']}")
            row.status = "running"
            row.updated_at = datetime.now(UTC)
            run_row = ModelUpdateRunModel(
                job_id=row.id,
                run_id=None,
                status="RUNNING",
                trigger_type=trigger_type,
                current_model_version_id=None,
                candidate_id=None,
                inputs_json="{}",
                metrics_json="{}",
                error_json="{}",
                started_at=started_at,
                finished_at=None,
            )
            session.add(run_row)
            session.commit()
            session.refresh(run_row)
            run_row_id = run_row.id

        work_root = Path(settings.run_storage_dir) / f"model-update-{uuid.uuid4().hex}"
        current_model_dir = work_root / "current_model"
        candidate_model_dir = work_root / "candidate_model"

        try:
            model = ModelRegistry().get_model(int(job["model_id"]))
            if not model:
                raise ModelUpdateJobError(f"target model not found: {job['model_id']}")
            active_version_id = model.get("active_version_id")
            if not active_version_id:
                raise ModelUpdateJobError("target model has no active version")
            versions = ModelRegistry().list_versions(int(job["model_id"])) or []
            current_version = next((item for item in versions if int(item.get("id")) == int(active_version_id)), None)
            if not current_version:
                raise ModelUpdateJobError(f"active model version not found: {active_version_id}")
            model_version_id = int(current_version["id"])

            source_dir = Path(str(current_version.get("artifact_dir") or ""))
            if not source_dir.exists():
                raise ModelUpdateJobError(f"active model artifact dir not found: {source_dir}")
            work_root.mkdir(parents=True, exist_ok=True)
            shutil.copytree(source_dir, current_model_dir)
            candidate_model_dir.mkdir(parents=True, exist_ok=True)

            metadata_store = MetadataStore(settings.metadata_database)
            resolved_inputs = resolve_input_bindings(
                input_bindings=job.get("input_bindings") or [],
                store=metadata_store,
            )
            config = dict(job.get("config") or {})
            config.setdefault("model_update_job_id", job["id"])

            model_context = self._model_context(model=model, current_version=current_version, current_model_dir=current_model_dir)
            update_context = {
                "job_id": job["id"],
                "target_model_id": job["model_id"],
                "target_model_name": model.get("model_name"),
                "family_fingerprint": model.get("family_fingerprint"),
                "current_model_dir": str(current_model_dir),
                "candidate_model_dir": str(candidate_model_dir),
                "candidate_manifest_path": str(candidate_model_dir / "manifest.yaml"),
                "candidate_artifacts_dir": str(candidate_model_dir / "artifacts"),
                "promote_mode": job.get("promote_mode", "manual"),
                "input_binding_count": len(job.get("input_bindings") or []),
            }

            run_record = execute_plugin_version(
                package_name=str(job["trainer_package_name"]),
                version=str(job["trainer_package_version"]),
                inputs=resolved_inputs,
                config=config,
                trigger_type=trigger_type,
                instance_id=None,
                store=metadata_store,
                execution_context={
                    "model": model_context,
                    "model_update": update_context,
                },
            )
            plugin_run_id = str(run_record.get("run_id") or "")

            metrics = dict(run_record.get("metrics") or {})
            outputs = dict(run_record.get("outputs") or {})
            candidate_created = bool(outputs.get("candidate_created")) or (candidate_model_dir / "manifest.yaml").exists()
            if candidate_created and (candidate_model_dir / "manifest.yaml").exists():
                candidate = self._import_candidate(
                    job=job,
                    model=model,
                    candidate_model_dir=candidate_model_dir,
                    plugin_run_id=plugin_run_id,
                    actor=actor,
                )
                candidate_row_id = int(candidate["id"])
                metrics["candidate_version"] = candidate.get("version")
                metrics["candidate_version_id"] = candidate.get("version_id")
                run_status = "COMPLETED_WITH_CANDIDATE"
            else:
                run_status = "COMPLETED_NO_CANDIDATE"

        except Exception as exc:  # noqa: BLE001
            run_status = "FAILED"
            error_payload = {"code": exc.__class__.__name__, "message": str(exc)}
            self._audit("model.update.job.failed", "model_update_job", str(job["id"]), actor, {"error": error_payload})
        finally:
            finished_at = datetime.now(UTC)
            with self.session_factory() as session:
                job_row = session.get(ModelUpdateJobModel, int(job["id"]))
                run_row = session.get(ModelUpdateRunModel, int(run_row_id)) if run_row_id is not None else None
                if job_row is not None:
                    job_row.status = "configured" if run_status != "FAILED" else "failed"
                    job_row.last_run_at = finished_at
                    job_row.next_run_at = self._compute_next_run_at(job_row, from_time=finished_at) if job_row.schedule_enabled else None
                    job_row.updated_at = finished_at
                if run_row is not None:
                    run_row.run_id = plugin_run_id
                    run_row.status = run_status
                    run_row.current_model_version_id = model_version_id
                    run_row.candidate_id = candidate_row_id
                    run_row.inputs_json = _json_dumps(_summarize_inputs(resolved_inputs))
                    run_row.metrics_json = _json_dumps(metrics)
                    run_row.error_json = _json_dumps(error_payload)
                    run_row.finished_at = finished_at
                session.commit()

        result = {
            "job": self.get_job(int(job["id"])),
            "run": self.list_runs(int(job["id"]), limit=1)[0],
            "candidate": self.get_candidate(candidate_row_id) if candidate_row_id else None,
        }
        self._audit(
            "model.update.job.completed" if not error_payload else "model.update.job.failed",
            "model_update_job",
            str(job["id"]),
            actor,
            result,
        )
        return result

    def _import_candidate(
        self,
        *,
        job: dict[str, Any],
        model: dict[str, Any],
        candidate_model_dir: Path,
        plugin_run_id: str,
        actor: str,
    ) -> dict[str, Any]:
        manifest_path = candidate_model_dir / "manifest.yaml"
        if not manifest_path.exists():
            raise ModelUpdateJobError("candidate manifest.yaml not found")
        manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
        if not isinstance(manifest, dict):
            raise ModelUpdateJobError("candidate manifest.yaml must be a YAML object")
        if str(manifest.get("schema")) != "ipp-model/v1":
            raise ModelUpdateJobError("candidate model schema must be ipp-model/v1")
        candidate_model = manifest.get("model") if isinstance(manifest.get("model"), dict) else {}
        candidate_family = manifest.get("model_family") if isinstance(manifest.get("model_family"), dict) else {}
        if candidate_model.get("name") != model.get("model_name"):
            raise ModelUpdateJobError("candidate model.name must match target model")
        if candidate_family.get("family_fingerprint") != model.get("family_fingerprint"):
            raise ModelUpdateJobError("candidate family_fingerprint must match target model")

        archive_bytes = _zip_dir(candidate_model_dir)
        uploaded = ModelRegistry().upload_package_bytes(
            filename=f"{candidate_model.get('name', 'candidate')}-{candidate_model.get('version', 'version')}.zip",
            content=archive_bytes,
            actor=actor,
        )
        try:
            validated = ModelRegistry().validate_version(model_id=int(uploaded.model_id), version_id=int(uploaded.version_id))
        except ModelRegistryError:
            validated = {}

        now = datetime.now(UTC)
        with self.session_factory() as session:
            row = ModelUpdateCandidateModel(
                job_id=int(job["id"]),
                run_id=plugin_run_id,
                model_id=int(job["model_id"]),
                version=str(candidate_model.get("version") or uploaded.version),
                version_id=int(uploaded.version_id),
                candidate_dir=str(candidate_model_dir),
                manifest_json=_json_dumps(manifest),
                artifacts_json=_json_dumps(manifest.get("artifacts") if isinstance(manifest.get("artifacts"), dict) else {}),
                metrics_json=_json_dumps(_load_json_file(candidate_model_dir / "metrics.json")),
                status="VALIDATED",
                reason="candidate imported from model update job",
                created_at=now,
                validated_at=now,
                promoted_at=None,
                rejected_at=None,
            )
            session.add(row)
            session.commit()
            session.refresh(row)
            payload = self._candidate_to_dict(row)
            payload["validated_model_version"] = validated
            self._audit("model.update.candidate.validated", "model_update_candidate", str(row.id), actor, payload)
            return payload

    def _validate_trainer_and_model(self, *, model_id: int, trainer_package_name: str, trainer_package_version: str) -> None:
        metadata_store = MetadataStore(settings.metadata_database)
        version = metadata_store.get_plugin_version(trainer_package_name, trainer_package_version)
        if version is None:
            raise ModelUpdateJobError(f"trainer plugin version not found: {trainer_package_name}@{trainer_package_version}")
        manifest = version.get("manifest") or {}
        model_update = manifest.get("modelUpdate") or manifest.get("model_update") or {}
        if not isinstance(model_update, dict) or not bool(model_update.get("enabled")):
            raise ModelUpdateJobError("selected plugin is not a model update trainer: modelUpdate.enabled must be true")

        model = ModelRegistry().get_model(model_id)
        if model is None:
            raise ModelUpdateJobError(f"target model not found: {model_id}")
        declared_family = str(model_update.get("familyFingerprint") or model_update.get("family_fingerprint") or "").strip()
        if declared_family and declared_family != model.get("family_fingerprint"):
            raise ModelUpdateJobError("trainer modelUpdate.familyFingerprint does not match target model")

    def _model_context(self, *, model: dict[str, Any], current_version: dict[str, Any], current_model_dir: Path) -> dict[str, Any]:
        artifacts = {}
        raw_artifacts = current_version.get("artifacts") or {}
        if isinstance(raw_artifacts, dict):
            for key, value in raw_artifacts.items():
                if not isinstance(value, dict):
                    continue
                path = value.get("path")
                if path:
                    copied = current_model_dir / str(path)
                    artifacts[key] = {**value, "path": str(copied)}
        return {
            "model_name": model.get("model_name"),
            "model_version": current_version.get("version"),
            "family_fingerprint": model.get("family_fingerprint"),
            "model_dir": str(current_model_dir),
            "artifacts": artifacts,
        }

    def _compute_next_run_at(self, row: ModelUpdateJobModel, *, from_time: datetime) -> datetime:
        interval = max(60, int(row.schedule_interval_sec or 86400))
        return from_time + timedelta(seconds=interval)

    def _job_to_dict(self, row: ModelUpdateJobModel) -> dict[str, Any]:
        return {
            "id": row.id,
            "name": row.name,
            "model_id": row.model_id,
            "trainer_package_name": row.trainer_package_name,
            "trainer_package_version": row.trainer_package_version,
            "trainer_instance_id": row.trainer_instance_id,
            "input_bindings": _json_loads(row.input_bindings_json, []),
            "schedule_enabled": bool(row.schedule_enabled),
            "schedule_interval_sec": row.schedule_interval_sec,
            "promote_mode": row.promote_mode,
            "metric_policy": _json_loads(row.metric_policy_json, {}),
            "config": _json_loads(row.config_json, {}),
            "status": row.status,
            "last_run_at": _dt(row.last_run_at),
            "next_run_at": _dt(row.next_run_at),
            "created_at": _dt(row.created_at),
            "updated_at": _dt(row.updated_at),
        }

    def _run_to_dict(self, row: ModelUpdateRunModel) -> dict[str, Any]:
        return {
            "id": row.id,
            "job_id": row.job_id,
            "run_id": row.run_id,
            "status": row.status,
            "trigger_type": row.trigger_type,
            "current_model_version_id": row.current_model_version_id,
            "candidate_id": row.candidate_id,
            "inputs": _json_loads(row.inputs_json, {}),
            "metrics": _json_loads(row.metrics_json, {}),
            "error": _json_loads(row.error_json, {}),
            "started_at": _dt(row.started_at),
            "finished_at": _dt(row.finished_at),
        }

    def _candidate_to_dict(self, row: ModelUpdateCandidateModel) -> dict[str, Any]:
        return {
            "id": row.id,
            "job_id": row.job_id,
            "run_id": row.run_id,
            "model_id": row.model_id,
            "version": row.version,
            "version_id": row.version_id,
            "candidate_dir": row.candidate_dir,
            "manifest": _json_loads(row.manifest_json, {}),
            "artifacts": _json_loads(row.artifacts_json, {}),
            "metrics": _json_loads(row.metrics_json, {}),
            "status": row.status,
            "reason": row.reason,
            "created_at": _dt(row.created_at),
            "validated_at": _dt(row.validated_at),
            "promoted_at": _dt(row.promoted_at),
            "rejected_at": _dt(row.rejected_at),
        }

    def _ensure_compat_columns(self) -> None:
        """Additive schema compatibility for older model-update tables.

        SQLAlchemy create_all() creates missing tables only; it does not add
        missing columns to existing MySQL/SQLite tables. Older deployments that
        have already applied pkg22/pkg23/pkg24 can therefore miss columns added
        later, for example model_update_candidates.version_id. Keep this
        idempotent and additive only.
        """
        inspector = inspect(self.engine)
        table_names = set(inspector.get_table_names())
        statements: list[str] = []

        if "model_update_jobs" in table_names:
            columns = {column["name"] for column in inspector.get_columns("model_update_jobs")}
            if "trainer_package_name" not in columns:
                statements.append("ALTER TABLE model_update_jobs ADD COLUMN trainer_package_name VARCHAR(160) NOT NULL DEFAULT ''")
            if "trainer_package_version" not in columns:
                statements.append("ALTER TABLE model_update_jobs ADD COLUMN trainer_package_version VARCHAR(80) NOT NULL DEFAULT ''")
            if "trainer_instance_id" not in columns:
                statements.append("ALTER TABLE model_update_jobs ADD COLUMN trainer_instance_id INTEGER NULL")
            if "input_bindings_json" not in columns:
                statements.append("ALTER TABLE model_update_jobs ADD COLUMN input_bindings_json TEXT")

        if "model_update_runs" in table_names:
            columns = {column["name"] for column in inspector.get_columns("model_update_runs")}
            if "current_model_version_id" not in columns:
                statements.append("ALTER TABLE model_update_runs ADD COLUMN current_model_version_id INTEGER NULL")
            if "candidate_id" not in columns:
                statements.append("ALTER TABLE model_update_runs ADD COLUMN candidate_id INTEGER NULL")
            if "inputs_json" not in columns:
                statements.append("ALTER TABLE model_update_runs ADD COLUMN inputs_json TEXT")

        if "model_update_candidates" in table_names:
            columns = {column["name"] for column in inspector.get_columns("model_update_candidates")}
            if "version_id" not in columns:
                statements.append("ALTER TABLE model_update_candidates ADD COLUMN version_id INTEGER NULL")
            if "reason" not in columns:
                statements.append("ALTER TABLE model_update_candidates ADD COLUMN reason TEXT")
            if "rejected_at" not in columns:
                statements.append("ALTER TABLE model_update_candidates ADD COLUMN rejected_at DATETIME NULL")

        if not statements:
            return
        with self.engine.begin() as conn:
            for statement in statements:
                conn.execute(text(statement))

    def _audit(self, event_type: str, target_type: str, target_id: str, actor: str, details: dict[str, Any]) -> None:
        try:
            MetadataStore(settings.metadata_database).record_audit_event(
                event_type=event_type,
                target_type=target_type,
                target_id=target_id,
                actor=actor,
                details=details,
            )
        except Exception:
            pass

    def _engine_target(self, database: str | Path) -> str:
        value = str(database)
        if "://" in value:
            return value
        return f"sqlite:///{value}"


def _json_dumps(value: Any) -> str:
    return json.dumps(value if value is not None else {}, ensure_ascii=False, default=str)


def _json_loads(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


def _dt(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _zip_dir(path: Path) -> bytes:
    import io

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for item in path.rglob("*"):
            if item.is_file():
                archive.write(item, item.relative_to(path).as_posix())
    return buffer.getvalue()


def _load_json_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except json.JSONDecodeError:
        return {}


def _summarize_inputs(inputs: dict[str, Any]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for key, value in inputs.items():
        if isinstance(value, dict) and value.get("__ipp_type") == "dataframe":
            meta = value.get("metadata") if isinstance(value.get("metadata"), dict) else {}
            summary[key] = {
                "__ipp_type": "dataframe",
                "rows": meta.get("rows"),
                "columns": value.get("columns"),
                "tags": meta.get("tags"),
                "start_time": meta.get("start_time"),
                "end_time": meta.get("end_time"),
            }
        elif isinstance(value, (list, tuple)):
            summary[key] = {"type": "list", "length": len(value)}
        elif isinstance(value, dict):
            summary[key] = {"type": "object", "keys": list(value.keys())[:50]}
        else:
            summary[key] = value
    return summary
