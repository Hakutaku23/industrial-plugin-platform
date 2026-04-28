from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import inspect, text

from platform_api.services.model_registry import ModelRegistry


class ModelDeletionError(ValueError):
    def __init__(self, code: str, message: str, *, http_status: int = 400, detail: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status
        self.detail = detail or {}

    def to_detail(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, **self.detail}


@dataclass(frozen=True)
class _TableInfo:
    exists: bool
    columns: set[str]


class ModelDeletionService:
    """Delete unused model records and their model-store files.

    Deletion is intentionally conservative:
    - models still bound by plugin instances are blocked;
    - models used by model update jobs are blocked;
    - active models require force=True even if otherwise unused;
    - files are moved to an internal trash directory before DB deletion, then purged
      after the DB transaction succeeds.
    """

    def __init__(self, registry: ModelRegistry | None = None) -> None:
        self.registry = registry or ModelRegistry()
        self.registry.initialize()
        self.engine = self.registry.engine
        self.storage_root = self.registry.storage_root.resolve()

    def check_delete(self, model_id: int) -> dict[str, Any]:
        model = self._get_model_record(model_id)
        if model is None:
            raise ModelDeletionError(
                "E_MODEL_NOT_FOUND",
                f"model not found: {model_id}",
                http_status=404,
            )

        model_name = str(model["model_name"])
        active_version_id = model.get("active_version_id")
        counts = self._reference_counts(model_id)
        blockers: list[dict[str, Any]] = []
        warnings: list[dict[str, Any]] = []

        if counts.get("model_bindings", 0) > 0:
            blockers.append(
                {
                    "code": "E_MODEL_HAS_BINDINGS",
                    "message": "模型仍被插件实例绑定，禁止删除。请先解除实例模型绑定。",
                    "count": counts["model_bindings"],
                }
            )
        if counts.get("model_update_jobs", 0) > 0:
            blockers.append(
                {
                    "code": "E_MODEL_HAS_UPDATE_JOBS",
                    "message": "模型仍被模型更新任务引用，禁止删除。请先删除或停用相关模型更新任务。",
                    "count": counts["model_update_jobs"],
                }
            )

        requires_force = bool(active_version_id)
        if requires_force:
            warnings.append(
                {
                    "code": "W_MODEL_HAS_ACTIVE_VERSION",
                    "message": "模型存在 active 版本。若确认没有实例或更新任务引用，可强制删除。",
                    "active_version_id": active_version_id,
                }
            )

        model_dir = self._model_dir(model_name)
        storage = self._storage_summary(model_dir)
        deletable = not blockers and not requires_force
        can_delete_with_force = not blockers
        return {
            "model": {
                "id": int(model["id"]),
                "model_name": model_name,
                "display_name": model.get("display_name"),
                "family_fingerprint": model.get("family_fingerprint"),
                "status": model.get("status"),
                "active_version_id": active_version_id,
            },
            "deletable": deletable,
            "requires_force": requires_force,
            "can_delete_with_force": can_delete_with_force,
            "blockers": blockers,
            "warnings": warnings,
            "references": counts,
            "storage": storage,
        }

    def delete_model(
        self,
        *,
        model_id: int,
        force: bool = False,
        delete_files: bool = True,
        actor: str = "local-dev",
        reason: str = "manual model delete",
    ) -> dict[str, Any]:
        check = self.check_delete(model_id)
        model = check["model"]
        model_name = str(model["model_name"])
        if check["blockers"]:
            raise ModelDeletionError(
                "E_MODEL_DELETE_BLOCKED",
                "model is still referenced and cannot be deleted",
                http_status=409,
                detail={"check": check},
            )
        if check["requires_force"] and not force:
            raise ModelDeletionError(
                "E_MODEL_DELETE_REQUIRES_FORCE",
                "model has active version; set force=true after confirming it is not referenced",
                http_status=409,
                detail={"check": check},
            )

        deleted_files = False
        trash_dir: Path | None = None
        model_dir = self._model_dir(model_name)
        if delete_files and model_dir.exists():
            trash_dir = self._move_model_dir_to_trash(model_dir=model_dir, model_id=model_id, model_name=model_name)
            deleted_files = True

        try:
            with self.engine.begin() as connection:
                # Delete optional model-update candidate rows first. Jobs referencing
                # this model are blocked, so these are orphan/history rows only.
                self._safe_delete(connection, "model_update_candidates", "model_id", model_id)
                self._safe_delete(connection, "model_deployments", "model_id", model_id)
                self._safe_delete(connection, "model_bindings", "model_id", model_id)
                self._safe_delete(connection, "model_versions", "model_id", model_id)
                result = connection.execute(text("DELETE FROM model_records WHERE id = :model_id"), {"model_id": model_id})
                if result.rowcount == 0:
                    raise ModelDeletionError("E_MODEL_NOT_FOUND", f"model not found: {model_id}", http_status=404)
        except Exception:
            if trash_dir is not None:
                self._restore_model_dir_from_trash(model_dir=model_dir, trash_dir=trash_dir)
            raise

        trash_purged = False
        if trash_dir is not None and trash_dir.exists():
            shutil.rmtree(trash_dir, ignore_errors=True)
            trash_purged = not trash_dir.exists()

        return {
            "deleted": True,
            "model_id": model_id,
            "model_name": model_name,
            "delete_files": bool(delete_files),
            "deleted_files": deleted_files,
            "trash_purged": trash_purged,
            "reason": reason,
            "actor": actor,
            "deleted_at": datetime.now(UTC).isoformat(),
            "preflight": check,
        }

    def _get_model_record(self, model_id: int) -> dict[str, Any] | None:
        with self.engine.connect() as connection:
            row = connection.execute(
                text(
                    "SELECT id, model_name, display_name, family_fingerprint, status, active_version_id "
                    "FROM model_records WHERE id = :model_id"
                ),
                {"model_id": model_id},
            ).mappings().first()
            return dict(row) if row is not None else None

    def _reference_counts(self, model_id: int) -> dict[str, int]:
        return {
            "model_versions": self._count_if_column("model_versions", "model_id", model_id),
            "model_deployments": self._count_if_column("model_deployments", "model_id", model_id),
            "model_bindings": self._count_if_column("model_bindings", "model_id", model_id),
            "model_update_jobs": self._count_if_column("model_update_jobs", "model_id", model_id),
            "model_update_candidates": self._count_if_column("model_update_candidates", "model_id", model_id),
        }

    def _table_info(self, table_name: str) -> _TableInfo:
        inspector = inspect(self.engine)
        if not inspector.has_table(table_name):
            return _TableInfo(False, set())
        return _TableInfo(True, {column["name"] for column in inspector.get_columns(table_name)})

    def _count_if_column(self, table_name: str, column_name: str, value: int) -> int:
        info = self._table_info(table_name)
        if not info.exists or column_name not in info.columns:
            return 0
        with self.engine.connect() as connection:
            row = connection.execute(
                text(f"SELECT COUNT(*) AS count_value FROM {table_name} WHERE {column_name} = :value"),
                {"value": value},
            ).mappings().first()
            return int(row["count_value"] if row is not None else 0)

    def _safe_delete(self, connection, table_name: str, column_name: str, value: int) -> None:
        info = self._table_info(table_name)
        if not info.exists or column_name not in info.columns:
            return
        connection.execute(text(f"DELETE FROM {table_name} WHERE {column_name} = :value"), {"value": value})

    def _model_dir(self, model_name: str) -> Path:
        path = (self.storage_root / model_name).resolve()
        if self.storage_root not in path.parents and path != self.storage_root:
            raise ModelDeletionError("E_MODEL_STORAGE_PATH_UNSAFE", "resolved model directory escapes model store")
        return path

    def _storage_summary(self, model_dir: Path) -> dict[str, Any]:
        if not model_dir.exists():
            return {"model_dir": str(model_dir), "exists": False, "file_count": 0, "total_bytes": 0}
        if not model_dir.is_dir():
            return {"model_dir": str(model_dir), "exists": True, "file_count": 1, "total_bytes": model_dir.stat().st_size}
        file_count = 0
        total_bytes = 0
        for path in model_dir.rglob("*"):
            if path.is_file():
                file_count += 1
                try:
                    total_bytes += path.stat().st_size
                except OSError:
                    pass
        return {"model_dir": str(model_dir), "exists": True, "file_count": file_count, "total_bytes": total_bytes}

    def _move_model_dir_to_trash(self, *, model_dir: Path, model_id: int, model_name: str) -> Path:
        if not model_dir.exists():
            raise ModelDeletionError("E_MODEL_STORAGE_NOT_FOUND", f"model directory not found: {model_dir}")
        if model_dir == self.storage_root:
            raise ModelDeletionError("E_MODEL_STORAGE_PATH_UNSAFE", "refuse to delete model store root")
        trash_root = self.storage_root / "_deleted"
        trash_root.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
        safe_name = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in model_name)
        trash_dir = trash_root / f"{safe_name}-{model_id}-{timestamp}"
        shutil.move(str(model_dir), str(trash_dir))
        return trash_dir

    def _restore_model_dir_from_trash(self, *, model_dir: Path, trash_dir: Path) -> None:
        try:
            if trash_dir.exists() and not model_dir.exists():
                shutil.move(str(trash_dir), str(model_dir))
        except Exception:
            # Best effort only. Raising here would hide the original DB error.
            pass
