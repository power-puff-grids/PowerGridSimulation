from math import acos, tan

HP_TO_KW = 0.7457  # mechanical horsepower conversion to kW
# https://www.energy.gov/sites/default/files/2014/04/f15/10097517.pdf

MOTOR_REFERENCES = { 
    "well": {
        "model": "BMR VHS405TP-4-125P",
        "rated_hp": 125.0,
        "full_load_efficiency": 0.954,
        "full_load_power_factor": 0.865,
        "source": "https://bmr-usa.com/wp-content/uploads/2022/11/BMR-USA-PRICING-CATALOG-FINAL-2.pdf",
    },
    "booster": {
        "model": "Baldor EFM4110T",
        "rated_hp": 40.0,
        "full_load_efficiency": 0.941,  # nominal basis, not typical curve
        "full_load_power_factor": 0.82,
        "source": "https://www.baldor.com/catalog/EFM4110T",
    },
}


def full_load_motor_demand(motor_name: str) -> tuple[float, float]:
    motor = MOTOR_REFERENCES[motor_name]
    active_kw = motor["rated_hp"] * HP_TO_KW / motor["full_load_efficiency"]
    reactive_kvar = active_kw * tan(acos(motor["full_load_power_factor"]))
    return active_kw / 1000.0, reactive_kvar / 1000.0
