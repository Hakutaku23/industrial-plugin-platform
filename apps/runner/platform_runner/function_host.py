import contextlib
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any


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
        payload = json.loads(sys.stdin.read())
    except json.JSONDecodeError as exc:
        print(f"invalid execution payload: {exc}", file=sys.stderr)
        return 2

    try:
        result = _call_function(entry_path, callable_name, payload)
    except Exception as exc:
        print(f"plugin function failed: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(result, ensure_ascii=False))
    return 0


def _call_function(entry_path: Path, callable_name: str, payload: dict[str, Any]) -> Any:
    module_name = f"plugin_entry_{abs(hash(entry_path))}"
    spec = importlib.util.spec_from_file_location(module_name, entry_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load entry module")

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    with contextlib.redirect_stdout(sys.stderr):
        spec.loader.exec_module(module)
        func = getattr(module, callable_name)
        return func(payload)


if __name__ == "__main__":
    raise SystemExit(main())

