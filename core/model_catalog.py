"""Public model options from Nimble's saved OpenRouter catalog; no API requests."""
import json
import math
import re
from pathlib import Path
from core.settings import ROOT, Settings


def available_models(settings: Settings, path: Path | None = None) -> list[dict]:
    options = {}
    if settings.provider == 'openrouter':
        try:
            rows = json.loads((path or ROOT / '.nimble' / 'available-models.json').read_text())
        except (OSError, ValueError):
            rows = {}
        if isinstance(rows, dict):
            for model, row in rows.items():
                if not isinstance(row, dict) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}', model):
                    continue
                if model.startswith('openrouter/') or model.endswith(':batch'):
                    continue
                architecture = row.get('architecture') or {}
                if architecture.get('output_modalities', ['text']) != ['text']:
                    continue
                if not {'response_format', 'temperature', 'max_tokens'}.issubset(row.get('supported_parameters') or []):
                    continue
                pricing = row.get('pricing') or {}
                def price(key):
                    try:
                        value = float(pricing[key]) * 1_000_000
                        return value if math.isfinite(value) and value >= 0 else None
                    except (KeyError, TypeError, ValueError, OverflowError):
                        return None
                options[model] = {'id': model, 'input_per_million': price('prompt'),
                                  'output_per_million': price('completion')}
    # Preserve the explicitly configured default if the saved catalog is missing.
    if settings.model:
        options.setdefault(settings.model, {'id': settings.model, 'input_per_million': None, 'output_per_million': None})
    return [options[key] for key in sorted(options)]
