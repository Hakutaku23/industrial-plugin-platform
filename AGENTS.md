# AGENTS.md

## 1. Purpose

This repository contains the source code for an industrial algorithm plugin platform.

The platform is intended to support plugin package upload, dataflow configuration, runner-based execution, writeback control, logging, auditing, and future multi-language runtime support.

Agents working in this repository must prioritize architectural consistency, incremental delivery, runtime isolation, auditability, and testability.

---

## 2. Working Style

When making changes in this repo, follow these principles:

1. Prefer incremental changes over large rewrites.
2. Preserve a runnable local development workflow.
3. Keep the platform core decoupled from plugin business logic.
4. Avoid embedding plugin-specific logic directly into API services.
5. Prefer configuration-driven behavior whenever possible.
6. Keep changes easy to review and easy to revert.
7. Treat production-facing writeback paths as high-risk code.
8. Do not optimize prematurely across the whole stack.

---

## 3. Repository Intent

This project is being built as a general-purpose industrial plugin platform, not as a single fixed rotary kiln application.

That means:

- package upload is a platform capability
- runner execution is a platform capability
- connector abstraction is a platform capability
- writeback control is a platform capability
- audit logging is a platform capability
- approval and rollback are platform capabilities

Avoid coding assumptions that only fit one plant, one device, one tag layout, or one algorithm.

Do not hardcode plant tags, one-off data source contracts, or rotary-kiln-specific workflow behavior into shared modules.

---

## 4. Expected Top-Level Structure

Agents should preserve or gradually evolve toward the following structure:

```text
frontend/              # Vue 3 + TypeScript admin console
apps/api/              # FastAPI control plane
apps/runner/           # Runner manager and execution services
apps/worker/           # Scheduling / background task execution
crates/                # Rust crates for performance-sensitive components
plugin_sdk/            # SDKs and examples for plugin authors
docs/                  # Architecture and specification docs
scripts/               # Dev and automation scripts
config/                # Deploy-time platform YAML config files
```

Do not introduce ad-hoc directories when an existing module boundary is more appropriate.

---

## 5. Tech Preferences

### Frontend

Preferred:

- Vue 3
- TypeScript
- Vite
- Pinia
- Vue Router
- ECharts

Frontend source discipline:

- Keep source files in `.vue` and `.ts`
- Do not commit transpiled `.js` files into `frontend/src/`
- Build outputs belong in `dist/`, not beside source modules

### Backend

Preferred:

- Python 3.12+
- FastAPI
- SQLAlchemy
- Pydantic
- PostgreSQL for metadata
- Redis for short-lived state / queue / cache

### Systems / Performance

Preferred for performance-critical parts:

- Rust

Use Rust especially for:

- high-throughput runtime utilities
- process supervision helpers
- binary SDKs
- data transformation tools
- connector helpers where throughput or safety matters

Do not move ordinary business CRUD or simple orchestration logic into Rust unless there is a clear performance or safety reason.

---

## 6. Architectural Guardrails

Agents must follow these rules:

### 6.1 Do not run uploaded plugin code inside the main API process

Uploaded plugins must run via isolated runner processes or equivalent execution boundaries.

### 6.2 Do not let plugins write directly to platform metadata storage

Plugins may return outputs. The platform is responsible for validation, writeback, persistence, and auditing.

### 6.3 Keep connectors abstract

Data source logic should go through connector abstractions, not through plugin-specific direct calls unless explicitly justified and isolated.

### 6.4 Keep platform metadata explicit

Plugin packages, versions, instances, schedules, bindings, approvals, and audit events should have explicit models and tables.

### 6.5 Prefer schemas over implicit conventions

Manifest files, API payloads, runner contracts, and writeback contracts should be defined through schemas or strongly typed structures.

### 6.6 Keep control plane and data plane separate

Control-plane concerns belong in API/services/metadata modules.
Data-plane concerns belong in runner/worker/runtime modules.
Do not mix the two casually.

### 6.7 No plant-specific shortcuts in shared layers

Do not add hardcoded tag names, plant IDs, device IDs, or proprietary mappings to reusable platform modules.

---

## 7. Configuration Rules

Treat platform configuration in three layers:

1. **Deploy-time YAML file config**
   - stored under `config/`
   - used for platform storage, metadata backend, scheduler, runner defaults, logging, connector defaults

2. **Environment variable overrides**
   - used for machine- or deployment-specific overrides
   - should override file config, not replace structured config entirely

3. **Runtime metadata in database**
   - data sources
   - plugin instances
   - bindings
   - runs
   - audits
   - writeback records

Do not move runtime metadata back into flat JSON/YAML files.

Preferred format for deploy-time config:

- YAML (`config/platform.yaml`)
- optional environment-specific overlays such as `config/platform.dev.yaml`
- environment variables only for host-specific overrides or secrets

If a new setting affects the whole platform process, prefer YAML file config plus env override.
If a new setting belongs to one plugin instance or one data source, keep it in metadata storage.

---

## 8. Repository Operating Expectations

Agents should preserve local development usability.

When adding a new service, also add or update:

- startup instructions
- local environment variable documentation
- example config
- minimal run/test commands
- one minimal fixture or example where practical

Prefer dev scripts that allow the user to run a small working slice locally.

If standard scripts do not yet exist, prefer to introduce conventional entry points such as:

- frontend: `pnpm dev`, `pnpm build`, `pnpm test`
- api/worker/runner: `pytest`, `uvicorn ...`, module-based startup commands
- Rust crates: `cargo test`, `cargo fmt`, `cargo clippy`

Do not assume these commands already exist; add them or document the gap.

---

## 9. Testing Expectations

For meaningful changes, agents should add or update tests where practical.

Minimum expectation by layer:

- frontend: component logic and state tests when the setup exists
- backend: API tests and service tests
- runner: contract tests for input/output handling, exit codes, and timeouts
- Rust crates: unit tests and `cargo test` compatibility

High-risk changes must not be merged without focused tests where feasible, especially for:

- manifest validation
- package extraction security
- writeback policy enforcement
- runner input/output protocol
- approval and rollback behavior
- configuration loading and override precedence

If a change cannot be tested immediately, keep the change surface small and document the missing coverage.

---

## 10. Documentation Expectations

When changing core architecture, plugin contracts, runner behavior, package format, repository structure, or configuration loading, update relevant docs in `docs/`.

At minimum, keep these aligned:

- `docs/ARCHITECTURE.md`
- `docs/PLUGIN_SPEC.md`
- `docs/RUNNER_PROTOCOL.md`
- `AGENTS.md`

If implementation and docs diverge, implementation should not silently drift without updating the corresponding design docs.

For significant protocol changes, create or update adjacent docs such as:

- `docs/DATAFLOW_SPEC.md`
- `docs/SECURITY_MODEL.md`
- `docs/METADATA_MODEL.md`

---

## 11. Plugin Package Assumptions

Until the spec changes, agents should assume:

- each plugin package contains a `manifest.yaml`
- Python plugins expose a standard callable or CLI entry
- binary plugins expose a controlled CLI entry
- zip/tar.gz are distribution formats, not execution semantics
- platform-managed dataflow binding maps declared inputs/outputs to real connectors

Do not introduce one-off plugin loading logic for a single example package unless it is clearly marked as temporary.

---

## 12. Security Expectations

Agents must avoid introducing insecure defaults.

Default assumptions:

- no unrestricted plugin network access
- no unrestricted host filesystem access
- no direct plugin writeback without platform validation
- no secret values hardcoded in repo
- no production credentials committed
- no plugin access to platform metadata database credentials
- no implicit promotion from dev to prod without an explicit release action

If a feature would weaken isolation or auditability, prefer a safer baseline first.

If a change affects writeback, approval, secrets, package extraction, or process-wide configuration, explicitly call that out in the change summary.

---

## 13. Migration Expectations

This project may evolve from an earlier fixed-function industrial control system.

When migrating old code:

- extract reusable capabilities
- isolate plant-specific logic
- convert hard-coded tag mappings into configuration
- avoid carrying over unnecessary coupling
- prefer migration steps over one-shot rewrites

Do not preserve old coupling just because it is already implemented.

---

## 14. Definition of Done

A task is not complete when code merely compiles.

For non-trivial changes, completion usually means:

- code changed in the right module boundary
- tests added or updated where practical
- docs updated if contracts or architecture changed
- local run path preserved or documented
- no obvious hardcoded plant-specific assumptions introduced

For protocol-level changes, also ensure:

- examples updated
- schema or type definitions updated
- backward compatibility assessed
- migration notes added if needed

For configuration changes, also ensure:

- file config example updated
- env override path documented
- default values remain explicit
- runtime metadata boundaries remain unchanged

---

## 15. Commit / Change Discipline

When preparing changes, agents should:

- keep module boundaries clean
- avoid unrelated formatting churn
- avoid renaming files unless necessary
- prefer one coherent change set at a time
- separate docs-only changes from runtime/protocol changes when practical

Where possible, changes should be shaped so they can be reviewed by feature area:

- docs
- API
- runner
- worker
- frontend
- Rust core
- config

---

## 16. Good First Milestones

Agents should generally prefer this implementation order unless instructed otherwise:

1. docs and schemas
2. backend metadata models
3. plugin registry upload flow
4. manifest parser and validation
5. Python runner MVP
6. mock connector and writeback flow
7. frontend package/config pages
8. deploy-time config extraction
9. binary runner support
10. Rust optimization modules

Do not jump to advanced protocol support before the platform foundation is stable.

---

## 17. Anti-Patterns to Avoid

Avoid these common mistakes:

- embedding plugin business logic in API routers
- adding plant-specific tag mapping in shared code
- making plugin upload equal to immediate trusted execution
- letting plugins write directly to external systems
- hiding protocol decisions inside implementation without documenting them
- moving code to Rust just because it is “core”
- building UI pages tightly coupled to one example plugin
- committing generated frontend `.js` files beside TypeScript source
- storing runtime metadata in deploy-time config files

---

## 18. Current Priority

The immediate goal is to build the platform foundation first.

Current priorities are:

- architecture stabilization
- plugin package spec
- runner contract definition
- metadata model definition
- deploy-time config extraction
- local MVP that can upload and execute a simple plugin package

Do not optimize for advanced plant-specific features before the platform core is stable.

---

## 19. When Unsure

If requirements are ambiguous, prefer decisions that:

- preserve extensibility
- preserve local runnability
- reduce coupling
- keep security defaults conservative
- make future plugin support easier
- avoid locking the platform into one industrial scenario

When forced to choose, bias toward a smaller, reviewable, reversible implementation.
