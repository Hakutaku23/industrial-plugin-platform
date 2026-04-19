import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from platform_runner.executor import LocalPythonRunner


class LocalPythonRunnerTests(unittest.TestCase):
    def test_demo_plugin_executes_in_subprocess(self) -> None:
        repo_root = Path(__file__).resolve().parents[3]
        plugin_dir = repo_root / "plugin_sdk" / "examples" / "demo_python_plugin"

        result = LocalPythonRunner().execute_function(
            package_dir=plugin_dir,
            entry_file="runtime/main.py",
            callable_name="run",
            payload={
                "context": {"run_id": "run-test-001"},
                "inputs": {"value": 21},
                "config": {},
                "capabilities": {"network": False, "filesystem": "scoped", "writeback": False},
            },
            timeout_sec=10,
        )

        self.assertEqual(result.status, "success")
        self.assertEqual(result.outputs["doubled"], 42)


if __name__ == "__main__":
    unittest.main()

