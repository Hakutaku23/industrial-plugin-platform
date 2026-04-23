from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from platform_api.core.config import settings


class LockManagerError(RuntimeError):
    """Raised when Redis execution lock operations fail."""


@dataclass(frozen=True)
class InstanceExecutionLease:
    instance_id: int
    token: str
    key: str


class RedisExecutionLockManager:
    def __init__(self, redis_client, *, key_prefix: str) -> None:
        self.redis = redis_client
        self.key_prefix = key_prefix.rstrip(":")

    @classmethod
    def from_settings(cls) -> "RedisExecutionLockManager":
        try:
            import redis
        except ImportError as exc:  # pragma: no cover
            raise LockManagerError("redis package is not installed in the Python environment") from exc

        redis_url = settings.scheduler.redis_url
        if redis_url:
            client = redis.Redis.from_url(redis_url, decode_responses=True)
        else:
            defaults = settings.connectors.redis
            client = redis.Redis(
                host=defaults.default_host,
                port=int(defaults.default_port),
                db=int(defaults.default_db),
                decode_responses=True,
                socket_connect_timeout=float(defaults.default_connect_timeout_sec),
                socket_timeout=float(defaults.default_socket_timeout_sec),
            )
        return cls(client, key_prefix=settings.scheduler.lock_key_prefix)

    def acquire(self, instance_id: int, *, ttl_sec: int) -> InstanceExecutionLease | None:
        lease = InstanceExecutionLease(
            instance_id=int(instance_id),
            token=uuid.uuid4().hex,
            key=self._key(instance_id),
        )
        try:
            acquired = bool(
                self.redis.set(
                    lease.key,
                    lease.token,
                    nx=True,
                    ex=max(1, int(ttl_sec)),
                )
            )
        except Exception as exc:  # noqa: BLE001
            raise LockManagerError(f"failed to acquire Redis execution lock: {exc}") from exc
        return lease if acquired else None

    def release(self, lease: InstanceExecutionLease) -> None:
        script = """
        if redis.call('GET', KEYS[1]) == ARGV[1] then
            return redis.call('DEL', KEYS[1])
        end
        return 0
        """
        try:
            self.redis.eval(script, 1, lease.key, lease.token)
        except Exception as exc:  # noqa: BLE001
            raise LockManagerError(f"failed to release Redis execution lock: {exc}") from exc

    def force_release(self, instance_id: int) -> bool:
        try:
            return bool(self.redis.delete(self._key(instance_id)))
        except Exception as exc:  # noqa: BLE001
            raise LockManagerError(f"failed to force release Redis execution lock: {exc}") from exc

    def is_locked(self, instance_id: int) -> bool:
        try:
            return bool(self.redis.exists(self._key(instance_id)))
        except Exception as exc:  # noqa: BLE001
            raise LockManagerError(f"failed to inspect Redis execution lock: {exc}") from exc

    def list_active_locks(self, *, limit: int = 200) -> list[dict[str, Any]]:
        pattern = f"{self.key_prefix}:*"
        items: list[dict[str, Any]] = []
        try:
            for key in self.redis.scan_iter(match=pattern, count=min(max(10, limit), 1000)):
                ttl_ms = self.redis.pttl(key)
                instance_id = self._instance_id_from_key(key)
                items.append(
                    {
                        "key": key,
                        "instance_id": instance_id,
                        "ttl_sec": None if ttl_ms is None or ttl_ms < 0 else round(ttl_ms / 1000.0, 3),
                    }
                )
                if len(items) >= limit:
                    break
        except Exception as exc:  # noqa: BLE001
            raise LockManagerError(f"failed to list Redis execution locks: {exc}") from exc
        items.sort(key=lambda item: (item["instance_id"] if item["instance_id"] is not None else 10**12, item["key"]))
        return items

    def _key(self, instance_id: int) -> str:
        return f"{self.key_prefix}:{int(instance_id)}"

    def _instance_id_from_key(self, key: str) -> int | None:
        prefix = f"{self.key_prefix}:"
        if not key.startswith(prefix):
            return None
        raw = key[len(prefix):].strip()
        if not raw.isdigit():
            return None
        return int(raw)
