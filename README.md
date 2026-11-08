# PowerGridSimulation

Power Puff Grids: synthetic agricultural power-grid simulation and cyber-physical telemetry research, contextualized to the Central Valley/Bakersfield area. This is not measured utility or farm data.

The first pipeline is Pandapower → MQTT → false-data injection → expected-value detection and alert. The four-bus model is being developed on the `simulation` branch. The shared foundation on `main` does not yet include a runnable simulation or validated results.

## Shared interfaces

Read [DATA_SCHEMA.md](DATA_SCHEMA.md) before implementing telemetry, attacks or dataset joins. It is a draft for team review and records the proposed shared interfaces and open decisions.

- `data/raw_context/`: source inputs with provenance and redistribution terms.
- `data/generated/`: reproducible local outputs; ignored by Git except its directory placeholder.
- `data/sample/`: explicitly labeled interface fixtures; not validated research results.
- `data/metadata/`: feature definitions, provisional scenarios and source tracking.

Brooklyn produces physical results; Brian publishes/subscribes to `grid/telemetry`; Audrey modifies copies of messages; Alina combines records and detects discrepancies. The proposed v1.0 telemetry contract groups measurements by device and snapshot; attack labels stay in a separate ground-truth log. Physical results retain MW/per-unit units; telemetry uses explicit kW/kV keys with documented conversions. Review the contract before integration.

## Simulation status

This integration branch contains the runnable four-bus simulation, three scenarios, validated physical/telemetry exports, and a tested controlled MQTT attack relay. Combined dataset assembly and detection remain the next stage. Some older sample files remain interface illustrations; the solver-derived normal snapshot is labeled separately.

Work on assigned branches and merge reviewed PRs into main. Do not treat provisional ratings or example records as measured observations. Source acquisition, physical validation, reproducibility verification and dataset licensing remain required before publication.

## Publisher integration checkpoint (updated 2026-11-07)

Branch: `integration-publisher`, based on simulation `c6c75fc`. Brian's complete MQTT branch through `54c6882` (2026-11-05) is merged with history preserved, including handlers and packaging metadata. Publisher integration changes are applied on top of that merge. No changes have been made to the remote MQTT branch.

The integration copy of `Comms` adds optional host/port, an optional QoS argument, and returns Paho's publish receipt. Existing defaults remain localhost:1883 and QoS0. The publisher requests QoS1 and waits for each broker acknowledgment before closing. It reports partial progress on errors. Broker acknowledgment does not prove subscriber receipt or detection. QoS1 can produce duplicate deliveries; preserve delivery IDs downstream.

Install the dependencies in a virtual environment, then use three terminals from this checkout:

```sh
python3.14 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Terminal 1: start the project broker in the foreground (no background service required):

```sh
mosquitto -p 1883
```

Terminal 2: subscribe before publishing:

```sh
mosquitto_sub -h localhost -p 1883 -t 'grid/telemetry/#' -q 1 -v
```

Terminal 3, with the virtual environment active:

```sh
PYTHONPATH=src python -m powergrid_sim.run_scenarios
PYTHONPATH=src python -m powergrid_sim.publish_telemetry
```

Publisher options: `--input PATH`, `--host HOST`, `--port PORT`, `--timeout SECONDS`. The default input is `data/generated/mqtt_telemetry.csv`. The command validates the complete file before connecting, parses measurements as JSON, and preserves all original identifiers and timestamps. Each message goes to `grid/telemetry/{device}`, following Brian's current sender. Team agreement/schema documentation for forwarded relay topics remains pending. This entry point does not invoke attack or detection handlers.

The physical CSV exporter also now writes lowercase `true`/`false`, matching DATA_SCHEMA.md.

Verification: all 36 tests passed using CPython3.14.4, Paho2.2.0 and Mosquitto2.1.2. The live test generated three scenarios, published 30 envelopes, and compared every received payload and device topic to its original. Its broker uses an ephemeral loopback port and is stopped afterward. Run `PYTHONPATH=src python -m pytest -q tests`; the live test skips if Mosquitto is unavailable. Homebrew's Mosquitto executable is also detected at `/opt/homebrew/opt/mosquitto/sbin/mosquitto`.

No experiment messages were sent to a remote broker. The temporary Python test environment's alternative broker package was not used for the live verification. Final tests used Mosquitto.

## MQTT branch merge verification — 2026-11-07

Merged the full MQTT branch through `54c6882` while retaining simulation `c6c75fc` and the publisher integration changes. Resolved the dependency conflict by retaining python-igraph and Paho. All 36 tests passed, including the live Mosquitto test with 30 generated messages. An additional offline check verified the merged handlers with the attack function from `77b04f0`: valid envelopes, recording/quarantine, selected-device attacks, unchanged forwarding, disable, original preservation, and separate attack records passed.

Follow-up validation issues: a malformed date ending in Z is accepted by the handler validator; a list-valued device field raises TypeError instead of returning validation errors. These edge cases were fixed during the relay integration below, with regression tests. The full attack relay over MQTT and downstream detection have not been verified by this checkpoint.

## Bounded relay experiments (2026-11-07)

The integration branch merges Audrey's attack branch through `77b04f0` and uses its existing `false_data_injection` function with Brian's `AttackRouter`, `AttackRelay`, and `Recorder`. Start Mosquitto in another terminal, then run from this checkout with the environment active:

```sh
# Forward all three scenarios unchanged:
PYTHONPATH=src python -m integration.run_relay

# Add 30 kW to solar telemetry in each scenario:
PYTHONPATH=src python -m integration.run_relay --attack-device solar_pv --measurement active_power_kw --offset 30

# Reduce received battery SOC by 10 percentage points:
PYTHONPATH=src python -m integration.run_relay --attack-device battery --measurement soc_percent --offset -10
```

Each invocation generates a fresh physical run and 30 original messages, waits until both subscriptions are accepted, publishes originals to `grid/telemetry/{device}`, and records deliveries from `grid/processed/{device}`. Use `--host`, `--port`, `--timeout`, and `--output-root` as needed. Offsets use the selected measurement's documented units. Without `--attack-device`, all messages pass unchanged. An enabled attack applies to the selected device in all three scenarios; the physical scenario name remains unchanged. The process ends after the complete batch is forwarded and received. Run one experiment at a time on these shared topics; unexpected or mismatched traffic fails the run rather than receiving a guessed label.

Outputs are isolated under `data/generated/experiments/<experiment_id>/` (ignored by Git):

- `physical_results.csv` and `mqtt_telemetry.csv`: original simulation truth and original envelopes.
- `relay_input.jsonl`: original deliveries with receipt metadata; repeated incoming deliveries are logged but each original message identity is forwarded once.
- `forwarded_messages.jsonl`: forwarded payloads, original relay-delivery linkage, actual forwarding time, and destination topic.
- `received_messages.jsonl`: processed deliveries with new delivery IDs and actual UTC receipt time; duplicate downstream deliveries remain distinct.
- `attack_records.jsonl`: separate injection records linked to the relay input delivery.
- `attack_deliveries.jsonl`: injection records linked to actual downstream delivery IDs using controlled forwarding bookkeeping.
- Relay/receiver quarantine logs, simulation stdout/stderr logs, and `summary.json` with configuration, counts, times, and completion/failure status.

Original messages are never rewritten by attacks. Experiment identifiers and actual receipt times are metadata; simulated timestamps remain the fixed fixture time. Fresh UUID output folders avoid overwriting earlier runs. Failed experiments retain their artifacts and a failed summary. Received payloads are checked against exact proposed forwarding payloads only to validate transport/lineage; a future detector must compare to the independent original physical baseline, not to the attack-modified forwarding copy.

The receive callback queues relay work. A separate worker runs routing and waits for QoS1 acknowledgments, allowing MQTT's network thread to continue processing them. Generic send/subscribe now accept optional QoS and return Paho results. The envelope validator now rejects malformed dates and nonstring device identifiers.

Verification: `PYTHONPATH=src python -m pytest -q tests src/attacks/Tests` passed 56 tests, including three live Mosquitto cases: benign forwarding, solar injection, and battery-SOC injection. Each received 30 messages with exact expected payloads; attack cases had three modified messages and three downstream attack links. Detector alerts and the final combined dataset are the next stage.
