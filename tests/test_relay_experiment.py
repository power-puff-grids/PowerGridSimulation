import csv
from copy import deepcopy
import json
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
import pytest
from mqtt_telemetry.handlers import validate_envelope
from powergrid_sim.publish_telemetry import load_messages


@pytest.fixture
def local_broker(tmp_path):
    broker_path = shutil.which('mosquitto')
    fallback = Path('/opt/homebrew/opt/mosquitto/sbin/mosquitto')
    if not broker_path and fallback.exists():
        broker_path = str(fallback)
    if not broker_path:
        pytest.skip('Mosquitto required for relay integration test')
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    config = tmp_path / 'broker.conf'
    config.write_text(f'listener {port} 127.0.0.1\nallow_anonymous true\npersistence false\n')
    broker = subprocess.Popen([broker_path, '-c', str(config)], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    try:
        deadline = time.monotonic() + 5
        while True:
            if broker.poll() is not None:
                stderr = broker.stderr
                assert stderr is not None
                pytest.fail(stderr.read().decode())
            try:
                with socket.create_connection(('127.0.0.1', port), timeout=0.1):
                    break
            except OSError:
                if time.monotonic() >= deadline:
                    raise TimeoutError('Broker startup timed out')
                time.sleep(0.02)
        yield port
    finally:
        broker.terminate()
        try:
            broker.wait(timeout=5)
        except subprocess.TimeoutExpired:
            broker.kill()
            broker.wait()


def json_lines(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


@pytest.mark.parametrize('device,measurement,offset', [
    (None, 'active_power_kw', 30),
    ('solar_pv', 'active_power_kw', 30),
    ('battery', 'soc_percent', -10),
])
def test_relay_records_and_payloads(local_broker, tmp_path, device, measurement, offset):
    output_root = tmp_path / 'experiments'
    command = [sys.executable, '-m', 'integration.run_relay', '--host', '127.0.0.1',
               '--port', str(local_broker), '--output-root', str(output_root), '--timeout', '10']
    if device:
        command += ['--attack-device', device, '--measurement', measurement, '--offset', str(offset)]
    result = subprocess.run(command, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    folders = list(output_root.iterdir())
    assert len(folders) == 1
    folder = folders[0]
    summary = json.loads((folder / 'summary.json').read_text())
    assert summary['status'] == 'completed'
    assert summary['original_messages'] == summary['broker_acknowledged'] == summary['forwarded_messages'] == 30
    originals = {m['message_id']: m for m in load_messages(folder / 'mqtt_telemetry.csv')}
    before = deepcopy(originals)
    raw = json_lines(folder / 'relay_input.jsonl')
    received = json_lines(folder / 'received_messages.jsonl')
    forwarded = json_lines(folder / 'forwarded_messages.jsonl')
    attacks = json_lines(folder / 'attack_records.jsonl')
    links = json_lines(folder / 'attack_deliveries.jsonl')
    assert len(raw) == len(received) == len(forwarded) == 30
    assert len({r['meta']['delivery_id'] for r in received}) == 30
    assert {r['message']['message_id'] for r in received} == set(originals)
    for item in raw:
        assert item['message'] == originals[item['message']['message_id']]
    for item in received:
        message = item['message']
        expected = deepcopy(originals[message['message_id']])
        if device and expected['device'] == device:
            expected['measurements'][measurement] += offset
        assert message == expected
        assert validate_envelope(message) == []
        assert item['meta']['received_at'].endswith('Z')
        assert not {'attack_label','attack_type','attack_target'} & set(message)
    assert originals == before
    assert len(attacks) == len(links) == (3 if device else 0)
    assert summary['attacked_messages'] == len(attacks)
    raw_delivery_ids = {r['meta']['delivery_id'] for r in raw}
    delivery_by_id = {r['meta']['delivery_id']: r for r in received}
    for attack in attacks:
        assert attack['relay_delivery_id'] in raw_delivery_ids
        original = originals[attack['original_message_id']]
        assert original['device'] == device
        details = attack['false_data_injection']
        assert details['measurement'] == measurement
        assert details['offset'] == offset
        assert details['original_value'] == original['measurements'][measurement]
        assert details['manipulated_value'] == details['original_value'] + offset
        assert attack['replay'] is None
        assert 'original_value' not in attack and 'manipulated_value' not in attack
        assert attack['attack_target'] == f'measurements.{measurement}'
    for link in links:
        assert delivery_by_id[link['delivery_id']]['message']['message_id'] == link['original_message_id']
    assert (folder / 'relay_quarantine.jsonl').read_text() == ''
    assert (folder / 'receiver_quarantine.jsonl').read_text() == ''
    with (folder / 'physical_results.csv').open(newline='') as source:
        physical = list(csv.DictReader(source))
    assert {r['scenario'] for r in physical} == {'normal','high_irrigation_demand','dust_reduced_solar'}


@pytest.mark.parametrize('field,value', [('timestamp','not-a-dateZ'),('device',[]),('run_id','   ')])
def test_validator_returns_errors_for_malformed_values(field, value):
    path = Path(__file__).parents[1] / 'data/sample/telemetry_example.json'
    message = json.loads(path.read_text())
    message[field] = value
    assert validate_envelope(message)
