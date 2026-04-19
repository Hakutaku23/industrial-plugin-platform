from datetime import UTC, datetime
from typing import Any


def run(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "success",
        "outputs": {
            "test_value": 42,
            "status_text": "no-input plugin executed",
            "generated_at": datetime.now(UTC).isoformat(),
        },
        "logs": ["no-input smoke test completed"],
        "metrics": {
            "input_count": len(payload.get("inputs", {})),
        },
    }
