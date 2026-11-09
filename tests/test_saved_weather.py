# synthetic saved-run fixtures verify plumbing not weather observations
import csv
import hashlib
import json
from pathlib import Path
from uuid import uuid4
import pytest
from integration.simulation_input import archive_weather_input
from integration.run_relay import run_experiment
from integration.run_batch import BatchCase, verify_experiment
from powergrid_sim.scenarios import get_scenarios
from powergrid_sim.run_scenarios import run_scenario
from powergrid_sim.physical_export import physical_row, write_physical_csv
from powergrid_sim.telemetry import snapshot_messages, write_telemetry_csv
from test_relay_experiment import local_broker


@pytest.fixture
def saved_run(tmp_path):
    folder = tmp_path/'saved'
    folder.mkdir()
    raw=folder/'source.json'
    raw.write_text('{"fixture": true}')
    physical, messages, weather = [], [], []
    for time in ("2025-07-01T12:00:00Z","2025-07-01T13:00:00Z"):
        for scenario in get_scenarios():
            net=run_scenario(scenario)
            row=physical_row(net,scenario,"fixture-run",time)
            physical.append(row)
            messages.extend(snapshot_messages(row,{f"bus_{i}":12.47 for i in range(1,5)}))
            weather.append({key:row[key] for key in ("run_id","snapshot_id","timestamp","scenario")})
    write_physical_csv(physical,folder/'physical_results.csv')
    write_telemetry_csv(messages,folder/'mqtt_telemetry.csv')
    with (folder/'weather_inputs.csv').open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(weather[0]));writer.writeheader();writer.writerows(weather)
    (folder/'summary.json').write_text(json.dumps(dict(run_id="fixture-run",all_converged=True,
        pv_model={"test_fixture":True},snapshots=6,messages=60,source_path=str(raw),
        source_sha256=hashlib.sha256(raw.read_bytes()).hexdigest())))
    return folder


def test_archives_exact_bytes(saved_run,tmp_path):
    target=tmp_path/'archive';target.mkdir()
    metadata=archive_weather_input(saved_run,target)
    assert metadata['original_messages']==60
    for name in ('physical_results.csv','mqtt_telemetry.csv','weather_inputs.csv'):
        assert (target/name).read_bytes()==(saved_run/name).read_bytes()
    assert (target/'weather_source.json').read_bytes()==(saved_run/'source.json').read_bytes()


@pytest.mark.parametrize('corruption',['telemetry','coverage','hash'])
def test_rejects_invalid_source(saved_run,tmp_path,corruption):
    if corruption=='telemetry':
        p=saved_run/'mqtt_telemetry.csv'
        with p.open() as f:reader=csv.DictReader(f);fields=reader.fieldnames;rows=list(reader)
        assert fields is not None
        data=json.loads(rows[0]['measurements']);data['voltage_kv']+=1
        rows[0]['measurements']=json.dumps(data)
        with p.open('w',newline='') as f:writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader();writer.writerows(rows)
    elif corruption=='coverage':
        p=saved_run/'weather_inputs.csv';lines=p.read_text().splitlines();p.write_text('\n'.join(lines[:-1])+'\n')
    else:
        (saved_run/'source.json').write_text('changed')
    target=tmp_path/'archive';target.mkdir()
    with pytest.raises(ValueError):archive_weather_input(saved_run,target)


@pytest.mark.parametrize('device',[None,'solar_pv'])
def test_saved_input_over_real_mqtt(saved_run,tmp_path,local_broker,device):
    before={p.name:p.read_bytes() for p in saved_run.iterdir()}
    folder=run_experiment(tmp_path/'experiments',host='127.0.0.1',port=local_broker,
        timeout=10,simulation_input=saved_run,attack_device=device,offset=5)
    counts=verify_experiment(folder,BatchCase('fixture',device,'active_power_kw',5))
    assert counts['original_messages']==counts['received_deliveries']==60
    assert counts['measurement_rows']==90
    assert counts['attacked_messages']==(6 if device else 0)
    assert {p.name:p.read_bytes() for p in saved_run.iterdir()}==before


def test_saved_input_batch(local_broker,saved_run,tmp_path):
    from integration.run_batch import run_batch
    folder=run_batch(tmp_path/'batch',host='127.0.0.1',port=local_broker,
        timeout=10,simulation_input=saved_run)
    manifest=json.loads((folder/'manifest.json').read_text())
    assert manifest['status']=='completed'
    assert manifest['totals_verified']['original_messages']==540
    assert manifest['totals_verified']['measurement_rows']==810
    assert manifest['totals_verified']['attacked_messages']==48
    assert manifest['planned_counts_without_duplicates']['original_messages']==540
