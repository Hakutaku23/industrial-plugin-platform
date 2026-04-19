$ErrorActionPreference = "Stop"
$env:PYTHONPATH = "apps/api;apps/runner"
$python = "D:\miniconda3\envs\Learn\python.exe"
& $python -m uvicorn platform_api.main:app --reload
