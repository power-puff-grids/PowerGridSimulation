# Shared data contract — draft v0.2

Status: proposed for team review; not yet an approved interface. Samples illustrate the contract and are not validated simulation results. This is synthetic simulation data, not measured farm or utility data.

## Identity, time and units

`run_id` identifies one execution. `snapshot_id` uniquely identifies one physical state within that execution and is copied unchanged into its derived messages. Use globally unique identifiers (UUIDs recommended). `message_id` uniquely identifies an individual telemetry message. The grouped envelope below supersedes the earlier one-measurement proposal. Match physical truth using `(run_id, snapshot_id)`, then device and measurement; timestamps alone are not join keys.

`timestamp` is the simulated event time, encoded as UTC ISO 8601 with a `Z` suffix. It must not be represented as a real historical observation. Every measurement from a snapshot shares its timestamp. Independent snapshots do not imply elapsed-time dynamics. `received_at` denotes actual subscriber receipt time; it is distinct from simulated event time. Scenario names or ordering must not be used to infer elapsed time.

CSV encoding: UTF-8, header row, comma delimiter, decimal point, no index column. Booleans: `true`/`false`; labels: integer 0/1. Numerical fields must be finite; NaN and infinity are prohibited. Use an empty CSV field / JSON null only for explicitly optional values. Preserve numerical precision; round for display only. Units are fixed by the field or measurement definition; never silently convert units.

## Physical results: data/generated/physical_results.csv

One row per successfully solved snapshot. All columns below are required. Failed/nonfinite snapshots must fail validation and be recorded separately in an execution diagnostic; do not publish them as valid physical results. `converged` is therefore true for all published rows.

| Field | Type | Meaning/unit |
|---|---|---|
| run_id | string | Execution identity |
| snapshot_id | string | Physical state identity |
| timestamp | string | Simulated event time, UTC |
| scenario | enum | normal, high_irrigation_demand, dust_reduced_solar |
| description | string | Human-readable scenario description |
| converged | boolean | Solver convergence |
| bus_1_voltage_pu … bus_4_voltage_pu | float | Solved voltage magnitude, per unit of each bus nominal voltage |
| line_1_loading_percent … line_3_loading_percent | float | Solved line loading, % of configured current rating |
| solar_output_mw | float | Solved PV active injection, MW; positive generation |
| pump_demand_mw | float | Solved pump active consumption, MW |
| pump_reactive_demand_mvar | float | Solved pump reactive consumption, MVAr |
| battery_power_mw | float | Solved storage active power, MW; positive charging, negative discharging |
| battery_soc_percent | float | Configured snapshot SOC, %, not dynamically solved |

Line 1 connects Bus 1–2, line 2 Bus 2–3, line 3 Bus 3–4. Logical bus numbers are stable project identifiers, not Pandapower's zero-based table indices. Extract solved quantities from result tables; SOC comes from storage configuration. Confirm sign conventions against the installed Pandapower version during implementation.

Exact column order is provided in `data/sample/physical_results_header.csv`. That file contains no simulated results.

## MQTT: grid/telemetry

**Decision: one JSON object per device per snapshot, with grouped measurements.** All values in one object represent the same solved snapshot. The baseline has ten devices: four buses, three lines, solar PV, irrigation pump and battery. Publish ten device messages per snapshot.

Required envelope fields: `schema_version`, `run_id`, `snapshot_id`, `message_id`, `timestamp`, `device`, `measurements`, `scenario`. All fields except `measurements` are nonempty strings; `schema_version` is `"1.0"`. `measurements` is an object whose documented keys have finite numerical values (booleans are not numbers). All keys listed for that device below are required. Unknown keys/devices and unsupported versions must be rejected or quarantined explicitly, not silently interpreted. New incompatible names, units or meaning require a new major version and team review.

```json
{
  "schema_version": "1.0",
  "run_id": "example-run",
  "snapshot_id": "example-snapshot",
  "message_id": "example-message",
  "timestamp": "2026-10-18T14:00:00Z",
  "device": "solar_pv",
  "measurements": {"active_power_kw": 150.0, "voltage_kv": 12.47},
  "scenario": "normal"
}
```

This example is an interface fixture, not a validated solver result. Device voltage means voltage at its connection bus: solar Bus 2, battery Bus 3, pump Bus 4. `voltage_kv` is RMS line-to-line voltage magnitude. Measurement names carry fixed units; no separate `unit` key occurs in the envelope.

| Device | Required measurement keys | Conversion from physical results |
|---|---|---|
| bus_1 … bus_4 | voltage_kv | bus_N_voltage_pu × that bus's nominal kV |
| line_1 … line_3 | loading_percent | line_N_loading_percent unchanged |
| solar_pv | active_power_kw, voltage_kv | solar_output_mw × 1000; Bus 2 voltage conversion |
| irrigation_pump | active_power_kw, reactive_power_kvar, voltage_kv | pump_demand_mw × 1000; pump_reactive_demand_mvar × 1000; Bus 4 voltage conversion |
| battery | active_power_kw, soc_percent, voltage_kv | battery_power_mw × 1000; battery_soc_percent unchanged; Bus 3 voltage conversion |

Physical CSV retains MW, MVAr and per-unit values. Telemetry uses kW, kvar and kV explicitly, without renaming physical columns. Bus nominal voltage comes from the versioned model configuration (currently a provisional 12.47 kV for all four buses); never assume 1 pu equals 1 kV. Battery power is positive charging and negative discharging. See `data/metadata/telemetry_measurements.csv` for the machine-readable mapping.

`data/generated/mqtt_telemetry.csv` is the immutable publisher log: one row per original device message, with envelope fields as columns and `measurements` stored as a valid JSON object string using standard CSV quoting. This is distinct from the flattened combined dataset below. The JSON and CSV samples encode the same example.

**No `attack_type`, `attack_label`, `condition_type` or `attack_target` in live telemetry.** Labels are trusted experimental sidecar metadata, joined later. This supersedes the original payload-label proposal. Benign ground-truth records use `attack_type="none"`, `attack_label=0`; JSON uses `null` only for explicitly nullable fields, never Python `None`.

## Attacks and combined dataset

Never mutate original physical rows or original messages. Attack metadata is trusted sidecar ground truth, not authenticated by the telemetry payload. Never trust payload labels as detector evidence.

The subscriber records every received device message with a locally generated unique `delivery_id` and actual UTC `received_at`; duplicate payloads remain distinct deliveries. Preserve the raw received envelope, including claimed identifiers. Controlled attack code records provenance separately; payload IDs are not authenticated evidence.

Proposed attack records share these fields: `attack_id`, `injected_at`,
`original_message_id`, `attack_type`, `attack_target`,
`false_data_injection`, and `replay`.

For false-data injection, `false_data_injection` contains `measurement`,
`original_value`, `manipulated_value`, and `offset`; `replay` is null.
Values and offset use the selected measurement's units. Change one scalar
per attack and preserve the original envelope identifiers.

For replay, `replay` contains `replayed_id`, `replayed_timestamp`, and
`replayed_measurements`; `false_data_injection` is null. `replayed_id`
equals the earlier message's `message_id` and the shared
`original_message_id`. Replayed measurements are an independent copy of
the earlier message's measurements.

Attack-specific values are nested in their respective sections; there
are no top-level `original_value` or `manipulated_value` fields.
`injected_at` records actual UTC attack preparation time. Trusted
experiment bookkeeping adds `delivery_id` after receipt to distinguish
deliveries. CSV serialization of the nested sections remains pending
team agreement. Identifier tampering and multi-field value changes
require a documented extension before implementation.

### Whole-message replay — proposed extension

A replay attack returns an independent deep copy of an earlier telemetry
message. All payload fields remain unchanged, including timestamp, message_id,
run_id, snapshot_id, device, measurements, and scenario. Neither the original
message nor physical simulation results are modified. The function prepares
the replay payload; publishing it is a separate integration step.

The separate attack record uses attack_type="replay_attack", a new
attack_id, and original_message_id identifying the earlier message.
For replay, attack_target="message" denotes the whole payload.
The replay section records its earlier ID, simulated timestamp,
and measurements. Subscriber delivery_id identifies the new receipt.

For dataset integration, trusted experiment bookkeeping must identify the
current reference run and snapshot independently of the replayed payload.
The payload's retained identifiers describe the earlier state. Do not use
that earlier state as the current expected truth. All measurement rows from
the replayed delivery receive attack_label=1, even if some values happen to
match current conditions. Current-reference bookkeeping and its storage
format remain subject to team agreement before integration.

Combined row granularity: **one measurement from one received device delivery**. Flatten `measurements` after receipt. Required columns: `schema_version`, `delivery_id`, `message_id`, `original_message_id`, `run_id`, `snapshot_id`, `timestamp`, `received_at`, `scenario`, `device`, `measurement`, `unit`, `expected_value`, `received_value`, `condition_type`, `attack_type`, `attack_label`, `attack_target`. All flattened measurements from the same delivery share `delivery_id`; `(delivery_id, measurement)` is unique. `measurement` is the exact nested key, e.g. `active_power_kw`; `unit` is from the mapping. Expected values must use the same telemetry units as received values.

Use trusted experiment bookkeeping and immutable publisher logs to resolve original messages and snapshot truth. Record unresolved joins as diagnostics; do not silently assign a benign label. Benign records have empty `attack_target`. `attack_label=1` applies to every measurement row from a delivery containing an attack, including unchanged sibling measurements; `attack_target` identifies the scalar actually changed. Thus message-level attack presence is distinct from per-measurement corruption. Scenario-to-condition mapping lives in `data/metadata/scenarios.csv`.

`attack_label`: 0 benign, 1 attack. `attack_type`: none, false_data_injection, replay_attack. Legitimate high demand and dust remain benign. `attack_label`, `attack_type`, `condition_type`, and `attack_target` are evaluation labels/metadata and prohibited detector input features. Identifiers and scenario metadata should also be excluded from learned features unless an explicit evaluation design justifies them.

An expected-value detector assumes access to an independent trusted reference; disclose this assumption. Prevent leakage across original/manipulated pairs and related snapshots when constructing evaluation splits.

## Changes requiring team review

Review the grouped-device envelope, separate ground-truth labels, identifiers, combined-row design, and timestamp semantics. Decide high-demand pump reactive power/power factor before scenario implementation. Version 1.0 denotes this proposed grouped contract; define any replay/disruption extensions before use. Update this document and notify teammates before renaming shared fields. Current examples are interface fixtures only; no published research dataset exists yet.

## Publisher integration candidate — 2026-11-04

On `integration-publisher`, the original-message publisher follows Brian's `2fb885d` implementation and uses `grid/telemetry/{device}`. Consumers subscribe to `grid/telemetry/+` or `grid/telemetry/#`, rather than the exact parent topic. This documents tested candidate behavior; it does not imply team approval of relay/detector routing. The envelope, unit mappings, identities and label separation above are unchanged.

Publisher QoS1 acknowledgments confirm broker acceptance, while delivery logs must confirm subscriber receipt. CSV timestamps remain simulated event time; they are not publish-time or latency measurements. Retrying a partially acknowledged batch preserves message IDs and can cause repeated deliveries; distinguish them by delivery IDs.

## Relay experiment records — 2026-11-07

The bounded integration runner records the existing live envelope unchanged on per-device original and processed topics. No attack/condition labels are added to telemetry. Each receiving client assigns its own `delivery_id` and actual UTC `received_at`; relay input IDs and downstream receipt IDs describe different deliveries.

`attack_records.jsonl` retains the attack function's fields and adds `relay_delivery_id`, identifying the recorded original message delivery at the relay. `attack_deliveries.jsonl` copies that trusted sidecar record and adds downstream `delivery_id` after receiving an exact-match forwarded payload. These are separate experiment logs, not changes to the envelope or to the required combined CSV columns. The runner forwards each original ID once; repeated raw deliveries are retained in the input log. All downstream deliveries receive distinct IDs and attacked copies link to the same originating injection record.

This initial bounded configuration attacks one existing scalar on one device across all three scenarios or forwards the entire batch unchanged. Original IDs, scenario and simulated timestamp are preserved. Unknown/mismatched source or received messages fail the experiment; no unresolved match is silently labeled benign. Physical source truth remains separate from forwarding bookkeeping. Dynamic attack toggles, replay and identity manipulation need separate lineage rules before use.

## Integration compatibility — nested attack details

Current relay outputs store Audrey's shared nested attack records as JSONL. `attack_records.jsonl` adds `relay_delivery_id`; `attack_deliveries.jsonl` additionally links the same record to downstream `delivery_id`. Attack-specific values remain inside `false_data_injection` or `replay`, never inside live telemetry. This JSONL representation does not decide the still-pending CSV serialization of nested attack details or rename the combined dataset fields.

Earlier archived flat FDI JSONL records remain readable by the FDI batch verifier without changing the source files. New experiments emit nested records. The current live runner/batch does not perform replay; earlier payload identity must be separated from current physical reference identity before replay transport/dataset integration.
