"""One-shot script: reads scraped_data.json, calls Gemini, saves cached_analysis.json.

Run this once when you want to refresh the cached analysis (after scraping changes,
prompt iterations, or model upgrades). The demo always loads from the cached file
to ensure reliability and zero latency during live presentations.
"""
from __future__ import annotations

import json
from pathlib import Path

from utils.llm_client import generate_seo_report

SCRAPED_DATA_PATH = Path("scraped_data.json")
CACHED_ANALYSIS_PATH = Path("cached_analysis.json")


def main() -> None:
    if not SCRAPED_DATA_PATH.exists():
        raise FileNotFoundError(
            f"{SCRAPED_DATA_PATH} not found. Run `python test_scrape.py` first."
        )

    print(f"Loading scraped data from {SCRAPED_DATA_PATH}...")
    with SCRAPED_DATA_PATH.open(encoding="utf-8") as f:
        scraped_data = json.load(f)

    print("Calling Gemini for analysis (this may take 15-30 seconds)...")
    report = generate_seo_report(scraped_data)

    print(f"\nReport generated. Saving to {CACHED_ANALYSIS_PATH}...")
    with CACHED_ANALYSIS_PATH.open("w", encoding="utf-8") as f:
        json.dump(report.model_dump(), f, indent=2, ensure_ascii=False)

    print("\n✅ Done.")
    print(f"   Keyword gaps: {len(report.keyword_gaps)}")
    print(f"   Content insights: {len(report.content_strategy_insights)}")
    print(f"   Low-confidence claims: {report.low_confidence_count()}")
    print(f"   Flagged uncertainties: {len(report.flagged_uncertainties)}")
    print(f"   Model: {report.model_used}, Prompt: {report.prompt_version}")


if __name__ == "__main__":
    main()