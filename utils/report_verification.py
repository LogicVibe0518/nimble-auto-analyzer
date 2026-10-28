"""Deterministic provenance and literal-gap checks; semantic quality needs review."""
import re
from core.schemas import AnalysisReport, ScrapeResult

def normal(text: str) -> str:
    return ' '.join(text.split()).casefold()

def _contains_quote(quote: str, body: str | None) -> bool:
    return bool(quote.strip() and body and normal(quote) in normal(body))

def source_text(source: ScrapeResult) -> str:
    return ' '.join([source.title or '', source.meta_description or '', source.body_text or '',
        *[heading for headings in source.headings.values() for heading in headings]])

def contains_keyword(keyword: str, text: str) -> bool:
    phrase = normal(keyword)
    return bool(phrase and re.search(r'(?<!\w)' + re.escape(phrase) + r'(?!\w)', normal(text)))

def verify_report(report: AnalysisReport, data: dict[str, ScrapeResult]) -> AnalysisReport:
    notes = list(report.flagged_uncertainties)
    client = data.get('client')
    valid_gaps = []
    for gap in report.keyword_gaps:
        source = data.get(gap.which_competitor)
        reason = None
        if not source or not source.success or not _contains_quote(gap.source_quote, source_text(source)):
            reason = 'its quoted competitor evidence could not be verified'
        elif not contains_keyword(gap.keyword, source_text(source)):
            reason = 'the keyword was not found in that competitor page'
        elif client and contains_keyword(gap.keyword, source_text(client)):
            reason = 'the keyword already appears on the supplied client page'
        if reason:
            notes.append(f"Excluded keyword opportunity '{gap.keyword}' because {reason}.")
        else:
            valid_gaps.append(gap)
    valid_insights = []
    for insight in report.content_strategy_insights:
        matches = [source for source in data.values() if source.success and insight.source_quote
            and _contains_quote(insight.source_quote, source_text(source))
            and (not insight.source_url or insight.source_url == source.url)]
        unique = {source.url for source in matches}
        if len(unique) == 1:
            valid_insights.append(insight.model_copy(update={'source_url': next(iter(unique))}))
        else:
            notes.append(f"Excluded content insight '{insight.insight[:65]}' because its quoted evidence could not be attributed to one source.")
    meta = report.meta_description_suggestion
    if meta.character_count != len(meta.suggested_meta):
        notes.append('AI-reported meta description length corrected by deterministic validation.')
    meta = meta.model_copy(update={'character_count':len(meta.suggested_meta),
        'current_meta':client.meta_description if client else meta.current_meta})
    if not 150 <= len(meta.suggested_meta) <= 160:
        notes.append('The suggested description is outside the requested 150–160 character range; review it before use.')
    notes.append('Keyword checks cover literal phrases on the supplied pages. They do not measure search demand or prove semantic absence across the whole website.')
    return report.model_copy(update={'keyword_gaps':valid_gaps, 'content_strategy_insights':valid_insights,
        'meta_description_suggestion':meta, 'flagged_uncertainties':list(dict.fromkeys(notes))})
