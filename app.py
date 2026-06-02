"""Nimble Auto-Analyzer — Streamlit UI entry point.

Renders the SEO competitor analysis form and placeholder feedback
after the user requests a report. Analysis pipeline logic lives elsewhere.
"""

from __future__ import annotations

import streamlit as st

# --- Page config ---

st.set_page_config(
    page_title="Nimble Auto-Analyzer",
    page_icon="📊",
    layout="centered",
)

# --- Session state ---

_INPUT_KEYS: tuple[str, str, str] = ("client_url", "comp1_url", "comp2_url")
_SUBMITTED_KEYS: tuple[str, str, str] = (
    "submitted_client",
    "submitted_comp1",
    "submitted_comp2",
)

for key in _INPUT_KEYS:
    if key not in st.session_state:
        st.session_state[key] = ""

# --- Header ---

st.title("Nimble Auto-Analyzer")
st.caption("Internal SEO Competitor Analysis · Built for Nimble Informatics")
st.write(
    "Paste a client URL and two competitor URLs to generate a detailed SEO analysis report."
)

st.divider()

# --- URL input form ---

with st.form("report_form"):
    st.text_input(
        "Client Website URL",
        placeholder="https://example.com",
        key="client_url",
    )
    st.text_input(
        "Competitor 1 URL",
        placeholder="https://example.com",
        key="comp1_url",
    )
    st.text_input(
        "Competitor 2 URL",
        placeholder="https://example.com",
        key="comp2_url",
    )
    submitted = st.form_submit_button("Generate Report", type="primary")

if submitted:
    st.session_state.submitted_client = st.session_state.client_url
    st.session_state.submitted_comp1 = st.session_state.comp1_url
    st.session_state.submitted_comp2 = st.session_state.comp2_url

# --- Placeholder result (shown only after first submit) ---

if all(k in st.session_state for k in _SUBMITTED_KEYS):
    st.success(
        "Report generation requested for:\n\n"
        f"- **Client:** {st.session_state.submitted_client}\n"
        f"- **Competitor 1:** {st.session_state.submitted_comp1}\n"
        f"- **Competitor 2:** {st.session_state.submitted_comp2}"
    )
