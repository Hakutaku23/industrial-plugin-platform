import unittest

from platform_api.services.instance_validation import (
    BindingValidationError,
    validate_execution_inputs,
    validate_instance_bindings,
)
from platform_api.services.manifest import PluginManifest


def build_manifest() -> PluginManifest:
    return PluginManifest.model_validate(
        {
            "apiVersion": "plugin.platform/v1",
            "kind": "PluginPackage",
            "metadata": {
                "name": "demo-plugin",
                "displayName": "Demo Plugin",
                "version": "1.0.0",
                "author": "tester",
                "description": "demo",
                "tags": [],
            },
            "spec": {
                "pluginType": "python",
                "packageFormat": "directory",
                "entry": {"mode": "function", "file": "main.py", "callable": "run"},
                "runtime": {"timeoutSec": 30},
                "schedule": {"type": "manual"},
                "inputs": [
                    {"name": "input_001", "type": "number", "required": True},
                    {"name": "input_014", "type": "number", "required": True},
                    {"name": "window", "type": "object", "required": False},
                ],
                "outputs": [
                    {"name": "output_001", "type": "number", "required": False},
                ],
                "permissions": {
                    "network": False,
                    "filesystem": "scoped",
                    "writeback": False,
                    "subprocess": False,
                },
            },
            "compatibility": {
                "platformApi": "0.1.0",
                "runnerApi": "0.1.0",
                "supportedEnvironments": ["dev"],
            },
        }
    )


class InstanceValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.manifest = build_manifest()

    def test_validate_instance_bindings_rejects_missing_required_input(self) -> None:
        with self.assertRaises(BindingValidationError) as ctx:
            validate_instance_bindings(
                manifest=self.manifest,
                input_bindings=[
                    {
                        "input_name": "input_001",
                        "data_source_id": 1,
                        "source_tag": "tag:001",
                    }
                ],
                output_bindings=[],
            )
        self.assertIn("input_014", str(ctx.exception))

    def test_validate_instance_bindings_rejects_unknown_output(self) -> None:
        with self.assertRaises(BindingValidationError) as ctx:
            validate_instance_bindings(
                manifest=self.manifest,
                input_bindings=[
                    {
                        "input_name": "input_001",
                        "data_source_id": 1,
                        "source_tag": "tag:001",
                    },
                    {
                        "input_name": "input_014",
                        "data_source_id": 1,
                        "source_tag": "tag:014",
                    },
                ],
                output_bindings=[
                    {
                        "output_name": "unknown_output",
                        "data_source_id": 1,
                        "target_tag": "tag:out",
                    }
                ],
            )
        self.assertIn("unknown_output", str(ctx.exception))

    def test_validate_execution_inputs_rejects_missing_required_input(self) -> None:
        with self.assertRaises(BindingValidationError) as ctx:
            validate_execution_inputs(
                manifest=self.manifest,
                inputs={"input_001": 1.0},
            )
        self.assertIn("input_014", str(ctx.exception))

    def test_validate_execution_inputs_rejects_unknown_input(self) -> None:
        with self.assertRaises(BindingValidationError) as ctx:
            validate_execution_inputs(
                manifest=self.manifest,
                inputs={
                    "input_001": 1.0,
                    "input_014": 2.0,
                    "extra": 3.0,
                },
            )
        self.assertIn("extra", str(ctx.exception))

    def test_validate_instance_bindings_accepts_complete_required_bindings(self) -> None:
        validate_instance_bindings(
            manifest=self.manifest,
            input_bindings=[
                {
                    "input_name": "input_001",
                    "data_source_id": 1,
                    "source_tag": "tag:001",
                },
                {
                    "input_name": "input_014",
                    "data_source_id": 1,
                    "source_tag": "tag:014",
                },
                {
                    "binding_type": "batch",
                    "input_name": "window",
                    "data_source_id": 1,
                    "source_tags": ["tag:100", "tag:101"],
                    "output_format": "ordered-list",
                },
            ],
            output_bindings=[
                {
                    "output_name": "output_001",
                    "data_source_id": 1,
                    "target_tag": "tag:out",
                }
            ],
        )


if __name__ == "__main__":
    unittest.main()
