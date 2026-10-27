"""Check simulation-to-message conversion without an MQTT broker."""

from copy import deepcopy
import csv
import json
from uuid import UUID

import pytest

from powergrid_sim.physical_export import DEFAULT_TIMESTAMP, PROJECT_ROOT, physical_row
from powergrid_sim.run_scenarios import run_scenario
from powergrid_sim.scenarios import get_scenarios
from powergrid_sim.telemetry import ENVELOPE_FIELDS, snapshot_messages, write_telemetry_csv


@pytest.fixture
def normal_row():
    scenario = get_scenarios()[0]
    return physical_row(run_scenario(scenario), scenario, "test-run", DEFAULT_TIMESTAMP)


@pytest.mark.parametrize("scenario", get_scenarios(), ids=lambda s: s.scenario)
def test_message_contract_and_csv(scenario, tmp_path):
    net = run_scenario(scenario)
    row = physical_row(net, scenario, "test-run", DEFAULT_TIMESTAMP)
    before = deepcopy(row)
    nominal = {f"bus_{n}": float(net.bus.at[n-1, "vn_kv"]) for n in range(1, 5)}
    messages = snapshot_messages(row, nominal)
    assert row == before
    assert len(messages) == 10
    assert len({m["message_id"] for m in messages}) == 10
    with (PROJECT_ROOT / "data/metadata/telemetry_measurements.csv").open(newline="") as source:
        mapping = list(csv.DictReader(source))
    expected_keys = {}
    for item in mapping:
        expected_keys.setdefault(item["device"], set()).add(item["measurement"])
    assert {m["device"]: set(m["measurements"]) for m in messages} == expected_keys
    assert sum(len(m["measurements"]) for m in messages) == 15
    for message in messages:
        assert set(message) == set(ENVELOPE_FIELDS)
        UUID(message["message_id"])
        assert message["schema_version"] == "1.0"
        for key in ("run_id", "snapshot_id", "timestamp", "scenario"):
            assert message[key] == row[key]
        for item in (r for r in mapping if r["device"] == message["device"]):
            expected = row[item["physical_field"]]
            if item["unit"] == "kV":
                bus = item["physical_field"].removesuffix("_voltage_pu")
                expected *= nominal[bus]
            elif item["unit"] in ("kW", "kvar"):
                expected *= 1000
            assert message["measurements"][item["measurement"]] == expected
    output = tmp_path / "nested/messages.csv"
    write_telemetry_csv(messages, output)
    with output.open(newline="") as source:
        reader = csv.DictReader(source)
        assert reader.fieldnames == ENVELOPE_FIELDS
        saved = list(reader)
    assert len(saved) == 10
    for stored, message in zip(saved, messages):
        assert json.loads(stored.pop("measurements")) == message["measurements"]
        assert stored == {k: v for k, v in message.items() if k != "measurements"}


def test_uses_each_bus_nominal_voltage(normal_row):
    nominal = {"bus_1": 12.47, "bus_2": 11.0, "bus_3": 10.0, "bus_4": 9.0}
    devices = {m["device"]: m["measurements"] for m in snapshot_messages(normal_row, nominal)}
    assert devices["solar_pv"]["voltage_kv"] == normal_row["bus_2_voltage_pu"] * 11.0
    assert devices["battery"]["voltage_kv"] == normal_row["bus_3_voltage_pu"] * 10.0
    assert devices["irrigation_pump"]["voltage_kv"] == normal_row["bus_4_voltage_pu"] * 9.0


@pytest.mark.parametrize("value", [float("nan"), float("inf"), True])
def test_rejects_invalid_measurements(normal_row, value):
    normal_row["pump_demand_mw"] = value
    with pytest.raises(ValueError):
        snapshot_messages(normal_row, {f"bus_{n}": 12.47 for n in range(1, 5)})


def test_rejects_unsolved_row(normal_row):
    normal_row["converged"] = False
    with pytest.raises(ValueError, match="converged"):
        snapshot_messages(normal_row, {f"bus_{n}": 12.47 for n in range(1, 5)})


def test_rejects_invalid_nominal_voltage(normal_row):
    nominal = {f"bus_{n}": 12.47 for n in range(1, 5)}
    nominal["bus_2"] = 0
    with pytest.raises(ValueError, match="positive"):
        snapshot_messages(normal_row, nominal)
