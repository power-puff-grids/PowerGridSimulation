import time, random
import pandapower as pp
from build_grid import build_grid
from publish import TelemPublisher

net = build_grid()
pub = TelemPublisher()

pp.runpp(net, numba=False)
# demonstration with one solar panel and an irrigation pump
# two subscribers
for step in range(25):
    net.sgen.at[0, "p_mw"] = random.uniform(0.0, 0.15) #changing
    net.load.at[0, "q_mvar"] = random.uniform(0.0, 0.08)
    pp.runpp(net, numba=False)

    measurement1 = {"bus": int(net.sgen.at[0, "bus"]),
                    "solar_power_mw": float(net.res_sgen.at[0, "p_mw"]),
                    "solar_reactive_power_mvar": float(net.res_sgen.at[0, "q_mvar"])}
    pub.send(net.sgen.at[0, "name"], measurement1, step)
    measurement2 = {"bus": int(net.load.at[0, "bus"]),
                    "irrigation_pump_mw": float(net.res_load.at[0, "p_mw"]),
                    "irrigation_pump_reactive_mvar": float(net.res_load.at[0, "q_mvar"])}
    pub.send(net.load.at[0, "name"], measurement1, step)
    time.sleep(1)
