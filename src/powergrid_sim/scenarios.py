"""Independent benign snapshots. Inputs are not measured farm observations."""
from dataclasses import dataclass
from .pump_parameters import full_load_motor_demand

NORMAL_SOLAR_MW = 0.15  # Provisional engineering assumption: 150 kW
DUST_SOLAR_REDUCTION = 0.50  # Synthetic condition: 50% less solar output


@dataclass(frozen=True)
class Scenario:
    """Input settings for one snapshot... these are not power-flow results."""

    scenario: str
    condition_type: str
    description: str
    solar_setpoint_mw: float
    pump_setpoint_mw: float
    pump_reactive_setpoint_mvar: float
    battery_setpoint_mw: float = 0.0  # Idle. positive means charging
    battery_soc_percent: float = 50.0  # Assumed initial SOC. no time evolution

def get_scenarios() -> tuple[Scenario, ...]:
    """Calculate pump settings from the documented full-load motor references."""
    booster_p, booster_q = full_load_motor_demand("booster")
    well_p, well_q = full_load_motor_demand("well")

    return (
        Scenario(
            scenario="normal",
            condition_type="normal",
            description="Booster at rated output, well off, reservoir water available.",
            solar_setpoint_mw=NORMAL_SOLAR_MW,
            pump_setpoint_mw=booster_p,
            pump_reactive_setpoint_mvar=booster_q,
        ),
        Scenario(
            scenario="high_irrigation_demand",
            condition_type="high_irrigation",
            description="Booster and well at rated output simultaneously.",
            solar_setpoint_mw=NORMAL_SOLAR_MW,
            pump_setpoint_mw=booster_p + well_p,
            pump_reactive_setpoint_mvar=booster_q + well_q,
        ),
        Scenario(
            scenario="dust_reduced_solar",
            condition_type="dust_reduced_solar",
            description="Normal pump state, controlled synthetic 50% solar reduction.",
            solar_setpoint_mw=NORMAL_SOLAR_MW * (1.0 - DUST_SOLAR_REDUCTION),
            pump_setpoint_mw=booster_p,
            pump_reactive_setpoint_mvar=booster_q,
        ),
    )
