from typing import Any

from platform_api.services.metadata_store import MetadataStore


class ConnectorError(RuntimeError):
    """Raised when a connector cannot read or write a requested tag."""


class Connector:
    def read_tag(self, tag: str) -> Any:
        raise NotImplementedError

    def write_tag(self, tag: str, value: Any) -> None:
        raise NotImplementedError


class MockConnector(Connector):
    def __init__(self, data_source: dict[str, Any], store: MetadataStore) -> None:
        self.data_source = data_source
        self.store = store

    def read_tag(self, tag: str) -> Any:
        if not self.data_source["read_enabled"]:
            raise ConnectorError("data source is not readable")

        points = self.data_source["config"].get("points", {})
        if tag not in points:
            raise ConnectorError(f"mock tag not found: {tag}")
        return points[tag]

    def write_tag(self, tag: str, value: Any) -> None:
        if not self.data_source["write_enabled"]:
            raise ConnectorError("data source is not writable")

        config = dict(self.data_source["config"])
        points = dict(config.get("points", {}))
        points[tag] = value
        config["points"] = points
        self.store.update_data_source_config(int(self.data_source["id"]), config)
        self.data_source["config"] = config


class RedisConnector(Connector):
    def __init__(self, data_source: dict[str, Any]) -> None:
        try:
            import redis
        except ImportError as exc:
            raise ConnectorError("redis package is not installed in the Python environment") from exc

        config = data_source["config"]
        self.data_source = data_source
        self.prefix = str(config.get("keyPrefix", ""))
        self.client = redis.Redis(
            host=config.get("host", "127.0.0.1"),
            port=int(config.get("port", 6379)),
            db=int(config.get("db", 0)),
            password=config.get("password") or None,
            decode_responses=True,
            socket_connect_timeout=float(config.get("connectTimeoutSec", 2)),
            socket_timeout=float(config.get("socketTimeoutSec", 2)),
        )

    def read_tag(self, tag: str) -> Any:
        if not self.data_source["read_enabled"]:
            raise ConnectorError("data source is not readable")
        value = self.client.get(self._key(tag))
        if value is None:
            raise ConnectorError(f"redis key not found: {tag}")
        return _coerce_scalar(value)

    def write_tag(self, tag: str, value: Any) -> None:
        if not self.data_source["write_enabled"]:
            raise ConnectorError("data source is not writable")
        self.client.set(self._key(tag), value)

    def _key(self, tag: str) -> str:
        return f"{self.prefix}{tag}"


def build_connector(data_source: dict[str, Any], store: MetadataStore) -> Connector:
    connector_type = data_source["connector_type"]
    if connector_type == "mock":
        return MockConnector(data_source, store)
    if connector_type == "redis":
        return RedisConnector(data_source)
    raise ConnectorError(f"unsupported connector type: {connector_type}")


def _coerce_scalar(value: str) -> Any:
    try:
        if "." in value:
            return float(value)
        return int(value)
    except ValueError:
        return value

