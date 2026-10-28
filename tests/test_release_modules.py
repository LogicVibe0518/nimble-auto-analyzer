import json
import time
from pathlib import Path
from types import SimpleNamespace
import pytest
from fastapi.testclient import TestClient
from core.settings import read_settings, Settings
from core.storage import JobStore
from core.schemas import AnalysisReport, ScrapeResult
from utils.report_verification import verify_report
from utils.gemini_provider import ModelResponse
from apps.api import main as api

@pytest.fixture
def fixture():
    return json.loads(Path('benchmarks/datasets/synthetic_fixture.json').read_text())['cases'][0]

def test_other_project_credentials_are_never_selected(tmp_path, monkeypatch):
    monkeypatch.setenv('GEMINI_API_KEY','do-not-use')
    monkeypatch.setenv('GOOGLE_API_KEY','do-not-use-either')
    assert read_settings(tmp_path/'missing').api_key == ''
    config=tmp_path/'fresh'; config.write_text('NIMBLE_OPENROUTER_API_KEY=${GEMINI_API_KEY}\n')
    assert read_settings(config).api_key == '${GEMINI_API_KEY}'
    assert 'secret' not in repr(Settings(api_key='secret'))

def test_reports_survive_restart_and_incomplete_jobs_are_marked(tmp_path):
    file=tmp_path/'jobs.sqlite'
    store=JobStore(file); store.initialize()
    store.create({'id':'done','status':'complete','report':{'summary':'kept'}})
    store.update('done',pdf=b'%PDF-fixture')
    store.create({'id':'pending','status':'running'})
    restarted=JobStore(file); restarted.initialize()
    assert restarted.pdf('done') == b'%PDF-fixture'
    assert restarted.get('done')['report']['summary'] == 'kept'
    assert restarted.get('pending')['status'] == 'failed'

def test_false_gap_already_on_client_is_removed(fixture):
    data={key:ScrapeResult.model_validate(value) for key,value in fixture['sources'].items()}
    data['client'].body_text += ' Renewable energy audits.'
    report=verify_report(AnalysisReport.model_validate(fixture['report']),data)
    assert report.keyword_gaps == []
    assert any('already appears' in note for note in report.flagged_uncertainties)

def test_keyword_cannot_borrow_an_unrelated_real_quote(fixture):
    fixture['report']['keyword_gaps'][0]['keyword']='imaginary private helipad'
    report=verify_report(AnalysisReport.model_validate(fixture['report']),
        {key:ScrapeResult.model_validate(value) for key,value in fixture['sources'].items()})
    assert report.keyword_gaps == []

def test_missing_key_is_rejected_before_any_job(tmp_path,monkeypatch):
    monkeypatch.setattr(api,'read_settings',lambda:Settings())
    with TestClient(api.create_app(tmp_path/'jobs.sqlite')) as client:
        response=client.post('/api/analyses',json={'client_url':'https://one.example',
            'competitor_1_url':'https://two.example','competitor_2_url':'https://three.example'})
        assert response.status_code == 503
        assert client.get('/api/analyses').json() == []
        assert client.post('/api/analyses',headers={'Origin':'https://untrusted.example'},json={}).status_code == 403

def test_api_job_and_pdf_round_trip_then_restart(tmp_path,monkeypatch,fixture):
    monkeypatch.setattr(api,'read_settings',lambda:Settings(api_key='test-only',model='stub'))
    def pipeline(request, progress, *, model_name=None):
        progress('Verifying source quotations')
        return b'%PDF-local-test',AnalysisReport.model_validate(fixture['report']),{key:ScrapeResult.model_validate(value) for key,value in fixture['sources'].items()}
    monkeypatch.setattr(api,'run_pipeline',pipeline)
    database=tmp_path/'jobs.sqlite'
    with TestClient(api.create_app(database)) as client:
        response=client.post('/api/analyses',json={'client_url':'https://one.example',
            'competitor_1_url':'https://two.example','competitor_2_url':'https://three.example'})
        assert response.status_code == 202
        id=response.json()['id']
        deadline=time.monotonic()+3
        while time.monotonic()<deadline:
            job=client.get('/api/analyses/'+id).json()
            if job['status'] in ['complete','failed']: break
            time.sleep(.01)
        assert job['status'] == 'complete'
        assert 'body_text' not in job['sources']['client']
    with TestClient(api.create_app(database)) as client:
        assert client.get('/api/analyses/'+id+'/report.pdf').content == b'%PDF-local-test'
        assert client.get('/api/analyses').json()[0]['id'] == id

def test_generation_repairs_once_and_uses_acquired_identity(monkeypatch,fixture):
    from utils import llm_client
    monkeypatch.setattr(llm_client,'require_settings',lambda:Settings(api_key='test-only',model='stub'))
    bad=dict(fixture['report'],client_url='https://invented.example')
    answers=iter(['not json', json.dumps(bad)])
    prompts=[]
    def generate(settings,system,prompt):
        prompts.append(prompt)
        return ModelResponse(next(answers),.01,10,20,0)
    monkeypatch.setattr(llm_client,'generate',generate)
    trace={}
    report=llm_client.generate_seo_report(fixture['sources'],trace=trace)
    assert len(prompts) == 2
    assert fixture['sources']['client']['body_text'][:50] in prompts[1]
    assert report.client_url == fixture['sources']['client']['url']
    assert report.generation_metrics['input_tokens'] == 20
    assert report.generation_metrics['repaired'] is True

def test_generation_does_not_retry_invalid_output_forever(monkeypatch,fixture):
    from utils import llm_client
    monkeypatch.setattr(llm_client,'require_settings',lambda:Settings(api_key='test-only',model='stub'))
    calls=[]
    def generate(*args):
        calls.append(1)
        return ModelResponse('invalid',.01,10,20,0)
    monkeypatch.setattr(llm_client,'generate',generate)
    with pytest.raises(RuntimeError,match='one repair'):
        llm_client.generate_seo_report(fixture['sources'])
    assert len(calls) == 2

def test_live_benchmark_respects_call_ceiling_without_legacy_keys(tmp_path,monkeypatch,fixture):
    from core import settings
    from utils import llm_client
    from benchmarks.evaluate import run_live
    monkeypatch.setattr(settings,'ROOT',tmp_path)
    monkeypatch.setattr(settings,'require_settings',lambda:Settings(api_key='test-only',model='stub'))
    count=[]
    def generate(sources,model_name=None,trace=None):
        count.append(model_name)
        trace.update(attempted_calls=1,first_pass_valid=True,repaired=False,calls=[])
        return AnalysisReport.model_validate(fixture['report'])
    monkeypatch.setattr(llm_client,'generate_seo_report',generate)
    result=run_live([fixture],['first','second'],3,max_calls=3)
    assert len(count) == 2
    assert result['attempted_calls'] == 2
    assert result['stop_reason']
    assert (tmp_path/'.nimble/benchmarks/latest.json').exists()

def test_redirect_policy_rechecked_before_destination_download(monkeypatch):
    from utils import safe_scraper as scraper
    policies=[]
    monkeypatch.setattr(scraper,'_public_ips',lambda *_:['93.184.216.34'])
    def allowed(url):
        policies.append(url)
        return 'blocked' not in url
    monkeypatch.setattr(scraper,'_allowed_by_robots',allowed)
    class Connection:
        def __init__(self,*args,**kwargs): pass
        def request(self,*args,**kwargs): pass
        def getresponse(self):
            return SimpleNamespace(status=302,getheader=lambda name:'https://blocked.example/page' if name=='Location' else None)
        def close(self): pass
    monkeypatch.setattr(scraper.http.client,'HTTPSConnection',Connection)
    with pytest.raises(scraper.FetchError,match='robots'):
        scraper.fetch_url('https://allowed.example/page',check_robots=True)
    assert policies == ['https://allowed.example/page','https://blocked.example/page']

def test_pdf_builder_creates_a_real_pdf_from_validated_fixture(fixture):
    from utils.pdf_builder import build_pdf
    report=AnalysisReport.model_validate(fixture['report'])
    result=build_pdf(report)
    assert result.startswith(b'%PDF-')
    assert len(result)>2000

def test_shared_pipeline_assembles_a_verified_pdf_without_network(monkeypatch,fixture):
    from core import settings
    from core.schemas import AnalysisRequest
    from utils import pipeline,llm_client
    monkeypatch.setattr(settings,'require_settings',lambda:Settings(api_key='test-only',model='stub'))
    sources={value['url']:ScrapeResult.model_validate(value) for value in fixture['sources'].values()}
    monkeypatch.setattr(pipeline,'scrape_url_safe',lambda url:sources[url])
    monkeypatch.setattr(llm_client,'generate_seo_report',lambda _, **kwargs:AnalysisReport.model_validate(fixture['report']))
    request=AnalysisRequest(client_url=fixture['sources']['client']['url'],
        competitor_1_url=fixture['sources']['competitor_1']['url'],competitor_2_url=fixture['sources']['competitor_2']['url'])
    # URL contracts normalize a trailing slash; fixture keys are normalized too.
    sources.update({url+'/':value for url,value in list(sources.items())})
    stages=[]
    pdf,report,result=pipeline.run_pipeline(request,stages.append)
    assert pdf.startswith(b'%PDF-')
    assert len(report.keyword_gaps)==1
    assert len(result)==3
    assert stages[-1]=='Report ready'
