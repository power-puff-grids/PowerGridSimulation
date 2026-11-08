import json
from types import SimpleNamespace

import pytest

from mqtt_telemetry.communication import Comms


class FakeClient:
    def message_callback_add(self, topic, callback):
        self.callback = callback

    def subscribe(self, topic, qos=0):
        return (0, 1)


@pytest.mark.parametrize("include_topic", [False, True])
def test_subscription_topic_metadata(include_topic):
    comms = Comms.__new__(Comms)
    comms.client = FakeClient()
    deliveries = []

    def record(message, meta):
        deliveries.append((message, meta))

    options = {"include_topic": True} if include_topic else {}
    comms.subscribe("grid/processed/+/+", record, qos=1, **options)

    payload = {"message_id": "earlier-message"}
    packet = SimpleNamespace(
        payload=json.dumps(payload).encode("utf-8"),
        topic="grid/processed/solar_pv/attempt-1",
    )

    comms.client.callback(None, None, packet)
    comms.client.callback(None, None, packet)

    assert len(deliveries) == 2
    assert deliveries[0][1]["delivery_id"] != deliveries[1][1]["delivery_id"]

    for message, meta in deliveries:
        assert message == payload
        assert meta["received_at"].endswith("Z")
        if include_topic:
            assert meta["topic"] == packet.topic
        else:
            assert "topic" not in meta
