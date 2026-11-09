# Alina's mini demo: expected-vs-received telemetry detection

## What this demonstrates

This is a small, reproducible proof of the assigned detection task. It creates 32 synthetic 5-second telemetry records, packages each as an MQTT-shaped JSON payload, combines physical inputs and network metadata in one labeled CSV, checks the received bus voltage against a physical expectation, writes clear alerts, and plots expected against received voltage.

The values are demonstration data. This version does **not** connect to a live MQTT broker and does **not** read the team's actual simulator export. It mirrors the message payload/subscribe-processing step offline so the detector can be demonstrated without broker setup. Replace the sample generator with the group's simulator export and actual MQTT subscriber output when those are available.

## Run it

Requirements: Python 3.10+, pandas, numpy, matplotlib.

```bash
python -m pip install -r requirements.txt
python detector_demo.py
```

The script writes:

- `combined_labeled_dataset.csv` — physical values, MQTT-like metadata, labels, detector result, and alert text in one table.
- `expected_vs_received.png` — plot with the false-data injection samples marked in red.

It also prints the attack test result and stops with an assertion failure if any of the four injected attack records are missed or if this sample creates a false alarm.

## Whiteboard version

```text
Simulator inputs (pump load, solar output, reactive load)
    -> physical model calculates expected bus voltage
    -> sensor/MQTT-shaped JSON message provides received voltage
    -> combine both streams + timestamp/device/network fields
    -> residual = abs(received voltage - expected voltage)
    -> residual > tolerance?
         YES -> label detector result suspicious; print alert
         NO  -> record OK
    -> save labeled CSV + expected/received plot
```

The threshold is `0.012 pu` for this sample. It is a demo setting, not a validated grid-protection limit. The four injected samples add `0.075 pu`, so the detector finds all four. Environmental-stress and equipment-fault rows use different physical operating inputs and update the expected voltage; they are labeled accordingly but do not trigger a cyber alert when received telemetry stays consistent with those inputs.

## Expected-value comparison

For the demo, expected voltage uses a simplified linearized radial-feeder approximation:

```text
Zbase = Vbase^2 / Sbase
Rpu = Rline / Zbase
Xpu = Xline / Zbase
Pnet = pump load - solar generation
Vexpected_pu ~= 1 - (Rpu * Pnet_pu + Xpu * Qnet_pu)
residual = abs(Vreceived_pu - Vexpected_pu)
```

This is deliberately small enough to explain by hand. It is **not** a full AC power flow and it is not a validated model of the team's final network. For the real project, calculate expected bus voltages from the exact grid model and each operating scenario, ideally with the team's pandapower network and `runpp`, then compare the MQTT-received value to the model output using a tolerance calibrated on normal runs.

## Labels and CSV columns

`scenario_label` is scenario-engine ground truth: `normal`, `environmental_stress`, `equipment_fault`, or `false_data_injection`. `is_attack` is the binary ground-truth flag. `detected_attack` is the detector's independent result. Keep both: the detector must not use the ground-truth label to decide whether a row is suspicious.

The CSV also stores timestamp, MQTT topic, device ID, pump/solar/reactive inputs, expected and received voltage, residual, packet rate, message size, latency, dropped-packet flag, raw JSON payload, and alert text. This follows the proposal's goal of retaining physical measurements, network features, scenario labels, affected device, and attack intensity/type as a single benchmark row.

## Test result from this run

- Rows: 32
- False-data injection ground-truth rows: 4
- Injected attack rows detected: 4/4
- False alarms on the 28 non-attack rows: 0
- First alert: `ALERT: sensor.bus_2.voltage received 1.0698 pu; expected 0.9963 pu; difference 0.0736 pu (limit 0.012 pu). Possible false-data injection.`

This proves only that the intentionally large, single-sensor offset in this synthetic test is detected. It does not prove detection of subtle or coordinated/stealthy false-data attacks, replay attacks, real communication loss, or real-grid behavior. A residual threshold can miss attacks that keep the measurement physically consistent; the project should test those cases separately.

## Slide-ready explanation

> At each time step, the demo calculates the voltage the simulated feeder should produce from pump demand, solar generation, and reactive load. It then compares that expected value with the voltage carried in the telemetry message. If the absolute difference is greater than the tolerance, the detector raises an alert and records the result. In the test, four false-data injections were added; all four triggered alerts, while the normal, environmental-stress, and equipment-fault examples did not.

A good sentence to say during the demo: **“The label tells us what scenario we injected; the residual check is a separate detector decision. We compare them afterward to see whether the detector worked.”**

## Where to point in the code

- `expected_bus_voltage_pu()` — computes the model's expected voltage from system inputs.
- `scenario_for_step()` — defines normal, environmental, fault, and false-data injection periods.
- `make_rows()` — creates the message payload, reconstructs an MQTT-like message, computes the residual, applies the threshold, assigns labels, and writes the alert field.
- `main()` — exports the combined CSV, creates the comparison plot, reports test counts, and asserts that the attack test passes.

See `REFERENCES.md` for the exact documentation/paper source map and wording you can place on the slides.

## How the demo maps to the technology slide

The current script directly uses Python, NumPy, pandas, and Matplotlib. It demonstrates the processing and visualization part of the proposed stack. It does not yet use pandapower, OpenDSSDirect.py, NetworkX, Paho/Mosquitto, or scikit-learn; the `ALINA_DEMO_TALK_TRACK.md` explains how those fit into the full flow and gives wording that does not overstate implementation status. The expected-value function is a temporary baseline to be replaced by bus results from the team's power-flow simulator.

## Shared telemetry message contract

`telemetry_schema.py` now builds the agreed nested message envelope:

```json
{
  "timestamp": "2026-10-19T17:00:00Z",
  "run_id": "demo_run_001",
  "sequence": 0,
  "device_id": "meter.bus_2",
  "bus_id": "bus_2",
  "measurements": {
    "pump_load_mw": 0.16,
    "solar_generation_mw": 0.04,
    "active_power_mw": 0.12,
    "reactive_power_mvar": 0.05,
    "voltage_pu": 0.995
  }
}
```

The actual demo serializes and parses this shape locally. It does not connect to Mosquitto. `scenario_label`, `attack_type`, target, and intensity are written separately to `ground_truth_labels.csv`; the combined labeled dataset joins those trusted labels after making the detector decision. The detector reads `measurements.voltage_pu`, expected voltage, and the threshold. It does not read the scenario or attack label.

The sequence and UTC timestamp make the envelope useful to the replay-attack work, but this Alina demo does not implement a replay detector. The attack branch can import the same `build_telemetry_message()` function instead of copying the schema or `build_grid()` implementation.

A simulator or MQTT branch can reuse the serializer rather than rebuilding the envelope:

```python
from telemetry_schema import build_telemetry_message

payload = build_telemetry_message(
    timestamp=timestamp_utc,
    run_id=run_id,
    sequence=step,
    device_id="solar_pv_1",
    bus_id="bus_2",
    measurements={
        "active_power_mw": float(active_power_mw),
        "reactive_power_mvar": float(reactive_power_mvar),
        "voltage_pu": float(voltage_pu),
    },
)
# Adapt this call to the team's TelemetryPublisher method signature.
publisher.send(payload)
```
