"""Heuristics for distinguishing header rows from body rows."""

from __future__ import annotations

import re

SAMPLE_SIZE_HEADER_CELL_PATTERN = re.compile(r"^n\s*=", re.IGNORECASE)
DASH_VALUE_PATTERN = re.compile(r"^[\-–—]+$")
INTERVAL_VALUE_PATTERN = re.compile(r"^\d+(?:\.\d+)?%?\s*\([^)]*\d[^)]*\)$")
YEAR_RANGE_VALUE_PATTERN = re.compile(r"^\d{4}\s*(?:[-–—]|,)\s*\d{4}$")
CONTINUATION_NOTE_PATTERN = re.compile(
    r"\b(?:cont\.?|continued|continues?)\b.*\b(?:previous|next)\s+page\b|"
    r"\b(?:previous|next)\s+page\b.*\b(?:cont\.?|continued|continues?)\b|"
    r"\bfrom\s+(?:the\s+)?previous\s+page\b",
    re.IGNORECASE,
)
BOUNDARY_RULE_TOLERANCE = 3.0
SEPARATOR_MAX_HEADER_ROWS = 8
POST_SEPARATOR_NOTE_MAX_ROWS = 2
POST_SEPARATOR_NOTE_MAX_GAP = 30.0


def _clean_cell(value: str) -> str:
    return " ".join(str(value).replace("−", "-").replace("–", "-").replace("—", "-").split())


def _is_value_like_cell(value: str) -> bool:
    cleaned = _clean_cell(value)
    if not cleaned:
        return False
    if DASH_VALUE_PATTERN.fullmatch(cleaned):
        return True
    if INTERVAL_VALUE_PATTERN.fullmatch(cleaned):
        return True
    if YEAR_RANGE_VALUE_PATTERN.fullmatch(cleaned):
        return True
    digit_count = sum(char.isdigit() for char in cleaned)
    if digit_count == 0:
        return False
    alpha_count = sum(char.isalpha() for char in cleaned)
    if "%" in cleaned or any(char in cleaned for char in "()<>±"):
        return digit_count >= max(1, alpha_count)
    return digit_count >= alpha_count


def _is_value_matrix_row(row: list[str]) -> bool:
    populated = [_clean_cell(cell) for cell in row if _clean_cell(cell)]
    if len(populated) < 2:
        return False
    trailing = [_clean_cell(cell) for cell in row[1:] if _clean_cell(cell)]
    value_like = sum(_is_value_like_cell(cell) for cell in populated)
    trailing_value_like = sum(_is_value_like_cell(cell) for cell in trailing)
    if len(row) <= 3:
        return trailing_value_like >= 1
    return (
        value_like >= max(3, int(len(populated) * 0.55))
        or trailing_value_like >= max(2, int(len(trailing) * 0.55))
    )


def _count_trailing_value_like_cells(row: list[str]) -> tuple[int, int]:
    trailing = [_clean_cell(cell) for cell in row[1:] if _clean_cell(cell)]
    value_like_count = 0
    for cell in trailing:
        compact_cell = cell.replace(" ", "")
        if _is_value_like_cell(cell) and re.fullmatch(r"[A-Za-z]{1,4}\d+[A-Za-z]?", compact_cell) is None:
            value_like_count += 1
    return value_like_count, len(trailing)


def _detect_separator_rule_headers(
    rows: list[list[str]],
    row_bounds: list[tuple[float, float]],
    horizontal_rules: list[float],
) -> dict[str, object] | None:
    """Use an internal horizontal rule as the header/body separator when supported by value rows."""
    if not rows or len(row_bounds) != len(rows):
        return None
    sorted_rules = sorted(horizontal_rules)
    candidates: list[dict[str, object]] = []
    for rule_y in sorted_rules:
        rows_above_rule = [
            row_idx
            for row_idx, (row_top, row_bottom) in enumerate(row_bounds)
            if row_bottom <= rule_y + BOUNDARY_RULE_TOLERANCE
            or (row_top < rule_y < row_bottom and row_bottom - rule_y <= BOUNDARY_RULE_TOLERANCE * 1.25)
        ]
        header_rows = [
            row_idx
            for row_idx in rows_above_rule
            if any(_clean_cell(cell) for cell in rows[row_idx])
        ]
        preamble_rows: list[int] = []
        while len(header_rows) > 1:
            first_row_idx = header_rows[0]
            first_row = rows[first_row_idx]
            first_row_has_left_text = bool(_clean_cell(first_row[0]))
            later_counts = [
                sum(bool(_clean_cell(cell)) for cell in rows[row_idx])
                for row_idx in header_rows[1:]
            ]
            if (
                first_row_has_left_text
                and sum(bool(_clean_cell(cell)) for cell in first_row) <= 2
                and max(later_counts, default=0) >= max(3, len(first_row) // 2)
            ):
                preamble_rows.append(first_row_idx)
                header_rows = header_rows[1:]
                continue
            break
        if not header_rows or len(header_rows) > SEPARATOR_MAX_HEADER_ROWS:
            continue
        if max(header_rows) >= SEPARATOR_MAX_HEADER_ROWS:
            continue
        header_contains_body_values = False
        for row_idx in header_rows:
            if not _is_value_matrix_row(rows[row_idx]):
                continue
            trailing = [_clean_cell(cell) for cell in rows[row_idx][1:] if _clean_cell(cell)]
            sample_size_cells = sum(bool(SAMPLE_SIZE_HEADER_CELL_PATTERN.search(cell)) for cell in trailing)
            if sample_size_cells >= max(2, len(trailing) // 2):
                continue
            alpha_cells = sum(bool(re.search(r"[A-Za-z]", cell)) for cell in trailing)
            if alpha_cells >= max(2, len(trailing) // 2):
                continue
            header_contains_body_values = True
            break
        if header_contains_body_values:
            continue
        below_rows = [
            row_idx
            for row_idx, (row_top, _) in enumerate(row_bounds)
            if row_top >= rule_y - BOUNDARY_RULE_TOLERANCE
        ]
        if not below_rows:
            continue

        note_rows: list[int] = []
        continuation_note_rows: list[int] = []
        for row_idx in below_rows[:POST_SEPARATOR_NOTE_MAX_ROWS]:
            row_top = row_bounds[row_idx][0]
            if row_top - rule_y > POST_SEPARATOR_NOTE_MAX_GAP:
                break
            row_text = " ".join(_clean_cell(cell) for cell in rows[row_idx] if _clean_cell(cell))
            if CONTINUATION_NOTE_PATTERN.search(row_text) is not None:
                note_rows.append(row_idx)
                continuation_note_rows.append(row_idx)
                continue
            if not row_text:
                note_rows.append(row_idx)
                continue
            break

        first_body_row_idx = next(
            (
                row_idx
                for row_idx in below_rows
                if row_idx not in set(note_rows) and any(_clean_cell(cell) for cell in rows[row_idx])
            ),
            None,
        )
        if first_body_row_idx is None:
            continue

        body_support = "first_body_value_matrix"
        first_body_row = rows[first_body_row_idx]
        first_body_has_left_label = bool(_clean_cell(first_body_row[0]))
        first_body_trailing = [_clean_cell(cell) for cell in first_body_row[1:] if _clean_cell(cell)]
        if _is_value_matrix_row(first_body_row):
            first_body_sample_size_cells = sum(
                bool(SAMPLE_SIZE_HEADER_CELL_PATTERN.search(cell))
                for cell in first_body_trailing
            )
            if first_body_sample_size_cells >= max(2, len(first_body_trailing) // 2):
                continue
        else:
            first_body_numeric_trailing_count = sum(bool(re.search(r"\d", cell)) for cell in first_body_trailing)
            first_body_alpha_trailing_count = sum(bool(re.search(r"[A-Za-z]", cell)) for cell in first_body_trailing)
            if not first_body_has_left_label or (
                first_body_trailing
                and (
                    first_body_numeric_trailing_count == 0
                    or (first_body_alpha_trailing_count > 1 and first_body_numeric_trailing_count < 2)
                )
            ):
                continue
            support_row_idx = next(
                (
                    row_idx
                    for row_idx in below_rows
                    if row_idx > first_body_row_idx
                    and row_idx not in set(note_rows)
                    and _is_value_matrix_row(rows[row_idx])
                ),
                None,
            )
            if support_row_idx is None or support_row_idx - first_body_row_idx > 3:
                continue
            body_support = (
                "label_only_body_starter_with_value_rows"
                if not first_body_trailing
                else "sparse_body_starter_with_value_rows"
            )
        body_rows = [row_idx for row_idx in range(first_body_row_idx, len(rows)) if row_idx not in set(note_rows)]
        candidates.append(
            {
                "header_rows": header_rows,
                "body_rows": body_rows,
                "preamble_rows": preamble_rows,
                "rule_y": rule_y,
                "first_body_row_idx": first_body_row_idx,
                "body_support": body_support,
                "post_header_note_rows": note_rows,
                "continuation_note_rows": continuation_note_rows,
            }
        )
    if not candidates:
        return None
    multicolumn_leaf_candidates: list[dict[str, object]] = []
    for candidate in candidates:
        if candidate["body_support"] != "label_only_body_starter_with_value_rows":
            continue
        header_rows = [row_idx for row_idx in candidate["header_rows"] if isinstance(row_idx, int)]
        if len(header_rows) < 2:
            continue
        leaf_row = rows[header_rows[-1]]
        leaf_value_cells = [_clean_cell(cell) for cell in leaf_row[1:] if _clean_cell(cell)]
        if len(leaf_value_cells) < max(2, (len(leaf_row) - 1) // 2):
            continue
        group_row_found = False
        for row_idx in header_rows[:-1]:
            prior_row = rows[row_idx]
            prior_value_cells = [_clean_cell(cell) for cell in prior_row[1:] if _clean_cell(cell)]
            prior_has_blank_gap = any(
                _clean_cell(prior_row[col_idx]) and col_idx + 1 < len(prior_row) and not _clean_cell(prior_row[col_idx + 1])
                for col_idx in range(1, len(prior_row) - 1)
            )
            if prior_value_cells and (prior_has_blank_gap or len(prior_value_cells) < len(leaf_value_cells)):
                group_row_found = True
                break
        if group_row_found:
            multicolumn_leaf_candidates.append(candidate)
    if multicolumn_leaf_candidates:
        return min(multicolumn_leaf_candidates, key=lambda item: int(item["first_body_row_idx"]))
    return min(candidates, key=lambda item: int(item["first_body_row_idx"]))


def _looks_like_generated_row_boundary_rules(
    row_bounds: list[tuple[float, float]],
    horizontal_rules: list[float],
) -> bool:
    if not row_bounds or not horizontal_rules:
        return False
    boundary_values = [value for bounds in row_bounds for value in bounds]
    matched_boundaries = sum(
        any(abs(rule - boundary) <= BOUNDARY_RULE_TOLERANCE for rule in horizontal_rules)
        for boundary in boundary_values
    )
    return matched_boundaries >= max(4, int(len(boundary_values) * 0.8))


def _detect_value_region_anchor(rows: list[list[str]]) -> dict[str, object] | None:
    """Use the first label-plus-value row to split a header prefix from body rows."""
    direct_value_row_idx: int | None = None
    direct_value_like_count = 0
    direct_nonempty_value_count = 0
    for row_idx, row in enumerate(rows):
        if not row or not _clean_cell(row[0]):
            continue
        trailing = [_clean_cell(cell) for cell in row[1:] if _clean_cell(cell)]
        if not trailing:
            continue
        value_like_count, _ = _count_trailing_value_like_cells(row)
        required_value_cells = 1 if len(row) <= 3 else max(2, int(len(trailing) * 0.6))
        if value_like_count >= required_value_cells:
            direct_value_row_idx = row_idx
            direct_value_like_count = value_like_count
            direct_nonempty_value_count = len(trailing)
            break
    if direct_value_row_idx is None:
        return None

    body_start = direct_value_row_idx
    for row_idx in range(direct_value_row_idx - 1, -1, -1):
        row = rows[row_idx]
        if not row or not _clean_cell(row[0]):
            break
        trailing = [_clean_cell(cell) for cell in row[1:] if _clean_cell(cell)]
        if not trailing:
            body_start = row_idx
            continue
        value_like_count, _ = _count_trailing_value_like_cells(row)
        if len(trailing) <= 1:
            if value_like_count == 0:
                break
            body_start = row_idx
            continue
        repeated_text_values = len(set(trailing)) <= max(1, len(trailing) // 2)
        if value_like_count == 0 and repeated_text_values:
            body_start = row_idx
            continue
        break

    header_rows = [
        row_idx
        for row_idx in range(body_start)
        if any(_clean_cell(cell) for cell in rows[row_idx])
    ]
    preamble_rows: list[int] = []
    while len(header_rows) > 1:
        first_row_idx = header_rows[0]
        first_row = rows[first_row_idx]
        first_row_has_left_text = bool(_clean_cell(first_row[0]))
        later_counts = [
            sum(bool(_clean_cell(cell)) for cell in rows[row_idx])
            for row_idx in header_rows[1:]
        ]
        if (
            first_row_has_left_text
            and sum(bool(_clean_cell(cell)) for cell in first_row) <= 2
            and max(later_counts, default=0) >= max(3, len(first_row) // 2)
        ):
            preamble_rows.append(first_row_idx)
            header_rows = header_rows[1:]
            continue
        break

    return {
        "body_start": body_start,
        "header_rows": header_rows,
        "body_rows": list(range(body_start, len(rows))),
        "preamble_rows": preamble_rows,
        "anchor_data_row_idx": direct_value_row_idx,
        "anchor_value_like_cells": direct_value_like_count,
        "anchor_nonempty_value_region_cells": direct_nonempty_value_count,
    }


def detect_header_rows_with_metadata(
    rows: list[list[str]],
    *,
    row_bounds: list[tuple[float, float]] | None = None,
    horizontal_rules: list[float] | None = None,
    separator_horizontal_rules: list[float] | None = None,
) -> tuple[list[int], list[int], dict[str, object]]:
    """Identify likely header rows and expose how the decision was made."""
    separator_rules = separator_horizontal_rules if separator_horizontal_rules is not None else horizontal_rules
    if (
        separator_horizontal_rules is None
        and separator_rules is not None
        and row_bounds is not None
        and _looks_like_generated_row_boundary_rules(row_bounds, separator_rules)
    ):
        separator_rules = None
    separator_detection = (
        _detect_separator_rule_headers(rows, row_bounds, separator_rules)
        if rows and row_bounds and separator_rules and len(row_bounds) == len(rows)
        else None
    )
    value_anchor_detection = _detect_value_region_anchor(rows)

    use_separator_detection = separator_detection is not None

    if use_separator_detection:
        header_rows = list(separator_detection["header_rows"])
        source = "horizontal_rule_separator"
        rule_strength = "strong"
    elif value_anchor_detection is not None:
        header_rows = list(value_anchor_detection["header_rows"])
        source = "value_region_anchor"
        rule_strength = None
    else:
        header_rows = []
        source = "unclassified_no_separator_or_value_anchor"
        rule_strength = None

    body_rows = (
        list(separator_detection["body_rows"])
        if use_separator_detection and separator_detection is not None
        else list(value_anchor_detection["body_rows"])
        if source == "value_region_anchor" and value_anchor_detection is not None
        else [row_idx for row_idx in range(len(rows)) if any(_clean_cell(cell) for cell in rows[row_idx])]
    )
    metadata = {
        "source": source,
        "rule_strength": rule_strength,
        "rule_based_headers": list(separator_detection["header_rows"]) if separator_detection is not None else [],
        "content_based_headers": [],
        "promoted_header_rows": [],
        "rule_content_disagreement": False,
    }
    if use_separator_detection and separator_detection is not None:
        metadata.update(
            {
                "separator_rule_y": separator_detection["rule_y"],
                "separator_header_rows": separator_detection["header_rows"],
                "preamble_rows": separator_detection["preamble_rows"],
                "separator_first_body_row_idx": separator_detection["first_body_row_idx"],
                "separator_body_support": separator_detection["body_support"],
                "post_header_note_rows": separator_detection["post_header_note_rows"],
                "continuation_note_rows": separator_detection["continuation_note_rows"],
            }
        )
    elif source == "value_region_anchor" and value_anchor_detection is not None:
        metadata.update(
            {
                "value_anchor_body_start": value_anchor_detection["body_start"],
                "value_anchor_header_rows": value_anchor_detection["header_rows"],
                "preamble_rows": value_anchor_detection["preamble_rows"],
                "value_anchor_data_row_idx": value_anchor_detection["anchor_data_row_idx"],
                "value_anchor_value_like_cells": value_anchor_detection["anchor_value_like_cells"],
                "value_anchor_nonempty_value_region_cells": value_anchor_detection[
                    "anchor_nonempty_value_region_cells"
                ],
            }
        )
    return header_rows, body_rows, metadata


def compare_header_body_split_rules(
    rows: list[list[str]],
    *,
    row_bounds: list[tuple[float, float]] | None = None,
    horizontal_rules: list[float] | None = None,
    separator_horizontal_rules: list[float] | None = None,
    selected_header_rows: list[int] | None = None,
    selected_body_rows: list[int] | None = None,
) -> dict[str, object]:
    """Compare two simple header/body split candidates without selecting either."""
    selected_body_start = min(selected_body_rows) if selected_body_rows else None
    rule_source = separator_horizontal_rules if separator_horizontal_rules is not None else horizontal_rules
    hline_candidate: dict[str, object] = {
        "rule": "selective_hline_prefix",
        "body_start": None,
        "header_rows": [],
        "preamble_rows": [],
        "reason": "no_selective_hline_candidate",
    }
    if rows and row_bounds and rule_source and len(row_bounds) == len(rows):
        if (
            separator_horizontal_rules is None
            and _looks_like_generated_row_boundary_rules(row_bounds, rule_source)
        ):
            rule_source = None
    if rows and row_bounds and rule_source and len(row_bounds) == len(rows):
        sorted_rules = sorted(rule_source)
        separator_detection = _detect_separator_rule_headers(rows, row_bounds, sorted_rules)
        if separator_detection is not None:
            hline_candidate = {
                "rule": "selective_hline_prefix",
                "body_start": separator_detection["first_body_row_idx"],
                "header_rows": separator_detection["header_rows"],
                "preamble_rows": separator_detection["preamble_rows"],
                "reason": "validated_full_width_separator",
                "rule_y": separator_detection["rule_y"],
                "body_support": separator_detection["body_support"],
            }
        else:
            for rule_y in sorted_rules:
                header_count = sum(row_bottom <= rule_y + BOUNDARY_RULE_TOLERANCE for _, row_bottom in row_bounds)
                if 0 < header_count < len(rows):
                    hline_candidate = {
                        "rule": "selective_hline_prefix",
                        "body_start": header_count,
                        "header_rows": list(range(header_count)),
                        "preamble_rows": [],
                        "reason": "first_selective_hline_boundary",
                        "rule_y": rule_y,
                    }
                    break

    data_anchor_candidate: dict[str, object] = {
        "rule": "first_value_region_data_row",
        "body_start": None,
        "header_rows": [],
        "reason": "no_data_anchor_found",
    }
    value_anchor_detection = _detect_value_region_anchor(rows)
    if value_anchor_detection is not None:
        data_anchor_candidate = {
            "rule": "first_value_region_data_row",
            "body_start": value_anchor_detection["body_start"],
            "header_rows": value_anchor_detection["header_rows"],
            "preamble_rows": value_anchor_detection["preamble_rows"],
            "reason": "value_region_anchor",
            "anchor_data_row_idx": value_anchor_detection["anchor_data_row_idx"],
            "anchor_value_like_cells": value_anchor_detection["anchor_value_like_cells"],
            "anchor_nonempty_value_region_cells": value_anchor_detection[
                "anchor_nonempty_value_region_cells"
            ],
        }

    candidate_starts = [
        candidate["body_start"]
        for candidate in (hline_candidate, data_anchor_candidate)
        if isinstance(candidate.get("body_start"), int)
    ]
    return {
        "selected": {
            "body_start": selected_body_start,
            "header_rows": selected_header_rows or [],
        },
        "candidates": [hline_candidate, data_anchor_candidate],
        "rules_agree": len(candidate_starts) == 2 and candidate_starts[0] == candidate_starts[1],
    }


def detect_header_rows(
    rows: list[list[str]],
    *,
    row_bounds: list[tuple[float, float]] | None = None,
    horizontal_rules: list[float] | None = None,
    separator_horizontal_rules: list[float] | None = None,
) -> tuple[list[int], list[int]]:
    """Identify likely header rows near the top of the table."""
    return detect_header_rows_with_metadata(
        rows,
        row_bounds=row_bounds,
        horizontal_rules=horizontal_rules,
        separator_horizontal_rules=separator_horizontal_rules,
    )[:2]
