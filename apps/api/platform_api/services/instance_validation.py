from typing import Any

from platform_api.services.manifest import InterfaceSpec, PluginManifest


class BindingValidationError(ValueError):
    """Raised when instance bindings or execution payloads do not match the manifest."""


def validate_instance_bindings(
    *,
    manifest: PluginManifest,
    input_bindings: list[dict[str, Any]],
    output_bindings: list[dict[str, Any]],
) -> None:
    _validate_input_bindings(interfaces=manifest.spec.inputs, bindings=input_bindings)
    _validate_named_bindings(
        interfaces=manifest.spec.outputs,
        bindings=output_bindings,
        binding_name_key="output_name",
        required_missing_message="missing required output bindings",
        unknown_message="unknown output bindings",
    )


def validate_instance_binding_data_sources(
    *,
    manifest: PluginManifest,
    input_bindings: list[dict[str, Any]],
    data_source_resolver,
) -> None:
    interface_by_name = {item.name: item for item in manifest.spec.inputs}
    for index, binding in enumerate(input_bindings, start=1):
        if not isinstance(binding, dict):
            continue
        binding_type = str(binding.get('binding_type', 'single')).strip().lower() or 'single'
        binding_name = str(binding.get('input_name', '')).strip()
        if not binding_name:
            continue
        interface = interface_by_name.get(binding_name)
        if interface is None:
            continue
        rule = _manifest_input_binding_rule(interface)
        if not rule:
            continue

        required_binding_type = _string_field(rule, 'bindingType', 'binding_type')
        if required_binding_type and binding_type != required_binding_type:
            raise BindingValidationError(
                f'input binding {binding_name} must use binding_type={required_binding_type}'
            )

        required_connector_type = _string_field(
            rule,
            'connectorType',
            'connector_type',
            'requiredConnectorType',
            'required_connector_type',
        )
        if required_connector_type:
            try:
                data_source_id = int(binding.get('data_source_id'))
            except (TypeError, ValueError) as exc:
                raise BindingValidationError(
                    f'input binding {binding_name} has invalid data_source_id'
                ) from exc
            data_source = data_source_resolver(data_source_id)
            actual_connector_type = str((data_source or {}).get('connector_type', '')).strip()
            if actual_connector_type != required_connector_type:
                raise BindingValidationError(
                    f'input binding {binding_name} requires {required_connector_type} data source, got {actual_connector_type or "missing"}'
                )
            _validate_manifest_data_source_rule(binding_name, data_source or {}, rule)

        declared_tags = _normalize_tags(
            rule.get('sourceTags')
            or rule.get('source_tags')
            or rule.get('requiredSourceTags')
            or rule.get('required_source_tags')
        )
        if declared_tags and binding_type == 'history':
            selected_tags = set(_normalize_tags(binding.get('source_tags')))
            lock_source_tags = bool(rule.get('lockSourceTags') or rule.get('lock_source_tags'))
            missing_tags = [tag for tag in declared_tags if tag not in selected_tags]
            if lock_source_tags and missing_tags:
                raise BindingValidationError(
                    f'input binding {binding_name} is missing manifest-required source tags: {", ".join(missing_tags)}'
                )


def validate_execution_inputs(*, manifest: PluginManifest, inputs: dict[str, Any]) -> None:
    declared_names = {item.name for item in manifest.spec.inputs}
    required_names = {item.name for item in manifest.spec.inputs if item.required}
    provided_names = {str(name).strip() for name in inputs.keys() if str(name).strip()}

    missing_required = sorted(required_names - provided_names)
    if missing_required:
        raise BindingValidationError(
            f"missing required plugin inputs: {', '.join(missing_required)}"
        )

    unknown_names = sorted(provided_names - declared_names)
    if unknown_names:
        raise BindingValidationError(
            f"unknown plugin inputs: {', '.join(unknown_names)}"
        )


def _validate_input_bindings(
    *,
    interfaces: list[InterfaceSpec],
    bindings: list[dict[str, Any]],
) -> None:
    declared_names = {item.name for item in interfaces}
    required_names = {item.name for item in interfaces if item.required}
    seen_names: set[str] = set()
    duplicate_names: set[str] = set()
    provided_names: list[str] = []

    for index, binding in enumerate(bindings, start=1):
        if not isinstance(binding, dict):
            raise BindingValidationError(f"input_name binding #{index} must be an object")

        binding_type = str(binding.get("binding_type", "single")).strip().lower() or "single"
        if binding_type not in {"single", "batch", "history"}:
            raise BindingValidationError(
                f"input_name binding #{index} uses unsupported binding_type: {binding_type}"
            )

        if binding_type == "single":
            binding_name = str(binding.get("input_name", "")).strip()
            if not binding_name:
                raise BindingValidationError(f"input_name binding #{index} has an empty name")
            source_tag = str(binding.get("source_tag", "")).strip()
            if not source_tag:
                raise BindingValidationError(
                    f"single input_name binding {binding_name} has no source_tag"
                )
            provided_names.append(binding_name)
            if binding_name in seen_names:
                duplicate_names.add(binding_name)
            seen_names.add(binding_name)
            continue

        if binding_type == "history":
            binding_name = str(binding.get("input_name", "")).strip()
            if not binding_name:
                raise BindingValidationError(f"history input binding #{index} has an empty name")
            source_tags = _normalize_tags(binding.get("source_tags"))
            if not source_tags:
                raise BindingValidationError(
                    f"history input binding {binding_name} has no source_tags"
                )
            window = binding.get("window") if isinstance(binding.get("window"), dict) else {}
            start_offset = _int_field(window.get("start_offset_min", binding.get("start_offset_min", 60)), "start_offset_min")
            end_offset = _int_field(window.get("end_offset_min", binding.get("end_offset_min", 0)), "end_offset_min")
            sample_interval = _int_field(window.get("sample_interval_sec", binding.get("sample_interval_sec", 60)), "sample_interval_sec")
            if start_offset <= end_offset:
                raise BindingValidationError(
                    f"history input binding {binding_name} requires start_offset_min > end_offset_min"
                )
            if sample_interval <= 0:
                raise BindingValidationError(
                    f"history input binding {binding_name} requires positive sample_interval_sec"
                )
            provided_names.append(binding_name)
            if binding_name in seen_names:
                duplicate_names.add(binding_name)
            seen_names.add(binding_name)
            continue

        output_format = str(binding.get("output_format", "named-map")).strip().lower() or "named-map"
        if output_format not in {"named-map", "ordered-list"}:
            raise BindingValidationError(
                f"batch input binding #{index} uses unsupported output_format: {output_format}"
            )

        binding_name = str(binding.get("input_name", "")).strip()
        source_tags = _normalize_tags(binding.get("source_tags"))
        source_mappings = _normalize_source_mappings(binding.get("source_mappings"))

        if output_format == "ordered-list":
            if not binding_name:
                raise BindingValidationError(
                    f"ordered-list batch input binding #{index} must declare input_name"
                )
            if not source_tags:
                raise BindingValidationError(
                    f"batch input_name binding {binding_name} has no source_tags"
                )
            provided_names.append(binding_name)
            if binding_name in seen_names:
                duplicate_names.add(binding_name)
            seen_names.add(binding_name)
            continue

        if binding_name:
            read_tags = source_tags or [item["tag"] for item in source_mappings]
            if not read_tags:
                raise BindingValidationError(
                    f"batch input_name binding {binding_name} has no source tags"
                )
            provided_names.append(binding_name)
            if binding_name in seen_names:
                duplicate_names.add(binding_name)
            seen_names.add(binding_name)
            continue

        if not source_mappings:
            raise BindingValidationError(
                f"named-map batch input binding #{index} must declare input_name or source_mappings"
            )

        mapping_keys = [item["key"] for item in source_mappings]
        duplicate_mapping_keys = _duplicate_names(mapping_keys)
        if duplicate_mapping_keys:
            raise BindingValidationError(
                f"duplicate named-map input keys: {', '.join(duplicate_mapping_keys)}"
            )

        for mapping_key in mapping_keys:
            provided_names.append(mapping_key)
            if mapping_key in seen_names:
                duplicate_names.add(mapping_key)
            seen_names.add(mapping_key)

    if duplicate_names:
        raise BindingValidationError(
            f"duplicate input_name values: {', '.join(sorted(duplicate_names))}"
        )

    provided_name_set = set(provided_names)
    unknown_names = sorted(provided_name_set - declared_names)
    if unknown_names:
        raise BindingValidationError(f"unknown input bindings: {', '.join(unknown_names)}")

    missing_required = sorted(required_names - provided_name_set)
    if missing_required:
        raise BindingValidationError(
            f"missing required input bindings: {', '.join(missing_required)}"
        )


def _validate_named_bindings(
    *,
    interfaces: list[InterfaceSpec],
    bindings: list[dict[str, Any]],
    binding_name_key: str,
    required_missing_message: str,
    unknown_message: str,
) -> None:
    declared_names = {item.name for item in interfaces}
    required_names = {item.name for item in interfaces if item.required}
    seen_names: set[str] = set()
    duplicate_names: set[str] = set()
    provided_names: list[str] = []

    for index, binding in enumerate(bindings, start=1):
        if not isinstance(binding, dict):
            raise BindingValidationError(f"{binding_name_key} binding #{index} must be an object")

        binding_name = str(binding.get(binding_name_key, "")).strip()
        if not binding_name:
            raise BindingValidationError(f"{binding_name_key} binding #{index} has an empty name")
        provided_names.append(binding_name)
        if binding_name in seen_names:
            duplicate_names.add(binding_name)
        seen_names.add(binding_name)

        binding_type = str(binding.get("binding_type", "single")).strip().lower() or "single"
        if binding_type not in {"single", "batch"}:
            raise BindingValidationError(
                f"{binding_name_key} binding {binding_name} uses unsupported binding_type: {binding_type}"
            )

        if binding_type == "single":
            tag_key = "source_tag" if binding_name_key == "input_name" else "target_tag"
            tag_value = str(binding.get(tag_key, "")).strip()
            if not tag_value:
                raise BindingValidationError(
                    f"single {binding_name_key} binding {binding_name} has no {tag_key}"
                )
            continue

        tags_key = "source_tags" if binding_name_key == "input_name" else "target_tags"
        tags = _normalize_tags(binding.get(tags_key))
        if not tags:
            raise BindingValidationError(
                f"batch {binding_name_key} binding {binding_name} has no {tags_key}"
            )

    if duplicate_names:
        raise BindingValidationError(
            f"duplicate {binding_name_key} values: {', '.join(sorted(duplicate_names))}"
        )

    provided_name_set = set(provided_names)
    unknown_names = sorted(provided_name_set - declared_names)
    if unknown_names:
        raise BindingValidationError(f"{unknown_message}: {', '.join(unknown_names)}")

    missing_required = sorted(required_names - provided_name_set)
    if missing_required:
        raise BindingValidationError(
            f"{required_missing_message}: {', '.join(missing_required)}"
        )


def _validate_manifest_data_source_rule(binding_name: str, data_source: dict[str, Any], rule: dict[str, Any]) -> None:
    data_source_rule = rule.get('dataSource') or rule.get('data_source') or rule.get('datasource')
    if not isinstance(data_source_rule, dict):
        return
    config = data_source.get('config') if isinstance(data_source.get('config'), dict) else {}
    expected_database = _string_field(data_source_rule, 'database')
    if expected_database and str(config.get('database', '')).strip() != expected_database:
        raise BindingValidationError(
            f'input binding {binding_name} requires TDengine database={expected_database}'
        )
    expected_table = _string_field(data_source_rule, 'table_name', 'tableName')
    if expected_table:
        actual_table = str(config.get('table_name', config.get('tableName', ''))).strip()
        if actual_table != expected_table:
            raise BindingValidationError(
                f'input binding {binding_name} requires TDengine table_name={expected_table}'
            )


def _manifest_input_binding_rule(interface: InterfaceSpec) -> dict[str, Any] | None:
    schema = interface.schema_
    if not isinstance(schema, dict):
        return None
    for key in ('ippBinding', 'inputBinding', 'x-ipp-binding', 'binding'):
        value = schema.get(key)
        if isinstance(value, dict):
            return value
    return None


def _string_field(record: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ''


def _normalize_source_mappings(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    normalized: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        tag = str(item.get("tag", "")).strip()
        key = str(item.get("key", "")).strip()
        if not tag or not key:
            continue
        normalized.append({"tag": tag, "key": key})
    return normalized


def _normalize_tags(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    normalized: list[str] = []
    seen: set[str] = set()
    for item in value:
        tag = str(item).strip()
        if not tag or tag in seen:
            continue
        normalized.append(tag)
        seen.add(tag)
    return normalized


def _duplicate_names(values: list[str]) -> list[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        else:
            seen.add(value)
    return sorted(duplicates)


def _int_field(value: Any, field: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise BindingValidationError(f"{field} must be an integer") from exc
