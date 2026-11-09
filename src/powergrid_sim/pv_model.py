#Documented synthetic fixed-array model using pvlib and is NOT a farm calibration.
from dataclasses import asdict, dataclass
import math
import numpy as np
import pandas as pd
import pvlib

@dataclass(frozen=True)
class PVConfig:
    latitude: float = 35.205583  # CIMIS125 reference coordinates
    longitude: float = -118.778410
    altitude_m: float = 152.4  # CIMIS125 metadata: 500 ft × 0.3048
    tilt_deg: float = 30.0  # Assumed fixed rack (not optimized)
    azimuth_deg: float = 180.0  # Assumed south-facing array
    dc_capacity_w: float = 150000.0  # Assumed DC nameplate (not observed)
    ac_capacity_w: float = 150000.0  # Assumed AC inverter limit, DC/AC ratio 1
    gamma_pdc: float = -0.004  # Assumed generic coefficient, per degrees C
    inverter_efficiency: float = 0.96  # pvlib PVWatts nominal default
    albedo: float = 0.20  # Assumed ground reflectance
    module_wind_m_s: float = 1.0  # Faiman default assumption (NOT measured wind)
    faiman_u0: float = 25.0  # pvlib default, W/(m^2 C)
    faiman_u1: float = 6.84  # pvlib default, W/(m^2 C (m/s))
    ashrae_b: float = 0.05  # Generic beam incidence-angle loss assumption

def model_config() -> dict:
    return {**asdict(PVConfig()), "irradiance_decomposition": "Erbs",
        "transposition": "isotropic", "beam_iam": "ASHRAE; diffuse IAM=1",
        "temperature": "Faiman", "dc": "PVWatts v5", "inverter": "PVWatts",
        "other_losses_percent": dict(soiling=0, shading=3, snow=0, mismatch=2,
            wiring=2, connections=0.5, lid=1.5, nameplate_rating=1, age=0, availability=3),
        "interval": "UTC start labels; geometry at +30 minutes",
        "dust": "synthetic post-AC scaling; not a physical soiling model"}

def pv_profile(weather: list[dict], config: PVConfig = PVConfig()) -> list[dict]:
    if not weather:
        raise ValueError("Weather profile must not be empty")
    if not all(math.isfinite(v) for v in asdict(config).values()):
        raise ValueError("PV parameters must be finite")
    if not (-90 <= config.latitude <= 90 and -180 <= config.longitude <= 180
            and 0 <= config.tilt_deg <= 90 and 0 <= config.azimuth_deg < 360
            and config.dc_capacity_w > 0 and config.ac_capacity_w > 0
            and 0 < config.inverter_efficiency <= 1 and 0 <= config.albedo <= 1
            and config.module_wind_m_s >= 0 and config.faiman_u0 > 0
            and config.faiman_u1 >= 0 and config.gamma_pdc <= 0 and config.ashrae_b >= 0):
        raise ValueError("Invalid PV configuration")

    frame = pd.DataFrame(weather)
    labels = pd.DatetimeIndex(pd.to_datetime(frame["timestamp"], utc=True))
    if labels.has_duplicates or not labels.is_monotonic_increasing:
        raise ValueError("Weather timestamps must be unique and increasing")

    # Weather loader enforces UTC and complete intervals
    # this function checks physics inputs.
    ghi = np.asarray(frame["ghi_mean_w_m2"], dtype=float)
    air = np.asarray(frame["temperature_2m_c"], dtype=float)

    if not np.isfinite(ghi).all() or not np.isfinite(air).all() or (ghi < 0).any():
        raise ValueError("Invalid irradiance or temperature")

    midpoint = labels + pd.Timedelta(minutes=30)
    position = pvlib.solarposition.get_solarposition(midpoint, config.latitude,
        config.longitude, altitude=config.altitude_m, method="nrel_numpy")
    zenith = np.asarray(position["zenith"], dtype=float)
    azimuth = np.asarray(position["azimuth"], dtype=float)
    parts = pvlib.irradiance.erbs(ghi, zenith, midpoint)
    dni = np.asarray(parts["dni"])
    dhi = np.asarray(parts["dhi"])
    poa = pvlib.irradiance.get_total_irradiance(config.tilt_deg, config.azimuth_deg,
        zenith, azimuth, dni, ghi, dhi, albedo=config.albedo, model="isotropic")
    aoi = pvlib.irradiance.aoi(config.tilt_deg, config.azimuth_deg, zenith, azimuth)
    iam = pvlib.iam.ashrae(aoi, b=config.ashrae_b)
    poa_global = np.asarray(poa["poa_global"])
    effective = np.asarray(poa["poa_direct"]) * iam + np.asarray(poa["poa_diffuse"])

    # Midpoint approximation near sunrise/sunset; record masked source radiation.
    dark = (zenith >= 90) | (ghi == 0)
    effective = np.where(dark, 0.0, effective)
    poa_global = np.where(dark, 0.0, poa_global)
    cell = pvlib.temperature.faiman(poa_global, air, config.module_wind_m_s,
        config.faiman_u0, config.faiman_u1)
    dc = pvlib.pvsystem.pvwatts_dc(effective, cell, config.dc_capacity_w, config.gamma_pdc)
    losses = pvlib.pvsystem.pvwatts_losses(**model_config()["other_losses_percent"])
    dc = np.maximum(0, dc * (1 - losses / 100))
    ac = pvlib.inverter.pvwatts(dc, pdc0=config.ac_capacity_w/config.inverter_efficiency,
        eta_inv_nom=config.inverter_efficiency)
    results = []

    for i, hour in enumerate(weather):
        solar_clean_ac_mw = float(ac[i]) / 1e6
        row = dict(hour, solar_model_timestamp=midpoint[i].strftime("%Y-%m-%dT%H:%M:%SZ"),
            solar_zenith_deg=float(zenith[i]), dni_estimated_w_m2=float(dni[i]),
            dhi_estimated_w_m2=float(dhi[i]), poa_global_w_m2=float(poa_global[i]),
            effective_irradiance_w_m2=float(effective[i]), cell_temperature_c=float(cell[i]),
            dc_after_losses_w=float(dc[i]), solar_clean_ac_mw=solar_clean_ac_mw,
            midpoint_dark_mask=bool(dark[i]),
            masked_ghi_wh_m2=float(hour["ghi_wh_m2"]) if dark[i] else 0.0)

        if not all(math.isfinite(value) for value in row.values() if isinstance(value, (float, int))):
            raise ValueError("Nonfinite PV result")
        if not 0 <= solar_clean_ac_mw <= config.ac_capacity_w / 1e6:
            raise ValueError("PV AC power outside inverter bounds")
        results.append(row)

    return results
