"""URL validation schemas for Nimble Auto-Analyzer.

Defines the AnalysisRequest model and validate_request() helper used
before scraping or report generation.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, ValidationError

_FIELD_LABELS: dict[str, str] = {
    "client_url": "Client Website URL",
    "competitor_1_url": "Competitor 1 URL",
    "competitor_2_url": "Competitor 2 URL",
}

_URL_ERROR_TYPES: frozenset[str] = frozenset(
    {
        "url_parsing",
        "url_scheme",
        "url_syntax_violation",
        "url_type",
        "url_too_long",
    }
)


class AnalysisRequest(BaseModel):
    """Validated trio of HTTP(S) URLs for a competitor analysis run."""

    model_config = ConfigDict(str_strip_whitespace=True)

    client_url: HttpUrl
    competitor_1_url: HttpUrl
    competitor_2_url: HttpUrl


class ScrapeResult(BaseModel):
    """Universal contract returned by every scraper.

    Success or failure, the shape is the same. The ``success`` field tells the
    caller which path to take. On failure, body fields are None and
    ``error_message`` is populated.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    url: str
    success: bool
    status_code: int | None = None
    title: str | None = None
    meta_description: str | None = None
    headings: dict[str, list[str]] = Field(default_factory=dict)
    body_text: str | None = None
    word_count: int | None = None
    internal_links: list[str] = Field(default_factory=list)
    error_message: str | None = None
    scraper_used: str = "bs4"

    def is_usable_for_analysis(self) -> bool:
        return (
            self.success
            and self.body_text is not None
            and len(self.body_text) >= 100
        )


ConfidenceLevel = Literal["high", "medium", "low"]
CompetitorLabel = Literal["competitor_1", "competitor_2"]


class KeywordGap(BaseModel):
    """A keyword or phrase competitors use that the client does not."""

    model_config = ConfigDict(str_strip_whitespace=True)

    keyword: str
    which_competitor: CompetitorLabel
    source_quote: str
    opportunity_rationale: str
    confidence: ConfidenceLevel


class MetaDescriptionSuggestion(BaseModel):
    """Proposed meta description rewrite for the client site."""

    model_config = ConfigDict(str_strip_whitespace=True)

    current_meta: str | None
    suggested_meta: str
    character_count: int
    reasoning: str
    keywords_targeted: list[str] = Field(default_factory=list)


class ContentStrategyInsight(BaseModel):
    """Observation about a content strategy gap or opportunity."""

    model_config = ConfigDict(str_strip_whitespace=True)

    insight: str
    source_quote: str | None
    confidence: ConfidenceLevel
    recommended_action: str


class AnalysisReport(BaseModel):
    """Structured SEO competitor analysis output from the AI pipeline."""

    model_config = ConfigDict(str_strip_whitespace=True)

    client_url: str
    competitor_urls: list[str]
    executive_summary: str
    keyword_gaps: list[KeywordGap] = Field(default_factory=list)
    meta_description_suggestion: MetaDescriptionSuggestion
    content_strategy_insights: list[ContentStrategyInsight] = Field(
        default_factory=list
    )
    flagged_uncertainties: list[str] = Field(default_factory=list)
    generated_at_iso: str
    model_used: str
    prompt_version: str

    def total_claims(self) -> int:
        return (
            len(self.keyword_gaps)
            + len(self.content_strategy_insights)
            + 1
        )

    def low_confidence_count(self) -> int:
        low_gaps = sum(1 for gap in self.keyword_gaps if gap.confidence == "low")
        low_insights = sum(
            1
            for insight in self.content_strategy_insights
            if insight.confidence == "low"
        )
        return low_gaps + low_insights


def _label_for_field(loc: tuple[Any, ...]) -> str:
    for part in loc:
        if isinstance(part, str) and part in _FIELD_LABELS:
            return _FIELD_LABELS[part]
    return "One of the URLs"


def _reason_for_error(error: dict[str, Any]) -> str:
    error_type = error.get("type", "")
    if error_type == "missing":
        return "is required."
    if error_type in _URL_ERROR_TYPES:
        return (
            "doesn't look valid — please check it includes https:// "
            "and a proper domain."
        )
    msg = str(error.get("msg", "")).strip()
    if msg:
        return f"is invalid: {msg}"
    return "is invalid."


def _format_validation_error(error: dict[str, Any]) -> str:
    label = _label_for_field(tuple(error.get("loc", ())))
    return f"{label} {_reason_for_error(error)}"


def validate_request(
    client_url: str,
    competitor_1_url: str,
    competitor_2_url: str,
) -> tuple[AnalysisRequest | None, list[str]]:
    """Validate three URL strings and return a request model or errors.

    Args:
        client_url: Raw client website URL from the user.
        competitor_1_url: Raw first competitor URL.
        competitor_2_url: Raw second competitor URL.

    Returns:
        On success, ``(AnalysisRequest, [])``. On failure,
        ``(None, list_of_human_friendly_error_messages)``.

    Side effects:
        None. Does not perform network I/O.
    """
    try:
        request = AnalysisRequest(
            client_url=client_url,
            competitor_1_url=competitor_1_url,
            competitor_2_url=competitor_2_url,
        )
        return request, []
    except ValidationError as exc:
        messages = [_format_validation_error(err) for err in exc.errors()]
        return None, messages
