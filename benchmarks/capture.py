"""Capture one frozen source triplet without invoking an AI provider."""
import argparse
import json
import re
from datetime import datetime, timezone
from hashlib import sha256
from core.settings import ROOT
from utils.safe_scraper import scrape_url_safe


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--id',required=True)
    parser.add_argument('--client',required=True)
    parser.add_argument('--competitor-one',required=True)
    parser.add_argument('--competitor-two',required=True)
    args=parser.parse_args()
    if not re.fullmatch(r'[a-z0-9-]{1,60}',args.id):
        parser.error('id must contain 1–60 lowercase letters, digits or hyphens')
    urls={'client':args.client,'competitor_1':args.competitor_one,'competitor_2':args.competitor_two}
    sources={label:scrape_url_safe(url).model_dump() for label,url in urls.items()}
    for label,source in sources.items():
        print(label + ': ' + ('retrieved' if source['success'] else source['error_message']))
    if not sources['client']['success']:
        raise SystemExit('Client page unavailable; no dataset was saved.')
    dataset={'cases':[{'id':args.id,'sources':sources,'ground_truth':{'reviewed':False,'expected_keywords':[]},
        'captured_at':datetime.now(timezone.utc).isoformat(),
        'source_hash':sha256(json.dumps(sources,sort_keys=True).encode()).hexdigest()}]}
    directory=ROOT/'.nimble'/'datasets'; directory.mkdir(parents=True,exist_ok=True)
    output=directory/(args.id+'.json')
    with output.open('x') as file:
        json.dump(dataset,file,indent=2)
    print(f'Saved {output}. Review source quality and annotate genuine opportunities before evaluation.')

if __name__=='__main__': main()
