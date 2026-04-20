import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class FunctionHostPackageImportTests(unittest.TestCase):
    def _run_host(self, package_dir: Path, entry_file: str, payload: dict[str, object]) -> subprocess.CompletedProcess[str]:
        root_dir = Path(__file__).resolve().parents[1]
        env = dict()
        env.update(**__import__('os').environ)
        existing_pythonpath = env.get("PYTHONPATH")
        env["PYTHONPATH"] = str(root_dir) if not existing_pythonpath else f"{root_dir}{__import__('os').pathsep}{existing_pythonpath}"
        return subprocess.run(
            [sys.executable, "-m", "platform_runner.function_host", str(package_dir), entry_file, "run"],
            input=json.dumps(payload),
            text=True,
            capture_output=True,
            check=False,
            cwd=package_dir,
            env=env,
        )

    def test_supports_relative_imports_from_package_entry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            package_dir = Path(tmp_dir)
            runtime_dir = package_dir / "runtime"
            runtime_dir.mkdir(parents=True)
            (runtime_dir / "__init__.py").write_text("", encoding="utf-8")
            (runtime_dir / "helpers.py").write_text(
                "def scale(value):\n    return value * 2\n",
                encoding="utf-8",
            )
            (runtime_dir / "main.py").write_text(
                "from .helpers import scale\n\n"
                "def run(payload):\n"
                "    value = payload['inputs']['x']\n"
                "    return {'status': 'success', 'outputs': {'y': scale(value)}, 'logs': [], 'metrics': {}}\n",
                encoding="utf-8",
            )
            completed = self._run_host(package_dir, "runtime/main.py", {"inputs": {"x": 21}})
            self.assertEqual(completed.returncode, 0, msg=completed.stderr)
            result = json.loads(completed.stdout)
            self.assertEqual(result["outputs"]["y"], 42)

    def test_falls_back_for_non_module_style_entry_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            package_dir = Path(tmp_dir)
            weird_dir = package_dir / "runtime-assets"
            weird_dir.mkdir(parents=True)
            (weird_dir / "main.py").write_text(
                "def run(payload):\n"
                "    return {'status': 'success', 'outputs': {'ok': True}, 'logs': [], 'metrics': {}}\n",
                encoding="utf-8",
            )
            completed = self._run_host(package_dir, "runtime-assets/main.py", {"inputs": {}})
            self.assertEqual(completed.returncode, 0, msg=completed.stderr)
            result = json.loads(completed.stdout)
            self.assertTrue(result["outputs"]["ok"])


if __name__ == "__main__":
    unittest.main()
