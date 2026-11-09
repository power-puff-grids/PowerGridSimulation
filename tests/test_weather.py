from copy import deepcopy
import pytest
from powergrid_sim.weather import weather_rows, solar_proxy_mw
# check for bad weather parsing and bad conversions. reject all missing hours, incorrect units, incorrect time, and invalid values.
def payload():
    keys = [f"20250701{hour:02}" for hour in range(24)]
    return {"header": {"start": "20250701", "end": "20250701", "time_standard": "UTC", "fill_value": -999},
        "parameters": {"ALLSKY_SFC_SW_DWN": {"units": "Wh/m^2"}, "T2M": {"units": "C"}},
        "properties": {"parameter": {"ALLSKY_SFC_SW_DWN": dict.fromkeys(keys, 500.0), "T2M": dict.fromkeys(keys, 30.0)}}}

def test_hourly_conversion_and_utc():
    rows = weather_rows(payload())
    assert len(rows) == 24
    assert rows[0]["timestamp"] == "2025-07-01T00:00:00Z"
    assert rows[-1]["timestamp"] == "2025-07-01T23:00:00Z"
    assert rows[0]["ghi_mean_w_m2"] == 500
    assert solar_proxy_mw(500) == pytest.approx(0.075)
    assert solar_proxy_mw(500, 0.5) == pytest.approx(0.0375)
    assert solar_proxy_mw(0) == 0
    assert solar_proxy_mw(1100) == 0.15

@pytest.mark.parametrize("value", [-999, float("nan"), float("inf"), True, "500", -1])
def test_invalid_irradiance_is_rejected(value):
    data = payload()
    data["properties"]["parameter"]["ALLSKY_SFC_SW_DWN"]["2025070100"] = value
    with pytest.raises(ValueError):
        weather_rows(data)

@pytest.mark.parametrize("change", ["gap", "extra", "units", "timezone"])
def test_misaligned_or_ambiguous_input_rejected(change):
    data = deepcopy(payload())
    if change == "gap":
        del data["properties"]["parameter"]["T2M"]["2025070100"]
    elif change == "extra":
        data["properties"]["parameter"]["T2M"]["2025070200"] = 30
    elif change == "units":
        data["parameters"]["ALLSKY_SFC_SW_DWN"]["units"] = "kWh/m^2/day"
    else:
        data["header"]["time_standard"] = "LST"
    with pytest.raises(ValueError):
        weather_rows(data)

@pytest.mark.parametrize("ghi,dust", [(-1,0), (float("nan"),0), (500,-0.1), (500,1.1)])
def test_invalid_proxy_inputs(ghi,dust):
    with pytest.raises(ValueError):
        solar_proxy_mw(ghi,dust)
