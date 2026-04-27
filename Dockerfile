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


FROM python:${PYTHON_VERSION}-bookworm AS python-deps

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
    && pip install --index-url https://download.pytorch.org/whl/cpu torch==2.6.0


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
    PLATFORM_UI_DIST_DIR=/opt/app/frontend/dist \
    PLATFORM_RUNNER_BINARY_PATH=bin/ipp_runner_core \
    PLATFORM_SCHEDULER_DAEMON_BINARY_PATH=bin/ipp_scheduler_core

RUN apt-get update && apt-get install -y --no-install-recommends \
    bash \
    ca-certificates \
    libffi8 \
    libgcc-s1 \
    libgomp1 \
    libssl3 \
    libstdc++6 \
    locales \
    && sed -i 's/# en_US.UTF-8 UTF-8/en_US.UTF-8 UTF-8/' /etc/locale.gen \
    && locale-gen en_US.UTF-8 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/app

COPY --from=python-deps /opt/venv /opt/venv

# Python 源码不编译、不删除，完整保留在 Docker 镜像内，便于厂区第一版上线测试与现场排查。
COPY apps/api/platform_api /opt/app/apps/api/platform_api
COPY apps/runner/platform_runner /opt/app/apps/runner/platform_runner

# Rust 部分仍然编译后进入 runtime 镜像。
COPY --from=rust-builder /build/crates/target/release/ipp_runner_core /opt/app/bin/ipp_runner_core
COPY --from=rust-builder /build/crates/target/release/ipp_scheduler_core /opt/app/bin/ipp_scheduler_core

COPY --from=frontend-builder /build/frontend/dist /opt/app/frontend/dist
COPY config /opt/app/config
COPY requirements.txt /opt/app/requirements.txt

RUN chmod +x /opt/app/bin/ipp_runner_core /opt/app/bin/ipp_scheduler_core \
    && mkdir -p \
        /opt/app/target/release \
        /opt/app/var/packages \
        /opt/app/var/runs \
        /opt/app/var/manual-package-check \
        /opt/app/var/license \
    && ln -sf /opt/app/bin/ipp_runner_core /opt/app/target/release/ipp_runner_core \
    && ln -sf /opt/app/bin/ipp_scheduler_core /opt/app/target/release/ipp_scheduler_core \
    && python - <<'PY'
import platform_api.main  # noqa: F401
import platform_runner.executor  # noqa: F401
import platform_runner.function_host  # noqa: F401
print('python source import check passed')
PY

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "platform_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
