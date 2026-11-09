"""Small cyber-physical telemetry detector demo using the shared MQTT schema.

The sample is synthetic. The feeder calculation is a simplified linearized
voltage-drop approximation, not a full pandapower power flow. Messages are
serialized and parsed locally; no MQTT broker is required for this demo.
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from telemetry_schema import build_telemetry_message, validate_telemetry_message

OUT = Path(__file__).resolve().parent
RUN_ID = "demo_run_001"
DEVICE_ID = "meter.bus_2"
BUS_ID = "bus_2"
R_LINE_OHM = 4.0
X_LINE_OHM = 2.0
V_BASE_KV = 12.47
S_BASE_MVA = 1.0
ALARM_TOLERANCE_PU = 0.012
RNG = np.random.default_rng(17)


def expected_bus_voltage_pu(pump_mw: float, solar_mw: float, q_mvar: float) -> float:
    """Approximate receiving-end voltage from net P/Q using linearized DistFlow."""
    z_base_ohm = V_BASE_KV**2 / S_BASE_MVA
    r_pu = R_LINE_OHM / z_base_ohm
    x_pu = X_LINE_OHM / z_base_ohm
    p_net_pu = (pump_mw - solar_mw) / S_BASE_MVA
    q_net_pu = q_mvar / S_BASE_MVA
    return 1.0 - (r_pu * p_net_pu + x_pu * q_net_pu)


def scenario_for_step(step: int) -> tuple[str, float, float, float, float]:
    """Return ground-truth class, P/Q inputs, and injected FDI offset."""
    if step < 8:
        return "normal", 0.16, 0.04, 0.05, 0.0
    if step < 16:
        return "environmental_stress", 0.24, 0.015, 0.07, 0.0
    if step < 24:
        return "equipment_fault", 0.28, 0.04, 0.08, 0.0
    if step < 28:
        return "false_data_injection", 0.16, 0.04, 0.05, 0.075
    return "normal", 0.18, 0.05, 0.05, 0.0


def detect_message(message: dict, expected_voltage_pu: float) -> tuple[float, bool, str]:
    """Detect a physical mismatch using telemetry only, never ground-truth labels."""
    validate_telemetry_message(message)
    received = float(message["measurements"]["voltage_pu"])
    residual = abs(received - expected_voltage_pu)
    detected = residual > ALARM_TOLERANCE_PU
    if detected:
        alert = (
            f"ALERT: {message['device_id']} received {received:.4f} pu; "
            f"expected {expected_voltage_pu:.4f} pu; difference {residual:.4f} pu "
            f"(limit {ALARM_TOLERANCE_PU:.3f} pu). Possible false-data injection."
        )
    else:
        alert = "OK: received voltage is within the expected tolerance."
    return residual, detected, alert


def make_samples() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Create telemetry and independent labels, then merge for final evaluation."""
    detector_rows: list[dict] = []
    ground_truth_rows: list[dict] = []
    start = pd.Timestamp("2026-10-19T09:00:00Z")

    for sequence in range(32):
        label, pump_mw, solar_mw, q_mvar, injected_error_pu = scenario_for_step(sequence)
        expected = expected_bus_voltage_pu(pump_mw, solar_mw, q_mvar)
        noise = float(RNG.normal(0, 0.0015))
        received = expected + noise + injected_error_pu
        timestamp = (start + pd.Timedelta(seconds=sequence * 5)).isoformat().replace("+00:00", "Z")
        measurements = {
            "pump_load_mw": pump_mw,
            "solar_generation_mw": solar_mw,
            "active_power_mw": pump_mw - solar_mw,
            "reactive_power_mvar": q_mvar,
            "voltage_pu": received,
        }
        payload = build_telemetry_message(
            timestamp=timestamp,
            run_id=RUN_ID,
            sequence=sequence,
            device_id=DEVICE_ID,
            bus_id=BUS_ID,
            measurements=measurements,
        )
        # Round-trip through JSON to mimic a subscriber decoding MQTT message.payload.
        message = json.loads(json.dumps(payload))
        validate_telemetry_message(message)
        residual, detected, alert = detect_message(message, expected)

        network = {
            "mqtt_topic": "powergrid/site1/bus2/telemetry",
            "packet_rate_per_s": 1.0,
            "packet_size_bytes": len(json.dumps(payload)),
            "latency_ms": 18.0 + float(RNG.uniform(0, 5)),
            "dropped_packet": False,
        }
        detector_rows.append({
            "timestamp": message["timestamp"],
            "run_id": message["run_id"],
            "sequence": message["sequence"],
            "device_id": message["device_id"],
            "bus_id": message["bus_id"],
            "pump_load_mw": measurements["pump_load_mw"],
            "solar_generation_mw": measurements["solar_generation_mw"],
            "active_power_mw": measurements["active_power_mw"],
            "reactive_power_mvar": measurements["reactive_power_mvar"],
            "expected_voltage_pu": expected,
            "received_voltage_pu": message["measurements"]["voltage_pu"],
            "residual_pu": residual,
            **network,
            "detected_attack": detected,
            "alert_message": alert,
            "mqtt_payload_json": json.dumps(payload, separators=(",", ":")),
        })
        # This trusted scenario-engine output is separate from the MQTT message.
        ground_truth_rows.append({
            "run_id": RUN_ID,
            "sequence": sequence,
            "device_id": DEVICE_ID,
            "scenario_label": label,
            "attack_type": "false_data_injection" if label == "false_data_injection" else "none",
            "attack_target_device": DEVICE_ID if label == "false_data_injection" else "",
            "attack_intensity_pu": injected_error_pu,
            "is_attack": label == "false_data_injection",
        })

    detector_df = pd.DataFrame(detector_rows)
    truth_df = pd.DataFrame(ground_truth_rows)
    # Join labels only after the independent detector decision has been made.
    combined = detector_df.merge(
        truth_df,
        on=["run_id", "sequence", "device_id"],
        how="left",
        validate="one_to_one",
    )
    if combined["scenario_label"].isna().any():
        raise AssertionError("Every telemetry row must have one ground-truth label")
    return combined, truth_df


def main() -> None:
    df, truth = make_samples()
    csv_path = OUT / "combined_labeled_dataset.csv"
    truth_path = OUT / "ground_truth_labels.csv"
    plot_path = OUT / "expected_vs_received.png"
    df.to_csv(csv_path, index=False)
    truth.to_csv(truth_path, index=False)

    fig, ax = plt.subplots(figsize=(11, 5.4))
    x = np.arange(len(df))
    ax.plot(x, df["expected_voltage_pu"], label="Expected voltage (model)", linewidth=2)
    ax.plot(x, df["received_voltage_pu"], label="Received MQTT voltage", marker="o", markersize=3)
    attacks = df["is_attack"]
    ax.scatter(x[attacks], df.loc[attacks, "received_voltage_pu"], color="red", marker="x", s=75,
               label="False-data injection", zorder=5)
    ax.fill_between(x, df["expected_voltage_pu"] - ALARM_TOLERANCE_PU,
                    df["expected_voltage_pu"] + ALARM_TOLERANCE_PU,
                    color="green", alpha=0.10, label="Allowed tolerance")
    ax.set(title="Expected vs. received bus voltage", xlabel="5-second sample", ylabel="Voltage (per unit)")
    ax.grid(True, alpha=0.25)
    ax.legend(loc="best")
    fig.tight_layout()
    fig.savefig(plot_path, dpi=180)
    plt.close(fig)

    attacks_detected = int((df["is_attack"] & df["detected_attack"]).sum())
    false_alarms = int((~df["is_attack"] & df["detected_attack"]).sum())
    print(f"Wrote {csv_path.name} ({len(df)} rows)")
    print(f"Wrote {truth_path.name} ({len(truth)} ground-truth rows)")
    print(f"Wrote {plot_path.name}")
    print(f"False-data injection samples detected: {attacks_detected}/4")
    print(f"False alarms on non-attack samples: {false_alarms}")
    print("First attack alert:")
    print(df.loc[df["is_attack"], "alert_message"].iloc[0])
    assert attacks_detected == 4, "Expected all four injected samples to be detected"
    assert false_alarms == 0, "Unexpected false alarm in the synthetic sample"
    assert "attack_type" not in json.loads(df.loc[0, "mqtt_payload_json"])
    assert "scenario_label" not in json.loads(df.loc[0, "mqtt_payload_json"])


if __name__ == "__main__":
    main()
