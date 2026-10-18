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

Proposed attack log columns: `attack_id`, `original_message_id`, `delivery_id`, `attack_type`, `attack_target`, `original_value`, `manipulated_value`, `injected_at`. For the first controlled false-data experiment, change one scalar per attack; `attack_target` is a path such as `measurements.active_power_kw`. `delivery_id` is populated by trusted experiment bookkeeping when the manipulated message is received. Numeric values use the targeted measurement's units. `injected_at` is actual UTC injection time. The attack copy preserves the original envelope identifiers so the initial attack changes only the targeted measurement; it must not mutate the original object or log. Separate delivery IDs disambiguate originals and manipulated copies. Replay, identifier tampering and multi-field attacks require a documented extension before implementation.

Combined row granularity: **one measurement from one received device delivery**. Flatten `measurements` after receipt. Required columns: `schema_version`, `delivery_id`, `message_id`, `original_message_id`, `run_id`, `snapshot_id`, `timestamp`, `received_at`, `scenario`, `device`, `measurement`, `unit`, `expected_value`, `received_value`, `condition_type`, `attack_type`, `attack_label`, `attack_target`. All flattened measurements from the same delivery share `delivery_id`; `(delivery_id, measurement)` is unique. `measurement` is the exact nested key, e.g. `active_power_kw`; `unit` is from the mapping. Expected values must use the same telemetry units as received values.

Use trusted experiment bookkeeping and immutable publisher logs to resolve original messages and snapshot truth. Record unresolved joins as diagnostics; do not silently assign a benign label. Benign records have empty `attack_target`. `attack_label=1` applies to every measurement row from a delivery containing an attack, including unchanged sibling measurements; `attack_target` identifies the scalar actually changed. Thus message-level attack presence is distinct from per-measurement corruption. Scenario-to-condition mapping lives in `data/metadata/scenarios.csv`.

`attack_label`: 0 benign, 1 attack. `attack_type`: none, false_data_injection, replay_attack. Legitimate high demand and dust remain benign. `attack_label`, `attack_type`, `condition_type`, and `attack_target` are evaluation labels/metadata and prohibited detector input features. Identifiers and scenario metadata should also be excluded from learned features unless an explicit evaluation design justifies them.

An expected-value detector assumes access to an independent trusted reference; disclose this assumption. Prevent leakage across original/manipulated pairs and related snapshots when constructing evaluation splits.

## Changes requiring team review

Review the grouped-device envelope, separate ground-truth labels, identifiers, combined-row design, and timestamp semantics. Decide high-demand pump reactive power/power factor before scenario implementation. Version 1.0 denotes this proposed grouped contract; define any replay/disruption extensions before use. Update this document and notify teammates before renaming shared fields. Current examples are interface fixtures only; no published research dataset exists yet.
