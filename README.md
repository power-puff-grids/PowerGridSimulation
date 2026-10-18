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
