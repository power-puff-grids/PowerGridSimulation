from copy import deepcopy
import json
from pathlib import Path
import pytest
from attacks.attacks import false_data_injection, replay_attack
from integration.attack_records import fdi_details


@pytest.fixture
def sample():
    return json.loads((Path(__file__).parents[1] / 'data/sample/telemetry_example.json').read_text())


def test_reads_nested_details_without_mutating_source(sample):
    _, record = false_data_injection(sample, 5.0)
    before = deepcopy(record)
    details = fdi_details(record)
    assert details == {'measurement':'active_power_kw', 'original_value':150.0,
                       'manipulated_value':155.0, 'offset':5.0}
    details['original_value'] = 0
    assert record == before


def test_replay_is_not_interpreted_as_fdi(sample):
    _, record = replay_attack(sample)
    with pytest.raises(ValueError, match='Expected a false_data_injection'):
        fdi_details(record)


@pytest.mark.parametrize('problem',['missing_details','replay_details','ambiguous_flat','nonfinite_offset'])
def test_rejects_inconsistent_nested_record(sample, problem):
    _, record = false_data_injection(sample, 5.0)
    if problem == 'missing_details':
        record['false_data_injection'] = None
    elif problem == 'replay_details':
        record['replay'] = {'replayed_id':'old-message'}
    elif problem == 'ambiguous_flat':
        record['original_value'] = 150.0
    else:
        record['false_data_injection']['offset'] = float('nan')
    with pytest.raises(ValueError):
        fdi_details(record)
