from copy import deepcopy
import csv
import json
from pathlib import Path
from typing import Callable
import pytest
from powergrid_sim.publish_telemetry import load_messages, publish_messages
from powergrid_sim.telemetry import ENVELOPE_FIELDS, write_telemetry_csv

@pytest.fixture
def messages():
    return json.loads((Path(__file__).parents[1] / 'data/sample/normal_snapshot_telemetry.json').read_text())

def test_load_preserves_original_payloads(messages, tmp_path):
    path = tmp_path / 'messages.csv'
    write_telemetry_csv(messages, path)
    assert load_messages(path) == messages

@pytest.mark.parametrize('corruption', ['nan', 'boolean', 'unknown_device', 'extra_measurement', 'bad_time', 'duplicate_id'])
def test_rejects_corrupt_batch(messages, tmp_path, corruption):
    if corruption == 'nan':
        messages[-1]['measurements']['soc_percent'] = 'NaN'
    elif corruption == 'boolean':
        messages[-1]['measurements']['soc_percent'] = True
    elif corruption == 'unknown_device':
        messages[-1]['device'] = 'unknown'
    elif corruption == 'extra_measurement':
        messages[-1]['measurements']['extra'] = 1.0
    elif corruption == 'bad_time':
        messages[-1]['timestamp'] = 'not-a-timeZ'
    else:
        messages[-1]['message_id'] = messages[0]['message_id']
    path = tmp_path / 'messages.csv'
    write_telemetry_csv(messages, path)
    with pytest.raises(ValueError, match='row'):
        load_messages(path)

class FakeClient:
    def __init__(self):
        self.connected = True

    def is_connected(self) -> bool:
        return self.connected

class FakeReceipt:
    def __init__(self, rc: int, wait: Callable[[float], None], acknowledged: bool):
        self.rc = rc
        self.wait = wait
        self.acknowledged = acknowledged

    def wait_for_publish(self, timeout: float) -> None:
        self.wait(timeout)

    def is_published(self) -> bool:
        return self.acknowledged

class FakeComms:
    def __init__(self, *, acknowledged=True, rc=0):
        self.client = FakeClient()
        self.sent = []
        self.closed = False
        self.waited = 0
        self.acknowledged = acknowledged
        self.rc = rc

    def m_send(self, message, qos=0):
        assert qos == 1
        self.sent.append(deepcopy(message))
        def wait(timeout):
            self.waited += 1
        return FakeReceipt(self.rc, wait, self.acknowledged)

    def close(self):
        self.closed = True

def test_waits_for_every_ack_before_closing(messages):
    transport = FakeComms()
    before = deepcopy(messages)
    assert publish_messages(messages, comms_factory=lambda **kw: transport) == 10
    assert transport.sent == messages == before
    assert transport.waited == 10 and transport.closed

@pytest.mark.parametrize('rc,ack', [(0,False),(4,True)])
def test_publish_failure_is_reported_and_closes(messages, rc, ack):
    transport = FakeComms(rc=rc, acknowledged=ack)
    with pytest.raises(RuntimeError, match='0/10'):
        publish_messages(messages, comms_factory=lambda **kw: transport)
    assert transport.closed
    assert len(transport.sent) == 1

def test_connection_timeout_closes(messages):
    transport = FakeComms()
    transport.client.connected = False
    with pytest.raises(RuntimeError, match='connection'):
        publish_messages(messages, timeout=0.001, comms_factory=lambda **kw: transport)
    assert transport.closed and not transport.sent
