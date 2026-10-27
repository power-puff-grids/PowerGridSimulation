import pytest
from powergrid_sim.run_scenarios import run_scenario
from powergrid_sim.scenarios import get_scenarios
from powergrid_sim.validation import validate_results

@pytest.fixture
def solved_grid():
    return run_scenario(get_scenarios()[0])

@pytest.mark.parametrize("scenario", get_scenarios(), ids=lambda s: s.scenario)
def test_required_scenarios_pass(scenario):
    validate_results(run_scenario(scenario))

def test_rejects_nonconvergence(solved_grid):
    solved_grid.converged = False
    with pytest.raises(ValueError, match="did not converge"):
        validate_results(solved_grid)

@pytest.mark.parametrize("bad_value", [float("nan"), float("inf")])
def test_rejects_nonfinite_voltage(solved_grid, bad_value):
    solved_grid.res_bus.loc[0, "vm_pu"] = bad_value
    with pytest.raises(ValueError, match="missing or infinite"):
        validate_results(solved_grid)

def test_rejects_missing_line_result(solved_grid):
    solved_grid.res_line.drop(solved_grid.res_line.index[0], inplace=True)
    with pytest.raises(ValueError, match="missing or mismatched"):
        validate_results(solved_grid)

@pytest.mark.parametrize("power", ["p_mw", "q_mvar"])
def test_rejects_power_imbalance(solved_grid, power):
    solved_grid.res_ext_grid.loc[0, power] += 0.001
    with pytest.raises(ValueError, match="Power balance failed"):
        validate_results(solved_grid)

@pytest.mark.parametrize("soc", [float("nan"), -1.0, 101.0])
def test_rejects_invalid_soc(solved_grid, soc):
    solved_grid.storage.loc[0, "soc_percent"] = soc
    with pytest.raises(ValueError, match="Battery SOC"):
        validate_results(solved_grid)