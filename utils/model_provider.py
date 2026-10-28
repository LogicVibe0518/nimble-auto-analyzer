"""Provider selection is explicit; credentials never fall back across providers."""
from core.settings import Settings
from core.provider_contract import ModelResponse

def generate(settings: Settings, system: str, prompt: str) -> ModelResponse:
    if settings.provider == 'openrouter':
        from utils.openrouter_provider import generate as call
    elif settings.provider == 'gemini':
        from utils.gemini_provider import generate as call
    else:
        raise ValueError('Unsupported Nimble provider')
    return call(settings,system,prompt)
