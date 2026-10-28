"""Explicit, project-scoped configuration. Legacy/other-project keys are ignored."""
from dataclasses import dataclass, field
from pathlib import Path
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]

@dataclass(frozen=True)
class Settings:
    api_key: str = field(default='', repr=False)
    model: str = ''
    provider: str = 'openrouter'
    timeout_ms: int = 60000
    max_output_tokens: int = 8192

def read_settings(path: Path | None = None) -> Settings:
    file = path if path is not None else ROOT / '.env.nimble'
    # No environment fallback or variable interpolation: other project secrets
    # can never be selected by an inherited shell environment.
    values = dotenv_values(file, interpolate=False) if file.is_file() else {}
    provider = values.get('NIMBLE_PROVIDER') or 'openrouter'
    key_name = {'openrouter':'NIMBLE_OPENROUTER_API_KEY', 'gemini':'NIMBLE_GEMINI_API_KEY'}.get(provider)
    if not key_name:
        raise ValueError('Unsupported Nimble provider')
    return Settings(api_key=values.get(key_name) or '', model=values.get('NIMBLE_MODEL') or '', provider=provider)

def require_settings() -> Settings:
    settings = read_settings()
    if not settings.api_key or not settings.model:
        raise ValueError('Configure a fresh Nimble key and model with scripts/configure_nimble.py first.')
    return settings
