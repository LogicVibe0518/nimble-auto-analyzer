import json
from pathlib import Path
from benchmarks.evaluate import run_offline


def test_fixture_audit_is_not_presented_as_live_model_benchmark():
    cases=json.loads(Path('benchmarks/datasets/synthetic_fixture.json').read_text())['cases']
    result = run_offline(cases)
    assert result['mode'] == 'offline_fixture_audit'
    assert result['schema_valid'] == 1
    assert result['cases'][0]['quote_grounding_rate'] == 1.0
    assert 'NOT measured model comparisons' in result['disclaimer']
