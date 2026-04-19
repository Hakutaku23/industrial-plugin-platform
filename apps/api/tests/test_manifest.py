import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from platform_api.services.manifest import ManifestError, load_manifest, parse_manifest_text


class ManifestTests(unittest.TestCase):
    def test_demo_manifest_loads(self) -> None:
        manifest_path = (
            Path(__file__).resolve().parents[3]
            / "plugin_sdk"
            / "examples"
            / "demo_python_plugin"
            / "manifest.yaml"
        )
        manifest = load_manifest(manifest_path)

        self.assertEqual(manifest.metadata.name, "demo-python-plugin")
        self.assertEqual(manifest.spec.plugin_type, "python")
        self.assertEqual(manifest.spec.entry.mode, "function")

    def test_reserved_output_name_is_rejected(self) -> None:
        content = """
apiVersion: plugin.platform/v1
kind: PluginPackage
metadata:
  name: bad-plugin
  displayName: Bad Plugin
  version: 0.1.0
  author: Dev
  description: Bad output name
spec:
  pluginType: python
  packageFormat: zip
  entry:
    mode: function
    file: runtime/main.py
    callable: run
  runtime:
    timeoutSec: 20
  schedule:
    type: manual
  inputs: []
  outputs:
    - name: status
      type: string
  permissions:
    network: false
    filesystem: scoped
    writeback: false
compatibility:
  platformApi: ">=0.1.0"
  runnerApi: ">=0.1.0"
"""
        with self.assertRaises(ManifestError):
            parse_manifest_text(content)


if __name__ == "__main__":
    unittest.main()

