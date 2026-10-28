"""End-to-end application orchestrator, also repairs the original Streamlit import.

Settings are validated first; model generation only starts after successful client scraping.
"""
from __future__ import annotations
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from core.schemas import AnalysisRequest, AnalysisReport, ScrapeResult
from utils.safe_scraper import scrape_url_safe
from utils.report_verification import verify_report

StageCallback = Callable[[str], None]

def run_pipeline(request: AnalysisRequest, progress: StageCallback | None = None, *, model_name: str | None = None) -> tuple[bytes, AnalysisReport, dict[str, ScrapeResult]]:
    from core.settings import require_settings
    require_settings()
    announce = progress or (lambda _: None)
    announce("Fetching websites safely")
    urls = {"client": str(request.client_url), "competitor_1": str(request.competitor_1_url), "competitor_2": str(request.competitor_2_url)}
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {label: executor.submit(scrape_url_safe, url) for label, url in urls.items()}
        results = {label: fut.result() for label, fut in futures.items()}
    if not results["client"].is_usable_for_analysis():
        raise ValueError(f"Client website could not be analysed: {results['client'].error_message or 'insufficient content'}")
    announce("Generating source-grounded analysis")
    from utils.llm_client import generate_seo_report  # lazy import requires configured API key
    report = generate_seo_report({label: item.model_dump() for label, item in results.items()}, model_name=model_name)
    announce("Verifying source quotations")
    report = verify_report(report, results)
    failures = [f"{label}: {entry.error_message}" for label, entry in results.items() if not entry.success]
    if failures:
        report = report.model_copy(update={"flagged_uncertainties": report.flagged_uncertainties + [f"Unretrieved website: {x}" for x in failures]})
    announce("Rendering PDF")
    from utils.pdf_builder import build_pdf
    pdf = build_pdf(report)
    announce("Report ready")
    return pdf, report, results
