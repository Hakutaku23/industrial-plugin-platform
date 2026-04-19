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

Input binding:

```json
{
  "input_name": "temperature",
  "data_source_id": 1,
  "source_tag": "sthb:DCS_AO_RTO_014_AI"
}
```

Output binding:

```json
{
  "output_name": "setpoint",
  "data_source_id": 1,
  "target_tag": "sthb:DCS_AO_RTO_014_AO",
  "dry_run": true
}
```

Rules:

- `input_name` and `output_name` are plugin-facing semantic fields.
- `source_tag` must reference a readable point if a point policy exists.
- `target_tag` must reference a writable point if a point policy exists.
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
