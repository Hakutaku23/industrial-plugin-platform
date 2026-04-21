from __future__ import annotations

import sys
import tempfile
import types
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from platform_api.services.metadata_store import MetadataStore  # noqa: E402


class InstanceNameConflictTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.store = MetadataStore(Path(self.tempdir.name) / 'platform.sqlite3')
        self.store.initialize()
        self._register_package('pkg-a', '0.1.0')
        self._register_package('pkg-b', '0.1.0')

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def _register_package(self, name: str, version: str) -> None:
        package_dir = Path(self.tempdir.name) / name / version
        package_dir.mkdir(parents=True, exist_ok=True)
        metadata = types.SimpleNamespace(
            name=name,
            display_name=name,
            version=version,
            description='test',
        )
        manifest_payload = {
            'apiVersion': 'plugin.platform/v1',
            'kind': 'PluginPackage',
            'metadata': {
                'name': name,
                'displayName': name,
                'version': version,
                'author': 'test',
                'description': 'test',
                'tags': [],
            },
            'spec': {
                'pluginType': 'python',
                'packageFormat': 'directory',
                'entry': {'mode': 'function', 'file': 'runtime/main.py', 'callable': 'run'},
                'runtime': {'timeoutSec': 30},
                'schedule': {'type': 'manual'},
                'inputs': [],
                'outputs': [],
                'permissions': {'network': False, 'filesystem': 'scoped', 'writeback': False, 'subprocess': False},
            },
            'compatibility': {'platformApi': 'v1', 'runnerApi': 'v1', 'supportedEnvironments': []},
        }
        manifest = types.SimpleNamespace(
            metadata=metadata,
            model_dump=lambda **_: manifest_payload,
        )
        record = types.SimpleNamespace(
            digest=f'digest-{name}-{version}',
            package_dir=package_dir,
            manifest=manifest,
        )
        self.store.register_package_upload(record)

    def test_create_duplicate_instance_name_rejected(self) -> None:
        self.store.create_plugin_instance(
            name='demo-instance',
            package_name='pkg-a',
            version='0.1.0',
            input_bindings=[],
            output_bindings=[],
            config={},
            writeback_enabled=False,
        )
        with self.assertRaisesRegex(ValueError, 'plugin instance already exists'):
            self.store.create_plugin_instance(
                name='demo-instance',
                package_name='pkg-b',
                version='0.1.0',
                input_bindings=[],
                output_bindings=[],
                config={},
                writeback_enabled=False,
            )

    def test_update_rename_to_existing_name_rejected(self) -> None:
        first = self.store.create_plugin_instance(
            name='instance-a',
            package_name='pkg-a',
            version='0.1.0',
            input_bindings=[],
            output_bindings=[],
            config={},
            writeback_enabled=False,
        )
        second = self.store.create_plugin_instance(
            name='instance-b',
            package_name='pkg-b',
            version='0.1.0',
            input_bindings=[],
            output_bindings=[],
            config={},
            writeback_enabled=False,
        )
        self.assertIsNotNone(first)
        self.assertIsNotNone(second)
        with self.assertRaisesRegex(ValueError, 'plugin instance already exists'):
            self.store.update_plugin_instance(
                instance_id=int(second.id),
                name='instance-a',
                package_name='pkg-b',
                version='0.1.0',
                input_bindings=[],
                output_bindings=[],
                config={},
                writeback_enabled=False,
            )


if __name__ == '__main__':
    unittest.main()
