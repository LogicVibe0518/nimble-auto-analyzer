"""One-shot script: reads cached_analysis.json, builds PDF, saves sample_report.pdf."""
from __future__ import annotations

import json
from pathlib import Path

from core.schemas import AnalysisReport
from utils.pdf_builder import save_pdf

CACHED_PATH = Path("cached_analysis.json")
OUTPUT_PATH = Path("sample_report.pdf")


def main() -> None:
    if not CACHED_PATH.exists():
        raise FileNotFoundError(
            f"{CACHED_PATH} not found. Run `python generate_cache.py` first."
        )

    print(f"Loading {CACHED_PATH}...")
    with CACHED_PATH.open(encoding="utf-8") as f:
        data = json.load(f)
    report = AnalysisReport.model_validate(data)

    print("Building PDF...")
    save_pdf(report, OUTPUT_PATH)

    print(f"✅ Saved to {OUTPUT_PATH.resolve()}")
    print("   Open it with your PDF viewer or double-click in File Explorer.")


if __name__ == "__main__":
    main()