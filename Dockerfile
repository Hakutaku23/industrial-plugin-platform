ARG PYTHON_VERSION=3.12
ARG NODE_VERSION=22-bookworm-slim
ARG RUST_IMAGE=rust:1-bookworm

FROM node:${NODE_VERSION} AS frontend-builder

WORKDIR /build/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend ./
RUN npm run build:raw


FROM ${RUST_IMAGE} AS rust-builder

WORKDIR /build/crates
COPY crates/Cargo.toml crates/Cargo.lock ./
COPY crates/ipp_runner_core/Cargo.toml crates/ipp_runner_core/Cargo.toml
COPY crates/ipp_scheduler_core/Cargo.toml crates/ipp_scheduler_core/Cargo.toml
RUN mkdir -p ipp_runner_core/src ipp_scheduler_core/src \
    && printf 'fn main() { println!("bootstrap"); }\n' > ipp_runner_core/src/main.rs \
    && printf 'fn main() { println!("bootstrap"); }\n' > ipp_scheduler_core/src/main.rs \
    && cargo build --release -p ipp_runner_core -p ipp_scheduler_core || true

COPY crates ./
RUN cargo build --release -p ipp_runner_core -p ipp_scheduler_core


FROM python:${PYTHON_VERSION}-bookworm AS python-builder

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    VIRTUAL_ENV=/opt/venv \
    PATH=/opt/venv/bin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    ca-certificates \
    gcc \
    g++ \
    libffi-dev \
    libssl-dev \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv "$VIRTUAL_ENV" \
    && pip install --upgrade pip setuptools wheel

WORKDIR /build
COPY requirements.txt /build/requirements.txt
RUN grep -vi '^torch==' /build/requirements.txt > /build/requirements.no-torch.txt \
    && pip install -r /build/requirements.no-torch.txt \
    && pip install --index-url https://download.pytorch.org/whl/cpu torch==2.6.0 \
    && pip install "Cython>=3.0,<4"

COPY apps/api/platform_api /build/apps/api/platform_api
COPY apps/runner/platform_runner /build/apps/runner/platform_runner

RUN python - <<'PY'
import os
from pathlib import Path
from setuptools import Extension, setup
from Cython.Build import cythonize

TARGET_GROUPS = [
    (
        Path("/build/apps/api"),
        [
            Path("/build/apps/api/platform_api/core"),
            Path("/build/apps/api/platform_api/services"),
        ],
    ),
    (
        Path("/build/apps/runner"),
        [
            Path("/build/apps/runner/platform_runner"),
        ],
    ),
]

compiled_sources: list[str] = []

for base, package_roots in TARGET_GROUPS:
    os.chdir(base)
    extensions = []
    for package_root in package_roots:
        for source in package_root.rglob("*.py"):
            if source.name == "__init__.py":
                continue
            module_name = ".".join(source.relative_to(base).with_suffix("").parts)
            extensions.append(Extension(module_name, [str(source.relative_to(base))]))
            compiled_sources.append(str(source))

    if not extensions:
        continue

    setup(
        script_name="setup.py",
        script_args=["build_ext", "--inplace", "-j", "4"],
        ext_modules=cythonize(
            extensions,
            compiler_directives={
                "language_level": "3",
                "embedsignature": True,
                "binding": True,
            },
            build_dir=str(Path("/build/.cython-build") / base.name),
            nthreads=4,
        ),
    )

Path("/build/compiled-python-files.txt").write_text(
    "\n".join(sorted(set(compiled_sources))) + "\n",
    encoding="utf-8",
)
PY

RUN PYTHONPATH=/build/apps/api:/build/apps/runner python - <<'PY'
import platform_api.main  # noqa: F401
import platform_runner.executor  # noqa: F401
import platform_runner.function_host  # noqa: F401
print("compiled python modules import check passed")
PY

RUN python - <<'PY'
from pathlib import Path
import shutil

compiled_list = Path("/build/compiled-python-files.txt")
if compiled_list.exists():
    for line in compiled_list.read_text(encoding="utf-8").splitlines():
        source = Path(line.strip())
        if not source:
            continue
        if source.exists():
            source.unlink()

for pycache in Path("/build/apps").rglob("__pycache__"):
    shutil.rmtree(pycache, ignore_errors=True)

shutil.rmtree("/build/.cython-build", ignore_errors=True)
compiled_list.unlink(missing_ok=True)
PY


FROM python:${PYTHON_VERSION}-slim-bookworm AS runtime

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    LANG=en_US.UTF-8 \
    LC_ALL=en_US.UTF-8 \
    VIRTUAL_ENV=/opt/venv \
    PATH=/opt/venv/bin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
    PYTHONPATH=/opt/app/apps/api:/opt/app/apps/runner \
    PLATFORM_PROJECT_ROOT=/opt/app \
    PLATFORM_UI_SERVE_DIST=true \
    PLATFORM_UI_DIST_DIR=/opt/app/frontend/dist

RUN apt-get update && apt-get install -y --no-install-recommends \
    bash \
    ca-certificates \
    libgcc-s1 \
    libgomp1 \
    libstdc++6 \
    locales \
    && sed -i 's/# en_US.UTF-8 UTF-8/en_US.UTF-8 UTF-8/' /etc/locale.gen \
    && locale-gen en_US.UTF-8 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/app

COPY --from=python-builder /opt/venv /opt/venv
COPY --from=python-builder /build/apps/api/platform_api /opt/app/apps/api/platform_api
COPY --from=python-builder /build/apps/runner/platform_runner /opt/app/apps/runner/platform_runner
COPY --from=rust-builder /build/crates/target/release/ /opt/app/target/release/
COPY --from=frontend-builder /build/frontend/dist /opt/app/frontend/dist
COPY config /opt/app/config

RUN mkdir -p \
    /opt/app/target/release \
    /opt/app/var/packages \
    /opt/app/var/runs \
    /opt/app/var/manual-package-check

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "platform_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
