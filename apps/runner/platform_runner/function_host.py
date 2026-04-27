from __future__ import annotations

import contextlib
import importlib
import importlib.util
import json
import os
import re
import sys
import tempfile
import traceback
from pathlib import Path
from typing import Any

_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_MAX_TRACEBACK_CHARS = 12000


def main() -> int:
    _apply_stable_numeric_env_defaults()
    if len(sys.argv) not in {4, 5}:
        _print_stderr("usage: function_host <package_dir> <entry_ref> <callable> [entry_type]")
        return 2

    package_dir = Path(sys.argv[1]).resolve()
    entry_ref = sys.argv[2]
    callable_name = sys.argv[3]
    entry_type = (sys.argv[4] if len(sys.argv) == 5 else os.getenv("IPP_ENTRY_TYPE", "file")).strip().lower()
    if entry_type not in {"file", "module"}:
        _emit_failure(
            code="E_PLUGIN_ENTRY_TYPE_UNSUPPORTED",
            message=f"unsupported entry type: {entry_type}",
        )
        return 0

    try:
        payload = _read_payload_from_env_or_stdin()
    except Exception as exc:  # noqa: BLE001
        _emit_failure(
            code="E_PLUGIN_PAYLOAD_INVALID",
            message=f"invalid execution payload: {exc}",
            exc=exc,
        )
        return 0

    try:
        raw_result = _call_entry(package_dir, entry_ref, entry_type, callable_name, payload)
        result = _normalize_result(raw_result)
        _write_result(result)
        return 0
    except Exception as exc:  # noqa: BLE001
        _emit_failure(
            code=_classify_exception(exc),
            message=str(exc) or exc.__class__.__name__,
            exc=exc,
        )
        return 0


def _apply_stable_numeric_env_defaults() -> None:
    """Set safe defaults before plugin import loads numpy/scikit-learn/OpenBLAS."""
    defaults = {
        'OPENBLAS_NUM_THREADS': '1',
        'OMP_NUM_THREADS': '1',
        'MKL_NUM_THREADS': '1',
        'NUMEXPR_NUM_THREADS': '1',
        'VECLIB_MAXIMUM_THREADS': '1',
        'BLIS_NUM_THREADS': '1',
        'JOBLIB_MULTIPROCESSING': '0',
        'SKLEARN_ALLOW_INVALID_OPENMP': '1',
    }
    for key, value in defaults.items():
        os.environ.setdefault(key, value)


def _read_payload_from_env_or_stdin() -> dict[str, Any]:
    input_file = os.getenv("IPP_INPUT_FILE", "").strip()
    if input_file:
        raw = Path(input_file).read_text(encoding="utf-8")
    else:
        raw = sys.stdin.read()
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("execution payload must be a JSON object")
    return payload


def _call_entry(
    package_dir: Path,
    entry_ref: str,
    entry_type: str,
    callable_name: str,
    payload: dict[str, Any],
) -> Any:
    if entry_type == "module":
        module = _load_entry_module_by_name(package_dir, entry_ref)
    else:
        entry_path = _resolve_entry_path(package_dir=package_dir, entry_file=entry_ref)
        module = _load_entry_module_by_file(package_dir, entry_path)
    try:
        func = getattr(module, callable_name)
    except AttributeError as exc:
        raise AttributeError(f"callable not found: {callable_name}") from exc
    if not callable(func):
        raise TypeError(f"entry attribute is not callable: {callable_name}")
    with contextlib.redirect_stdout(sys.stderr):
        return func(payload)


def _resolve_entry_path(*, package_dir: Path, entry_file: str) -> Path:
    entry_path = (package_dir / entry_file).resolve()
    if package_dir not in entry_path.parents and entry_path != package_dir:
        raise ValueError("entry file escapes package directory")
    if not entry_path.exists():
        raise FileNotFoundError(f"entry file not found: {entry_file}")
    if not entry_path.is_file():
        raise ValueError(f"entry path is not a file: {entry_file}")
    return entry_path


def _load_entry_module_by_name(package_dir: Path, module_name: str):
    if not _valid_module_name(module_name):
        raise ValueError(f"invalid entry module name: {module_name}")
    package_dir_str = str(package_dir)
    if package_dir_str not in sys.path:
        sys.path.insert(0, package_dir_str)
    importlib.invalidate_caches()
    with contextlib.redirect_stdout(sys.stderr):
        if module_name in sys.modules:
            del sys.modules[module_name]
        return importlib.import_module(module_name)


def _load_entry_module_by_file(package_dir: Path, entry_path: Path):
    package_dir_str = str(package_dir)
    if package_dir_str not in sys.path:
        sys.path.insert(0, package_dir_str)

    module_name = _module_name_from_entry(package_dir, entry_path)
    if module_name is not None:
        return _load_entry_module_by_name(package_dir, module_name)

    fallback_name = f"plugin_entry_{abs(hash(entry_path))}"
    spec = importlib.util.spec_from_file_location(fallback_name, entry_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load entry module")

    module = importlib.util.module_from_spec(spec)
    sys.modules[fallback_name] = module
    with contextlib.redirect_stdout(sys.stderr):
        spec.loader.exec_module(module)
    return module


def _module_name_from_entry(package_dir: Path, entry_path: Path) -> str | None:
    try:
        relative = entry_path.relative_to(package_dir)
    except ValueError:
        return None
    if entry_path.suffix != ".py":
        return None
    parts = list(relative.with_suffix("").parts)
    if not parts:
        return None
    if any(not _IDENTIFIER_RE.match(part) for part in parts):
        return None
    return ".".join(parts)


def _valid_module_name(value: str) -> bool:
    parts = str(value or "").split(".")
    return bool(parts) and all(_IDENTIFIER_RE.match(part) for part in parts)


def _normalize_result(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise TypeError("plugin result must be a JSON object")
    status = str(raw.get("status", "failed") or "failed")
    outputs = raw.get("outputs", {})
    metrics = raw.get("metrics", {})
    logs = raw.get("logs", [])
    error = raw.get("error", {})
    if status not in {"success", "partial_success", "failed"}:
        status = "failed"
    if not isinstance(outputs, dict):
        raise TypeError("plugin outputs must be an object")
    if not isinstance(metrics, dict):
        raise TypeError("plugin metrics must be an object")
    if not isinstance(logs, list):
        raise TypeError("plugin logs must be a list")
    if not isinstance(error, dict):
        error = {}
    return {
        "status": status,
        "outputs": outputs,
        "metrics": metrics,
        "logs": [str(item) for item in logs],
        "error": error,
    }


def _emit_failure(*, code: str, message: str, exc: BaseException | None = None) -> None:
    trace = _traceback_text(exc)
    result = {
        "status": "failed",
        "outputs": {},
        "metrics": {
            "host_error_code": code,
            "host_exception_type": exc.__class__.__name__ if exc else "RuntimeError",
        },
        "logs": [
            f"plugin host captured failure: {code}",
            message,
        ],
        "error": {
            "code": code,
            "message": message,
            "traceback": trace,
        },
    }
    _print_stderr(f"[IPP_PLUGIN_ERROR] {code}: {message}")
    if trace:
        _print_stderr(trace)
    try:
        _write_result(result)
    except Exception as write_exc:  # noqa: BLE001
        _print_stderr(f"[IPP_PLUGIN_ERROR] failed to write structured result: {write_exc}")


def _write_result(result: dict[str, Any]) -> None:
    result_json = json.dumps(result, ensure_ascii=False)
    result_file = os.getenv("IPP_RESULT_FILE", "").strip()
    if result_file:
        result_path = Path(result_file)
        result_path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(
            prefix=f".{result_path.name}.",
            suffix=".tmp",
            dir=str(result_path.parent),
            text=True,
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(result_json)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_name, result_path)
        finally:
            try:
                if Path(tmp_name).exists():
                    Path(tmp_name).unlink()
            except OSError:
                pass
        return
    print(result_json)


def _traceback_text(exc: BaseException | None) -> str:
    if exc is None:
        return ""
    text = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    if len(text) > _MAX_TRACEBACK_CHARS:
        return "..." + text[-_MAX_TRACEBACK_CHARS:]
    return text


def _classify_exception(exc: BaseException) -> str:
    if isinstance(exc, FileNotFoundError):
        return "E_PLUGIN_ENTRY_NOT_FOUND"
    if isinstance(exc, AttributeError):
        return "E_PLUGIN_CALLABLE_NOT_FOUND"
    if isinstance(exc, ModuleNotFoundError):
        return "E_PLUGIN_IMPORT_FAILED"
    if isinstance(exc, ImportError):
        return "E_PLUGIN_IMPORT_FAILED"
    if isinstance(exc, TypeError):
        return "E_PLUGIN_CONTRACT_INVALID"
    return "E_PLUGIN_FUNCTION_FAILED"


def _print_stderr(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
