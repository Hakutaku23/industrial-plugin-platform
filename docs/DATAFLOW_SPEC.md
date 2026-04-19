# DATAFLOW_SPEC.md

## 1. Current MVP Scope

The local MVP supports plugin instance bindings where the platform resolves data
source tags before execution and applies output writeback after execution.

Plugins receive semantic input names, not raw plant tags. Redis keys, Mock
points, and future TDengine/OPC UA points stay in platform-managed data source
configuration.

## 2. Data Source Point Catalog

Each data source may define a `pointCatalog` array. Each point is permissioned
independently:

```json
{
  "class": "DCS",
  "canRead": true,
  "readTag": "sthb:DCS_AO_RTO_014_AI",
  "canWrite": false,
  "writeTag": ""
}
```

Rules:

- `class` is a grouping label for operators.
- `readTag` is the Redis key or connector tag used for reads.
- `writeTag` is the Redis key or connector tag used for writeback.
- `canRead=false` means the point cannot be selected or read.
- `canWrite=false` means the point cannot be selected or written.
- If a point is not writable, its write tag should be empty in operator-facing
  configuration.
- `readTags` and `writeTags` are derived indexes for compatibility and quick
  lookup.

Snake-case compatibility is accepted for imported configs:

- `point_catalog`
- `read_tags`
- `write_tags`
- `can_read`
- `can_write`
- `read_tag`
- `write_tag`

## 3. Instance Bindings

An instance may have multiple input bindings and multiple output bindings.

Single input binding:

```json
{
  "binding_type": "single",
  "input_name": "temperature",
  "data_source_id": 1,
  "source_tag": "sthb:DCS_AO_RTO_014_AI"
}
```

Batch input binding:

```json
{
  "binding_type": "batch",
  "input_name": "state_batch",
  "data_source_id": 1,
  "source_tags": [
    "sthb:DCS_AO_RTO_014_AI",
    "sthb:DCS_AO_RTO_015_AI"
  ],
  "output_format": "named-map"
}
```

Single output binding:

```json
{
  "binding_type": "single",
  "output_name": "setpoint",
  "data_source_id": 1,
  "target_tag": "sthb:DCS_AO_RTO_014_AO",
  "dry_run": true
}
```

Batch output binding:

```json
{
  "binding_type": "batch",
  "output_name": "setpoints",
  "data_source_id": 1,
  "target_tags": [
    "sthb:DCS_AO_RTO_014_AO",
    "sthb:DCS_AO_RTO_015_AO"
  ],
  "dry_run": true
}
```

Rules:

- `input_name` and `output_name` are plugin-facing semantic fields.
- `source_tag` must reference a readable point if a point policy exists.
- `target_tag` must reference a writable point if a point policy exists.
- `binding_type` defaults to `single` for compatibility with early MVP
  instance records.
- A batch input still maps to one plugin input name. With
  `output_format="named-map"`, the plugin receives an object whose keys are the
  selected tags. With `output_format="ordered-list"`, the plugin receives an
  array whose values follow the configured `source_tags` order.
- A batch output maps one plugin output name to multiple target tags. The plugin
  output must be an object whose keys are the target tags, for example:

```json
{
  "setpoints": {
    "sthb:DCS_AO_RTO_014_AO": 42.1,
    "sthb:DCS_AO_RTO_015_AO": 43.2
  }
}
```

- Batch writeback records one writeback result per target tag. Missing target
  values are blocked per tag and do not block unrelated tags.
- `dry_run=true` still validates whether the target is allowed for writeback,
  but does not write to the connector.
- Actual writeback additionally requires instance-level `writeback_enabled=true`
  and data-source-level `write_enabled=true`.

## 4. Instance Scheduling

The local MVP stores scheduling policy on each plugin instance:

```json
{
  "schedule_enabled": true,
  "schedule_interval_sec": 30,
  "last_scheduled_run_at": null,
  "next_scheduled_run_at": "2026-04-19T12:00:30"
}
```

Rules:

- `schedule_enabled=true` allows the local scheduler to trigger the instance.
- `schedule_interval_sec` is the repeat interval in seconds. The API enforces a
  minimum of 5 seconds for local development.
- Manual runs remain available even when scheduling is stopped.
- Stopping an instance disables the schedule and clears the next scheduled run;
  it does not forcibly kill a run that is already inside the runner process.
- Scheduled executions use the same input resolution and writeback guard as
  manual executions, but run records use `trigger_type="schedule"`.
- The current scheduler is an in-process local MVP. Production deployment should
  move this responsibility to the worker/orchestrator layer without changing the
  instance binding contract.

## 5. Redis Key Entry

If the Redis key already includes the namespace, enter the full key as the tag:

```text
sthb:DCS_AO_RTO_014_AI
```

Leave `keyPrefix` empty in that case. If `keyPrefix` is set to `sthb:`, then the
point tag should be entered without that prefix, for example:

```text
DCS_AO_RTO_014_AI
```
