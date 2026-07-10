"""Deterministic value-pattern detection for raw cell strings."""

from __future__ import annotations

import re

from table1_parser.heuristics.models import ValuePatternGuess
from table1_parser.text_cleaning import clean_text


INTEGER_TOKEN = r"(?:\d{1,3}(?:,\d{3})*|\d+)"
DECIMAL_TOKEN = r"(?:\d{1,3}(?:,\d{3})*|\d+)(?:\.\d+)?"
SIGNED_DECIMAL_TOKEN = rf"-?{DECIMAL_TOKEN}"
FOOTNOTE_SUFFIX_TOKEN = r"(?:\s*(?:[*†‡§¶#{}|]+|[a-z]))*"
INTEGER_COUNT_PCT_PATTERN = re.compile(rf"^{INTEGER_TOKEN}\s*\(\s*{DECIMAL_TOKEN}%?\s*\)$")
DECIMAL_COUNT_PCT_PATTERN = re.compile(rf"^{DECIMAL_TOKEN}\s*\(\s*{DECIMAL_TOKEN}%\s*\)$")
MEAN_SD_PATTERN = re.compile(
    rf"^{SIGNED_DECIMAL_TOKEN}(?:\s*\(\s*{SIGNED_DECIMAL_TOKEN}\s*\)|\s*±\s*{SIGNED_DECIMAL_TOKEN}|\s+6\s+{SIGNED_DECIMAL_TOKEN}){FOOTNOTE_SUFFIX_TOKEN}$"
)
MEDIAN_IQR_PATTERN = re.compile(
    rf"^{SIGNED_DECIMAL_TOKEN}\s*\(\s*{SIGNED_DECIMAL_TOKEN}\s*,\s*{SIGNED_DECIMAL_TOKEN}\s*\)$"
)
P_VALUE_PATTERN = re.compile(rf"^(?:[<>]=?\s*)?(?:0?\.\d+|\.\d+|1\.0+){FOOTNOTE_SUFFIX_TOKEN}$", re.IGNORECASE)
N_ONLY_PATTERN = re.compile(rf"^{INTEGER_TOKEN}$")


def detect_value_pattern(raw_value: str) -> ValuePatternGuess:
    """Classify a raw value string into a conservative pattern family."""
    value = clean_text(raw_value)
    lowered = clean_text(raw_value).lower().strip()
    if lowered.startswith("p"):
        remainder = lowered[1:].lstrip()
        lowered = remainder[1:].lstrip() if remainder.startswith(("=", ":")) else remainder

    if MEDIAN_IQR_PATTERN.fullmatch(lowered):
        return ValuePatternGuess(raw_value=raw_value, pattern="median_iqr", confidence=0.95)
    if INTEGER_COUNT_PCT_PATTERN.fullmatch(lowered) or DECIMAL_COUNT_PCT_PATTERN.fullmatch(lowered):
        return ValuePatternGuess(raw_value=raw_value, pattern="count_pct", confidence=0.95)
    if value.startswith("<") or value.startswith(">"):
        if P_VALUE_PATTERN.fullmatch(lowered):
            return ValuePatternGuess(raw_value=raw_value, pattern="p_value", confidence=0.98)
    if P_VALUE_PATTERN.fullmatch(lowered):
        return ValuePatternGuess(raw_value=raw_value, pattern="p_value", confidence=0.85)
    if MEAN_SD_PATTERN.fullmatch(value):
        return ValuePatternGuess(raw_value=raw_value, pattern="mean_sd", confidence=0.9)
    if N_ONLY_PATTERN.fullmatch(value):
        return ValuePatternGuess(raw_value=raw_value, pattern="n_only", confidence=0.9)
    return ValuePatternGuess(raw_value=raw_value, pattern="unknown", confidence=0.4)
