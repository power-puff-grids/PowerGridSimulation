# References and code attribution notes

Use these as citations for the implementation pattern and next integration step. The detector and scenario values in `detector_demo.py` are original demo code written for this project; they were not copied from a Stack Overflow answer. Attribute libraries and established methods to their documentation/papers.

## Code-to-source map

| Code area | What to cite | How to describe the relationship |
|---|---|---|
| `expected_bus_voltage_pu()` | Baran and Wu introduced the DistFlow equations for radial distribution systems; their paper is the theoretical lineage for simplified feeder voltage calculations. | “The mini demo uses a simplified linearized feeder voltage-drop estimate inspired by radial distribution power-flow modeling. This approximation is only for the demo; the project model should use pandapower power-flow results.” |
| Future real network model | pandapower documentation: network creation/elements and `runpp` power flow. The current demo does not call pandapower because the installed environment could not retrieve that package, so do not claim that this Python file currently runs pandapower. | “For the full simulation, the expected voltage will come from our pandapower network solution (`runpp`) rather than the mini-demo approximation.” |
| `make_rows()` message shape | Eclipse Paho MQTT Python documentation for `Client`, `subscribe()`, `on_message`, and `message.payload`. Current sample reconstructs a JSON payload offline; it does not use Paho or a live broker yet. | “The sample mirrors the MQTT message handling shape; the live adapter will subscribe to the project's telemetry topic and pass received payloads into the same detector.” |
| `main()` CSV export | pandas `DataFrame.to_csv` documentation. | “pandas writes the combined labeled DataFrame to CSV.” |
| Detector idea / labels | The project proposal's Chapter 2 and Chapter 3; for general background, cite the team's existing reference on false-data injection (Liang et al., 2017) and physics-informed anomaly detection (Zideh et al., 2024). | “The residual check is our baseline implementation of comparing telemetry to expected physical behavior; it is not a machine-learning model.” |

## Slide-ready references (IEEE-like style)

[1] M. E. Baran and F. F. Wu, “Optimal sizing of capacitors placed on a radial distribution system,” *IEEE Transactions on Power Delivery*, vol. 4, no. 1, pp. 735–743, 1989, doi: 10.1109/61.19266. (Radial distribution modeling / DistFlow background.)

[2] pandapower, “Run a Power Flow,” *pandapower Documentation*, https://pandapower.readthedocs.io/en/stable/powerflow/run.html (accessed Oct. 19, 2026). (Full-project simulation implementation reference; not called by this mini-demo.)

[3] Eclipse Foundation, “Eclipse Paho™ MQTT Python Client,” https://eclipse.dev/paho/clients/python/docs/ (accessed Oct. 19, 2026). (MQTT client, subscribe, callback, and payload integration reference; live broker is not used by this mini-demo.)

[4] pandas, “pandas.DataFrame.to_csv,” *pandas Documentation*, https://pandas.pydata.org/docs/reference/api/pandas.DataFrame.to_csv.html (accessed Oct. 19, 2026). (CSV export.)

[5] G. Liang, J. Zhao, F. Luo, S. R. Weller, and Z. Y. Dong, “A review of false data injection attacks against modern power systems,” *IEEE Transactions on Smart Grid*, vol. 8, no. 4, pp. 1630–1638, 2017, doi: 10.1109/TSG.2015.2495133. (Attack background; already listed as reference [13] in the project proposal.)

[6] M. J. Zideh, P. Chatterjee, and A. K. Srivastava, “Physics-informed machine learning for data anomaly detection, classification, localization, and mitigation: A review, challenges, and path forward,” *IEEE Access*, vol. 12, pp. 4597–4617, 2024, doi: 10.1109/ACCESS.2023.3347989. (Physics-informed detection background; already listed as reference [14] in the project proposal.)

## Attribution guardrail

Use “based on the documented API” for library usage, “inspired by” for the physical approximation, and “our implementation” for the threshold logic, synthetic test cases, labels, CSV schema, and alert wording. Avoid saying the entire detector was copied from pandapower, Paho, Stack Overflow, or an AI system.

## Additional references for the technologies slide

[7] pandapower, “Run a Power Flow,” *pandapower Documentation*. https://pandapower.readthedocs.io/en/stable/powerflow/run.html. (Use `runpp` and bus result tables for physical expected values in the full model.)

[8] DSS-Extensions, “OpenDSSDirect.py Documentation.” https://dss-extensions.org/OpenDSSDirect.py/. (Python interface for detailed distribution feeder simulation.)

[9] NetworkX Developers, “Graph—Undirected graphs with self loops,” *NetworkX Documentation*. https://networkx.org/documentation/stable/reference/classes/graph.html. (Representing buses/components as nodes and connections as edges.)

[10] Eclipse Foundation, “Client module,” *Eclipse Paho MQTT Python Documentation*. https://eclipse.dev/paho/files/paho.mqtt.python/html/client.html. (MQTT client, topic subscription, and message callbacks.)

[11] Eclipse Mosquitto, “Eclipse Mosquitto.” https://mosquitto.org/. (MQTT broker named in the project technology plan.)

[12] scikit-learn Developers, “IsolationForest,” *scikit-learn Documentation*. https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.IsolationForest.html. (Unsupervised outlier detection.)

[13] scikit-learn Developers, “Ensemble methods,” *scikit-learn Documentation*. https://scikit-learn.org/stable/api/sklearn.ensemble.html. (Includes RandomForestClassifier for labeled event classification.)

[14] pandas, “pandas.DataFrame.to_csv,” *pandas Documentation*. https://pandas.pydata.org/docs/reference/api/pandas.DataFrame.to_csv.html. (Writing the combined dataset to CSV.)

[15] Matplotlib Developers, “matplotlib.pyplot.plot,” *Matplotlib Documentation*. https://matplotlib.org/stable/api/_as_gen/matplotlib.pyplot.plot.html. (Plotting expected and received telemetry.)

[16] Python Software Foundation, “What’s New in Python 3.12,” *Python Documentation*. https://docs.python.org/3/whatsnew/3.12.html. (Language/runtime reference.)

Accessed Oct. 19, 2026. For slides, cite these docs for the tools and APIs; describe `detector_demo.py` as the group's baseline implementation. Do not imply that every listed technology is already called by that file.

## Shared telemetry schema note

`telemetry_schema.py` implements the group's agreed JSON envelope locally: UTC timestamp, run ID, sequence, device ID, bus ID, and nested numeric measurements. This serializer and its validation checks are our original project code. Paho documentation is a reference for the future live publisher/subscriber API, not the source of our message schema. Ground-truth scenario/attack labels remain in a separate file and join the detector records only after prediction.
