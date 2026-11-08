"""Local Mosquitto test; skipped when its executable is unavailable."""
import json
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import threading
import time

import paho.mqtt.client as mqtt
import pytest

from powergrid_sim.publish_telemetry import load_messages


def test_publisher_roundtrip_with_mosquitto(tmp_path):
    broker_path = shutil.which('mosquitto')
    if not broker_path:
        candidate = Path('/opt/homebrew/opt/mosquitto/sbin/mosquitto')
        broker_path = str(candidate) if candidate.exists() else None
    if not broker_path:
        pytest.skip('Mosquitto executable required for live broker test')
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    config = tmp_path / 'mosquitto.conf'
    config.write_text(f'listener {port} 127.0.0.1\nallow_anonymous true\npersistence false\n')
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    subscribed = threading.Event()
    complete = threading.Event()
    received = []
    path = tmp_path / 'messages.csv'
    physical = tmp_path / 'physical.csv'
    generation = subprocess.run([sys.executable, '-m', 'powergrid_sim.run_scenarios',
                                 '--output', str(physical), '--telemetry-output', str(path)],
                                capture_output=True, text=True, timeout=30)
    assert generation.returncode == 0, generation.stderr
    messages = load_messages(path)
    assert len(messages) == 30
    def on_connect(client, userdata, flags, reason, properties):
        if reason == 0:
            client.subscribe('grid/telemetry/#', qos=1)
    def on_subscribe(client, userdata, mid, reasons, properties):
        if all(reason.value < 128 for reason in reasons):
            subscribed.set()
    def on_message(client, userdata, message):
        received.append((message.topic, json.loads(message.payload)))
        if len(received) >= len(messages):
            complete.set()
    broker = subprocess.Popen([broker_path, '-c', str(config)], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    client.on_connect = on_connect
    client.on_subscribe = on_subscribe
    client.on_message = on_message
    try:
        deadline = time.monotonic() + 5
        while True:
            if broker.poll() is not None:
                pytest.fail(broker.stderr.read().decode())
            try:
                with socket.create_connection(('127.0.0.1', port), timeout=0.2):
                    break
            except OSError:
                if time.monotonic() > deadline:
                    raise TimeoutError('Mosquitto did not start')
                time.sleep(0.02)
        client.connect('127.0.0.1', port)
        client.loop_start()
        assert subscribed.wait(5), 'Subscriber was not ready'
        result = subprocess.run([sys.executable, '-m', 'powergrid_sim.publish_telemetry',
                                 '--input', str(path), '--host', '127.0.0.1', '--port', str(port)],
                                capture_output=True, text=True, timeout=20)
        assert result.returncode == 0, result.stderr
        assert '30/30' in result.stdout
        assert complete.wait(5), f'Only received {len(received)} messages'
        expected = {m['message_id']: m for m in messages}
        assert {m['message_id'] for _, m in received} == set(expected)
        for topic, message in received:
            assert topic == f"grid/telemetry/{message['device']}"
            assert message == expected[message['message_id']]
    finally:
        client.disconnect()
        client.loop_stop()
        broker.terminate()
        try:
            broker.wait(timeout=5)
        except subprocess.TimeoutExpired:
            broker.kill()
            broker.wait()
