"""Configure one NEW OpenRouter key without reading old project credentials."""
import getpass
import json
import os
from pathlib import Path
import sys
import httpx

ROOT = Path(__file__).resolve().parents[1]
BASE = 'https://openrouter.ai/api/v1'

def configure():
    target = ROOT / '.env.nimble'
    if target.exists():
        raise SystemExit('.env.nimble already exists. This command will not read or overwrite an existing key; ask for the explicit migration step.')
    print('Use a NEW OpenRouter key dedicated to Nimble. Nothing is read from Stratum or your shell keys.')
    key = getpass.getpass('New Nimble OpenRouter key (hidden): ').strip()
    if not key or any(character.isspace() for character in key):
        raise SystemExit('No valid key entered; no credentials were saved.')
    try:
        with httpx.Client(timeout=20, trust_env=False) as client:
            headers={'Authorization':'Bearer '+key}
            check=client.get(BASE+'/key',headers=headers)
            if check.status_code != 200:
                raise SystemExit(f'OpenRouter key validation failed (HTTP {check.status_code}). No credentials were saved.')
            response=client.get(BASE+'/models/user',headers=headers)
            if response.status_code != 200:
                raise SystemExit(f'Model discovery failed (HTTP {response.status_code}). No credentials were saved.')
            rows=response.json()['data']
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        print(f'OpenRouter discovery failed ({type(exc).__name__}). No credentials were saved.',file=sys.stderr)
        raise SystemExit(1)
    models={row['id']:row for row in rows if row.get('id') and not row['id'].startswith('openrouter/')
        and 'text' in (row.get('architecture',{}).get('output_modalities') or ['text'])
        and {'response_format','temperature','max_tokens'}.issubset(set(row.get('supported_parameters') or []))}
    if not models:
        raise SystemExit('No compatible JSON text models were returned for this account. No credentials were saved.')
    directory=ROOT/'.nimble'; directory.mkdir(exist_ok=True)
    (directory/'available-models.json').write_text(json.dumps(models,indent=2))
    print('\nCompatible models (newest catalog entries, grouped by family):')
    shown=set()
    for family in ['google/','openai/','anthropic/','deepseek/','qwen/','meta-llama/']:
        candidates=sorted([row for row in models.values() if row['id'].startswith(family)],key=lambda row:row.get('created',0),reverse=True)[:4]
        for row in candidates:
            pricing = row.get('pricing') or {}
            try:
                prices = f"  [catalog $/1M tokens: in {float(pricing['prompt'])*1_000_000:g}, out {float(pricing['completion'])*1_000_000:g}]"
            except (KeyError,ValueError,TypeError):
                prices = '  [see catalog for pricing]'
            print('  '+row['id']+prices)
            shown.add(row['id'])
    if not shown:
        for model in sorted(models)[:24]: print('  '+model)
    print('\nFull catalog and pricing metadata: .nimble/available-models.json')
    print('Catalog inclusion does not guarantee quota or a currently available upstream route.')
    model=input('\nExact model ID for the main app: ').strip()
    if model not in models:
        raise SystemExit('That ID is not in the compatible catalog. No credentials were saved.')
    fd=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'w') as file:
        file.write(f'NIMBLE_PROVIDER=openrouter\nNIMBLE_OPENROUTER_API_KEY={key}\nNIMBLE_MODEL={model}\n')
    print('Saved the new key in .env.nimble with owner-only permissions. No generation calls were made.')
    print('The benchmark can select different model IDs through this same OpenRouter key.')

if __name__ == '__main__': configure()
