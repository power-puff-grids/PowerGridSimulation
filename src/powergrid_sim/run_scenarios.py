"""Run independent steady-state scenarios on the same four-bus design."""
import pandapower as pp
from .build_grid import build_grid
from .scenarios import Scenario, get_scenarios
from .validation import validate_results

def apply_scenario(net: pp.pandapowerNet, scenario: Scenario) -> None:
    # inputs for the single PV, pump equivalent, and battery.
    for table in (net.sgen, net.load, net.storage):
        if len(table) != 1:
            raise ValueError("Expected exactly one solar generator, pump load, and battery.")

    solar = net.sgen.index[0]
    pump = net.load.index[0]
    battery = net.storage.index[0]
    net.sgen.loc[solar, "p_mw"] = scenario.solar_setpoint_mw
    net.load.loc[pump, "p_mw"] = scenario.pump_setpoint_mw
    net.load.loc[pump, "q_mvar"] = scenario.pump_reactive_setpoint_mvar
    net.storage.loc[battery, "p_mw"] = scenario.battery_setpoint_mw
    net.storage.loc[battery, "soc_percent"] = scenario.battery_soc_percent

def run_scenario(scenario: Scenario) -> pp.pandapowerNet:
    # rebuild the network (from start), apply inputs, and return its solved results.
    net = build_grid()
    apply_scenario(net, scenario)
    pp.runpp(net, numba=False) 
    validate_results(net)
    return net

def main() -> None:
    for scenario in get_scenarios():
        net = run_scenario(scenario)
        print(f"\nScenario: {scenario.scenario}")
        print(scenario.description)
        print(f"Converged: {net.converged}")
        print("Numerical validation: passed")
        print("Bus voltages (pu):")
        print(net.res_bus[["vm_pu"]].to_string())
        print("Line loading (%):")
        print(net.res_line[["loading_percent"]].to_string())
        print(f"Solar output (MW): {net.res_sgen.p_mw.sum():.9f}")
        print(f"Pump demand (MW): {net.res_load.p_mw.sum():.9f}")
        print(f"Pump reactive demand (MVAr): {net.res_load.q_mvar.sum():.9f}")
        print(f"Battery power (MW): {net.res_storage.p_mw.sum():.9f}")
        print(f"Battery SOC (%): {net.storage.soc_percent.iloc[0]:.1f}")
        print(f"Utility power (MW; positive import, negative export): {net.res_ext_grid.p_mw.sum():.9f}")
        print(f"Active line losses (MW): {net.res_line.pl_mw.sum():.9f}")



if __name__ == "__main__":
    main()
