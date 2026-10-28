import json
import httpx
import pytest
from core.settings import Settings, read_settings
from core.provider_contract import ProviderError
from utils import openrouter_provider as provider


def fake_client(monkeypatch,handler):
    original=httpx.Client
    def factory(*args,**kwargs):
        assert kwargs.get('trust_env') is False
        return original(*args,**kwargs,transport=httpx.MockTransport(handler))
    monkeypatch.setattr(provider.httpx,'Client',factory)


def test_explicit_key_model_and_usage(monkeypatch):
    monkeypatch.setenv('OPENROUTER_API_KEY','never-use-this')
    requests=[]
    def handler(request):
        requests.append(request)
        body=json.loads(request.content)
        assert request.url == 'https://openrouter.ai/api/v1/chat/completions'
        assert request.headers['Authorization'] == 'Bearer fresh-test-only'
        assert body['model'] == 'vendor/model'
        assert body['response_format']['type'] == 'json_object'
        assert body['provider'] == {'require_parameters':True,'allow_fallbacks':False}
        return httpx.Response(200,json={'id':'test-generation','model':'vendor/model','provider':'upstream',
            'choices':[{'message':{'content':'{"ok":true}'}}],
            'usage':{'prompt_tokens':30,'completion_tokens':40,'cost':.001,
                'completion_tokens_details':{'reasoning_tokens':5}}})
    fake_client(monkeypatch,handler)
    result=provider.generate(Settings(api_key='fresh-test-only',model='vendor/model'),'system','source data')
    assert len(requests)==1
    assert result.cost_credits == .001
    assert result.returned_model == 'vendor/model'
    assert result.thought_tokens==5

@pytest.mark.parametrize('status',[401,402,429,503])
def test_http_errors_are_scrubbed_and_not_retried(monkeypatch,status):
    calls=[]
    def handler(_):
        calls.append(1)
        return httpx.Response(status,json={'error':{'message':'sensitive provider content'}})
    fake_client(monkeypatch,handler)
    with pytest.raises(ProviderError) as caught:
        provider.generate(Settings(api_key='test-only',model='vendor/model'),'s','p')
    assert caught.value.code == status
    assert 'sensitive' not in str(caught.value)
    assert len(calls)==1


def test_missing_cost_is_unknown_not_free(monkeypatch):
    fake_client(monkeypatch,lambda _:httpx.Response(200,json={'choices':[{'message':{'content':'{}'}}]}))
    response=provider.generate(Settings(api_key='test-only',model='vendor/model'),'s','p')
    assert response.cost_credits is None


def test_embedded_provider_error_is_not_treated_as_report(monkeypatch):
    fake_client(monkeypatch,lambda _:httpx.Response(200,json={'error':{'code':429,'message':'private error'}}))
    with pytest.raises(ProviderError) as caught:
        provider.generate(Settings(api_key='test-only',model='vendor/model'),'s','p')
    assert caught.value.code==429


def test_config_selects_only_the_named_provider(tmp_path,monkeypatch):
    monkeypatch.setenv('OPENROUTER_API_KEY','legacy')
    monkeypatch.setenv('GEMINI_API_KEY','legacy')
    file=tmp_path/'config'
    assert read_settings(file).api_key==''
    file.write_text('NIMBLE_PROVIDER=openrouter\nNIMBLE_OPENROUTER_API_KEY=fresh-test-only\nNIMBLE_GEMINI_API_KEY=do-not-use\nNIMBLE_MODEL=vendor/model\n')
    settings=read_settings(file)
    assert settings.provider=='openrouter'
    assert settings.api_key=='fresh-test-only'
    assert settings.model=='vendor/model'
