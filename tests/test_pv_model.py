from dataclasses import replace
import math
import pytest
from powergrid_sim.pv_model import PVConfig, pv_profile
# tests for unexpected PV behavior. Ensures night time has 0 output, higher temperatures have reduced output, orientation
# of the panels have affect, reject invalid inputs.
def hour(timestamp="2025-07-04T19:00:00Z", ghi=1000., temperature=30.):
    return dict(timestamp=timestamp, ghi_wh_m2=ghi, ghi_mean_w_m2=ghi, temperature_2m_c=temperature)

def test_night_has_zero_output_and_ambient_cell_temperature():
    row = pv_profile([hour("2025-07-04T08:00:00Z",0)])[0]
    assert row["solar_clean_ac_mw"] == 0
    assert row["cell_temperature_c"] == 30
    assert row["solar_model_timestamp"] == "2025-07-04T08:30:00Z"

def test_sunlight_and_temperature_have_physical_effects():
    normal = pv_profile([hour()])[0]
    hot = pv_profile([hour(temperature=45)])[0]
    assert normal["cell_temperature_c"] > 30
    assert 0 < hot["solar_clean_ac_mw"] < normal["solar_clean_ac_mw"] < 0.15
    # Faiman equation evaluated independently from saved intermediate values.
    assert normal["cell_temperature_c"] == pytest.approx(30+normal["poa_global_w_m2"]/(25+6.84))
    # PVWatts DC equation and multiplicative system loss assumptions.
    retention = math.prod(1-loss/100 for loss in [0,3,0,2,2,.5,1.5,1,0,3])
    expected = normal["effective_irradiance_w_m2"]/1000*150000*(1-.004*(normal["cell_temperature_c"]-25))*retention
    assert normal["dc_after_losses_w"] == pytest.approx(expected)

def test_inverter_clipping_and_orientation():
    large = pv_profile([hour()],replace(PVConfig(),dc_capacity_w=600000))[0]
    assert large["solar_clean_ac_mw"] == pytest.approx(.15)
    south = pv_profile([hour()])[0]
    north = pv_profile([hour()],replace(PVConfig(),azimuth_deg=0))[0]
    assert south["solar_clean_ac_mw"] > north["solar_clean_ac_mw"]

@pytest.mark.parametrize("change", [dict(dc_capacity_w=0),dict(inverter_efficiency=0),dict(tilt_deg=100),dict(module_wind_m_s=-1),dict(gamma_pdc=float("nan"))])
def test_bad_configuration_rejected(change):
    with pytest.raises(ValueError):
        pv_profile([hour()],replace(PVConfig(),**change))

def test_bad_weather_and_duplicates_rejected():
    for weather in [[],[hour(ghi=-1)],[hour(temperature=float("nan"))],[hour(),hour()]]:
        with pytest.raises(ValueError):
            pv_profile(weather)

def test_masked_radiation_is_recorded_not_hidden():
    row = pv_profile([hour("2025-07-04T08:00:00Z",10)])[0]
    assert row["midpoint_dark_mask"]
    assert row["masked_ghi_wh_m2"] == 10
    assert row["solar_clean_ac_mw"] == 0
