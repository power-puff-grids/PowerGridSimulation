import csv
from uuid import UUID
import pytest
from powergrid_sim.physical_export import DEFAULT_TIMESTAMP, PROJECT_ROOT, physical_row, write_physical_csv
from powergrid_sim.run_scenarios import run_scenario
from powergrid_sim.scenarios import get_scenarios

def test_three_snapshot_csv_roundtrip(tmp_path):
    rows = []
    for scenario in get_scenarios():
        net = run_scenario(scenario)
        row = physical_row(net, scenario, "test-run", DEFAULT_TIMESTAMP)
        assert row["bus_4_voltage_pu"] == net.res_bus.at[3, "vm_pu"]
        assert row["line_2_loading_percent"] == net.res_line.at[1, "loading_percent"]
        assert row["solar_output_mw"] == net.res_sgen.at[0, "p_mw"]
        assert row["pump_demand_mw"] == net.res_load.at[0, "p_mw"]
        assert row["pump_reactive_demand_mvar"] == net.res_load.at[0, "q_mvar"]
        UUID(row["snapshot_id"])
        rows.append(row)
    output = tmp_path / "nested/physical_results.csv"
    write_physical_csv(rows, output)
    with output.open(newline="") as source:
        reader = csv.DictReader(source)
        with (PROJECT_ROOT / "data/sample/physical_results_header.csv").open(newline="") as template:
            assert reader.fieldnames == next(csv.reader(template))
        saved = list(reader)
    assert len(saved) == 3
    assert len({row["snapshot_id"] for row in saved}) == 3
    assert {row["run_id"] for row in saved} == {"test-run"}
    assert {row["timestamp"] for row in saved} == {DEFAULT_TIMESTAMP}
    assert all(row["converged"] == "True" for row in saved)
    assert [float(row["solar_output_mw"]) for row in saved] == [0.15, 0.15, 0.075]

def test_export_rejects_invalid_results():
    scenario = get_scenarios()[0]
    net = run_scenario(scenario)
    net.res_bus.loc[0, "vm_pu"] = float("nan")
    with pytest.raises(ValueError, match="missing or infinite"):
        physical_row(net, scenario, "test-run", DEFAULT_TIMESTAMP)

def test_schema_error_preserves_previous_file(tmp_path):
    output = tmp_path / "physical_results.csv"
    output.write_text("previous results")
    with pytest.raises(ValueError, match="shared schema"):
        write_physical_csv([{"unexpected": 1}], output)
    assert output.read_text() == "previous results"
