#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CRATES_DIR="${ROOT_DIR}/crates"
BIN_DIR="${ROOT_DIR}/bin"

mkdir -p "${BIN_DIR}"

echo "[1/3] Building Rust binaries..."
cargo build --release --manifest-path "${CRATES_DIR}/Cargo.toml" -p ipp_runner_core -p ipp_scheduler_core

echo "[2/3] Installing binaries into ${BIN_DIR} ..."
install -m 0755 "${CRATES_DIR}/target/release/ipp_runner_core" "${BIN_DIR}/ipp_runner_core"
install -m 0755 "${CRATES_DIR}/target/release/ipp_scheduler_core" "${BIN_DIR}/ipp_scheduler_core"

echo "[3/3] Installed binaries:"
ls -lh "${BIN_DIR}/ipp_runner_core" "${BIN_DIR}/ipp_scheduler_core"
