"""OpenRouter transport: explicit key, bounded request, no automatic model fallback."""
from time import perf_counter
import math
import httpx
from core.settings import Settings
from core.provider_contract import ModelResponse, ProviderError

BASE_URL = 'https://openrouter.ai/api/v1'

def _cost(value):
    if isinstance(value, (int,float)) and not isinstance(value,bool) and math.isfinite(value) and value >= 0:
        return float(value)
    return None

def generate(settings: Settings, system: str, prompt: str) -> ModelResponse:
    if not settings.api_key or not settings.model or settings.model.startswith('openrouter/'):
        raise ValueError('Configure a fresh Nimble OpenRouter key and a specific model ID, not an automatic router.')
    started = perf_counter()
    # Proxies, auth and certificates are not borrowed from the shell environment.
    # No redirect following: an Authorization header never follows another host.
    with httpx.Client(timeout=httpx.Timeout(settings.timeout_ms/1000, connect=10), trust_env=False) as client:
        response = client.post(BASE_URL + '/chat/completions', headers={
            'Authorization':'Bearer ' + settings.api_key,
            'X-OpenRouter-Title':'Nimble Auto-Analyzer',
        }, json={
            'model':settings.model, 'stream':False, 'temperature':.3,
            'max_tokens':settings.max_output_tokens,
            'messages':[{'role':'system','content':system},{'role':'user','content':prompt}],
            'response_format':{'type':'json_object'},
            'provider':{'require_parameters':True,'allow_fallbacks':False},
        })
    if response.status_code != 200:
        raise ProviderError(response.status_code, 'OpenRouter rejected the request; inspect account access, quota and model support.')
    try:
        data = response.json()
    except ValueError as exc:
        raise ProviderError(502, 'OpenRouter returned an unreadable response.') from exc
    if data.get('error'):
        code = data['error'].get('code', 502)
        raise ProviderError(int(code) if str(code).isdigit() else 502, 'OpenRouter returned a provider error.')
    choices = data.get('choices') or []
    message = choices[0].get('message',{}) if choices else {}
    text = message.get('content')
    if not isinstance(text,str) or not text.strip():
        raise ProviderError(502, 'The model returned no report text.')
    usage = data.get('usage') or {}
    return ModelResponse(text=text,latency_seconds=round(perf_counter()-started,3),
        input_tokens=usage.get('prompt_tokens'),output_tokens=usage.get('completion_tokens'),
        thought_tokens=(usage.get('completion_tokens_details') or {}).get('reasoning_tokens'),
        cost_credits=_cost(usage.get('cost')),response_id=data.get('id'),
        returned_model=data.get('model'),upstream_provider=data.get('provider'))
