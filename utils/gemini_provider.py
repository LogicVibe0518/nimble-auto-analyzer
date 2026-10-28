"""The only inference network boundary; injectable in tests and shared by evaluation."""
from time import perf_counter
from google import genai
from core.settings import Settings

from core.provider_contract import ModelResponse

def generate(settings: Settings, system: str, prompt: str) -> ModelResponse:
    start = perf_counter()
    # Milliseconds; exactly one SDK attempt. The application separately permits
    # one JSON repair call. No hidden quota retry loop or provider fallback.
    with genai.Client(api_key=settings.api_key, vertexai=False, http_options={
        'base_url': 'https://generativelanguage.googleapis.com',
        'timeout': settings.timeout_ms, 'retry_options': {'attempts': 1},
    }) as client:
        response = client.models.generate_content(model=settings.model, contents=prompt, config={
            'system_instruction': system, 'temperature': .3,
            'response_mime_type': 'application/json', 'max_output_tokens': settings.max_output_tokens,
        })
    if not response.text:
        raise RuntimeError('The model returned no report text.')
    usage = response.usage_metadata
    return ModelResponse(response.text, round(perf_counter()-start, 3),
        getattr(usage, 'prompt_token_count', None), getattr(usage, 'candidates_token_count', None),
        getattr(usage, 'thoughts_token_count', None))
