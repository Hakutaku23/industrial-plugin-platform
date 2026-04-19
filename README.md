# Industrial Plugin Platform

This repository is the foundation for an industrial algorithm plugin platform.

The first development target is a local MVP that can:

- validate a plugin `manifest.yaml`
- safely accept and unpack a plugin archive
- execute a simple Python plugin through an isolated runner process
- keep the frontend upload page in a clear Web console boundary

## Local Environment

Use the existing `Learn` Python environment:

```powershell
& "D:\miniconda3\envs\Learn\python.exe" --version
```

Redis, TDengine, and production databases are not required for local MVP work.
Use Mock Source / Mock Sink implementations until the Docker deployment phase.

## Run Tests

```powershell
$env:PYTHONPATH="apps/api;apps/runner"
& "D:\miniconda3\envs\Learn\python.exe" -m unittest discover apps/api/tests
& "D:\miniconda3\envs\Learn\python.exe" -m unittest discover apps/runner/tests
```

## Run API

```powershell
$env:PYTHONPATH="apps/api;apps/runner"
& "D:\miniconda3\envs\Learn\python.exe" -m uvicorn platform_api.main:app --reload
```

The first upload endpoint accepts raw archive bytes:

```text
POST /api/v1/packages?filename=demo-python-plugin.zip
Content-Type: application/octet-stream
```

Successful uploads are stored under `var/packages`, registered in
`var/platform.sqlite3`, and recorded as `plugin.package.uploaded` audit events.

## Frontend

The Web console skeleton lives in `frontend/`. The initial page is the plugin
upload screen, backed by the API endpoint above.
