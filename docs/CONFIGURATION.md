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

security:
  enabled: true
  session_cookie_name: ipp_session
  session_cookie_secure: false
  session_cookie_samesite: lax
  session_ttl_sec: 43200
  bootstrap_admin_username: admin
  bootstrap_admin_password: "admin123456"
```

开发模式也默认启用登录。登录成功后，后端写入 `HttpOnly` Session
Cookie，前端不应把 Token 写入 `localStorage`、`sessionStorage` 或页面状态中。
首次启动时会按 `bootstrap_admin_username` /
`bootstrap_admin_password` 创建或更新本地管理员账号。上线环境应通过
`PLATFORM_SECURITY_BOOTSTRAP_ADMIN_USERNAME` 和
`PLATFORM_SECURITY_BOOTSTRAP_ADMIN_PASSWORD` 覆盖默认账号，并启用 HTTPS 后将
`session_cookie_secure` 设置为 `true`。

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
