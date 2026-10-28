from fastapi.testclient import TestClient
import pytest
from apps.api.main import create_app

@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path / 'jobs.sqlite')) as session:
        yield session

def test_health_reports_local_mode(client):
    assert client.get('/health').json()['mode'] == 'local'

def test_reject_duplicate_urls_without_creating_job(client):
    assert client.post('/api/analyses', json={'client_url':'https://example.com',
        'competitor_1_url':'https://example.com','competitor_2_url':'https://other.example.com'}).status_code == 422

def test_pdf_unavailable_before_job(client):
    assert client.get('/api/analyses/does-not-exist/report.pdf').status_code == 404
