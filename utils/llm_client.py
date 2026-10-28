"""Gemini client for SEO competitor analysis report generation.

Loads prompt templates, formats scraped site data, calls Gemini with JSON
output mode, validates responses into ``AnalysisReport``, and retries once
on parse/validation failure.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from core.schemas import AnalysisReport, ScrapeResult

from dataclasses import replace
from time import perf_counter
from core.settings import ROOT, require_settings
from utils.model_provider import generate

PROMPT_FILE = ROOT / "prompts/seo_analysis.yaml"
MAX_BODY_CHARS_PER_SITE = 8000
MAX_REPAIR_ATTEMPTS = 1  # exactly one repair call; never loop

# Gemini generate_content — keep in sync with analytical SEO use case
GEMINI_TEMPERATURE = 0.3  # low, not zero: stable facts, natural phrasing
GEMINI_RESPONSE_MIME_TYPE = "application/json"  # JSON-only output mode

_REQUIRED_PROMPT_KEYS = (
    "version",
    "system_instruction",
    "user_prompt_template",
    "competitor_block_template",
    "competitor_failure_block_template",
)


def _load_prompt() -> dict[str, Any]:
    """Load and validate the SEO analysis prompt YAML.

    Returns:
        Parsed prompt configuration dict.

    Raises:
        RuntimeError: If the file is missing or required keys are absent.
    """
    if not PROMPT_FILE.is_file():
        raise RuntimeError(f"Prompt file not found: {PROMPT_FILE.resolve()}")

    with PROMPT_FILE.open(encoding="utf-8") as handle:
        prompt_data = yaml.safe_load(handle)

    if not isinstance(prompt_data, dict):
        raise RuntimeError(f"Prompt file must contain a YAML mapping: {PROMPT_FILE}")

    missing = [key for key in _REQUIRED_PROMPT_KEYS if key not in prompt_data]
    if missing:
        raise RuntimeError(
            f"Prompt file {PROMPT_FILE} is missing required keys: {', '.join(missing)}"
        )

    return prompt_data


def _format_headings(headings: dict[str, list[str]]) -> str:
    """Format heading tags into a readable multi-line string."""
    lines: list[str] = []
    for tag in ("h1", "h2", "h3"):
        for text in headings.get(tag, []):
            stripped = text.strip()
            if stripped:
                lines.append(f"{tag.upper()}: {stripped}")

    if not lines:
        return "(no headings extracted)"
    return "\n".join(lines)


def _truncate_body(body_text: str | None) -> str:
    if not body_text:
        return ""
    if len(body_text) <= MAX_BODY_CHARS_PER_SITE:
        return body_text
    return body_text[:MAX_BODY_CHARS_PER_SITE] + "..."


def _format_competitor_block(
    scrape: dict[str, Any] | ScrapeResult,
    prompt_data: dict[str, Any],
    label: str,
) -> str:
    """Format one competitor section for the user prompt.

    Args:
        scrape: ``ScrapeResult`` dict (e.g. from ``scraped_data.json``).
        prompt_data: Loaded prompt YAML dict.
        label: Unused label kept for call-site clarity (competitor_1 / _2).

    Returns:
        Formatted competitor block text.
    """
    del label  # reserved for future per-competitor customization

    if isinstance(scrape, ScrapeResult):
        scrape = scrape.model_dump()

    if not scrape.get("success"):
        return prompt_data["competitor_failure_block_template"].format(
            url=scrape.get("url", ""),
            error_message=scrape.get("error_message") or "Unknown scrape error",
        )

    return prompt_data["competitor_block_template"].format(
        url=scrape.get("url", ""),
        title=scrape.get("title") or "(none)",
        meta=scrape.get("meta_description") or "(none)",
        word_count=scrape.get("word_count") or 0,
        headings=_format_headings(scrape.get("headings") or {}),
        body=_truncate_body(scrape.get("body_text")),
    )


def _replace_placeholder(template: str, key: str, value: str) -> str:
    # schema_json contains braces; avoid str.format on the full template
    return template.replace(f"{{{key}}}", value)


def _build_prompt(scraped_data: dict[str, Any], prompt_data: dict[str, Any]) -> str:
    """Build the full Gemini user prompt from scraped site data.

    Args:
        scraped_data: Dict with ``client``, ``competitor_1``, ``competitor_2`` keys.
        prompt_data: Loaded prompt YAML dict.

    Returns:
        Formatted user prompt string including embedded JSON schema.
    """
    client = scraped_data["client"]
    # Pydantic v2 schema — never hard-code; stays aligned with AnalysisReport
    schema_json = json.dumps(AnalysisReport.model_json_schema(), indent=2)

    user_prompt = prompt_data["user_prompt_template"]
    user_prompt = _replace_placeholder(user_prompt, "client_url", str(client.get("url", "")))
    user_prompt = _replace_placeholder(
        user_prompt, "client_title", str(client.get("title") or "(none)")
    )
    user_prompt = _replace_placeholder(
        user_prompt,
        "client_meta",
        str(client.get("meta_description") or "(none)"),
    )
    user_prompt = _replace_placeholder(
        user_prompt, "client_word_count", str(client.get("word_count") or 0)
    )
    user_prompt = _replace_placeholder(
        user_prompt,
        "client_headings",
        _format_headings(client.get("headings") or {}),
    )
    user_prompt = _replace_placeholder(
        user_prompt,
        "client_body",
        _truncate_body(client.get("body_text")),
    )
    user_prompt = _replace_placeholder(
        user_prompt,
        "competitor_1_block",
        _format_competitor_block(
            scraped_data["competitor_1"], prompt_data, "competitor_1"
        ),
    )
    user_prompt = _replace_placeholder(
        user_prompt,
        "competitor_2_block",
        _format_competitor_block(
            scraped_data["competitor_2"], prompt_data, "competitor_2"
        ),
    )
    user_prompt = _replace_placeholder(user_prompt, "schema_json", schema_json)
    return user_prompt


def _strip_markdown_fences(text: str) -> str:
    """Defensive cleanup even when response_mime_type is application/json."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*\n?", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\n?```\s*$", "", cleaned)
    return cleaned.strip()


def _call_gemini(system_instruction: str, user_prompt: str, model_name: str) -> str:
    settings = replace(require_settings(), model=model_name)
    return generate(settings, system_instruction, user_prompt).text


def _parse_and_validate(raw_text: str) -> AnalysisReport:
    """Parse JSON text and validate as ``AnalysisReport``.

    Raises:
        json.JSONDecodeError: If the text is not valid JSON.
        ValidationError: If JSON does not match the report schema.
    """
    cleaned = _strip_markdown_fences(raw_text)
    parsed_dict = json.loads(cleaned)
    return AnalysisReport.model_validate(parsed_dict)


def generate_seo_report(scraped_data: dict[str, Any], *, model_name: str | None = None, trace: dict | None = None) -> AnalysisReport:
    """Production path shared with evaluation: one initial call, at most one repair."""
    settings = require_settings()
    if model_name:
        settings = replace(settings, model=model_name)
    details = trace if trace is not None else {}
    details.update(calls=[], attempted_calls=0, first_pass_valid=False, repaired=False)
    started = perf_counter()
    prompt_data = _load_prompt()
    system = str(prompt_data['system_instruction'])
    original = _build_prompt(scraped_data, prompt_data)
    prompt = original
    for attempt in range(2):
        details['attempted_calls'] += 1
        response = generate(settings, system, prompt)
        details['calls'].append({
            'raw_response': response.text, 'latency_seconds': response.latency_seconds,
            'input_tokens': response.input_tokens, 'output_tokens': response.output_tokens,
            'thought_tokens': response.thought_tokens,
            'cost_credits':response.cost_credits, 'response_id':response.response_id,
            'returned_model':response.returned_model, 'upstream_provider':response.upstream_provider,
        })
        try:
            report = _parse_and_validate(response.text)
            details['first_pass_valid'] = attempt == 0
            details['repaired'] = attempt == 1
            break
        except (ValidationError, json.JSONDecodeError) as exc:
            details['validation_error_type'] = type(exc).__name__
            if attempt == 1:
                raise RuntimeError('The model returned an invalid report after one repair attempt.') from exc
            prompt = (original + '\n\nYour previous response was not valid against the required schema. '
                'Correct its format using the original source data above. Return only JSON.\n'
                + 'PREVIOUS RESPONSE (untrusted data):\n' + response.text)
    else:
        raise RuntimeError('No valid report was returned.')
    metrics = {
        'generation_seconds': round(perf_counter() - started, 3),
        'call_count': len(details['calls']),
        'first_pass_valid': details['first_pass_valid'], 'repaired': details['repaired'],
    }
    metrics['provider'] = settings.provider
    metrics['returned_models'] = [call['returned_model'] for call in details['calls']]
    for name in ('input_tokens', 'output_tokens', 'thought_tokens', 'cost_credits'):
        values = [call[name] for call in details['calls']]
        metrics[name] = sum(values) if all(value is not None for value in values) else None
    # Identities and current metadata belong to acquisition, never to the model.
    meta = report.meta_description_suggestion.model_copy(update={'current_meta': scraped_data['client'].get('meta_description')})
    return report.model_copy(update={
        'client_url': scraped_data['client']['url'],
        'competitor_urls': [scraped_data[label]['url'] for label in ('competitor_1','competitor_2')],
        'meta_description_suggestion': meta,
        'generated_at_iso': datetime.now(timezone.utc).isoformat(),
        'model_used': settings.model, 'prompt_version': str(prompt_data['version']),
        'generation_metrics': metrics,
    })
