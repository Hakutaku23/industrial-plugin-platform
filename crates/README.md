# Rust Crates

Rust is reserved for performance-sensitive or safety-sensitive components:

- process supervision helpers
- high-throughput data transformation
- binary plugin SDK utilities
- package and path safety tools

Do not move ordinary API CRUD or low-throughput orchestration into Rust without
a clear performance or isolation reason.

