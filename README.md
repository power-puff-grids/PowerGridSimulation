# PowerGridSimulation

Power Puff Grids: synthetic agricultural power-grid simulation and cyber-physical telemetry research, contextualized to the Central Valley/Bakersfield area. This is not measured utility or farm data.

The first pipeline is Pandapower → MQTT → false-data injection → expected-value detection and alert. The existing four-bus model is in `src/powergrid_sim/build_grid.py`; multi-scenario generation and export are not yet complete or validated.

## Shared interfaces

Read [DATA_SCHEMA.md](DATA_SCHEMA.md) before implementing telemetry, attacks or dataset joins. It is a draft for team review and records the proposed shared interfaces and open decisions.

- `data/raw_context/`: source inputs with provenance and redistribution terms.
- `data/generated/`: reproducible local outputs; ignored by Git except its directory placeholder.
- `data/sample/`: explicitly labeled interface fixtures; not validated research results.
- `data/metadata/`: feature definitions, provisional scenarios and source tracking.

Brooklyn produces physical results; Brian publishes/subscribes to `grid/telemetry`; Audrey modifies copies of messages; Alina combines records and detects discrepancies. Coordinate proposed identifiers and timestamp semantics before integration.

## Existing model

Use a project virtual environment with dependencies from `requirements.txt`. Run `python src/powergrid_sim/build_grid.py` from the repository root. The existing script runs one snapshot, prints results and opens a plot; this draft does not claim it has been validated or that it exports the agreed CSV yet.

Work on assigned branches and merge reviewed PRs into main. Do not treat provisional ratings or example records as measured observations. Source acquisition, physical validation, reproducibility verification and dataset licensing remain required before publication.
