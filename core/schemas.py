"""URL validation schemas for Nimble Auto-Analyzer.

Defines the AnalysisRequest model and validate_request() helper used
before scraping or report generation.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, HttpUrl, ValidationError

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
