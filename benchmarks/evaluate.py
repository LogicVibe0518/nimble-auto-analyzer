"""Repeatable offline and live LLM evaluation for *SEO-specific* behaviour.

Offline mode audits prepared fixture outputs; it does NOT compare live models.
Live mode calls every nominated model through the configured provider on identical inputs. It incurs
API charges and requires a manually reviewed real-world benchmark corpus.
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from core.schemas import AnalysisReport, ScrapeResult
from utils.report_verification import verify_report


def score_output(raw_report: dict, sources: dict[str, dict]) -> dict[str, Any]:
    """Objective schema and quote-provenance checks; NOT an SEO quality grade."""
    report = AnalysisReport.model_validate(raw_report)
    scrape = {key: ScrapeResult.model_validate(value) for key, value in sources.items()}
    before = len(report.keyword_gaps) + len(report.content_strategy_insights)
    verified = verify_report(report, scrape)
    after = len(verified.keyword_gaps) + len(verified.content_strategy_insights)
    return {
        "schema_valid": True,
        "quoted_findings_submitted": before,
        "quoted_findings_verified": after,
        "quote_grounding_rate": round(after / before, 4) if before else None,
        "unsupported_findings_excluded": before - after,
        "meta_character_count_correct": report.meta_description_suggestion.character_count == len(report.meta_description_suggestion.suggested_meta),
        "requires_human_quality_review": True,
    }


def _p95(samples: list[float]) -> float | None:
    return sorted(samples)[max(0, math.ceil(len(samples) * .95) - 1)] if samples else None


def run_offline(cases: list[dict]) -> dict[str, Any]:
    evaluations = []
    for case in cases:
        try:
            score = score_output(case["report"], case["sources"])
            evaluations.append({"id": case["id"], "status": "valid", **score})
        except Exception as exc:
            evaluations.append({"id": case.get("id", "unknown"), "status": "invalid", "error_type": type(exc).__name__})
    return {
        "mode": "offline_fixture_audit",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "disclaimer": "These are fixture checks, NOT measured model comparisons or real SEO accuracy.",
        "total": len(evaluations),
        "schema_valid": sum(e["status"] == "valid" for e in evaluations),
        "cases": evaluations,
    }


def run_live(cases: list[dict], models: list[str], repeats: int, max_calls: int) -> dict[str, Any]:
    from core.settings import ROOT, require_settings
    from utils.llm_client import generate_seo_report
    import uuid
    require_settings()
    models = list(dict.fromkeys(models))
    runs = []
    attempted_calls = 0
    stop_reason = None
    run_id = uuid.uuid4().hex
    output_dir = ROOT / '.nimble' / 'benchmarks'
    output_dir.mkdir(parents=True, exist_ok=True)
    for case in cases:
        if stop_reason: break
        for repetition in range(repeats):
            if stop_reason: break
            # Alternate model order across repeats; all models see identical snapshots.
            ordered = models if repetition % 2 == 0 else list(reversed(models))
            for model in ordered:
                if max_calls - attempted_calls < 2:
                    stop_reason = 'Call ceiling reached; fewer than two calls remain for a bounded report attempt.'
                    break
                trace = {}
                started = time.perf_counter()
                entry = {'model': model, 'case': case['id'], 'repetition': repetition + 1}
                try:
                    report = generate_seo_report(case['sources'], model_name=model, trace=trace)
                    entry.update(status='success', **score_output(report.model_dump(), case['sources']))
                    entry['report'] = report.model_dump()
                    entry['verified_report'] = verify_report(report, {key:ScrapeResult.model_validate(value) for key,value in case['sources'].items()}).model_dump()
                    entry['metrics'] = report.generation_metrics
                    truth = case.get('ground_truth')
                    if truth and truth.get('reviewed') is True and isinstance(truth.get('expected_keywords'), list):
                        # This is literal annotation matching, never semantic SEO accuracy.
                        expected = {' '.join(value.split()).casefold() for value in truth['expected_keywords']}
                        returned = {' '.join(gap.keyword.split()).casefold() for gap in report.keyword_gaps}
                        hit = len(expected & returned)
                        entry['literal_annotation_precision'] = hit / len(returned) if returned else None
                        entry['literal_annotation_recall'] = hit / len(expected) if expected else None
                except Exception as exc:
                    entry.update(status='failed', error_type=type(exc).__name__)
                    if getattr(exc, 'code', None) in (401,402,403,429):
                        stop_reason = 'Provider authentication or quota failure; run stopped without automatic retries.'
                attempted_calls += trace.get('attempted_calls', 0)
                entry['trace'] = trace
                entry['latency_seconds'] = round(time.perf_counter()-started, 3)
                runs.append(entry)
                # Checkpoints preserve all completed runs if the process is interrupted.
                (output_dir / (run_id + '.checkpoint.json')).write_text(json.dumps({'run_id':run_id,'runs':runs}, indent=2))
                if stop_reason: break
    summary = {}
    for model in models:
        relevant = [row for row in runs if row['model'] == model]
        successful = [row for row in relevant if row['status'] == 'success']
        latency = [row['latency_seconds'] for row in relevant]
        grounding = [row['quote_grounding_rate'] for row in successful if row['quote_grounding_rate'] is not None]
        costs = [call.get('cost_credits') for row in relevant for call in row.get('trace',{}).get('calls',[])]
        known_costs = [value for value in costs if value is not None]
        cost_complete = bool(costs) and all(value is not None for value in costs) and sum(row.get('trace',{}).get('attempted_calls',0) for row in relevant) == len(costs)
        summary[model] = {
            'attempts':len(relevant), 'successes':len(successful),
            'success_rate':len(successful)/len(relevant) if relevant else None,
            'first_pass_valid':sum(bool(row.get('trace',{}).get('first_pass_valid')) for row in relevant),
            'repairs':sum(bool(row.get('trace',{}).get('repaired')) for row in relevant),
            'mean_grounding_rate':statistics.mean(grounding) if grounding else None,
            'median_seconds':statistics.median(latency) if latency else None,
            'reported_cost_credits':sum(known_costs) if known_costs else None,
            'cost_complete':cost_complete,
            'cost':'OpenRouter response usage; missing/failed-call charges may not be represented. Reconcile against account usage.',
            'quality':'Requires blind human review; excerpt survival is not SEO accuracy.',
        }
    result = {'mode':'live_provider_comparison', 'run_id':run_id,
        'generated_at':datetime.now(timezone.utc).isoformat(), 'attempted_calls':attempted_calls,
        'max_calls':max_calls, 'stop_reason':stop_reason, 'summary':summary, 'runs':runs,
        'disclaimer':'Small-sample task evaluation. Synthetic cases do not establish real-world SEO quality.'}
    serialized = json.dumps(result,indent=2)
    (output_dir / (run_id + '.json')).write_text(serialized)
    temp = output_dir / (run_id + '.latest.tmp')
    temp.write_text(serialized)
    temp.replace(output_dir / 'latest.json')
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=['offline','live'], default='offline')
    parser.add_argument('--dataset', type=Path, default=Path('benchmarks/datasets/synthetic_fixture.json'))
    parser.add_argument('--model', action='append', default=[], help='Exact OpenRouter model ID; repeat to compare models')
    parser.add_argument('--repeats', type=int, default=2)
    parser.add_argument('--out', type=Path)
    parser.add_argument('--max-calls', type=int, help='Required live API-call ceiling, including JSON repairs')
    args = parser.parse_args()
    if args.repeats < 1 or args.repeats > 10:
        parser.error('repeats must be between 1 and 10')
    if args.mode == 'live' and not args.model:
        parser.error('live mode needs at least one --model')
    if args.mode == 'live' and (args.max_calls is None or not 2 <= args.max_calls <= 100):
        parser.error('live mode requires --max-calls between 2 and 100, including repairs')
    cases = json.loads(args.dataset.read_text(encoding='utf-8'))["cases"]
    result = run_offline(cases) if args.mode == 'offline' else run_live(cases, args.model, args.repeats, args.max_calls)
    displayed = {key:value for key,value in result.items() if key != 'runs'} if args.mode == 'live' else result
    print(json.dumps(displayed, indent=2))
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(result, indent=2), encoding='utf-8')

if __name__ == '__main__': main()
