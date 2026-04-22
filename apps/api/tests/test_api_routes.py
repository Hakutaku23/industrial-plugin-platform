import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "apps" / "runner"))

from platform_api.api.routes import router


class ApiRouteAggregationTests(unittest.TestCase):
    def test_split_route_modules_are_registered(self) -> None:
        paths = {getattr(route, "path", "") for route in router.routes}

        expected_paths = {
            "/api/v1/auth/me",
            "/api/v1/packages",
            "/api/v1/data-sources",
            "/api/v1/instances",
            "/api/v1/scheduler/status",
            "/api/v1/runs",
            "/api/v1/audit-events",
        }

        self.assertTrue(expected_paths.issubset(paths))


if __name__ == "__main__":
    unittest.main()
