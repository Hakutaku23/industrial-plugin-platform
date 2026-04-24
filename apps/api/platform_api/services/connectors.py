from __future__ import annotations

import logging
import re
import time
from datetime import datetime, timedelta
from typing import Any, Callable, TypeVar

from platform_api.core.config import settings

logger = logging.getLogger(__name__)
_T = TypeVar("_T")


class ConnectorError(RuntimeError):
    """Raised when a connector cannot read or write a requested tag."""


class Connector:
    def __init__(self, data_source: dict[str, Any], store=None) -> None:
        self.data_source = data_source
        self.store = store

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

    @property
    def _connector_type(self) -> str:
        return str(self.data_source.get("connector_type", "unknown"))

    @property
    def _data_source_id(self) -> int:
        return int(self.data_source.get("id", -1))

    def _record_connector_event(self, *, event_type: str, operation: str, attempt: int, details: dict[str, Any]) -> None:
        if self.store is None:
            return
        payload = {
            "data_source_id": self._data_source_id,
            "data_source_name": self.data_source.get("name"),
            "connector_type": self._connector_type,
            "operation": operation,
            "attempt": attempt,
            **details,
        }
        try:
            self.store.record_audit_event(
                event_type=event_type,
                target_type="data_source",
                target_id=str(self._data_source_id),
                details=payload,
            )
        except Exception:  # noqa: BLE001
            logger.exception(
                "failed to record connector audit event %s for data source %s",
                event_type,
                self._data_source_id,
            )

    def _retry(self, *, operation: str, target: str, func: Callable[[], _T]) -> _T:
        max_attempts = max(1, int(settings.connectors.retry.max_attempts))
        base_delay_sec = max(0.0, float(settings.connectors.retry.base_delay_sec))
        max_delay_sec = max(base_delay_sec, float(settings.connectors.retry.max_delay_sec))
        last_error: Exception | None = None

        for attempt in range(1, max_attempts + 1):
            try:
                result = func()
                if attempt > 1:
                    self._record_connector_event(
                        event_type="connector.operation.recovered",
                        operation=operation,
                        attempt=attempt,
                        details={"target": target, "message": "connector operation recovered after retry"},
                    )
                return result
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                if attempt >= max_attempts:
                    self._record_connector_event(
                        event_type="connector.operation.failed",
                        operation=operation,
                        attempt=attempt,
                        details={"target": target, "message": str(exc)},
                    )
                    raise ConnectorError(
                        f"{self._connector_type} {operation} failed after {attempt} attempt(s): {exc}"
                    ) from exc

                delay = min(max_delay_sec, base_delay_sec * (2 ** (attempt - 1)))
                self._record_connector_event(
                    event_type="connector.operation.retrying",
                    operation=operation,
                    attempt=attempt,
                    details={"target": target, "message": str(exc), "retry_delay_sec": delay},
                )
                if delay > 0:
                    time.sleep(delay)

        if last_error is not None:
            raise ConnectorError(str(last_error)) from last_error
        raise ConnectorError(f"{self._connector_type} {operation} failed")


class MockConnector(Connector):
    def __init__(self, data_source: dict[str, Any], store) -> None:
        super().__init__(data_source, store)

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
    def __init__(self, data_source: dict[str, Any], store=None) -> None:
        super().__init__(data_source, store)
        try:
            import redis
        except ImportError as exc:  # pragma: no cover
            raise ConnectorError("redis package is not installed in the Python environment") from exc

        config = data_source["config"]
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
        value = self._retry(
            operation="read_tag",
            target=key,
            func=lambda: self.client.get(key),
        )
        if value is None:
            raise ConnectorError(f"redis key not found: {key}")
        return _coerce_scalar(value)

    def write_tag(self, tag: str, value: Any) -> None:
        ensure_tag_access(self.data_source, tag, "write")
        key = self._key(tag)
        ok = self._retry(
            operation="write_tag",
            target=key,
            func=lambda: self.client.set(key, value),
        )
        if not ok:
            raise ConnectorError(f"redis set returned false: {key}")

    def read_tags(self, tags: list[str]) -> dict[str, Any]:
        for tag in tags:
            ensure_tag_access(self.data_source, tag, "read")
        keys = [self._key(tag) for tag in tags]
        values = self._retry(
            operation="read_tags",
            target=", ".join(keys[:5]) + (" ..." if len(keys) > 5 else ""),
            func=lambda: self.client.mget(keys),
        )
        result: dict[str, Any] = {}
        for tag, key, value in zip(tags, keys, values):
            if value is None:
                raise ConnectorError(f"redis key not found: {key}")
            result[tag] = _coerce_scalar(value)
        return result

    def write_tags(self, values: dict[str, Any]) -> dict[str, dict[str, Any]]:
        for tag in values:
            ensure_tag_access(self.data_source, tag, "write")

        def _execute_pipeline():
            pipe = self.client.pipeline(transaction=False)
            for tag, value in values.items():
                pipe.set(self._key(tag), value)
            return pipe.execute()

        executed = self._retry(
            operation="write_tags",
            target=f"{len(values)} tag(s)",
            func=_execute_pipeline,
        )
        results: dict[str, dict[str, Any]] = {}
        for (tag, value), ok in zip(values.items(), executed):
            key = self._key(tag)
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
    def __init__(self, data_source: dict[str, Any], store=None) -> None:
        super().__init__(data_source, store)
        config = data_source["config"]
        self.url = str(config.get("url", "http://127.0.0.1:6041")).strip()
        self.user = str(config.get("user", "root")).strip() or "root"
        self.password = str(config.get("password", ""))
        self.database = str(config.get("database", "")).strip()
        self.table_name = str(config.get("table_name", config.get("tableName", ""))).strip()
        self.timezone = str(config.get("timezone", "Asia/Shanghai")).strip() or "Asia/Shanghai"
        self.ts_column = str(config.get("ts_column", config.get("tsColumn", "ts"))).strip() or "ts"
        self.value_column = str(config.get("value_column", config.get("valueColumn", "point_value"))).strip() or "point_value"
        self.point_code_column = str(config.get("point_code_column", config.get("pointCodeColumn", "point_code"))).strip() or "point_code"

    def read_tag(self, tag: str) -> Any:
        raise ConnectorError("tdengine is a historical data source; configure a history input binding instead")

    def read_tags(self, tags: list[str]) -> dict[str, Any]:
        raise ConnectorError("tdengine is a historical data source; configure a history input binding instead")

    def write_tag(self, tag: str, value: Any) -> None:
        raise ConnectorError("tdengine data source is read-only")

    def write_tags(self, values: dict[str, Any]) -> dict[str, dict[str, Any]]:
        return {tag: {"status": "failed", "value": value, "reason": "tdengine data source is read-only"} for tag, value in values.items()}

    def query_history(
        self,
        tags: list[str],
        *,
        start_time: datetime,
        end_time: datetime,
        sample_interval_sec: int = 60,
        lookback_before_start_sec: int = 600,
        fill_method: str = "ffill_then_interpolate",
        strict_first_value: bool = True,
    ) -> dict[str, Any]:
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
        start_time = _naive_datetime(start_time)
        end_time = _naive_datetime(end_time)
        if start_time >= end_time:
            raise ConnectorError("tdengine query start_time must be earlier than end_time")

        sample_interval_sec = max(1, int(sample_interval_sec))
        lookback_before_start_sec = max(0, int(lookback_before_start_sec))
        query_start = _naive_datetime(start_time - timedelta(seconds=lookback_before_start_sec))

        for tag in normalized_tags:
            ensure_tag_access(self.data_source, tag, "read")

        table_identifier = _sql_identifier(self.table_name)
        ts_identifier = _sql_identifier(self.ts_column)
        value_identifier = _sql_identifier(self.value_column)
        point_code_identifier = _sql_identifier(self.point_code_column)

        def _query():
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
                query_start_str = query_start.strftime("%Y-%m-%d %H:%M:%S")
                end_time_str = end_time.strftime("%Y-%m-%d %H:%M:%S")
                if len(normalized_tags) == 1:
                    tag_sql = f"{point_code_identifier}='{_sql_quote(normalized_tags[0])}'"
                else:
                    quoted = ", ".join(f"'{_sql_quote(tag)}'" for tag in normalized_tags)
                    tag_sql = f"{point_code_identifier} IN ({quoted})"
                sql = (
                    f"SELECT {ts_identifier}, {value_identifier}, {point_code_identifier} FROM {table_identifier} "
                    f"WHERE {tag_sql} AND {ts_identifier} >= '{query_start_str}' AND {ts_identifier} <= '{end_time_str}' "
                    f"ORDER BY {ts_identifier} ASC"
                )
                cursor.execute(sql)
                rows = cursor.fetchall()
                if not rows:
                    raw = pd.DataFrame(columns=["ts", "point_value", "point_code"])
                else:
                    raw = pd.DataFrame(rows, columns=["ts", "point_value", "point_code"])
                return _normalize_history_dataframe(
                    raw=raw,
                    tags=normalized_tags,
                    query_start=query_start,
                    start_time=start_time,
                    end_time=end_time,
                    sample_interval_sec=sample_interval_sec,
                    fill_method=fill_method,
                    strict_first_value=strict_first_value,
                )
            finally:
                if conn is not None:
                    conn.close()

        try:
            df = self._retry(
                operation="query_history",
                target=", ".join(normalized_tags[:5]) + (" ..." if len(normalized_tags) > 5 else ""),
                func=_query,
            )
        except ConnectorError as exc:
            raise ConnectorError(f"tdengine query failed: {exc}") from exc

        return _dataframe_payload(
            df=df,
            tags=normalized_tags,
            start_time=start_time,
            end_time=end_time,
            sample_interval_sec=sample_interval_sec,
            lookback_before_start_sec=lookback_before_start_sec,
            fill_method=fill_method,
        )


def build_connector(data_source: dict[str, Any], store) -> Connector:
    connector_type = data_source["connector_type"]
    if connector_type == "mock":
        return MockConnector(data_source, store)
    if connector_type == "redis":
        return RedisConnector(data_source, store)
    if connector_type == "tdengine":
        return TDengineConnector(data_source, store)
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


def _normalize_history_dataframe(
    *,
    raw,
    tags: list[str],
    query_start: datetime,
    start_time: datetime,
    end_time: datetime,
    sample_interval_sec: int,
    fill_method: str,
    strict_first_value: bool,
):
    import pandas as pd

    query_start = _naive_datetime(query_start)
    start_time = _naive_datetime(start_time)
    end_time = _naive_datetime(end_time)
    full_index = _naive_datetime_index(
        pd,
        pd.date_range(start=query_start, end=end_time, freq=f"{sample_interval_sec}s"),
    )
    if raw.empty:
        aligned = pd.DataFrame(index=full_index, columns=tags)
    else:
        raw = raw.copy()
        raw["ts"] = _naive_timestamp_series(pd, raw["ts"])
        raw = raw.dropna(subset=["ts", "point_code"])
        wide = raw.pivot_table(index="ts", columns="point_code", values="point_value", aggfunc="first").sort_index()
        wide.index = _naive_datetime_index(pd, wide.index)
        for tag in tags:
            if tag not in wide.columns:
                wide[tag] = None
        wide = wide[tags]
        merged_index = wide.index.union(full_index).sort_values()
        aligned = wide.reindex(merged_index)
        normalized_fill_method = str(fill_method or "ffill_then_interpolate").lower()
        if normalized_fill_method in {"ffill", "forward_fill", "ffill_then_interpolate"}:
            aligned = aligned.ffill()
        if normalized_fill_method in {"interpolate", "time_interpolate", "ffill_then_interpolate"}:
            aligned = aligned.interpolate(method="time", limit_area="inside")
        aligned = aligned.reindex(full_index)

    result = aligned.loc[start_time:end_time, tags]
    if result.empty:
        raise ConnectorError("tdengine history query returned an empty aligned dataframe")

    missing_first = [tag for tag in tags if tag not in result.columns or pd.isna(result.iloc[0][tag])]
    if missing_first and strict_first_value:
        raise ConnectorError(
            "tdengine history missing initial value for tags: "
            + ", ".join(missing_first)
            + "; increase lookback_before_start_sec or disable strict_first_value"
        )
    return result


def _dataframe_payload(
    *,
    df,
    tags: list[str],
    start_time: datetime,
    end_time: datetime,
    sample_interval_sec: int,
    lookback_before_start_sec: int,
    fill_method: str,
) -> dict[str, Any]:
    import pandas as pd

    safe = df.where(pd.notna(df), None)
    return {
        "__ipp_type": "dataframe",
        "orient": "split",
        "index_name": "ts",
        "index": [idx.strftime("%Y-%m-%d %H:%M:%S") for idx in safe.index],
        "columns": [str(col) for col in safe.columns],
        "data": safe.astype(object).values.tolist(),
        "metadata": {
            "source": "tdengine",
            "tags": tags,
            "start_time": start_time.strftime("%Y-%m-%d %H:%M:%S"),
            "end_time": end_time.strftime("%Y-%m-%d %H:%M:%S"),
            "sample_interval_sec": sample_interval_sec,
            "lookback_before_start_sec": lookback_before_start_sec,
            "fill_method": fill_method,
            "rows": int(len(safe)),
        },
    }



def _naive_datetime(value: datetime) -> datetime:
    """Return a tz-naive datetime while preserving the displayed local clock time."""
    if value.tzinfo is None:
        return value.replace(microsecond=0)
    return value.replace(tzinfo=None, microsecond=0)


def _naive_timestamp_series(pd, values):
    """Normalize TDengine timestamp values to tz-naive pandas datetimes."""
    converted = pd.to_datetime(values, errors="coerce")
    try:
        if getattr(converted.dt, "tz", None) is not None:
            return converted.dt.tz_localize(None)
    except AttributeError:
        pass
    return converted.map(_naive_pandas_timestamp)


def _naive_datetime_index(pd, index):
    converted = pd.DatetimeIndex(pd.to_datetime(index, errors="coerce"))
    if converted.tz is not None:
        return converted.tz_localize(None)
    return pd.DatetimeIndex([_naive_pandas_timestamp(item) for item in converted])


def _naive_pandas_timestamp(value):
    if value is None:
        return value
    try:
        if hasattr(value, "tz_localize") and getattr(value, "tzinfo", None) is not None:
            return value.tz_localize(None)
    except (TypeError, ValueError):
        pass
    if isinstance(value, datetime) and value.tzinfo is not None:
        return value.replace(tzinfo=None)
    return value

def _sql_identifier(value: str) -> str:
    normalized = str(value).strip()
    if not normalized:
        raise ConnectorError("empty TDengine SQL identifier")
    if not re.match(r"^[A-Za-z_][A-Za-z0-9_\.]*$", normalized):
        raise ConnectorError(f"unsafe TDengine SQL identifier: {normalized}")
    return normalized


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
