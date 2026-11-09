# NASA POWER hourly input validation. No interpolation or silent missing-data repair.
from datetime import datetime, timedelta, timezone
import math

def weather_rows(payload: dict) -> list[dict]:
    header = payload["header"]
    if header["time_standard"] != "UTC":
        raise ValueError("Weather input must use UTC")

    expected_units = {"ALLSKY_SFC_SW_DWN": "Wh/m^2", "T2M": "C"}
    parameters = payload["properties"]["parameter"]
    start = datetime.strptime(header["start"], "%Y%m%d").replace(tzinfo=timezone.utc)
    end = datetime.strptime(header["end"], "%Y%m%d").replace(tzinfo=timezone.utc) + timedelta(days=1)
    if end <= start:
        raise ValueError("Invalid weather date range")
    keys = []
    cursor = start

    while cursor < end:
        keys.append(cursor.strftime("%Y%m%d%H"))
        cursor += timedelta(hours=1)

    for name, unit in expected_units.items():
        if payload["parameters"][name]["units"] != unit:
            raise ValueError(f"Unexpected units for {name}")
        if set(parameters[name]) != set(keys):
            raise ValueError(f"Missing or extra hourly records for {name}")
    rows = []

    for key in keys:
        values = {}
        for name in expected_units:
            raw = parameters[name][key]
            if isinstance(raw, bool) or not isinstance(raw, (float, int)):
                raise ValueError(f"Nonnumeric weather value: {name} {key}")
            if not math.isfinite(raw) or raw == header["fill_value"]:
                raise ValueError(f"Missing/nonfinite weather value: {name} {key}")

            values[name] = float(raw)

        ghi = values["ALLSKY_SFC_SW_DWN"]

        if ghi < 0:
            raise ValueError("Negative solar radiation")
        rows.append({
            "timestamp": datetime.strptime(key, "%Y%m%d%H").strftime("%Y-%m-%dT%H:00:00Z"),
            "ghi_wh_m2": ghi,

            # One-hour energy / one hour = hourly mean power density.
            "ghi_mean_w_m2": ghi / 1.0,
            "temperature_2m_c": values["T2M"],
        })
    return rows

def solar_proxy_mw(ghi_mean_w_m2: float, dust_fraction: float = 0.0) -> float:
    # simplified horizontal irradiance proxy, NOT a calibrated PV system model.
    if not math.isfinite(ghi_mean_w_m2) or ghi_mean_w_m2 < 0:
        raise ValueError("Irradiance must be finite and nonnegative")

    if not math.isfinite(dust_fraction) or not 0 <= dust_fraction <= 1:
        raise ValueError("Dust fraction must be between zero and one")

    # assumptions: 150 kW reference output at 1000 W/m² and 150 kW cap.
    return min(0.150, 0.150 * ghi_mean_w_m2 / 1000.0) * (1.0 - dust_fraction)
