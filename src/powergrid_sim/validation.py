"""Numerical checks for the current four-bus, line-only feeder model."""
import numpy as np
import pandapower as pp

POWER_BALANCE_TOLERANCE = 1e-8  # MW = active power, MVAr = reactive power
def validate_results(net: pp.pandapowerNet) -> None:
    #Raise ValueError on incomplete, nonfinite, or unbalanced solved results.
    if not net.converged:
        raise ValueError("Power flow did not converge.")

    required = {
        "bus": ["vm_pu", "va_degree"],
        "line": ["loading_percent", "pl_mw", "ql_mvar"],
        "ext_grid": ["p_mw", "q_mvar"],
        "sgen": ["p_mw", "q_mvar"],
        "load": ["p_mw", "q_mvar"],
        "storage": ["p_mw", "q_mvar"],
    }
    for element, columns in required.items():
        result_name = f"res_{element}"
        results = net[result_name]
        if not results.index.equals(net[element].index):
            raise ValueError(f"{result_name}: missing or mismatched device rows.")
        if not np.isfinite(results[columns].to_numpy(dtype=float)).all():
            raise ValueError(f"{result_name}: missing or infinite measurements.")

    soc = net.storage.soc_percent.to_numpy(dtype=float)
    if not np.isfinite(soc).all() or ((soc < 0) | (soc > 100)).any():
        raise ValueError("Battery SOC must be finite and between 0 and 100 percent.")

    # Positive utility power goes to the feeder, positive storage power charges.
    for power, losses, unit in (
        ("p_mw", "pl_mw", "MW"),
        ("q_mvar", "ql_mvar", "MVAr"),
    ):
        residual = (
            net.res_ext_grid[power].sum()
            + net.res_sgen[power].sum()
            - net.res_load[power].sum()
            - net.res_storage[power].sum()
            - net.res_line[losses].sum()
        )
        if abs(residual) > POWER_BALANCE_TOLERANCE:
            raise ValueError(
                f"Power balance failed: residual {residual:.3e} {unit}; "
                f"tolerance {POWER_BALANCE_TOLERANCE:.1e} {unit}."
            )
