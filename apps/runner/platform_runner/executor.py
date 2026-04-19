import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class RunnerExecutionError(RuntimeError):
    """Raised when a plugin process cannot produce a valid standard result."""


@dataclass(frozen=True)
class RunnerResult:
    status: str
    outputs: dict[str, Any]
    logs: list[str]
    metrics: dict[str, Any]
    stderr: str
    returncode: int


class LocalPythonRunner:
    def execute_function(
        self,
        package_dir: Path,
        entry_file: str,
        callable_name: str,
        payload: dict[str, Any],
        timeout_sec: int,
    ) -> RunnerResult:
        runner_root = Path(__file__).resolve().parents[1]
        env = os.environ.copy()
        existing_pythonpath = env.get("PYTHONPATH")
        env["PYTHONPATH"] = (
            str(runner_root)
            if not existing_pythonpath
            else f"{runner_root}{os.pathsep}{existing_pythonpath}"
        )

        command = [
            sys.executable,
            "-m",
            "platform_runner.function_host",
            str(package_dir),
            entry_file,
            callable_name,
        ]
        completed = subprocess.run(
            command,
            input=json.dumps(payload),
            text=True,
            capture_output=True,
            timeout=timeout_sec,
            cwd=package_dir,
            env=env,
            check=False,
        )

        if completed.returncode != 0:
            raise RunnerExecutionError(
                f"plugin process failed with exit code {completed.returncode}: "
                f"{completed.stderr[-1000:]}"
            )

        try:
            raw = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise RunnerExecutionError("plugin stdout is not valid JSON") from exc

        if not isinstance(raw, dict):
            raise RunnerExecutionError("plugin result must be a JSON object")

        outputs = raw.get("outputs", {})
        logs = raw.get("logs", [])
        metrics = raw.get("metrics", {})
        if not isinstance(outputs, dict):
            raise RunnerExecutionError("plugin outputs must be an object")
        if not isinstance(logs, list):
            raise RunnerExecutionError("plugin logs must be a list")
        if not isinstance(metrics, dict):
            raise RunnerExecutionError("plugin metrics must be an object")

        return RunnerResult(
            status=str(raw.get("status", "failed")),
            outputs=outputs,
            logs=[str(item) for item in logs],
            metrics=metrics,
            stderr=completed.stderr,
            returncode=completed.returncode,
        )

