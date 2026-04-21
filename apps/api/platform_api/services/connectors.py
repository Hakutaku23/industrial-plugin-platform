from datetime import datetime
from typing import Any


class ConnectorError(RuntimeError):
    """Raised when a connector cannot read or write a requested tag."""


class Connector:
    def read_tag(self, tag: str) -> Any:
        raise NotImplementedError

    def write_tag(self, tag: str, value: Any) -> None:
        raise NotImplementedError

    def read_tags(self, tags: list[str]) -> dict[str, Any]:
        return {tag: self.read_tag(tag) for tag in tags}

    def write_tags(self, values: dict[str, Any]) -> dict[str, dict[str, Any]]:
        results: dict[str, dict[str, Any]] = {}
        for tag, value in values.items():
            try:
                self.write_tag(tag, value)
                results[tag] = {"status": "success", "value": value, "reason": ""}
            except Exception as exc:  # noqa: BLE001
                results[tag] = {"status": "failed", "value": value, "reason": str(exc)}
        return results


class MockConnector(Connector):
    def __init__(self, data_source: dict[str, Any], store) -> None:
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

    def read_tags(self, tags: list[str]) -> dict[str, Any]:
        return {tag: self.read_tag(tag) for tag in tags}

    def write_tags(self, values: dict[str, Any]) -> dict[str, dict[str, Any]]:
        results: dict[str, dict[str, Any]] = {}
        config = dict(self.data_source["config"])
        points = dict(config.get("points", {}))
        for tag, value in values.items():
            try:
                ensure_tag_access(self.data_source, tag, "write")
                points[tag] = value
                results[tag] = {"status": "success", "value": value, "reason": ""}
            except Exception as exc:  # noqa: BLE001
                results[tag] = {"status": "failed", "value": value, "reason": str(exc)}
        config["points"] = points
        self.store.update_data_source_config(int(self.data_source["id"]), config)
        self.data_source["config"] = config
        return results


class RedisConnector(Connector):
    def __init__(self, data_source: dict[str, Any]) -> None:
        try:
            import redis
        except ImportError as exc:  # pragma: no cover
            raise ConnectorError("redis package is not installed in the Python environment") from exc

        config = data_source["config"]
        self.data_source = data_source
        self.prefix = str(config.get("keyPrefix", "")).strip()
        raw_separator = config.get("keySeparator", ":")
        self.separator = ":" if raw_separator is None or str(raw_separator) == "" else str(raw_separator)
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
        key = self._key(tag)
        value = self.client.get(key)
        if value is None:
            raise ConnectorError(f"redis key not found: {key}")
        return _coerce_scalar(value)

    def write_tag(self, tag: str, value: Any) -> None:
        ensure_tag_access(self.data_source, tag, "write")
        self.client.set(self._key(tag), value)

    def read_tags(self, tags: list[str]) -> dict[str, Any]:
        for tag in tags:
            ensure_tag_access(self.data_source, tag, "read")
        keys = [self._key(tag) for tag in tags]
        values = self.client.mget(keys)
        result: dict[str, Any] = {}
        for tag, key, value in zip(tags, keys, values):
            if value is None:
                raise ConnectorError(f"redis key not found: {key}")
            result[tag] = _coerce_scalar(value)
        return result

    def write_tags(self, values: dict[str, Any]) -> dict[str, dict[str, Any]]:
        for tag in values:
            ensure_tag_access(self.data_source, tag, "write")
        pipe = self.client.pipeline(transaction=False)
        resolved_keys: list[tuple[str, str, Any]] = []
        for tag, value in values.items():
            key = self._key(tag)
            resolved_keys.append((tag, key, value))
            pipe.set(key, value)
        executed = pipe.execute()
        results: dict[str, dict[str, Any]] = {}
        for (tag, key, value), ok in zip(resolved_keys, executed):
            results[tag] = {
                "status": "success" if ok else "failed",
                "value": value,
                "reason": "" if ok else f"redis pipeline set failed: {key}",
            }
        return results

    def _key(self, tag: str) -> str:
        normalized_tag = str(tag).strip()
        if not self.prefix:
            return normalized_tag

        if self.prefix.endswith(self.separator):
            return f"{self.prefix}{normalized_tag}"
        if normalized_tag.startswith(self.separator):
            return f"{self.prefix}{normalized_tag}"
        return f"{self.prefix}{self.separator}{normalized_tag}"


class TDengineConnector(Connector):
    def __init__(self, data_source: dict[str, Any]) -> None:
        self.data_source = data_source
        config = data_source["config"]
        self.url = str(config.get("url", "http://127.0.0.1:6041")).strip()
        self.user = str(config.get("user", "root")).strip() or "root"
        self.password = str(config.get("password", ""))
        self.database = str(config.get("database", "")).strip()
        self.table_name = str(config.get("table_name", config.get("tableName", ""))).strip()
        self.timezone = str(config.get("timezone", "Asia/Shanghai")).strip() or "Asia/Shanghai"

    def read_tag(self, tag: str) -> Any:
        raise ConnectorError(
            "tdengine history data source requires instance-level query parameters; use query_history() in a future runtime integration",
        )

    def read_tags(self, tags: list[str]) -> dict[str, Any]:
        raise ConnectorError(
            "tdengine history data source requires instance-level query parameters; generic point binding is not enabled yet",
        )

    def write_tag(self, tag: str, value: Any) -> None:
        raise ConnectorError("tdengine data source is read-only")

    def write_tags(self, values: dict[str, Any]) -> dict[str, dict[str, Any]]:
        return {
            tag: {"status": "failed", "value": value, "reason": "tdengine data source is read-only"}
            for tag, value in values.items()
        }

    def query_history(self, tags: list[str], *, start_time: datetime, end_time: datetime):
        try:
            import pandas as pd
            import taosrest
        except ImportError as exc:  # pragma: no cover
            raise ConnectorError("taosrest and pandas must be installed to query TDengine history data") from exc

        normalized_tags = _unique_tags(tags)
        if not normalized_tags:
            raise ConnectorError("tdengine query requires at least one configured tag")
        if not self.database:
            raise ConnectorError("tdengine database is not configured")
        if not self.table_name:
            raise ConnectorError("tdengine table_name is not configured")
        if start_time > end_time:
            raise ConnectorError("tdengine query start_time must be earlier than end_time")

        for tag in normalized_tags:
            ensure_tag_access(self.data_source, tag, "read")

        conn = None
        try:
            conn = taosrest.connect(
                url=self.url,
                user=self.user,
                password=self.password,
                database=self.database,
                timezone=self.timezone,
            )
            cursor = conn.cursor()
            start_time_str = start_time.strftime("%Y-%m-%d %H:%M:%S")
            end_time_str = end_time.strftime("%Y-%m-%d %H:%M:%S")
            if len(normalized_tags) == 1:
                tag_sql = f"point_code='{_sql_quote(normalized_tags[0])}'"
            else:
                quoted = ", ".join(f"'{_sql_quote(tag)}'" for tag in normalized_tags)
                tag_sql = f"point_code IN ({quoted})"
            sql = (
                f"SELECT ts, point_value, point_code FROM {self.table_name} "
                f"WHERE {tag_sql} AND ts >= '{start_time_str}' AND ts <= '{end_time_str}'"
            )
            cursor.execute(sql)
            rows = cursor.fetchall()
            if not rows:
                return pd.DataFrame(columns=["ts", *normalized_tags])
            df = pd.DataFrame(rows, columns=["ts", "point_value", "point_code"])
            wide = (
                df.pivot_table(index="ts", columns="point_code", values="point_value", aggfunc="first")
                .sort_index()
                .reset_index()
            )
            wide.columns.name = None
            return wide
        except Exception as exc:  # noqa: BLE001
            raise ConnectorError(f"tdengine query failed: {exc}") from exc
        finally:
            if conn is not None:
                conn.close()


def build_connector(data_source: dict[str, Any], store) -> Connector:
    connector_type = data_source["connector_type"]
    if connector_type == "mock":
        return MockConnector(data_source, store)
    if connector_type == "redis":
        return RedisConnector(data_source)
    if connector_type == "tdengine":
        return TDengineConnector(data_source)
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


def _unique_tags(tags: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for tag in tags:
        normalized = str(tag).strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result


def _sql_quote(value: str) -> str:
    return value.replace("'", "''")
