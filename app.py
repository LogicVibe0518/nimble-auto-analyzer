"""Streamlit UI for Nimble Auto-Analyzer.

Thin presentation layer: collects URL inputs, calls the validation layer,
runs the pipeline orchestrator, and displays results. All business logic
lives in core/ and utils/.
"""

from __future__ import annotations

from datetime import datetime

import streamlit as st

from core.schemas import validate_request
from utils.pipeline import run_pipeline


# ----------------------------- Page Configuration -----------------------------
st.set_page_config(
    page_title="Nimble Auto-Analyzer",
    layout="centered",
    page_icon="📊",
)


# ----------------------------- Session State Init -----------------------------
for key in ("client_url", "competitor_1_url", "competitor_2_url"):
    if key not in st.session_state:
        st.session_state[key] = ""


# ----------------------------- Header -----------------------------
st.title("Nimble Auto-Analyzer")
st.caption("Internal SEO Competitor Analysis · Built for Nimble Informatics")
st.write(
    "Paste a client URL and two competitor URLs to generate a detailed, "
    "branded SEO analysis report in under a minute."
)

st.divider()


# ----------------------------- Input Form -----------------------------
with st.form("analysis_form"):
    client_url = st.text_input(
        "Client Website URL",
        key="client_url",
        placeholder="https://example.com",
    )
    competitor_1_url = st.text_input(
        "Competitor 1 URL",
        key="competitor_1_url",
        placeholder="https://example.com",
    )
    competitor_2_url = st.text_input(
        "Competitor 2 URL",
        key="competitor_2_url",
        placeholder="https://example.com",
    )
    submitted = st.form_submit_button("Generate Report", type="primary")


# ----------------------------- Submit Handler -----------------------------
if submitted:
    request, errors = validate_request(
        client_url=client_url,
        competitor_1_url=competitor_1_url,
        competitor_2_url=competitor_2_url,
    )

    if errors:
        st.error("Please fix the following before generating the report:")
        for error_message in errors:
            st.write(f"• {error_message}")
    else:
        st.session_state["validated_client"] = str(request.client_url)
        st.session_state["validated_comp1"] = str(request.competitor_1_url)
        st.session_state["validated_comp2"] = str(request.competitor_2_url)

        with st.status(
            "Generating SEO analysis report...", expanded=True
        ) as status:
            def update_progress(message: str) -> None:
                status.update(label=message)
                st.write(f"• {message}")

            try:
                pdf_bytes, report, scrape_results = run_pipeline(
                    request, update_progress
                )
                status.update(
                    label="✓ Report ready", state="complete", expanded=False
                )
                st.session_state["pdf_bytes"] = pdf_bytes
                st.session_state["report"] = report
                st.session_state["scrape_results"] = scrape_results
            except Exception as e:
                status.update(label="Pipeline failed", state="error")
                st.error(
                    f"Something went wrong: {e}. Please try again or "
                    "contact engineering."
                )


# ----------------------------- Results Display -----------------------------
if "pdf_bytes" in st.session_state and "report" in st.session_state:
    pdf_bytes = st.session_state["pdf_bytes"]
    report = st.session_state["report"]
    scrape_results = st.session_state.get("scrape_results", {})

    st.divider()

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Keyword Opportunities", len(report.keyword_gaps))
    with col2:
        st.metric("Content Insights", len(report.content_strategy_insights))
    with col3:
        st.metric("Limitations Flagged", len(report.flagged_uncertainties))

    st.subheader("Scrape Status")
    for label, result in scrape_results.items():
        if result.success:
            st.success(
                f"✓ {label}: {result.word_count} words extracted from "
                f"{result.url}"
            )
        else:
            st.warning(f"⚠ {label}: {result.error_message}")

    filename = (
        f"nimble_seo_report_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf"
    )
    st.download_button(
        label="📥 Download Full PDF Report",
        data=pdf_bytes,
        file_name=filename,
        mime="application/pdf",
        type="primary",
    )

    with st.expander("Preview: Executive Summary"):
        st.write(report.executive_summary)