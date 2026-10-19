import time, random
import pandapower as pp
from build_grid import build_grid
from publish import TelemPublisher

net = build_grid()
pub = TelemPublisher()

pp.runpp(net)
# demonstration with one solar panel
# must cast numpy
for step in range(25):
    net.sgen.at[0, "p_mw"] = random.uniform(0.0, 0.15)
    pp.runpp(net, numba=False)
    measurements = {"bus": int(net.sgen.at[0, "bus"]),
                    "solar_power_mw": float(net.res_sgen.at[0, "p_mw"]),
                    "solar_reactive_power_mvar": float(net.res_sgen.at[0, "q_mvar"])}
    pub.send(net.sgen.at[0, "name"], measurements, step)
    time.sleep(1)
