from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ModelOperationError(ValueError):
    """Structured model operation error for API and runtime hardening."""

    code: str
    message: str
    http_status: int = 400
    details: dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"

    def to_detail(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "code": self.code,
            "message": self.message,
        }
        if self.details:
            payload["details"] = self.details
        return payload


def model_error(code: str, message: str, *, http_status: int = 400, **details: Any) -> ModelOperationError:
    return ModelOperationError(code=code, message=message, http_status=http_status, details=details)
