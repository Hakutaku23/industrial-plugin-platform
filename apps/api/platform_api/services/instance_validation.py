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
    _validate_named_bindings(
        interfaces=manifest.spec.inputs,
        bindings=input_bindings,
        binding_name_key="input_name",
        required_missing_message="missing required input bindings",
        unknown_message="unknown input bindings",
    )
    _validate_named_bindings(
        interfaces=manifest.spec.outputs,
        bindings=output_bindings,
        binding_name_key="output_name",
        required_missing_message="missing required output bindings",
        unknown_message="unknown output bindings",
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
