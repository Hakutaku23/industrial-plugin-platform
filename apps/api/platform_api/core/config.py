import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


PROJECT_ROOT = Path(__file__).resolve().parents[4]


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _load_yaml_file(path: Path) -> dict[str, Any]:
    try:
        import yaml  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            'PyYAML is required for platform YAML config loading. Install it with: pip install pyyaml'
        ) from exc

    loaded = yaml.safe_load(path.read_text(encoding='utf-8')) or {}
    if not isinstance(loaded, dict):
        raise ValueError(f'config file must contain a mapping object: {path}')
    return loaded


def _load_json_file(path: Path) -> dict[str, Any]:
    import json

    loaded = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(loaded, dict):
        raise ValueError(f'config file must contain a mapping object: {path}')
    return loaded


def _load_structured_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}

    suffixes = [suffix.lower() for suffix in path.suffixes]
    if suffixes and suffixes[-1] in {'.yaml', '.yml'}:
        return _load_yaml_file(path)
    if suffixes and suffixes[-1] == '.json':
        return _load_json_file(path)
    raise ValueError(f'unsupported config file format: {path}')


def _set_nested(target: dict[str, Any], path: tuple[str, ...], value: Any) -> None:
    cursor = target
    for key in path[:-1]:
        node = cursor.get(key)
        if not isinstance(node, dict):
            node = {}
            cursor[key] = node
        cursor = node
    cursor[path[-1]] = value


def _env_str(name: str) -> str | None:
    value = os.getenv(name)
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _env_bool(name: str) -> bool | None:
    value = _env_str(name)
    if value is None:
        return None
    return value.lower() in {'1', 'true', 'yes', 'on'}


def _env_float(name: str) -> float | None:
    value = _env_str(name)
    if value is None:
        return None
    return float(value)


def _env_int(name: str) -> int | None:
    value = _env_str(name)
    if value is None:
        return None
    return int(value)


def _resolve_path(project_root: Path, value: str | Path) -> Path:
    path = value if isinstance(value, Path) else Path(value)
    if path.is_absolute():
        return path
    return (project_root / path).resolve()


class AppSettings(BaseModel):
    name: str = 'industrial-plugin-platform'
    environment: str = 'dev'


class StorageSettings(BaseModel):
    package_storage_dir: Path = Path('var/packages')
    run_storage_dir: Path = Path('var/runs')


class MetadataSettings(BaseModel):
    backend: str = 'sqlite'
    sqlite_path: Path = Path('var/platform.sqlite3')
    db_url: str | None = None


class SchedulerSettings(BaseModel):
    enabled: bool = True
    poll_interval_sec: float = 1.0
    max_workers: int = 4
    lock_ttl_sec: int = 300
    redis_url: str | None = None
    lock_key_prefix: str = 'lock:instance'


class RunnerSettings(BaseModel):
    default_timeout_sec: int = 30
    max_timeout_sec: int = 300
    work_root: Path = Path('var/runs')


class LoggingSettings(BaseModel):
    level: str = 'INFO'


class RedisDefaults(BaseModel):
    default_host: str = '127.0.0.1'
    default_port: int = 6379
    default_db: int = 0
    default_connect_timeout_sec: float = 2.0
    default_socket_timeout_sec: float = 2.0


class ConnectorRetrySettings(BaseModel):
    max_attempts: int = 3
    base_delay_sec: float = 1.0
    max_delay_sec: float = 8.0


class ConnectorSettings(BaseModel):
    redis: RedisDefaults = Field(default_factory=RedisDefaults)
    retry: ConnectorRetrySettings = Field(default_factory=ConnectorRetrySettings)


class SecuritySettings(BaseModel):
    enabled: bool = False
    session_cookie_name: str = 'ipp_session'
    session_cookie_secure: bool = False
    session_cookie_samesite: str = 'lax'
    session_ttl_sec: int = 12 * 60 * 60
    password_iterations: int = 390000
    trusted_hosts: list[str] = Field(default_factory=list)
    https_redirect: bool = False
    max_request_body_bytes: int = 20 * 1024 * 1024
    bootstrap_admin_username: str | None = None
    bootstrap_admin_password: str | None = None
    bootstrap_admin_display_name: str = 'Platform Administrator'
    bootstrap_admin_email: str | None = None


class UISettings(BaseModel):
    serve_dist: bool = True
    dist_dir: Path = Path('frontend/dist')
    index_file: str = 'index.html'


class Settings(BaseModel):
    project_root: Path
    app: AppSettings = Field(default_factory=AppSettings)
    storage: StorageSettings = Field(default_factory=StorageSettings)
    metadata: MetadataSettings = Field(default_factory=MetadataSettings)
    scheduler: SchedulerSettings = Field(default_factory=SchedulerSettings)
    runner: RunnerSettings = Field(default_factory=RunnerSettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)
    connectors: ConnectorSettings = Field(default_factory=ConnectorSettings)
    security: SecuritySettings = Field(default_factory=SecuritySettings)
    ui: UISettings = Field(default_factory=UISettings)

    @property
    def package_storage_dir(self) -> Path:
        return self.storage.package_storage_dir

    @property
    def run_storage_dir(self) -> Path:
        return self.storage.run_storage_dir

    @property
    def environment(self) -> str:
        return self.app.environment

    @property
    def metadata_db_path(self) -> Path:
        return self.metadata.sqlite_path

    @property
    def metadata_database(self) -> str | Path:
        return self.metadata.db_url or self.metadata.sqlite_path


def _base_project_root() -> Path:
    value = _env_str('PLATFORM_PROJECT_ROOT')
    if value is None:
        return PROJECT_ROOT
    return _resolve_path(PROJECT_ROOT, value)


def _first_existing(*paths: Path) -> Path | None:
    for path in paths:
        if path.exists():
            return path
    return None


def _load_raw_config(project_root: Path) -> dict[str, Any]:
    config: dict[str, Any] = {}

    base_file = _first_existing(
        project_root / 'config/platform.yaml',
        project_root / 'config/platform.yml',
        project_root / 'config/platform.json',
    )
    if base_file is not None:
        config = _deep_merge(config, _load_structured_file(base_file))

    environment = _env_str('PLATFORM_ENVIRONMENT') or (
        config.get('app', {}).get('environment') if isinstance(config.get('app'), dict) else None
    ) or 'dev'

    env_file = _first_existing(
        project_root / f'config/platform.{environment}.yaml',
        project_root / f'config/platform.{environment}.yml',
        project_root / f'config/platform.{environment}.json',
    )
    if env_file is not None:
        config = _deep_merge(config, _load_structured_file(env_file))

    explicit_file = _env_str('PLATFORM_CONFIG_FILE')
    if explicit_file:
        config = _deep_merge(config, _load_structured_file(_resolve_path(project_root, explicit_file)))

    return config


def _apply_env_overrides(config: dict[str, Any]) -> dict[str, Any]:
    updated = dict(config)
    mapping: list[tuple[str, tuple[str, ...], Any]] = [
        ('PLATFORM_ENVIRONMENT', ('app', 'environment'), _env_str('PLATFORM_ENVIRONMENT')),
        ('PLATFORM_PACKAGE_STORAGE_DIR', ('storage', 'package_storage_dir'), _env_str('PLATFORM_PACKAGE_STORAGE_DIR')),
        ('PLATFORM_RUN_STORAGE_DIR', ('storage', 'run_storage_dir'), _env_str('PLATFORM_RUN_STORAGE_DIR')),
        ('PLATFORM_METADATA_BACKEND', ('metadata', 'backend'), _env_str('PLATFORM_METADATA_BACKEND')),
        ('PLATFORM_METADATA_DB_PATH', ('metadata', 'sqlite_path'), _env_str('PLATFORM_METADATA_DB_PATH')),
        ('PLATFORM_METADATA_DB_URL', ('metadata', 'db_url'), _env_str('PLATFORM_METADATA_DB_URL')),
        ('PLATFORM_SCHEDULER_ENABLED', ('scheduler', 'enabled'), _env_bool('PLATFORM_SCHEDULER_ENABLED')),
        ('PLATFORM_SCHEDULER_POLL_INTERVAL_SEC', ('scheduler', 'poll_interval_sec'), _env_float('PLATFORM_SCHEDULER_POLL_INTERVAL_SEC')),
        ('PLATFORM_SCHEDULER_MAX_WORKERS', ('scheduler', 'max_workers'), _env_int('PLATFORM_SCHEDULER_MAX_WORKERS')),
        ('PLATFORM_SCHEDULER_LOCK_TTL_SEC', ('scheduler', 'lock_ttl_sec'), _env_int('PLATFORM_SCHEDULER_LOCK_TTL_SEC')),
        ('PLATFORM_SCHEDULER_REDIS_URL', ('scheduler', 'redis_url'), _env_str('PLATFORM_SCHEDULER_REDIS_URL')),
        ('PLATFORM_SCHEDULER_LOCK_KEY_PREFIX', ('scheduler', 'lock_key_prefix'), _env_str('PLATFORM_SCHEDULER_LOCK_KEY_PREFIX')),
        ('PLATFORM_RUNNER_DEFAULT_TIMEOUT_SEC', ('runner', 'default_timeout_sec'), _env_int('PLATFORM_RUNNER_DEFAULT_TIMEOUT_SEC')),
        ('PLATFORM_RUNNER_MAX_TIMEOUT_SEC', ('runner', 'max_timeout_sec'), _env_int('PLATFORM_RUNNER_MAX_TIMEOUT_SEC')),
        ('PLATFORM_CONNECTOR_RETRY_MAX_ATTEMPTS', ('connectors', 'retry', 'max_attempts'), _env_int('PLATFORM_CONNECTOR_RETRY_MAX_ATTEMPTS')),
        ('PLATFORM_CONNECTOR_RETRY_BASE_DELAY_SEC', ('connectors', 'retry', 'base_delay_sec'), _env_float('PLATFORM_CONNECTOR_RETRY_BASE_DELAY_SEC')),
        ('PLATFORM_CONNECTOR_RETRY_MAX_DELAY_SEC', ('connectors', 'retry', 'max_delay_sec'), _env_float('PLATFORM_CONNECTOR_RETRY_MAX_DELAY_SEC')),
        ('PLATFORM_LOG_LEVEL', ('logging', 'level'), _env_str('PLATFORM_LOG_LEVEL')),
        ('PLATFORM_SECURITY_ENABLED', ('security', 'enabled'), _env_bool('PLATFORM_SECURITY_ENABLED')),
        ('PLATFORM_SECURITY_TRUSTED_HOSTS', ('security', 'trusted_hosts'), [item.strip() for item in (_env_str('PLATFORM_SECURITY_TRUSTED_HOSTS') or '').split(',') if item.strip()] or None),
        ('PLATFORM_SECURITY_HTTPS_REDIRECT', ('security', 'https_redirect'), _env_bool('PLATFORM_SECURITY_HTTPS_REDIRECT')),
        ('PLATFORM_SECURITY_MAX_REQUEST_BODY_BYTES', ('security', 'max_request_body_bytes'), _env_int('PLATFORM_SECURITY_MAX_REQUEST_BODY_BYTES')),
        ('PLATFORM_SECURITY_SESSION_TTL_SEC', ('security', 'session_ttl_sec'), _env_int('PLATFORM_SECURITY_SESSION_TTL_SEC')),
        ('PLATFORM_SECURITY_SESSION_COOKIE_NAME', ('security', 'session_cookie_name'), _env_str('PLATFORM_SECURITY_SESSION_COOKIE_NAME')),
        ('PLATFORM_SECURITY_SESSION_COOKIE_SECURE', ('security', 'session_cookie_secure'), _env_bool('PLATFORM_SECURITY_SESSION_COOKIE_SECURE')),
        ('PLATFORM_SECURITY_BOOTSTRAP_ADMIN_USERNAME', ('security', 'bootstrap_admin_username'), _env_str('PLATFORM_SECURITY_BOOTSTRAP_ADMIN_USERNAME')),
        ('PLATFORM_SECURITY_BOOTSTRAP_ADMIN_PASSWORD', ('security', 'bootstrap_admin_password'), _env_str('PLATFORM_SECURITY_BOOTSTRAP_ADMIN_PASSWORD')),
        ('PLATFORM_SECURITY_BOOTSTRAP_ADMIN_EMAIL', ('security', 'bootstrap_admin_email'), _env_str('PLATFORM_SECURITY_BOOTSTRAP_ADMIN_EMAIL')),
        ('PLATFORM_UI_SERVE_DIST', ('ui', 'serve_dist'), _env_bool('PLATFORM_UI_SERVE_DIST')),
        ('PLATFORM_UI_DIST_DIR', ('ui', 'dist_dir'), _env_str('PLATFORM_UI_DIST_DIR')),
    ]
    for _name, path, value in mapping:
        if value is not None:
            _set_nested(updated, path, value)
    return updated


def _resolve_path_fields(project_root: Path, payload: dict[str, Any]) -> dict[str, Any]:
    result = _deep_merge({}, payload)

    storage = result.setdefault('storage', {})
    storage['package_storage_dir'] = str(
        _resolve_path(project_root, storage.get('package_storage_dir', 'var/packages'))
    )
    storage['run_storage_dir'] = str(
        _resolve_path(project_root, storage.get('run_storage_dir', 'var/runs'))
    )

    metadata = result.setdefault('metadata', {})
    sqlite_path = metadata.get('sqlite_path', 'var/platform.sqlite3')
    metadata['sqlite_path'] = str(_resolve_path(project_root, sqlite_path))

    runner = result.setdefault('runner', {})
    runner['work_root'] = str(_resolve_path(project_root, runner.get('work_root', 'var/runs')))

    ui = result.setdefault('ui', {})
    ui['dist_dir'] = str(_resolve_path(project_root, ui.get('dist_dir', 'frontend/dist')))
    return result


def load_settings() -> Settings:
    project_root = _base_project_root()
    raw = _load_raw_config(project_root)
    overridden = _apply_env_overrides(raw)
    normalized = _resolve_path_fields(project_root, overridden)
    normalized['project_root'] = str(project_root)
    return Settings.model_validate(normalized)


settings = load_settings()
