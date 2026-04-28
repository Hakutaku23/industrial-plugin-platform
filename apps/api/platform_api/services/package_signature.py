from __future__ import annotations

import base64
import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any, Literal


SignaturePolicy = Literal["off", "warn", "required"]


class PluginSignatureError(ValueError):
    """Raised when plugin signature validation must reject a package."""


@dataclass(frozen=True)
class PluginSignatureVerification:
    policy: str
    status: str
    required: bool
    verified: bool
    signed: bool
    algorithm: str = ""
    key_id: str = ""
    signed_file: str = ""
    message: str = ""
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def verify_plugin_signature(package_dir: Path) -> PluginSignatureVerification:
    """Verify optional plugin signature.json with a low-friction policy.

    Policy:
    - off: skip signature verification entirely.
    - warn: verify when signature.json is present; never block existing unsigned packages.
    - required: require signature.json + checksums.json + trusted key verification.

    Signature design:
    - signature.json signs the exact bytes of checksums.json.
    - checksums.json should cover manifest.yaml and all relevant plugin files.
    """
    policy = _signature_policy()
    required = policy == "required"
    if policy == "off":
        return PluginSignatureVerification(
            policy=policy,
            status="skipped_policy_off",
            required=False,
            verified=False,
            signed=False,
            message="plugin signature verification is disabled by policy",
        )

    root = package_dir.resolve()
    signature_path = root / "signature.json"
    checksums_path = root / "checksums.json"

    if not signature_path.exists():
        if required:
            raise PluginSignatureError("plugin signature is required but signature.json is missing")
        return PluginSignatureVerification(
            policy=policy,
            status="not_present",
            required=False,
            verified=False,
            signed=False,
            message="signature.json is not present; upload is allowed because policy=warn",
            warnings=["plugin package is unsigned"],
        )

    if not checksums_path.exists():
        return _fail_or_warn(
            policy=policy,
            code="missing_checksums",
            message="signature.json is present but checksums.json is missing",
            signed=True,
        )

    try:
        signature_payload = json.loads(signature_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return _fail_or_warn(
            policy=policy,
            code="invalid_signature_json",
            message=f"signature.json is not valid JSON: {exc}",
            signed=True,
        )

    if not isinstance(signature_payload, dict):
        return _fail_or_warn(
            policy=policy,
            code="invalid_signature_schema",
            message="signature.json must contain a JSON object",
            signed=True,
        )

    schema = str(signature_payload.get("schema", "")).strip()
    algorithm = str(signature_payload.get("algorithm", "")).strip().lower()
    key_id = str(signature_payload.get("key_id", "")).strip()
    signed_file = str(signature_payload.get("signed_file", "checksums.json")).strip() or "checksums.json"
    signature_b64 = str(signature_payload.get("signature", "")).strip()

    if schema and schema != "ipp-plugin-signature/v1":
        return _fail_or_warn(policy=policy, code="unsupported_signature_schema", message=f"unsupported signature schema: {schema}", signed=True, algorithm=algorithm, key_id=key_id, signed_file=signed_file)
    if algorithm != "ed25519":
        return _fail_or_warn(policy=policy, code="unsupported_signature_algorithm", message=f"unsupported signature algorithm: {algorithm or '<empty>'}", signed=True, algorithm=algorithm, key_id=key_id, signed_file=signed_file)
    if not key_id:
        return _fail_or_warn(policy=policy, code="missing_key_id", message="signature.json key_id is required", signed=True, algorithm=algorithm, signed_file=signed_file)
    if not signature_b64:
        return _fail_or_warn(policy=policy, code="missing_signature", message="signature.json signature is required", signed=True, algorithm=algorithm, key_id=key_id, signed_file=signed_file)
    try:
        _assert_safe_signed_file(signed_file)
    except PluginSignatureError as exc:
        return _fail_or_warn(policy=policy, code="unsafe_signed_file", message=str(exc), signed=True, algorithm=algorithm, key_id=key_id, signed_file=signed_file)
    if signed_file != "checksums.json":
        return _fail_or_warn(
            policy=policy,
            code="unsupported_signed_file",
            message="only signing checksums.json is supported in this platform version",
            signed=True,
            algorithm=algorithm,
            key_id=key_id,
            signed_file=signed_file,
        )

    try:
        signature = base64.b64decode(signature_b64.encode("ascii"), validate=True)
    except Exception as exc:  # noqa: BLE001
        return _fail_or_warn(policy=policy, code="invalid_signature_base64", message=f"signature is not valid base64: {exc}", signed=True, algorithm=algorithm, key_id=key_id, signed_file=signed_file)

    trusted_key = _load_trusted_public_key(key_id=key_id)
    if trusted_key is None:
        return _fail_or_warn(policy=policy, code="trusted_key_not_found", message=f"trusted public key not found or inactive: {key_id}", signed=True, algorithm=algorithm, key_id=key_id, signed_file=signed_file)

    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    except Exception as exc:  # noqa: BLE001
        return _fail_or_warn(
            policy=policy,
            code="crypto_backend_missing",
            message=f"cryptography package is required for signature verification: {exc}",
            signed=True,
            algorithm=algorithm,
            key_id=key_id,
            signed_file=signed_file,
        )

    try:
        public_key = Ed25519PublicKey.from_public_bytes(trusted_key)
        public_key.verify(signature, checksums_path.read_bytes())
    except Exception as exc:  # noqa: BLE001
        return _fail_or_warn(policy=policy, code="signature_invalid", message=f"signature verification failed: {exc}", signed=True, algorithm=algorithm, key_id=key_id, signed_file=signed_file)

    coverage_warnings = _checksums_coverage_warnings(package_dir=root)
    return PluginSignatureVerification(
        policy=policy,
        status="verified",
        required=required,
        verified=True,
        signed=True,
        algorithm="ed25519",
        key_id=key_id,
        signed_file=signed_file,
        message="plugin signature verified",
        warnings=coverage_warnings,
    )


def _signature_policy() -> SignaturePolicy:
    raw = os.getenv("PLATFORM_PLUGIN_SIGNATURE_POLICY", "warn").strip().lower()
    if raw not in {"off", "warn", "required"}:
        return "warn"
    return raw  # type: ignore[return-value]


def _trusted_keys_file() -> Path:
    configured = os.getenv("PLATFORM_PLUGIN_SIGNATURE_TRUSTED_KEYS_FILE", "").strip()
    if configured:
        path = Path(configured)
    else:
        project_root = Path(os.getenv("PLATFORM_PROJECT_ROOT", ".")).resolve()
        path = project_root / "config" / "plugin_trusted_keys.json"
    return path if path.is_absolute() else Path.cwd() / path


def _load_trusted_public_key(*, key_id: str) -> bytes | None:
    path = _trusted_keys_file()
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    keys = payload.get("keys")
    if not isinstance(keys, list):
        return None
    for item in keys:
        if not isinstance(item, dict):
            continue
        if str(item.get("key_id", "")).strip() != key_id:
            continue
        if str(item.get("algorithm", "")).strip().lower() != "ed25519":
            continue
        if str(item.get("status", "active")).strip().lower() not in {"active", "trusted"}:
            continue
        public_key_b64 = str(item.get("public_key", "")).strip()
        try:
            return base64.b64decode(public_key_b64.encode("ascii"), validate=True)
        except Exception:
            return None
    return None


def _fail_or_warn(
    *,
    policy: str,
    code: str,
    message: str,
    signed: bool,
    algorithm: str = "",
    key_id: str = "",
    signed_file: str = "",
) -> PluginSignatureVerification:
    if policy == "required":
        raise PluginSignatureError(message)
    return PluginSignatureVerification(
        policy=policy,
        status="failed_warn",
        required=False,
        verified=False,
        signed=signed,
        algorithm=algorithm,
        key_id=key_id,
        signed_file=signed_file,
        message=message,
        warnings=[code, message],
    )


def _assert_safe_signed_file(value: str) -> None:
    path = PurePosixPath(value.replace("\\", "/"))
    if not value or path.is_absolute() or ".." in path.parts:
        raise PluginSignatureError(f"unsafe signed_file path: {value}")


def _checksums_coverage_warnings(*, package_dir: Path) -> list[str]:
    checksums_path = package_dir / "checksums.json"
    try:
        payload = json.loads(checksums_path.read_text(encoding="utf-8"))
    except Exception:
        return ["checksums.json cannot be inspected for coverage"]
    files = payload.get("files") if isinstance(payload, dict) else None
    if not isinstance(files, dict):
        return ["checksums.json files object is missing"]
    warnings: list[str] = []
    if "manifest.yaml" not in files:
        warnings.append("checksums.json should include manifest.yaml when using signature.json")
    if "signature.json" in files:
        warnings.append("checksums.json should not include signature.json because signature signs checksums.json")
    return warnings
