"""Shared reference-section detection helpers."""

from __future__ import annotations

import re

from table1_parser.text_cleaning import clean_text


REFERENCE_HEADING_LINE_PATTERN = re.compile(
    r"^(?:references?|bibliography|works cited|literature cited)\s*[:.]?$",
    re.IGNORECASE,
)
INLINE_REFERENCE_START_PATTERN = re.compile(
    r"^(?P<heading>references?|bibliography|works cited|literature cited)\s+"
    r"(?P<body>(?:\[\s*)?\d{1,3}(?:\s*\])?[.)]?\s+.*)$",
    re.IGNORECASE,
)
MARKDOWN_REFERENCE_DECORATION_PATTERN = re.compile(r"[*_`]+")
MARKDOWN_REFERENCE_LINE_PREFIX_PATTERN = re.compile(r"^\s{0,3}(?:#{1,6}\s+|[-+*]\s+)")


def text_has_reference_section_start(text: str) -> bool:
    """Return whether text contains a reference-list heading or inline start."""
    for raw_line in text.splitlines():
        line = reference_start_text(raw_line)
        if not line:
            continue
        if REFERENCE_HEADING_LINE_PATTERN.match(line) or INLINE_REFERENCE_START_PATTERN.match(line):
            return True
    line = reference_start_text(text)
    return bool(INLINE_REFERENCE_START_PATTERN.search(line))


def reference_start_text(text: str) -> str:
    """Normalize markdown wrappers before reference-start detection."""
    unwrapped = MARKDOWN_REFERENCE_LINE_PREFIX_PATTERN.sub("", text.strip())
    unwrapped = MARKDOWN_REFERENCE_DECORATION_PATTERN.sub("", unwrapped)
    return clean_text(unwrapped)
