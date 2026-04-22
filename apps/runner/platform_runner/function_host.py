import contextlib
import importlib
import importlib.util
import io
import json
import os
import re
import sys
from pathlib import Path
from typing import Any


_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def main() -> int:
    if len(sys.argv) != 4:
        print("usage: function_host <package_dir> <entry_file> <callable>", file=sys.stderr)
        return 2

    package_dir = Path(sys.argv[1]).resolve()
    entry_file = sys.argv[2]
    callable_name = sys.argv[3]
    entry_path = (package_dir / entry_file).resolve()

    if package_dir not in entry_path.parents:
        print("entry file escapes package directory", file=sys.stderr)
        return 2
    if not entry_path.exists():
        print(f"entry file not found: {entry_file}", file=sys.stderr)
        return 2

    try:
        payload = _read_payload_from_env_or_stdin()
    except json.JSONDecodeError as exc:
        print(f"invalid execution payload: {exc}", file=sys.stderr)
        return 2

    try:
        result = _call_function(package_dir, entry_path, callable_name, payload)
    except Exception as exc:
        print(f"plugin function failed: {exc}", file=sys.stderr)
        return 1

    try:
        _write_result(result)
    except Exception as exc:
        print(f"failed to write plugin result: {exc}", file=sys.stderr)
        return 1
    return 0


def _read_payload_from_env_or_stdin() -> dict[str, Any]:
    input_file = os.getenv("IPP_INPUT_FILE", "").strip()
    if input_file:
        return json.loads(Path(input_file).read_text(encoding="utf-8"))
    return json.loads(sys.stdin.read())


def _write_result(result: Any) -> None:
    result_json = json.dumps(result, ensure_ascii=False)
    result_file = os.getenv("IPP_RESULT_FILE", "").strip()
    if result_file:
        Path(result_file).write_text(result_json, encoding="utf-8")
        return
    print(result_json)


def _call_function(
    package_dir: Path,
    entry_path: Path,
    callable_name: str,
    payload: dict[str, Any],
) -> Any:
    module = _load_entry_module(package_dir, entry_path)
    func = getattr(module, callable_name)
    with contextlib.redirect_stdout(sys.stderr):
        return func(payload)


def _load_entry_module(package_dir: Path, entry_path: Path):
    package_dir_str = str(package_dir)
    if package_dir_str not in sys.path:
        sys.path.insert(0, package_dir_str)

    module_name = _module_name_from_entry(package_dir, entry_path)
    if module_name is not None:
        importlib.invalidate_caches()
        with contextlib.redirect_stdout(sys.stderr):
            if module_name in sys.modules:
                del sys.modules[module_name]
            return importlib.import_module(module_name)

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


if __name__ == "__main__":
    raise SystemExit(main())
