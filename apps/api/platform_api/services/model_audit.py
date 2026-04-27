from __future__ import annotations

from typing import Any

from platform_api.core.config import settings
from platform_api.services.metadata_store import MetadataStore


def record_model_audit_event(
    *,
    event_type: str,
    target_type: str,
    target_id: str,
    actor: str = "local-dev",
    details: dict[str, Any] | None = None,
) -> None:
    """Best-effort model audit event writer.

    Audit failure must never block model promotion, binding or runtime execution.
    """
    try:
        MetadataStore(settings.metadata_database).record_audit_event(
            event_type=event_type,
            target_type=target_type,
            target_id=target_id,
            actor=actor,
            details=details or {},
        )
    except Exception:
        pass
