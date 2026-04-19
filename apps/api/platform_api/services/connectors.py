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
        ensure_tag_access(self.data_source, tag, "read")

        points = self.data_source["config"].get("points", {})
        if tag not in points:
            raise ConnectorError(f"mock tag not found: {tag}")
        return points[tag]

    def write_tag(self, tag: str, value: Any) -> None:
        ensure_tag_access(self.data_source, tag, "write")

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
        ensure_tag_access(self.data_source, tag, "read")
        value = self.client.get(self._key(tag))
        if value is None:
            raise ConnectorError(f"redis key not found: {tag}")
        return _coerce_scalar(value)

    def write_tag(self, tag: str, value: Any) -> None:
        ensure_tag_access(self.data_source, tag, "write")
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


def ensure_tag_access(data_source: dict[str, Any], tag: str, operation: str) -> None:
    if operation == "read":
        if not data_source["read_enabled"]:
            raise ConnectorError("data source is not readable")
        if not _has_point_policy(data_source, "read"):
            return
        if _tag_allowed_by_catalog(data_source, tag, "read") or tag in _tag_list(data_source, "read"):
            return
        raise ConnectorError(f"tag is not configured as readable: {tag}")

    if operation == "write":
        if not data_source["write_enabled"]:
            raise ConnectorError("data source is not writable")
        if not _has_point_policy(data_source, "write"):
            return
        if _tag_allowed_by_catalog(data_source, tag, "write") or tag in _tag_list(data_source, "write"):
            return
        raise ConnectorError(f"tag is not configured as writable: {tag}")

    raise ConnectorError(f"unsupported tag operation: {operation}")


def _has_point_policy(data_source: dict[str, Any], operation: str) -> bool:
    config = data_source["config"]
    catalog = config.get("pointCatalog") or config.get("point_catalog")
    if isinstance(catalog, list) and catalog:
        return True
    return bool(_tag_list(data_source, operation))


def _tag_allowed_by_catalog(data_source: dict[str, Any], tag: str, operation: str) -> bool:
    config = data_source["config"]
    catalog = config.get("pointCatalog") or config.get("point_catalog")
    if not isinstance(catalog, list):
        return False

    if operation == "read":
        tag_fields = ("readTag", "read_tag")
        permission_fields = ("canRead", "can_read")
    else:
        tag_fields = ("writeTag", "write_tag")
        permission_fields = ("canWrite", "can_write")

    for point in catalog:
        if not isinstance(point, dict):
            continue
        point_tag = _first_string(point, tag_fields)
        if point_tag != tag:
            continue
        return _first_bool(point, permission_fields, True)
    return False


def _tag_list(data_source: dict[str, Any], operation: str) -> set[str]:
    config = data_source["config"]
    keys = ("readTags", "read_tags") if operation == "read" else ("writeTags", "write_tags")
    tags: set[str] = set()
    for key in keys:
        value = config.get(key)
        if isinstance(value, list):
            tags.update(item for item in value if isinstance(item, str) and item)
    return tags


def _first_string(record: dict[str, Any], fields: tuple[str, ...]) -> str | None:
    for field in fields:
        value = record.get(field)
        if isinstance(value, str) and value:
            return value
    return None


def _first_bool(record: dict[str, Any], fields: tuple[str, ...], default: bool) -> bool:
    for field in fields:
        value = record.get(field)
        if isinstance(value, bool):
            return value
    return default


def _coerce_scalar(value: str) -> Any:
    try:
        if "." in value:
            return float(value)
        return int(value)
    except ValueError:
        return value
