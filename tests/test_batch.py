"""Batch control/artifact checks; the fixture is synthetic and uses no broker."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from integration.run_batch import batch_cases, run_batch, verify_experiment
from powergrid_sim.telemetry import write_telemetry_csv


def write_lines(path, rows):
    path.write_text(''.join(json.dumps(row) + '\n' for row in rows))


def make_artifacts(root, *, attack_device=None, measurement='active_power_kw', offset=0, **kwargs):
    # Use explicit fixture envelopes, not claimed power-flow observations.
    base = json.loads((Path(__file__).parents[1] / 'data/sample/normal_snapshot_telemetry.json').read_text())
    folder = root / 'fixture-experiment'
    folder.mkdir(parents=True)
    originals = []
    for scenario in ('normal','high_irrigation_demand','dust_reduced_solar'):
        for i, sample in enumerate(base):
            message = deepcopy(sample)
            message.update(scenario=scenario, message_id=f'{scenario}-{i}', snapshot_id=f'snapshot-{scenario}')
            originals.append(message)
    write_telemetry_csv(originals, folder / 'mqtt_telemetry.csv')
    raw, forwarded, received, records, links = [], [], [], [], []
    for i, message in enumerate(originals):
        raw_id, delivery_id = f'raw-{i}', f'delivery-{i}'
        raw.append({'meta': {'delivery_id': raw_id}, 'message': deepcopy(message)})
        altered = deepcopy(message)
        if message['device'] == attack_device:
            altered['measurements'][measurement] += offset
            record = {'attack_id': f'attack-{i}', 'original_message_id': message['message_id'],
                      'relay_delivery_id': raw_id, 'attack_type': 'false_data_injection',
                      'attack_target': f'measurements.{measurement}',
                      'original_value': message['measurements'][measurement],
                      'manipulated_value': altered['measurements'][measurement]}
            records.append(record)
            links.append({**record, 'delivery_id': delivery_id})
        forwarded.append({'relay_delivery_id': raw_id, 'topic': f"grid/processed/{message['device']}", 'message': altered})
        received.append({'meta': {'delivery_id': delivery_id}, 'message': altered})
    for name, rows in [('relay_input',raw),('forwarded_messages',forwarded),('received_messages',received),
                       ('attack_records',records),('attack_deliveries',links),('relay_quarantine',[]),('receiver_quarantine',[])]:
        write_lines(folder / f'{name}.jsonl', rows)
    summary = {'status':'completed', 'attack_device':attack_device, 'measurement':measurement if attack_device else None,
               'offset':offset if attack_device else None, 'original_messages':30,'broker_acknowledged':30,
               'forwarded_messages':30,'received_deliveries':30,'attacked_messages':len(records)}
    (folder / 'summary.json').write_text(json.dumps(summary))
    return folder


def test_plan_and_success_manifest(tmp_path):
    cases = batch_cases()
    assert len(cases) == len({c.case_id for c in cases}) == 9
    assert {c.offset for c in cases if c.attack_device == 'solar_pv'} == {-30,-15,-5,5,15,30}
    assert {c.offset for c in cases if c.attack_device == 'battery'} == {-10,10}
    folder = run_batch(tmp_path, experiment_runner=make_artifacts)
    manifest = json.loads((folder / 'manifest.json').read_text())
    assert manifest['status'] == 'completed'
    assert all(e['status'] == 'completed' for e in manifest['experiments'])
    assert manifest['totals_verified'] == {'original_messages':270,'received_deliveries':270,
        'measurement_rows':405,'attacked_messages':24,'modified_scalar_values':24,'attack_labeled_rows':54}
    assert (folder / 'manifest.csv').exists()
    assert all((folder / e['experiment_dir']).exists() for e in manifest['experiments'])


@pytest.mark.parametrize('continue_on_error,expected_calls',[(False,1),(True,9)])
def test_failure_manifest_and_exit_policy(tmp_path, continue_on_error, expected_calls):
    calls = []
    def failure(root, **kwargs):
        calls.append(root)
        raise RuntimeError('broker unavailable')
    folder = run_batch(tmp_path, continue_on_error=continue_on_error, experiment_runner=failure)
    data = json.loads((folder / 'manifest.json').read_text())
    assert data['status'] == 'failed' and len(calls) == expected_calls
    assert data['experiments'][0]['error'] == 'broker unavailable'
    assert all(value == 0 for value in data['totals_verified'].values())
    if not continue_on_error:
        assert all(e['status'] == 'not_run' for e in data['experiments'][1:])


def test_interruption_preserves_readable_manifest(tmp_path):
    def interrupted(root, **kwargs): raise KeyboardInterrupt
    with pytest.raises(KeyboardInterrupt):
        run_batch(tmp_path, experiment_runner=interrupted)
    folder = next(tmp_path.iterdir())
    data = json.loads((folder / 'manifest.json').read_text())
    assert data['status'] == data['experiments'][0]['status'] == 'interrupted'
    assert all(e['status'] == 'not_run' for e in data['experiments'][1:])


@pytest.mark.parametrize('corruption',['source','received','link','missing_delivery','summary'])
def test_rejects_corrupted_artifacts(tmp_path, corruption):
    case = next(c for c in batch_cases() if c.case_id == 'solar_plus_5kw')
    folder = make_artifacts(tmp_path, attack_device=case.attack_device, measurement=case.measurement, offset=case.offset)
    assert verify_experiment(folder, case)['attacked_messages'] == 3
    if corruption == 'source':
        path = folder / 'relay_input.jsonl'
        rows = [json.loads(line) for line in path.read_text().splitlines()]
        rows[0]['message']['measurements']['voltage_kv'] += 1
        write_lines(path, rows)
    elif corruption in ('received','missing_delivery'):
        path = folder / 'received_messages.jsonl'
        rows = [json.loads(line) for line in path.read_text().splitlines()]
        if corruption == 'received': rows[0]['message']['timestamp'] = 'unexpected'
        else: rows.pop()
        write_lines(path, rows)
    elif corruption == 'link':
        path = folder / 'attack_deliveries.jsonl'
        rows = [json.loads(line) for line in path.read_text().splitlines()]
        rows[0]['delivery_id'] = 'unresolved'
        write_lines(path, rows)
    else:
        path = folder / 'summary.json'
        data = json.loads(path.read_text());data['received_deliveries'] = 999
        path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match='Artifact verification failed'):
        verify_experiment(folder, case)


def test_preserves_failed_experiment_location(tmp_path):
    def fails_after_output(root, **kwargs):
        path = root / 'failed-experiment';path.mkdir(parents=True)
        (path / 'summary.json').write_text('{"status":"failed"}')
        raise RuntimeError('forwarding timeout')
    folder = run_batch(tmp_path, experiment_runner=fails_after_output)
    data = json.loads((folder / 'manifest.json').read_text())
    assert (folder / data['experiments'][0]['experiment_dir'] / 'summary.json').exists()


def test_invalid_timeout_has_no_outputs(tmp_path):
    with pytest.raises(ValueError): run_batch(tmp_path, timeout=float('nan'))
    assert not list(tmp_path.iterdir())
