from __future__ import annotations


class RustRunnerBridgeError(RuntimeError):
    """Raised when the Rust runner bridge cannot execute or parse a task."""


class RustRunnerBinaryNotFound(FileNotFoundError):
    """Raised when the configured Rust runner executable does not exist."""
