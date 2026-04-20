import unittest
from unittest.mock import patch

from platform_api.services.execution import _resolve_bound_inputs


class DummyStore:
    def get_data_source(self, data_source_id: int):
        return {
            "id": data_source_id,
            "name": "redis-demo",
            "connector_type": "redis",
            "config": {},
            "read_enabled": True,
            "write_enabled": False,
            "status": "configured",
        }


class DummyConnector:
    def read_tags(self, tags):
        return {tag: f"value-for-{tag}" for tag in tags}


class ExecutionBatchFanoutTests(unittest.TestCase):
    def test_resolve_bound_inputs_expands_named_map_batch_without_input_name(self):
        instance = {
            "input_bindings": [
                {
                    "binding_type": "batch",
                    "data_source_id": 1,
                    "output_format": "named-map",
                    "source_mappings": [
                        {"tag": "tag:001", "key": "input_001"},
                        {"tag": "tag:014", "key": "input_014"},
                    ],
                }
            ]
        }

        with patch('platform_api.services.execution.build_connector', return_value=DummyConnector()):
            resolved = _resolve_bound_inputs(instance, DummyStore())

        self.assertEqual(
            resolved,
            {
                "input_001": "value-for-tag:001",
                "input_014": "value-for-tag:014",
            },
        )


if __name__ == '__main__':
    unittest.main()
