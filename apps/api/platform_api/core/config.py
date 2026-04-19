import os
from pathlib import Path

from pydantic import BaseModel


PROJECT_ROOT = Path(__file__).resolve().parents[4]


def _env_str(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    return value.strip()


def _env_path(name: str, default: Path) -> Path:
    value = _env_str(name)
    if value is None:
        return default
    path = Path(value)
    if path.is_absolute():
        return path
    return (PROJECT_ROOT / path).resolve()


def _env_bool(name: str, default: bool) -> bool:
    value = _env_str(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float) -> float:
    value = _env_str(name)
    if value is None:
        return default
    return float(value)


class Settings(BaseModel):
    project_root: Path = _env_path("PLATFORM_PROJECT_ROOT", PROJECT_ROOT)
    package_storage_dir: Path = _env_path("PLATFORM_PACKAGE_STORAGE_DIR", PROJECT_ROOT / "var/packages")
    run_storage_dir: Path = _env_path("PLATFORM_RUN_STORAGE_DIR", PROJECT_ROOT / "var/runs")
    metadata_db_path: Path = _env_path("PLATFORM_METADATA_DB_PATH", PROJECT_ROOT / "var/platform.sqlite3")
    metadata_db_url: str | None = _env_str("PLATFORM_METADATA_DB_URL")
    environment: str = _env_str("PLATFORM_ENVIRONMENT", "dev") or "dev"
    scheduler_enabled: bool = _env_bool("PLATFORM_SCHEDULER_ENABLED", True)
    scheduler_poll_interval_sec: float = _env_float("PLATFORM_SCHEDULER_POLL_INTERVAL_SEC", 1.0)

    @property
    def metadata_database(self) -> Path | str:
        return self.metadata_db_url or self.metadata_db_path


settings = Settings()
