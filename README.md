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

Simulation implementation and validated run instructions will arrive in a separate reviewed PR. The `src/powergrid_sim/build_grid.py` file on this branch is currently a placeholder. Sample data here demonstrates interfaces only.

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

Follow-up validation issues: a malformed date ending in Z is accepted by the handler validator; a list-valued device field raises TypeError instead of returning validation errors. These edge cases are recorded for follow-up; the handler implementation is otherwise unchanged from its source branch. The full attack relay over MQTT and downstream detection have not been verified by this checkpoint.
