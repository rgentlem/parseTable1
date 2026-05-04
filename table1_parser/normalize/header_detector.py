"""Heuristics for distinguishing header rows from body rows."""

from __future__ import annotations

import re


NUMERIC_PATTERN = re.compile(r"\d")
HEADER_KEYWORD_PATTERN = re.compile(r"\b(overall|p[\s-]?value|total|n|%)\b", re.IGNORECASE)
COUNT_ROW_LABEL_PATTERN = re.compile(r"^(n|N|no\.?|number)$")
RANGE_LABEL_PATTERN = re.compile(r"^(?:[<>]=?\s*)?-?\d+(?:\.\d+)?(?:\s*-\s*-?\d+(?:\.\d+)?)?$")
COLUMN_THRESHOLD_HEADER_PATTERN = re.compile(
    r"^(?:(?:[<>]=?|[≤≥‡])\s*)?\d+(?:\.\d+)?\s*(?:mm|cm|m|kg|g|mg|ug|µg|years?|yr|yrs|%)$",
    re.IGNORECASE,
)
STATISTIC_HEADER_PATTERN = re.compile(
    r"^(?:%|se|sd|ci|iqr|mean(?:\s+[A-Za-z]+)?(?:,\s*[A-Za-z]+)?)$",
    re.IGNORECASE,
)
TOP_RULE_GAP = 12.0
BOUNDARY_RULE_TOLERANCE = 3.0
MAX_HEADER_ROWS = 3


def _numeric_density(row: list[str]) -> float:
    """Compute the fraction of populated cells containing numeric content."""
    populated = [cell for cell in row if cell]
    if not populated:
        return 0.0
    numeric = [cell for cell in populated if NUMERIC_PATTERN.search(cell)]
    return len(numeric) / len(populated)


def header_score(row: list[str], row_idx: int) -> float:
    """Score a row for header-likeness using simple deterministic signals."""
    joined = " ".join(cell for cell in row if cell)
    first_cell = next((cell for cell in row if cell), "")
    populated = [cell for cell in row if cell]
    score = 0.0
    if row_idx < 2:
        score += 0.25
    if HEADER_KEYWORD_PATTERN.search(joined):
        score += 0.4
    if (
        row_idx < 2
        and len(populated) >= 2
        and all(any(char.isalpha() for char in cell) for cell in populated)
        and max(len(cell.strip()) for cell in populated) <= 4
    ):
        score += 0.35
    text_density = (
        len([cell for cell in populated if any(char.isalpha() for char in cell)]) / len(populated)
        if populated
        else 0.0
    )
    threshold_header_cells = sum(bool(COLUMN_THRESHOLD_HEADER_PATTERN.fullmatch(cell.strip())) for cell in populated)
    statistic_header_cells = sum(bool(STATISTIC_HEADER_PATTERN.fullmatch(cell.strip())) for cell in populated)
    if text_density >= 0.75:
        score += 0.2
    if _numeric_density(row) <= 0.25:
        score += 0.2
    if (
        row_idx < MAX_HEADER_ROWS
        and populated
        and threshold_header_cells + statistic_header_cells >= max(2, len(populated) // 2)
    ):
        score += 0.35
    if row_idx > 0 and COUNT_ROW_LABEL_PATTERN.fullmatch(first_cell.strip()) and _numeric_density(row) >= 0.75:
        score -= 0.45
    return min(score, 1.0)


def detect_header_rows_with_metadata(
    rows: list[list[str]],
    *,
    row_bounds: list[tuple[float, float]] | None = None,
    horizontal_rules: list[float] | None = None,
) -> tuple[list[int], list[int], dict[str, object]]:
    """Identify likely header rows and expose how the decision was made."""
    content_headers: list[int] = []
    scan_limit = min(len(rows), MAX_HEADER_ROWS)
    for row_idx in range(scan_limit):
        score = header_score(rows[row_idx], row_idx)
        if score >= 0.55:
            content_headers.append(row_idx)
        elif row_idx == 0 and HEADER_KEYWORD_PATTERN.search(" ".join(rows[row_idx])):
            content_headers.append(row_idx)
        elif content_headers:
            break

    if not rows or not row_bounds or not horizontal_rules or len(row_bounds) != len(rows):
        rule_based_headers, rule_strength = [], None
    else:
        sorted_rules = sorted(horizontal_rules)
        first_top = row_bounds[0][0]
        top_rule_candidates = [
            rule_y
            for rule_y in sorted_rules
            if -BOUNDARY_RULE_TOLERANCE <= first_top - rule_y <= TOP_RULE_GAP
        ]
        top_rule = max(top_rule_candidates) if top_rule_candidates else None
        if top_rule is None:
            rule_based_headers, rule_strength = [], None
        else:
            rule_based_headers, rule_strength = [], None
            first_boundary_candidates = [
                rule_y
                for rule_y in sorted_rules
                if rule_y > top_rule + BOUNDARY_RULE_TOLERANCE
                and rule_y - first_top <= 60.0
            ]
            if first_boundary_candidates:
                first_boundary_rule = first_boundary_candidates[0]
                boundary_header_count = sum(
                    row_bottom <= first_boundary_rule + BOUNDARY_RULE_TOLERANCE
                    for _, row_bottom in row_bounds[:MAX_HEADER_ROWS]
                )
                if boundary_header_count:
                    rule_based_headers = list(range(boundary_header_count))
                    rule_strength = "strong" if boundary_header_count <= 2 else "moderate"
            max_header_idx = min(len(rows) - 2, MAX_HEADER_ROWS - 1)
            for row_idx in range(max_header_idx + 1):
                if rule_based_headers:
                    break
                current_bottom = row_bounds[row_idx][1]
                next_top = row_bounds[row_idx + 1][0]
                boundary_candidates = [
                    rule_y
                    for rule_y in sorted_rules
                    if current_bottom - BOUNDARY_RULE_TOLERANCE <= rule_y <= next_top + BOUNDARY_RULE_TOLERANCE
                ]
                if boundary_candidates:
                    gap_midpoint = (current_bottom + next_top) / 2.0
                    boundary_rule = min(boundary_candidates, key=lambda rule_y: abs(rule_y - gap_midpoint))
                else:
                    boundary_rule = None
                if boundary_rule is None:
                    continue
                header_count = row_idx + 1
                if header_count <= 2:
                    rule_based_headers, rule_strength = list(range(header_count)), "strong"
                    break
                candidate_rows = rows[:header_count]
                average_score = sum(header_score(row, index) for index, row in enumerate(candidate_rows)) / len(candidate_rows)
                if average_score >= 0.5:
                    rule_based_headers, rule_strength = list(range(header_count)), "moderate"
                    break

    if rule_strength == "strong":
        header_rows = rule_based_headers
        source = "horizontal_rules"
    elif rule_strength == "moderate" and (
        not content_headers or len(rule_based_headers) <= len(content_headers)
    ):
        header_rows = rule_based_headers
        source = "horizontal_rules"
    else:
        header_rows = content_headers
        source = "content"

    promoted_header_rows: list[int] = []
    next_row_idx = len(header_rows)
    if header_rows == list(range(len(header_rows))) and next_row_idx < min(len(rows), MAX_HEADER_ROWS):
        next_row = rows[next_row_idx]
        joined = " ".join(cell for cell in next_row if cell)
        populated = [cell for cell in next_row if cell]
        range_like_cells = sum(bool(RANGE_LABEL_PATTERN.fullmatch(cell.strip())) for cell in populated)
        if header_score(next_row, next_row_idx) >= 0.45 and (
            HEADER_KEYWORD_PATTERN.search(joined) or range_like_cells >= 2
        ):
            header_rows = [*header_rows, next_row_idx]
            promoted_header_rows = [next_row_idx]
            source = f"{source}+promotion"

    body_rows = [row_idx for row_idx in range(len(rows)) if row_idx not in header_rows]
    metadata = {
        "source": source,
        "rule_strength": rule_strength,
        "rule_based_headers": rule_based_headers,
        "content_based_headers": content_headers,
        "promoted_header_rows": promoted_header_rows,
        "rule_content_disagreement": bool(rule_based_headers and rule_based_headers != content_headers),
    }
    return header_rows, body_rows, metadata


def detect_header_rows(
    rows: list[list[str]],
    *,
    row_bounds: list[tuple[float, float]] | None = None,
    horizontal_rules: list[float] | None = None,
) -> tuple[list[int], list[int]]:
    """Identify likely header rows near the top of the table."""
    return detect_header_rows_with_metadata(
        rows,
        row_bounds=row_bounds,
        horizontal_rules=horizontal_rules,
    )[:2]
