# Backend Configuration

后端配置优先从项目内配置文件读取，也可以通过环境变量覆盖。

## 加载顺序

1. `config/platform.yaml`、`config/platform.yml` 或 `config/platform.json`
2. 与环境匹配的覆盖文件，例如 `config/platform.prod.yaml`
3. `PLATFORM_CONFIG_FILE` 指定的 YAML 或 JSON 文件
4. `PLATFORM_...` 环境变量覆盖

相对路径会按项目根目录解析。

## 常用配置

```yaml
app:
  environment: dev

storage:
  package_storage_dir: var/packages
  run_storage_dir: var/runs

metadata:
  backend: sqlite
  sqlite_path: var/platform.sqlite3
  db_url: null

scheduler:
  enabled: true
  poll_interval_sec: 1.0
```

上线使用 PostgreSQL 时，可以在部署环境中设置：

```yaml
metadata:
  backend: postgresql
  db_url: postgresql+psycopg://user:password@postgres:5432/platform
```

也可以使用环境变量：

```powershell
$env:PLATFORM_CONFIG_FILE="config/platform.prod.yaml"
$env:PLATFORM_METADATA_DB_URL="postgresql+psycopg://user:password@postgres:5432/platform"
```

注意：数据源、实例绑定、运行记录和审计事件属于运行时元数据，应保存在数据库中，不应写入配置文件。
