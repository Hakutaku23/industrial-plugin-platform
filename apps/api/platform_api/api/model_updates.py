from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from platform_api.security import Principal, require_permission
from platform_api.services.model_update_jobs import ModelUpdateJobError, ModelUpdateJobStore
from platform_api.services.model_update_scheduler import model_update_scheduler_service

router = APIRouter(prefix="/api/v1", tags=["model-updates"])


class ModelUpdateJobPayload(BaseModel):
    name: str = Field(min_length=1)
    model_id: int
    trainer_package_name: str
    trainer_package_version: str
    input_bindings: list[dict[str, Any]] = Field(default_factory=list)
    schedule_enabled: bool = False
    schedule_interval_sec: int = 86400
    promote_mode: str = "manual"
    metric_policy: dict[str, Any] = Field(default_factory=dict)
    config: dict[str, Any] = Field(default_factory=dict)


class PromoteCandidatePayload(BaseModel):
    reason: str = "manual promote candidate"


class RejectCandidatePayload(BaseModel):
    reason: str = "manual reject candidate"


def store() -> ModelUpdateJobStore:
    return ModelUpdateJobStore()


def _raise(exc: Exception, *, status_code: int = 400) -> None:
    raise HTTPException(status_code=status_code, detail={"code": exc.__class__.__name__, "message": str(exc)}) from exc


@router.get("/model-update-jobs")
def list_jobs(principal: Principal = Depends(require_permission("package.read"))) -> dict[str, Any]:
    return {"items": store().list_jobs()}


@router.post("/model-update-jobs", status_code=status.HTTP_201_CREATED)
def create_job(payload: ModelUpdateJobPayload, principal: Principal = Depends(require_permission("package.upload"))) -> dict[str, Any]:
    try:
        return store().create_job(payload.model_dump(), actor=principal.username)
    except ModelUpdateJobError as exc:
        _raise(exc)


@router.get("/model-update-jobs/{job_id}")
def get_job(job_id: int, principal: Principal = Depends(require_permission("package.read"))) -> dict[str, Any]:
    result = store().get_job(job_id)
    if result is None:
        raise HTTPException(status_code=404, detail={"code": "E_MODEL_UPDATE_JOB_NOT_FOUND", "message": f"model update job not found: {job_id}"})
    return result


@router.patch("/model-update-jobs/{job_id}")
def update_job(job_id: int, payload: dict[str, Any], principal: Principal = Depends(require_permission("package.upload"))) -> dict[str, Any]:
    try:
        return store().update_job(job_id, payload, actor=principal.username)
    except ModelUpdateJobError as exc:
        _raise(exc)


@router.delete("/model-update-jobs/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_job(job_id: int, principal: Principal = Depends(require_permission("package.upload"))) -> None:
    if not store().delete_job(job_id, actor=principal.username):
        raise HTTPException(status_code=404, detail={"code": "E_MODEL_UPDATE_JOB_NOT_FOUND", "message": f"model update job not found: {job_id}"})


@router.post("/model-update-jobs/{job_id}/run")
def run_job(job_id: int, principal: Principal = Depends(require_permission("instance.run"))) -> dict[str, Any]:
    try:
        return store().execute_job(job_id, trigger_type="model_update_manual", actor=principal.username)
    except ModelUpdateJobError as exc:
        _raise(exc)


@router.get("/model-update-jobs/{job_id}/runs")
def list_job_runs(
    job_id: int,
    limit: int = Query(50, ge=1, le=500),
    principal: Principal = Depends(require_permission("run.read")),
) -> dict[str, Any]:
    return {"items": store().list_runs(job_id, limit=limit)}


@router.get("/model-update-jobs/{job_id}/candidates")
def list_job_candidates(
    job_id: int,
    limit: int = Query(50, ge=1, le=500),
    principal: Principal = Depends(require_permission("package.read")),
) -> dict[str, Any]:
    return {"items": store().list_candidates(job_id, limit=limit)}


@router.get("/model-update-candidates/{candidate_id}")
def get_candidate(candidate_id: int, principal: Principal = Depends(require_permission("package.read"))) -> dict[str, Any]:
    result = store().get_candidate(candidate_id)
    if result is None:
        raise HTTPException(status_code=404, detail={"code": "E_MODEL_UPDATE_CANDIDATE_NOT_FOUND", "message": f"candidate not found: {candidate_id}"})
    return result


@router.post("/model-update-candidates/{candidate_id}/promote")
def promote_candidate(candidate_id: int, payload: PromoteCandidatePayload | None = None, principal: Principal = Depends(require_permission("package.upload"))) -> dict[str, Any]:
    try:
        return store().promote_candidate(candidate_id, actor=principal.username, reason=(payload.reason if payload else "manual promote candidate"))
    except ModelUpdateJobError as exc:
        _raise(exc)


@router.post("/model-update-candidates/{candidate_id}/reject")
def reject_candidate(candidate_id: int, payload: RejectCandidatePayload | None = None, principal: Principal = Depends(require_permission("package.upload"))) -> dict[str, Any]:
    try:
        return store().reject_candidate(candidate_id, actor=principal.username, reason=(payload.reason if payload else "manual reject candidate"))
    except ModelUpdateJobError as exc:
        _raise(exc)


@router.get("/model-update-scheduler/status")
def scheduler_status(principal: Principal = Depends(require_permission("system.read"))) -> dict[str, Any]:
    return model_update_scheduler_service.status()


@router.get("/model-update-scheduler/due-jobs")
def due_jobs(limit: int = Query(10, ge=1, le=100), principal: Principal = Depends(require_permission("system.read"))) -> dict[str, Any]:
    return {"items": store().list_due_jobs(limit=limit)}


@router.post("/model-update-scheduler/run-due")
def run_due_jobs(limit: int = Query(5, ge=1, le=100), principal: Principal = Depends(require_permission("instance.run"))) -> dict[str, Any]:
    return store().run_due_jobs(limit=limit, actor=principal.username)
