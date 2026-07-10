"""Shared conservative header-role matching helpers."""

from __future__ import annotations

import re
from dataclasses import dataclass

from table1_parser.text_cleaning import clean_text


P_VALUE_HEADER_PATTERN = re.compile(r"^p(?:\s*value|\s+for\s+trend|\s*trend)?$")
HEADER_MARKUP_PATTERN = re.compile(r"[_*`]+")
HEADER_HYPHEN_PATTERN = re.compile(r"\s*-\s*")
HEADER_NAMED_P_FOOTNOTE_SUFFIX_PATTERN = re.compile(
    r"^(?P<base>p(?:\s*value|\s+for\s+trend|\s*trend))\s*(?:\d+|[a-z]|[*†‡§¶#{}|]+)$"
)
HEADER_BARE_P_FOOTNOTE_SUFFIX_PATTERN = re.compile(r"^(?P<base>p)\s*(?:\d+|[*†‡§¶#{}|]+)$")


@dataclass(frozen=True, slots=True)
class PValueHeaderMatch:
    """A conservative p-value-like header match."""

    subtype: str
    confidence: float


def canonicalize_header_match_text(value: str) -> str:
    """Return a parser-facing header string for role matching only."""
    cleaned = HEADER_MARKUP_PATTERN.sub("", clean_text(value).lower())
    cleaned = HEADER_HYPHEN_PATTERN.sub(" ", cleaned)
    cleaned = clean_text(cleaned)
    named_p_match = HEADER_NAMED_P_FOOTNOTE_SUFFIX_PATTERN.fullmatch(cleaned)
    if named_p_match is not None:
        return clean_text(named_p_match.group("base"))
    bare_p_match = HEADER_BARE_P_FOOTNOTE_SUFFIX_PATTERN.fullmatch(cleaned)
    if bare_p_match is not None:
        return clean_text(bare_p_match.group("base"))
    return cleaned


def detect_p_value_header(label: str, col_idx: int, n_cols: int) -> PValueHeaderMatch | None:
    """Detect p-value or p-trend headers with light position-based confidence."""
    canonical = canonicalize_header_match_text(label)
    if P_VALUE_HEADER_PATTERN.fullmatch(canonical) is None:
        return None

    is_rightmost = col_idx == n_cols - 1
    is_almost_rightmost = col_idx >= max(0, n_cols - 2)
    is_bare_p = canonical == "p"
    if is_bare_p and not is_almost_rightmost:
        return None

    if is_rightmost:
        confidence = 0.98
    elif is_almost_rightmost:
        confidence = 0.94
    else:
        confidence = 0.85
    subtype = "p_trend" if "trend" in canonical else "p_value"
    return PValueHeaderMatch(subtype=subtype, confidence=confidence)
