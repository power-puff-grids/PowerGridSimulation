# Shared data contract — draft v0.1

Status: proposed for team review; not yet an approved interface. Samples illustrate the contract and are not validated simulation results. This is synthetic simulation data, not measured farm or utility data.

## Identity, time and units

`run_id` identifies one execution. `snapshot_id` uniquely identifies one physical state within that execution and is copied unchanged into its derived messages. Use globally unique identifiers (UUIDs recommended). `message_id` uniquely identifies an individual telemetry message. These three fields are proposed additions to the original shared fields. Match physical truth using `(run_id, snapshot_id)`, then device and measurement; timestamps alone are not join keys.

`timestamp` is the simulated event time, encoded as UTC ISO 8601 with a `Z` suffix. It must not be represented as a real historical observation. Every measurement from a snapshot shares its timestamp. Independent snapshots do not imply elapsed-time dynamics. Future `published_at` and `received_at` fields must denote actual communication times and be documented before use. Scenario names or ordering must not be used to infer elapsed time.

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

One JSON object per measurement. Required original fields remain unchanged: `timestamp`, `scenario`, `device`, `measurement`, `value`, `unit`, `condition_type`, `attack_type`, `attack_label`. Proposed additional required fields: `run_id`, `snapshot_id`, `message_id`.

`value` is a finite JSON number. All other fields are nonempty strings except `attack_label`, an integer. Benign publisher messages use `attack_type="none"` and `attack_label=0`. Scenario-to-condition mapping is in `data/metadata/scenarios.csv`.

| Device | Measurement | Unit | Physical CSV source |
|---|---|---|---|
| bus_1 … bus_4 | voltage_pu | pu | bus_N_voltage_pu |
| line_1 … line_3 | loading_percent | % | line_N_loading_percent |
| solar_pv | power_mw | MW | solar_output_mw |
| irrigation_pump | power_mw | MW | pump_demand_mw |
| irrigation_pump | reactive_power_mvar | MVAr | pump_reactive_demand_mvar |
| battery | power_mw | MW | battery_power_mw |
| battery | soc_percent | % | battery_soc_percent |

The baseline mapping yields 12 measurement messages per snapshot. `mqtt_telemetry.csv` uses the JSON field names as columns. A future receipt log must preserve duplicate arrivals instead of silently deduplicating replay messages.

## Attacks and combined dataset

Never mutate original physical rows or original messages. Attack metadata is trusted sidecar ground truth, not authenticated by the telemetry payload. Never trust payload labels as detector evidence.

Proposed attack log columns: `attack_id`, `original_message_id`, `manipulated_message_id`, `attack_type`, `attack_target`, `original_value`, `manipulated_value`, `injected_at`. Attack types initially supported: `false_data_injection`; reserve `replay_attack` for a later documented extension. Attack targets identify the changed field. Units are inherited from the original message. `injected_at` is actual UTC injection time. A changed envelope gets a new message identity and explicit original linkage. Replay may preserve payload identity and needs a separate delivery identity before implementation.

Proposed combined row granularity: one received delivery of one measurement. Required columns: `delivery_id`, `message_id`, `original_message_id`, `run_id`, `snapshot_id`, `timestamp`, `received_at`, `scenario`, `device`, `measurement`, `unit`, `expected_value`, `received_value`, `condition_type`, `attack_type`, `attack_label`, `attack_target`. Each delivery gets a unique ID. Benign rows link to their own original message and use empty `attack_target`; attacks link to the immutable original. Expected values come from the physical truth mapping, not the manipulated message. Do not create this output until the team agrees on identity propagation and subscriber behavior.

`attack_label`: 0 benign, 1 attack. `attack_type`: none, false_data_injection, replay_attack. Legitimate high demand and dust remain benign. `attack_label`, `attack_type`, `condition_type`, and `attack_target` are evaluation labels/metadata and prohibited detector input features. Identifiers and scenario metadata should also be excluded from learned features unless an explicit evaluation design justifies them.

An expected-value detector assumes access to an independent trusted reference; disclose this assumption. Prevent leakage across original/manipulated pairs and related snapshots when constructing evaluation splits.

## Changes requiring team review

Confirm proposed identifiers, combined-row design, and timestamp semantics. Decide high-demand pump reactive power/power factor before scenario implementation. Define schema versioning and any replay/disruption extensions before use. Update this document and notify teammates before renaming shared fields. Current examples are interface fixtures only; no published research dataset exists yet.
