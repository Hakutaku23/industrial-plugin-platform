from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from platform_api.services.connectors import ConnectorError, build_connector
from platform_api.services.metadata_store import MetadataStore


class InputBindingResolverError(ValueError):
    """Raised when configured input bindings cannot be resolved."""


def resolve_input_bindings(
    *,
    input_bindings: list[dict[str, Any]] | None,
    store: MetadataStore,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Resolve platform input bindings into plugin payload inputs.

    This is shared by model-update jobs and can be adopted by normal instance
    execution later. It intentionally accepts the same binding JSON shape used by
    plugin instances: single / batch / history.
    """
    bindings = input_bindings or []
    resolved: dict[str, Any] = {}
    current_time = now or datetime.now(UTC)

    for index, raw_binding in enumerate(bindings):
        if not isinstance(raw_binding, dict):
            raise InputBindingResolverError(f"input binding #{index + 1} must be an object")
        binding = dict(raw_binding)
        binding_type = str(binding.get("binding_type") or binding.get("bindingType") or "single").strip().lower()

        if binding_type == "single":
            _resolve_single_binding(binding=binding, store=store, resolved=resolved)
            continue
        if binding_type == "batch":
            _resolve_batch_binding(binding=binding, store=store, resolved=resolved)
            continue
        if binding_type == "history":
            _resolve_history_binding(binding=binding, store=store, resolved=resolved, now=current_time)
            continue

        raise InputBindingResolverError(f"unsupported input binding type: {binding_type}")

    return resolved


def _resolve_single_binding(*, binding: dict[str, Any], store: MetadataStore, resolved: dict[str, Any]) -> None:
    input_name = _required_string(binding, "input_name")
    source_tag = _required_string(binding, "source_tag")
    connector = _connector_for_binding(binding, store)
    resolved[input_name] = connector.read_tag(source_tag)


def _resolve_batch_binding(*, binding: dict[str, Any], store: MetadataStore, resolved: dict[str, Any]) -> None:
    connector = _connector_for_binding(binding, store)
    output_format = str(binding.get("output_format") or binding.get("outputFormat") or "named-map").strip()

    source_mappings = _source_mappings(binding)
    source_tags = _source_tags(binding)
    input_name = str(binding.get("input_name") or "").strip()

    if source_mappings:
        tags = [item["tag"] for item in source_mappings]
        values = connector.read_tags(tags)
        mapped = {item["key"]: values.get(item["tag"]) for item in source_mappings}
        if input_name:
            resolved[input_name] = mapped
        else:
            resolved.update(mapped)
        return

    if not source_tags:
        raise InputBindingResolverError("batch input binding requires source_tags or source_mappings")
    values = connector.read_tags(source_tags)

    if output_format == "ordered-list":
        if not input_name:
            raise InputBindingResolverError("ordered-list batch binding requires input_name")
        resolved[input_name] = [values.get(tag) for tag in source_tags]
        return

    mapped = {_safe_key(tag): values.get(tag) for tag in source_tags}
    if input_name:
        resolved[input_name] = mapped
    else:
        resolved.update(mapped)


def _resolve_history_binding(
    *,
    binding: dict[str, Any],
    store: MetadataStore,
    resolved: dict[str, Any],
    now: datetime,
) -> None:
    input_name = _required_string(binding, "input_name")
    source_tags = _source_tags(binding)
    if not source_tags:
        raise InputBindingResolverError(f"history input binding {input_name} requires source_tags")

    connector = _connector_for_binding(binding, store)
    if not hasattr(connector, "query_history"):
        raise InputBindingResolverError("history input binding requires a connector with query_history support")

    window = binding.get("window") if isinstance(binding.get("window"), dict) else {}
    start_offset_min = _int_window(window, "start_offset_min", "startOffsetMin", default=60)
    end_offset_min = _int_window(window, "end_offset_min", "endOffsetMin", default=0)
    sample_interval_sec = _int_window(window, "sample_interval_sec", "sampleIntervalSec", default=60)
    lookback_before_start_sec = _int_window(window, "lookback_before_start_sec", "lookbackBeforeStartSec", default=600)
    fill_method = str(window.get("fill_method") or window.get("fillMethod") or "ffill_then_interpolate")
    strict_first_value = bool(window.get("strict_first_value", window.get("strictFirstValue", True)))

    if start_offset_min <= end_offset_min:
        raise InputBindingResolverError("history start_offset_min must be greater than end_offset_min")
    if sample_interval_sec <= 0:
        raise InputBindingResolverError("history sample_interval_sec must be positive")

    end_time = now - timedelta(minutes=end_offset_min)
    start_time = now - timedelta(minutes=start_offset_min)

    resolved[input_name] = connector.query_history(
        source_tags,
        start_time=start_time,
        end_time=end_time,
        sample_interval_sec=sample_interval_sec,
        lookback_before_start_sec=lookback_before_start_sec,
        fill_method=fill_method,
        strict_first_value=strict_first_value,
    )


def _connector_for_binding(binding: dict[str, Any], store: MetadataStore):
    data_source_id = binding.get("data_source_id") or binding.get("dataSourceId")
    try:
        normalized_id = int(data_source_id)
    except (TypeError, ValueError) as exc:
        raise InputBindingResolverError("input binding data_source_id must be an integer") from exc

    data_source = _get_data_source(store, normalized_id)
    if data_source is None:
        raise InputBindingResolverError(f"data source not found: {normalized_id}")
    try:
        return build_connector(data_source, store)
    except ConnectorError as exc:
        raise InputBindingResolverError(str(exc)) from exc


def _get_data_source(store: MetadataStore, data_source_id: int) -> dict[str, Any] | None:
    getter = getattr(store, "get_data_source", None)
    if callable(getter):
        return getter(data_source_id)

    lister = getattr(store, "list_data_sources", None)
    if callable(lister):
        for item in lister():
            if int(item.get("id", -1)) == data_source_id:
                return item
    return None


def _required_string(binding: dict[str, Any], key: str) -> str:
    value = str(binding.get(key) or "").strip()
    if not value:
        raise InputBindingResolverError(f"input binding requires {key}")
    return value


def _source_tags(binding: dict[str, Any]) -> list[str]:
    value = binding.get("source_tags") or binding.get("sourceTags") or []
    if not isinstance(value, list):
        return []
    result: list[str] = []
    seen: set[str] = set()
    for item in value:
        tag = str(item).strip()
        if tag and tag not in seen:
            seen.add(tag)
            result.append(tag)
    return result


def _source_mappings(binding: dict[str, Any]) -> list[dict[str, str]]:
    value = binding.get("source_mappings") or binding.get("sourceMappings") or []
    if not isinstance(value, list):
        return []
    result: list[dict[str, str]] = []
    seen_keys: set[str] = set()
    for item in value:
        if not isinstance(item, dict):
            continue
        tag = str(item.get("tag") or "").strip()
        key = str(item.get("key") or "").strip()
        if not tag or not key:
            continue
        if key in seen_keys:
            raise InputBindingResolverError(f"duplicate source mapping key: {key}")
        seen_keys.add(key)
        result.append({"tag": tag, "key": key})
    return result


def _safe_key(tag: str) -> str:
    return "".join(char if char.isalnum() or char == "_" else "_" for char in str(tag).strip())


def _int_window(window: dict[str, Any], snake_key: str, camel_key: str, *, default: int) -> int:
    value = window.get(snake_key, window.get(camel_key, default))
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
