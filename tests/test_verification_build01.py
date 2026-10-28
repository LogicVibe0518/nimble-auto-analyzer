from core.schemas import AnalysisReport, ScrapeResult
from utils.report_verification import verify_report


def test_unverifiable_quote_is_removed():
    source = ScrapeResult(url='https://example.com', success=True, body_text='We provide solar roofing installations and maintenance.' * 4)
    report = AnalysisReport(
        client_url='https://client.example.com', competitor_urls=['https://example.com'], executive_summary='Fixture',
        keyword_gaps=[{'keyword':'fictitious', 'which_competitor':'competitor_1', 'source_quote':'This statement never occurred', 'opportunity_rationale':'Fixture', 'confidence':'high'}],
        meta_description_suggestion={'current_meta':None,'suggested_meta':'Test description','character_count':1,'reasoning':'Fixture','keywords_targeted':[]},
        content_strategy_insights=[],flagged_uncertainties=[], generated_at_iso='2026-10-23T00:00:00+00:00',model_used='test',prompt_version='fixture',
    )
    checked = verify_report(report, {'competitor_1': source})
    assert len(checked.keyword_gaps) == 0
    assert any('Excluded keyword' in note for note in checked.flagged_uncertainties)
    assert checked.meta_description_suggestion.character_count == len('Test description')
