"""Branded PDF report builder for Nimble Auto-Analyzer.

Renders an ``AnalysisReport`` into a consulting-style PDF using ReportLab
Platypus. No UI dependencies.

Section helpers (each ends with ``PageBreak`` except ``_limitations_page``):
``_build_styles``, ``_make_footer``, ``_confidence_badge``, ``_cover_page``,
``_executive_summary_page``, ``_keyword_gaps_page``, ``_meta_description_page``,
``_content_strategy_page``, ``_limitations_page``.

``build_pdf`` returns raw ``bytes`` for Streamlit download; use ``save_pdf`` to
write to disk.
"""

from __future__ import annotations

from datetime import datetime
from io import BytesIO
from pathlib import Path
from urllib.parse import urlparse
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import (
    Flowable,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from core.schemas import AnalysisReport, ConfidenceLevel

ACCENT_COLOR = colors.HexColor("#0F766E")
ACCENT_LIGHT = colors.HexColor("#CCFBF1")
TEXT_DARK = colors.HexColor("#0F172A")
TEXT_MUTED = colors.HexColor("#64748B")
BOX_NEUTRAL = colors.HexColor("#F1F5F9")
CONFIDENCE_COLORS = {
    "high": colors.HexColor("#10B981"),
    "medium": colors.HexColor("#F59E0B"),
    "low": colors.HexColor("#EF4444"),
}
COMPANY_NAME = "Nimble Informatics"
TOOL_NAME = "Nimble Auto-Analyzer"
TOOL_VERSION = "v0.4"

_MARGIN = 0.75 * inch
_CONTENT_WIDTH = LETTER[0] - 2 * _MARGIN


def _xml(text: str) -> str:
    return escape(text)


def _domain_from_url(url: str) -> str:
    netloc = urlparse(url).netloc
    return netloc.removeprefix("www.") if netloc else url


def _format_display_date(iso_timestamp: str) -> str:
    try:
        normalized = iso_timestamp.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        return parsed.strftime("%B %d, %Y")
    except ValueError:
        return iso_timestamp


def _competitor_label(which: str) -> str:
    return which.replace("_", " ").title()


def _build_styles() -> dict[str, ParagraphStyle]:
    """Return named paragraph styles for the report."""
    sample = getSampleStyleSheet()

    # --- Cover ---
    cover_title = ParagraphStyle(
        "CoverTitle",
        parent=sample["Normal"],
        fontName="Helvetica-Bold",
        fontSize=32,
        textColor=ACCENT_COLOR,
        alignment=TA_CENTER,
        spaceAfter=12,
        leading=36,
    )
    cover_subtitle = ParagraphStyle(
        "CoverSubtitle",
        parent=sample["Normal"],
        fontName="Helvetica",
        fontSize=14,
        textColor=TEXT_MUTED,
        alignment=TA_CENTER,
        spaceAfter=8,
    )
    cover_meta = ParagraphStyle(
        "CoverMeta",
        parent=sample["Normal"],
        fontName="Helvetica",
        fontSize=10,
        textColor=TEXT_MUTED,
        alignment=TA_CENTER,
        spaceAfter=6,
    )

    # --- Sections ---
    section_h1 = ParagraphStyle(
        "SectionH1",
        parent=sample["Normal"],
        fontName="Helvetica-Bold",
        fontSize=20,
        textColor=ACCENT_COLOR,
        spaceAfter=12,
        leading=24,
    )
    section_h2 = ParagraphStyle(
        "SectionH2",
        parent=sample["Normal"],
        fontName="Helvetica-Bold",
        fontSize=14,
        textColor=TEXT_DARK,
        spaceBefore=14,
        spaceAfter=8,
        leading=18,
    )

    # --- Body copy ---
    body = ParagraphStyle(
        "Body",
        parent=sample["Normal"],
        fontName="Helvetica",
        fontSize=10,
        textColor=TEXT_DARK,
        leading=14,
        spaceAfter=6,
        alignment=TA_JUSTIFY,
    )
    quote = ParagraphStyle(
        "Quote",
        parent=sample["Normal"],
        fontName="Helvetica-Oblique",
        fontSize=10,
        textColor=TEXT_MUTED,
        leftIndent=20,
        rightIndent=20,
        leading=13,
        spaceAfter=8,
    )
    caption = ParagraphStyle(
        "Caption",
        parent=sample["Normal"],
        fontName="Helvetica",
        fontSize=8,
        textColor=TEXT_MUTED,
        spaceAfter=4,
    )
    footer_text = ParagraphStyle(
        "FooterText",
        parent=sample["Normal"],
        fontName="Helvetica",
        fontSize=8,
        textColor=TEXT_MUTED,
        alignment=TA_LEFT,
    )
    muted_italic = ParagraphStyle(
        "MutedItalic",
        parent=body,
        fontName="Helvetica-Oblique",
        textColor=TEXT_MUTED,
    )
    keyword_title = ParagraphStyle(
        "KeywordTitle",
        parent=sample["Normal"],
        fontName="Helvetica-Bold",
        fontSize=12,
        textColor=TEXT_DARK,
        spaceBefore=10,
        spaceAfter=4,
    )
    meta_line = ParagraphStyle(
        "MetaLine",
        parent=sample["Normal"],
        fontName="Helvetica",
        fontSize=9,
        textColor=TEXT_MUTED,
        spaceAfter=4,
    )

    return {
        "CoverTitle": cover_title,
        "CoverSubtitle": cover_subtitle,
        "CoverMeta": cover_meta,
        "SectionH1": section_h1,
        "SectionH2": section_h2,
        "Body": body,
        "Quote": quote,
        "Caption": caption,
        "FooterText": footer_text,
        "MutedItalic": muted_italic,
        "KeywordTitle": keyword_title,
        "MetaLine": meta_line,
    }


def _make_footer(canvas: Canvas, doc: SimpleDocTemplate) -> None:
    """Draw static footer via canvas API (not Platypus Paragraph)."""
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(TEXT_MUTED)

    display_date = getattr(doc, "footer_date", "")
    left_text = f"Generated by {TOOL_NAME} · {display_date} · Confidential"
    canvas.drawString(_MARGIN, 0.45 * inch, left_text)
    canvas.drawRightString(LETTER[0] - _MARGIN, 0.45 * inch, str(doc.page))
    canvas.restoreState()


def _confidence_badge(level: ConfidenceLevel | str) -> Table:
    """Return an embeddable Table badge (never plain text)."""
    level_key = str(level).lower()
    badge_color = CONFIDENCE_COLORS.get(level_key, TEXT_MUTED)
    badge = Table(
        [[level_key.upper()]],
        colWidths=[0.75 * inch],
        rowHeights=[0.22 * inch],
    )
    badge.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), badge_color),
                ("TEXTCOLOR", (0, 0), (-1, -1), colors.white),
                ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("BOX", (0, 0), (-1, -1), 0.5, badge_color),
            ]
        )
    )
    return badge


def _text_box(
    text: str,
    styles: dict[str, ParagraphStyle],
    background: colors.Color,
) -> Table:
    """Paragraph inside a padded table cell for boxed content."""
    paragraph = Paragraph(_xml(text), styles["Body"])
    box = Table([[paragraph]], colWidths=[_CONTENT_WIDTH])
    box.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), background),
                ("LEFTPADDING", (0, 0), (-1, -1), 12),
                ("RIGHTPADDING", (0, 0), (-1, -1), 12),
                ("TOPPADDING", (0, 0), (-1, -1), 10),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    return box


def _cover_page(
    report: AnalysisReport, styles: dict[str, ParagraphStyle]
) -> list[Flowable]:
    """Build cover page flowables."""
    display_date = _format_display_date(report.generated_at_iso)
    domain = _domain_from_url(report.client_url)

    elements: list[Flowable] = [
        Spacer(1, 2 * inch),
        Paragraph("SEO Competitor Analysis Report", styles["CoverTitle"]),
        Paragraph(domain, styles["CoverSubtitle"]),
        Spacer(1, 0.35 * inch),
        Paragraph(display_date, styles["CoverMeta"]),
        Spacer(1, 0.25 * inch),
        Paragraph(f"Prepared by {COMPANY_NAME}", styles["CoverMeta"]),
        Spacer(1, 1.5 * inch),
        Paragraph(
            f"Internal Use · Confidential · {TOOL_NAME} {TOOL_VERSION}",
            styles["CoverMeta"],
        ),
        PageBreak(),  # end cover
    ]
    return elements


def _executive_summary_page(
    report: AnalysisReport, styles: dict[str, ParagraphStyle]
) -> list[Flowable]:
    """Build executive summary page flowables."""
    gap_count = len(report.keyword_gaps)
    insight_count = len(report.content_strategy_insights)
    limitation_count = len(report.flagged_uncertainties)

    elements: list[Flowable] = [
        Paragraph("Executive Summary", styles["SectionH1"]),
        Paragraph(_xml(report.executive_summary), styles["Body"]),
        Spacer(1, 0.2 * inch),
        Paragraph(
            (
                f"{gap_count} keyword opportunities identified · "
                f"{insight_count} content strategy insights · "
                f"{limitation_count} limitations flagged"
            ),
            styles["Caption"],
        ),
        PageBreak(),  # end executive summary
    ]
    return elements


def _keyword_gaps_page(
    report: AnalysisReport, styles: dict[str, ParagraphStyle]
) -> list[Flowable]:
    """Build keyword gap analysis page flowables."""
    elements: list[Flowable] = [
        Paragraph("Keyword Gap Analysis", styles["SectionH1"]),
        Paragraph(
            _xml(
                "Keywords prominently featured by competitors but missing from the "
                "client's content. Each finding is grounded in a verbatim quote from "
                "the source."
            ),
            styles["Body"],
        ),
        Spacer(1, 0.15 * inch),
    ]

    if not report.keyword_gaps:
        elements.append(
            Paragraph("No keyword gaps identified.", styles["MutedItalic"])
        )
    else:
        for gap in report.keyword_gaps:
            meta = Paragraph(
                f"Source: {_xml(_competitor_label(gap.which_competitor))}",
                styles["MetaLine"],
            )
            header_row = Table(
                [[meta, _confidence_badge(gap.confidence)]],
                colWidths=[_CONTENT_WIDTH - 0.85 * inch, 0.85 * inch],
            )
            header_row.setStyle(
                TableStyle(
                    [
                        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                        ("LEFTPADDING", (0, 0), (-1, -1), 0),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                        ("TOPPADDING", (0, 0), (-1, -1), 0),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ]
                )
            )

            block: list[Flowable] = [
                Paragraph(_xml(gap.keyword), styles["KeywordTitle"]),
                header_row,
                Paragraph(f'"{_xml(gap.source_quote)}"', styles["Quote"]),
                Paragraph(_xml(gap.opportunity_rationale), styles["Body"]),
                Spacer(1, 0.12 * inch),
            ]
            elements.append(KeepTogether(block))

    elements.append(PageBreak())  # end keyword gaps
    return elements


def _meta_description_page(
    report: AnalysisReport, styles: dict[str, ParagraphStyle]
) -> list[Flowable]:
    """Build meta description optimization page flowables."""
    meta = report.meta_description_suggestion
    current_text = meta.current_meta or "(none present)"
    keywords_line = ", ".join(meta.keywords_targeted) if meta.keywords_targeted else "—"

    elements: list[Flowable] = [
        Paragraph("Meta Description Optimization", styles["SectionH1"]),
        Paragraph("Current Meta Description:", styles["SectionH2"]),
        _text_box(current_text, styles, BOX_NEUTRAL),
        Spacer(1, 0.15 * inch),
        Paragraph("Suggested Meta Description:", styles["SectionH2"]),
        _text_box(meta.suggested_meta, styles, ACCENT_LIGHT),
        Paragraph(
            f"Character count: {meta.character_count} (target: 150-160)",
            styles["Caption"],
        ),
        Spacer(1, 0.1 * inch),
        Paragraph("Why this works:", styles["SectionH2"]),
        Paragraph(_xml(meta.reasoning), styles["Body"]),
        Spacer(1, 0.08 * inch),
        Paragraph(f"Keywords targeted: {_xml(keywords_line)}", styles["Body"]),
        PageBreak(),  # end meta description
    ]
    return elements


def _content_strategy_page(
    report: AnalysisReport, styles: dict[str, ParagraphStyle]
) -> list[Flowable]:
    """Build content strategy insights page flowables."""
    elements: list[Flowable] = [
        Paragraph("Content Strategy Insights", styles["SectionH1"]),
    ]

    if not report.content_strategy_insights:
        elements.append(
            Paragraph("No content strategy insights identified.", styles["MutedItalic"])
        )
    else:
        for insight in report.content_strategy_insights:
            block: list[Flowable] = [
                Paragraph(f"<b>{_xml(insight.insight)}</b>", styles["Body"]),
            ]
            if insight.source_quote:
                block.append(
                    Paragraph(f'"{_xml(insight.source_quote)}"', styles["Quote"])
                )
            block.extend(
                [
                    Paragraph(
                        f"Recommended action: {_xml(insight.recommended_action)}",
                        styles["Body"],
                    ),
                    _confidence_badge(insight.confidence),
                    Spacer(1, 0.12 * inch),
                ]
            )
            elements.append(KeepTogether(block))

    elements.append(PageBreak())  # end content strategy
    return elements


def _limitations_page(
    report: AnalysisReport, styles: dict[str, ParagraphStyle]
) -> list[Flowable]:
    """Build limitations and methodology page flowables."""
    display_date = _format_display_date(report.generated_at_iso)
    elements: list[Flowable] = [
        Paragraph("Limitations &amp; Methodology", styles["SectionH1"]),
    ]

    if report.flagged_uncertainties:
        elements.append(
            Paragraph(
                "Limitations flagged during analysis:", styles["SectionH2"]
            )
        )
        for item in report.flagged_uncertainties:
            elements.append(Paragraph(f"• {_xml(item)}", styles["Body"]))

    elements.append(Spacer(1, 0.12 * inch))
    elements.append(Paragraph("Methodology", styles["SectionH2"]))
    elements.append(
        Paragraph(
            _xml(
                f"This analysis was generated using {report.model_used} with prompt "
                f"version {report.prompt_version} on {display_date}. The analysis is "
                "based solely on the publicly available content of the homepages of "
                "the three URLs listed below. No third-party data sources or "
                "proprietary databases were used."
            ),
            styles["Body"],
        )
    )
    elements.append(Spacer(1, 0.1 * inch))
    elements.append(Paragraph(f"• {_xml(report.client_url)}", styles["Body"]))
    for url in report.competitor_urls:
        elements.append(Paragraph(f"• {_xml(url)}", styles["Body"]))

    # last section — no PageBreak
    return elements


def build_pdf(report: AnalysisReport) -> bytes:
    """Render an analysis report to PDF bytes.

    Args:
        report: Validated analysis output from the LLM pipeline.

    Returns:
        Raw PDF file contents.
    """
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=LETTER,
        leftMargin=_MARGIN,
        rightMargin=_MARGIN,
        topMargin=_MARGIN,
        bottomMargin=_MARGIN,
        title="SEO Analysis Report",
        author=COMPANY_NAME,
    )
    doc.footer_date = _format_display_date(report.generated_at_iso)

    styles = _build_styles()
    story: list[Flowable] = []
    story.extend(_cover_page(report, styles))
    story.extend(_executive_summary_page(report, styles))
    story.extend(_keyword_gaps_page(report, styles))
    story.extend(_meta_description_page(report, styles))
    story.extend(_content_strategy_page(report, styles))
    story.extend(_limitations_page(report, styles))

    doc.build(story, onFirstPage=_make_footer, onLaterPages=_make_footer)
    return buffer.getvalue()


def save_pdf(report: AnalysisReport, path: Path) -> None:
    """Write a PDF report to disk.

    Args:
        report: Validated analysis report.
        path: Destination file path.

    Side effects:
        Creates or overwrites ``path`` with PDF bytes.
    """
    path.write_bytes(build_pdf(report))
