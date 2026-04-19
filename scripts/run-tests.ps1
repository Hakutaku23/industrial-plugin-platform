$ErrorActionPreference = "Stop"
$env:PYTHONPATH = "apps/api;apps/runner"
$python = "D:\miniconda3\envs\Learn\python.exe"
& $python -m unittest discover apps/api/tests
& $python -m unittest discover apps/runner/tests
