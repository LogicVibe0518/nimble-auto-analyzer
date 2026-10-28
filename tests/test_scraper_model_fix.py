import json
import ssl
import time
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from core.settings import Settings
from core.schemas import ScrapeResult
from core.provider_contract import ModelResponse
from core.model_catalog import available_models


def test_catalog_exposes_only_text_model_options_and_public_prices(tmp_path):
    path = tmp_path / 'catalog.json'
    def row(**extra):
        return {'supported_parameters': ['response_format', 'temperature', 'max_tokens'],
                'architecture': {'output_modalities': ['text']},
                'pricing': {'prompt': '0.000001', 'completion': '0.000003'},
                'unrelated_private_field': 'must-not-leak', **extra}
    path.write_text(json.dumps({'vendor/text': row(), 'vendor/image': row(architecture={'output_modalities': ['text', 'image']}),
                               'vendor/text:batch': row(), 'openrouter/auto': row(), 'vendor/unsupported': row(supported_parameters=[])}))
    settings = Settings(api_key='must-not-leak', model='vendor/text')
    assert available_models(settings, path) == [{'id': 'vendor/text', 'input_per_million': 1.0, 'output_per_million': 3.0}]
    path.write_text('broken json')
    assert available_models(settings, path) == [{'id': 'vendor/text', 'input_per_million': None, 'output_per_million': None}]
    assert available_models(Settings(provider='gemini', model='gemini-test'), path)[0]['id'] == 'gemini-test'


@pytest.mark.parametrize('requested,expected', [(None, 'vendor/default'), ('vendor/selected', 'vendor/selected')])
def test_api_selection_reaches_model_generation_and_is_retained(tmp_path, monkeypatch, requested, expected):
    from apps.api import main as api
    from core import settings, model_catalog
    from utils import pipeline, llm_client
    fixture = json.loads(Path('benchmarks/datasets/synthetic_fixture.json').read_text())['cases'][0]
    config = Settings(api_key='test-only', model='vendor/default')
    monkeypatch.setattr(api, 'read_settings', lambda: config)
    monkeypatch.setattr(settings, 'require_settings', lambda: config)
    monkeypatch.setattr(llm_client, 'require_settings', lambda: config)
    monkeypatch.setattr(model_catalog, 'ROOT', tmp_path)
    directory = tmp_path / '.nimble'; directory.mkdir()
    (directory / 'available-models.json').write_text(json.dumps({'vendor/selected': {
        'supported_parameters': ['response_format', 'temperature', 'max_tokens'],
        'architecture': {'output_modalities': ['text']}}}))
    sources = {value['url'].rstrip('/'): ScrapeResult.model_validate(value) for value in fixture['sources'].values()}
    monkeypatch.setattr(pipeline, 'scrape_url_safe', lambda url: sources[url.rstrip('/')])
    calls = []
    def generate(settings, system, prompt):
        calls.append(settings.model)
        return ModelResponse(json.dumps(fixture['report']), .01, 10, 20, 0)
    monkeypatch.setattr(llm_client, 'generate', generate)
    payload = dict(zip(('client_url', 'competitor_1_url', 'competitor_2_url'), [value['url'] for value in fixture['sources'].values()]))
    if requested is not None:
        payload['model'] = requested
    with TestClient(api.create_app(tmp_path / 'jobs.sqlite')) as client:
        config_response = client.get('/api/config')
        assert 'test-only' not in config_response.text
        assert {row['id'] for row in config_response.json()['models']} == {'vendor/default', 'vendor/selected'}
        response = client.post('/api/analyses', json=payload)
        assert response.status_code == 202, response.text
        assert response.json()['model'] == expected
        id = response.json()['id']
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            job = client.get('/api/analyses/' + id).json()
            if job['status'] in ('complete', 'failed'):
                break
            time.sleep(.01)
        assert job['status'] == 'complete', job
        assert job['model'] == expected
        assert calls == [expected]
        assert client.get('/api/analyses/' + id + '/report.pdf').content.startswith(b'%PDF-')
        for invalid in ('openrouter/auto', 'vendor/unknown', ''):
            assert client.post('/api/analyses', json={**payload, 'model': invalid}).status_code == 422
        assert len(client.get('/api/analyses').json()) == 1


def test_scraper_keeps_tls_verification_and_explains_failed_robots(monkeypatch):
    from utils import safe_scraper as scraper
    monkeypatch.setattr(scraper, '_public_ips', lambda *_: ['93.184.216.34'])
    contexts = []
    class Connection:
        def __init__(self, host, port, *, timeout, context):
            assert host == 'hotel.example'
            contexts.append(context)
        def request(self, *args, **kwargs):
            raise ssl.SSLCertVerificationError('untrusted certificate')
        def close(self):
            pass
    monkeypatch.setattr(scraper.http.client, 'HTTPSConnection', Connection)
    result = scraper.scrape_url_safe('https://hotel.example/')
    assert not result.success
    assert result.error_message == 'Unable to verify robots.txt (HTTPS certificate verification failed); crawl skipped'
    assert contexts[0].check_hostname is True
    assert contexts[0].verify_mode == ssl.CERT_REQUIRED
    assert contexts[0].cert_store_stats()['x509_ca'] > 0
