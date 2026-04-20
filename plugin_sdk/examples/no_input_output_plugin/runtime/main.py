from typing import Any


def run(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "success",
        "outputs": {"test_value": 42},
        "logs": ["no input output plugin completed"],
        "metrics": {},
    }
