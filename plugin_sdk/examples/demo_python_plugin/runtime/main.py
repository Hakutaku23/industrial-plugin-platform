from typing import Any


def run(payload: dict[str, Any]) -> dict[str, Any]:
    value = payload.get("inputs", {}).get("value")
    if not isinstance(value, (int, float)):
        return {
            "status": "failed",
            "outputs": {},
            "logs": ["input value must be numeric"],
            "metrics": {},
            "error": {"code": "E_INPUT_INVALID"},
        }

    return {
        "status": "success",
        "outputs": {"doubled": value * 2},
        "logs": ["demo calculation completed"],
        "metrics": {"input_value": value},
    }

