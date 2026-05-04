"""Pipeline helper for converting extracted tables into normalized tables."""

from __future__ import annotations

import re

from table1_parser.heuristics.variable_grouper import group_variable_blocks
from table1_parser.heuristics.value_pattern_detector import detect_value_pattern
from table1_parser.normalize.header_detector import detect_header_rows_with_metadata
from table1_parser.normalize.row_signature import build_row_signature
from table1_parser.schemas import ExtractedTable, NormalizedTable
from table1_parser.schemas.normalized_table import RowView
from table1_parser.text_cleaning import clean_text, summarize_text_cleaning_provenance


ALPHA_PATTERN = re.compile(r"[A-Za-z]")
ALNUM_PATTERN = re.compile(r"[A-Za-z0-9]")
COUNT_PCT_STYLE_PATTERN = re.compile(r"\bn\s*\(\s*%\s*\)")
PERCENT_FRAGMENT_PATTERN = re.compile(r"^\(\s*\d+(?:\.\d+)?%\s*\)$")
UNCERTAINTY_FRAGMENT_PATTERN = re.compile(r"^(?:[+\-±]\s*)?\d+(?:\.\d+)?$")
STACKED_CELL_LINE_PATTERN = re.compile(r"(?:\r\n|\r|\n)+")
EMBEDDED_LABEL_COUNT_PATTERN = re.compile(r"^(?P<label>.*[A-Za-z][A-Za-z/%() .,\-]*)\s+(?P<count>\d[\d,]*)$")
FOOTNOTE_MARK_PATTERN = re.compile(r"[†‡§¶*]")
NA_LIKE_VALUE_PATTERN = re.compile(r"^(?:N/?A|NR|not reported)$", re.IGNORECASE)


def _is_noninformative_cell(value: str) -> bool:
    """Return whether a cell is empty or too weak to act as a reliable row label."""
    cleaned = clean_text(value)
    if not cleaned:
        return True
    if not ALNUM_PATTERN.search(cleaned):
        return True
    return len(cleaned) <= 2 and not ALPHA_PATTERN.search(cleaned)


def _looks_like_label_cell(value: str) -> bool:
    """Return whether a cell resembles a meaningful row-label cell."""
    cleaned = clean_text(value)
    if NA_LIKE_VALUE_PATTERN.fullmatch(cleaned):
        return False
    return bool(cleaned) and bool(ALPHA_PATTERN.search(cleaned)) and len(cleaned) >= 2


def _looks_like_label_prefix_cell(value: str) -> bool:
    """Return whether a first-column fragment can be part of a row label."""
    cleaned = clean_text(value)
    if not cleaned or not ALNUM_PATTERN.search(cleaned):
        return False
    if NA_LIKE_VALUE_PATTERN.fullmatch(cleaned):
        return False
    return detect_value_pattern(cleaned).pattern == "unknown"


def _has_data_like_values(values: list[str]) -> bool:
    """Return whether cells look like table data after ignoring p-values."""
    populated = [clean_text(value) for value in values if clean_text(value)]
    if not populated:
        return False
    data_like = sum(
        detect_value_pattern(value).pattern not in {"unknown", "p_value"} or (
            any(char.isdigit() for char in value) and detect_value_pattern(value).pattern != "p_value"
        )
        for value in populated
    )
    return data_like >= max(1, len(populated) // 2)


def _has_substantive_row_values(values: list[str]) -> bool:
    """Return whether a row has enough right-side values to be a data row."""
    populated = [clean_text(value) for value in values if clean_text(value)]
    if not populated:
        return False
    value_like = sum(
        detect_value_pattern(value).pattern != "unknown"
        or (any(char.isdigit() for char in value) and not ALPHA_PATTERN.search(value))
        or NA_LIKE_VALUE_PATTERN.fullmatch(value) is not None
        for value in populated
    )
    return value_like >= 2


def _split_embedded_label_count(value: str) -> tuple[str, str] | None:
    """Split a label fragment followed by a count-like value."""
    cleaned = clean_text(value)
    match = EMBEDDED_LABEL_COUNT_PATTERN.fullmatch(cleaned)
    if match is None:
        return None
    count = match.group("count")
    count_number = int(count.replace(",", ""))
    if "," not in count and count_number < 20:
        return None
    label = clean_text(match.group("label"))
    if label.lower().endswith((" to", " and", "-")):
        return None
    if not label or detect_value_pattern(label).pattern != "unknown":
        return None
    return label, count


def _repair_embedded_label_count_cells(
    raw_rows: list[list[str]],
    cleaned_rows: list[list[str]],
) -> tuple[list[list[str]], list[list[str]], dict[str, object] | None]:
    """Move a label tail out of the first value column when a count follows it."""
    if not raw_rows or max((len(row) for row in raw_rows), default=0) < 4:
        return raw_rows, cleaned_rows, None

    repaired_raw_rows = [list(row) for row in raw_rows]
    repaired_cleaned_rows = [list(row) for row in cleaned_rows]
    repaired_rows: list[int] = []
    for row_idx, row in enumerate(cleaned_rows):
        if len(row) < 3 or not _looks_like_label_prefix_cell(row[0]):
            continue
        split = _split_embedded_label_count(row[1])
        if split is None or not _has_substantive_row_values(row[2:]):
            continue
        label_tail, count_value = split
        raw_split = _split_embedded_label_count(raw_rows[row_idx][1])
        raw_label_tail = raw_split[0] if raw_split is not None else label_tail
        raw_count_value = raw_split[1] if raw_split is not None else count_value
        repaired_raw_rows[row_idx][0] = clean_text(f"{raw_rows[row_idx][0]} {raw_label_tail}")
        repaired_cleaned_rows[row_idx][0] = clean_text(f"{cleaned_rows[row_idx][0]} {label_tail}")
        repaired_raw_rows[row_idx][1] = raw_count_value
        repaired_cleaned_rows[row_idx][1] = count_value
        repaired_rows.append(row_idx)

    if not repaired_rows:
        return raw_rows, cleaned_rows, None
    return repaired_raw_rows, repaired_cleaned_rows, {
        "source_col_idx": 1,
        "label_col_idx": 0,
        "repaired_row_indices": repaired_rows,
        "repaired_row_count": len(repaired_rows),
    }


def _is_label_continuation(previous_label: str, candidate_label: str) -> bool:
    """Return whether a label-only row looks like a continuation of the prior label."""
    previous = clean_text(previous_label)
    candidate = clean_text(candidate_label)
    if not previous or not candidate or len(candidate.split()) > 5:
        return False
    if previous.count("(") > previous.count(")") and ")" in candidate:
        return True
    candidate_has_continuation_start = (
        candidate[0].islower()
        or candidate[0].isdigit()
        or ")" in candidate
        or FOOTNOTE_MARK_PATTERN.search(candidate) is not None
    )
    if previous.lower().endswith((" to", " and", " of", " for", "-")) and candidate_has_continuation_start:
        return True
    if candidate[0].islower() or candidate[0].isdigit():
        return True
    return bool(FOOTNOTE_MARK_PATTERN.search(candidate))


def _repair_vertical_label_continuations(
    raw_rows: list[list[str]],
    cleaned_rows: list[list[str]],
) -> tuple[list[list[str]], list[list[str]], dict[str, object] | None]:
    """Merge label-only continuation rows into the preceding data row."""
    if not raw_rows or max((len(row) for row in raw_rows), default=0) < 4:
        return raw_rows, cleaned_rows, None

    repaired_raw_rows = [list(row) for row in raw_rows]
    repaired_cleaned_rows = [list(row) for row in cleaned_rows]
    merged_rows: list[dict[str, int]] = []
    suppressed_rows: list[int] = []
    for row_idx in range(1, len(cleaned_rows)):
        if row_idx in suppressed_rows:
            continue
        current_label = clean_text(" ".join(cell for cell in cleaned_rows[row_idx][:2] if clean_text(cell)))
        if not current_label or _has_substantive_row_values(cleaned_rows[row_idx][1:]):
            continue
        target_idx = row_idx - 1
        while target_idx in suppressed_rows and target_idx > 0:
            target_idx -= 1
        previous_label = clean_text(repaired_cleaned_rows[target_idx][0]) if target_idx >= 0 else ""
        if not _has_substantive_row_values(repaired_cleaned_rows[target_idx][1:]):
            continue
        if not _is_label_continuation(previous_label, current_label):
            continue
        current_raw_label = clean_text(" ".join(cell for cell in raw_rows[row_idx][:2] if clean_text(cell)))
        repaired_raw_rows[target_idx][0] = clean_text(f"{repaired_raw_rows[target_idx][0]} {current_raw_label}")
        repaired_cleaned_rows[target_idx][0] = clean_text(f"{repaired_cleaned_rows[target_idx][0]} {current_label}")
        repaired_raw_rows[row_idx] = ["" for _ in repaired_raw_rows[row_idx]]
        repaired_cleaned_rows[row_idx] = ["" for _ in repaired_cleaned_rows[row_idx]]
        suppressed_rows.append(row_idx)
        merged_rows.append({"from_row_idx": row_idx, "to_row_idx": target_idx})

    if not suppressed_rows:
        return raw_rows, cleaned_rows, None
    return repaired_raw_rows, repaired_cleaned_rows, {
        "merged_rows": merged_rows,
        "removed_continuation_row_indices": suppressed_rows,
        "merged_row_count": len(suppressed_rows),
    }


def _split_stacked_cell_lines(value: str, *, cleaned: bool) -> list[str]:
    """Split extractor-preserved line stacks in one wide cell."""
    parts: list[str] = []
    for part in STACKED_CELL_LINE_PATTERN.split(value):
        stripped = part.strip()
        if not stripped:
            continue
        parts.append(clean_text(stripped) if cleaned else stripped)
    return parts


def _looks_like_stacked_numeric_value(value: str) -> bool:
    """Return whether a stacked-cell token is value-like enough to define a data column."""
    cleaned = clean_text(value)
    if not cleaned:
        return False
    if detect_value_pattern(cleaned).pattern != "unknown":
        return True
    if not any(char.isdigit() for char in cleaned):
        return False
    return not ALPHA_PATTERN.search(cleaned)


def _looks_like_uncertainty_fragment(value: str) -> bool:
    """Return whether a cell looks like an adjacent uncertainty fragment."""
    cleaned = clean_text(value)
    if not cleaned or not UNCERTAINTY_FRAGMENT_PATTERN.fullmatch(cleaned):
        return False
    return cleaned[0] in {"+", "-", "±"}


def _looks_like_estimate_value(value: str) -> bool:
    """Return whether a cell can be the estimate paired with an uncertainty fragment."""
    cleaned = clean_text(value)
    if not cleaned or not any(char.isdigit() for char in cleaned):
        return False
    if ALPHA_PATTERN.search(cleaned):
        return False
    return detect_value_pattern(cleaned).pattern in {"number", "percent", "unknown"}


def _looks_like_numeric_matrix_cell(value: str) -> bool:
    """Return whether a cell is numeric enough to belong to a value matrix."""
    cleaned = clean_text(value)
    if not cleaned or ALPHA_PATTERN.search(cleaned):
        return False
    return any(char.isdigit() for char in cleaned)


def _repair_split_uncertainty_columns(
    raw_rows: list[list[str]],
    cleaned_rows: list[list[str]],
    body_rows: list[int],
) -> tuple[list[list[str]], list[list[str]], list[dict[str, int]]]:
    """Merge adjacent estimate and uncertainty-fragment columns."""
    if not raw_rows or len(raw_rows[0]) < 4 or len(body_rows) < 3:
        return raw_rows, cleaned_rows, []

    repaired_raw_rows = [list(row) for row in raw_rows]
    repaired_cleaned_rows = [list(row) for row in cleaned_rows]
    repairs: list[dict[str, int]] = []
    first_matrix_row_idx = _first_dense_numeric_matrix_row(cleaned_rows)
    repair_body_rows = [
        row_idx
        for row_idx in body_rows
        if first_matrix_row_idx is None or row_idx >= first_matrix_row_idx
    ]
    for col_idx in range(2, len(cleaned_rows[0])):
        supporting_rows = 0
        nonempty_candidate_rows = 0
        for row_idx in repair_body_rows:
            if row_idx >= len(cleaned_rows):
                continue
            left = clean_text(repaired_cleaned_rows[row_idx][col_idx - 1])
            right = clean_text(repaired_cleaned_rows[row_idx][col_idx])
            if not right:
                continue
            nonempty_candidate_rows += 1
            if _looks_like_estimate_value(left) and _looks_like_uncertainty_fragment(right):
                supporting_rows += 1
        if (
            supporting_rows < max(3, len(repair_body_rows) // 5)
            or supporting_rows * 3 < max(1, nonempty_candidate_rows * 2)
        ):
            continue
        merged_row_count = 0
        for row_idx in repair_body_rows:
            if row_idx >= len(repaired_cleaned_rows):
                continue
            left = clean_text(repaired_cleaned_rows[row_idx][col_idx - 1])
            right = clean_text(repaired_cleaned_rows[row_idx][col_idx])
            if not (_looks_like_estimate_value(left) and _looks_like_uncertainty_fragment(right)):
                continue
            repaired_raw_rows[row_idx][col_idx - 1] = clean_text(
                f"{repaired_raw_rows[row_idx][col_idx - 1]} {repaired_raw_rows[row_idx][col_idx]}"
            )
            repaired_cleaned_rows[row_idx][col_idx - 1] = clean_text(f"{left} {right}")
            repaired_raw_rows[row_idx][col_idx] = ""
            repaired_cleaned_rows[row_idx][col_idx] = ""
            merged_row_count += 1
        for row_idx in range(len(repaired_cleaned_rows)):
            if first_matrix_row_idx is not None and row_idx >= first_matrix_row_idx:
                continue
            left = clean_text(repaired_cleaned_rows[row_idx][col_idx - 1])
            right = clean_text(repaired_cleaned_rows[row_idx][col_idx])
            if not right:
                continue
            repaired_raw_rows[row_idx][col_idx - 1] = clean_text(f"{repaired_raw_rows[row_idx][col_idx - 1]} {repaired_raw_rows[row_idx][col_idx]}")
            repaired_cleaned_rows[row_idx][col_idx - 1] = clean_text(f"{left} {right}")
            repaired_raw_rows[row_idx][col_idx] = ""
            repaired_cleaned_rows[row_idx][col_idx] = ""
        repairs.append({"from_col_idx": col_idx, "to_col_idx": col_idx - 1, "merged_row_count": merged_row_count})
    return repaired_raw_rows, repaired_cleaned_rows, repairs


def _first_dense_numeric_matrix_row(cleaned_rows: list[list[str]]) -> int | None:
    """Find the first row that looks like the start of the numeric value matrix."""
    for row_idx, row in enumerate(cleaned_rows):
        if len(row) < 4 or not clean_text(row[0]):
            continue
        populated_right = [clean_text(cell) for cell in row[1:] if clean_text(cell)]
        if len(populated_right) < 3:
            continue
        numeric_right = sum(_looks_like_numeric_matrix_cell(cell) for cell in populated_right)
        if numeric_right >= max(3, int(len(populated_right) * 0.65)):
            return row_idx
    return None


def _drop_trailing_nondata_column(
    raw_rows: list[list[str]],
    cleaned_rows: list[list[str]],
    body_rows: list[int],
) -> tuple[list[list[str]], list[list[str]], dict[str, int] | None]:
    """Drop a rightmost column that is populated but not part of the value matrix."""
    if not raw_rows or len(raw_rows[0]) < 4 or len(body_rows) < 3:
        return raw_rows, cleaned_rows, None
    last_col_idx = len(cleaned_rows[0]) - 1
    populated = 0
    data_like = 0
    previous_data_like = 0
    for row_idx in body_rows:
        if row_idx >= len(cleaned_rows):
            continue
        last = clean_text(cleaned_rows[row_idx][last_col_idx])
        previous = clean_text(cleaned_rows[row_idx][last_col_idx - 1])
        populated += int(bool(last))
        data_like += int(_looks_like_numeric_matrix_cell(last))
        previous_data_like += int(_looks_like_numeric_matrix_cell(previous))
    if (
        populated < max(3, len(body_rows) // 5)
        or data_like >= max(3, len(body_rows) // 4)
        or previous_data_like < max(3, len(body_rows) // 4)
    ):
        return raw_rows, cleaned_rows, None
    return (
        [row[:last_col_idx] for row in raw_rows],
        [row[:last_col_idx] for row in cleaned_rows],
        {"dropped_col_idx": last_col_idx, "populated_body_rows": populated, "data_like_body_rows": data_like},
    )


def _drop_sparse_nonmatrix_value_columns(
    raw_rows: list[list[str]],
    cleaned_rows: list[list[str]],
    body_rows: list[int],
) -> tuple[list[list[str]], list[list[str]], list[dict[str, int]]]:
    """Drop sparse non-numeric value columns introduced by page-margin text."""
    if not raw_rows or len(raw_rows[0]) < 4 or len(body_rows) < 3:
        return raw_rows, cleaned_rows, []
    dropped: list[dict[str, int]] = []
    keep_indices = [0]
    matrix_rows = [row_idx for row_idx in body_rows if row_idx < len(cleaned_rows) and _has_substantive_row_values(cleaned_rows[row_idx][1:])]
    if len(matrix_rows) < 3:
        matrix_rows = body_rows
    for col_idx in range(1, len(cleaned_rows[0])):
        populated = 0
        numeric = 0
        left_numeric = 0
        right_numeric = 0
        for row_idx in matrix_rows:
            if row_idx >= len(cleaned_rows):
                continue
            value = clean_text(cleaned_rows[row_idx][col_idx])
            if col_idx > 1:
                left_numeric += int(_looks_like_numeric_matrix_cell(cleaned_rows[row_idx][col_idx - 1]))
            if col_idx + 1 < len(cleaned_rows[row_idx]):
                right_numeric += int(_looks_like_numeric_matrix_cell(cleaned_rows[row_idx][col_idx + 1]))
            if not value:
                continue
            populated += 1
            numeric += int(_looks_like_numeric_matrix_cell(value))
        if (
            (populated and numeric == 0 and populated <= max(4, len(body_rows) // 4))
            or (
                populated == 0
                and left_numeric >= max(3, len(matrix_rows) // 4)
                and right_numeric >= max(3, len(matrix_rows) // 4)
            )
        ):
            dropped.append({"dropped_col_idx": col_idx, "populated_body_rows": populated})
            continue
        keep_indices.append(col_idx)
    if not dropped:
        return raw_rows, cleaned_rows, []
    return (
        [[row[col_idx] for col_idx in keep_indices] for row in raw_rows],
        [[row[col_idx] for col_idx in keep_indices] for row in cleaned_rows],
        dropped,
    )


def _repair_extra_wide_value_column(
    raw_rows: list[list[str]],
    cleaned_rows: list[list[str]],
) -> tuple[list[list[str]], list[list[str]], dict[str, object] | None]:
    """Expand a collapsed extracted value-region cell into visual value columns."""
    if not raw_rows or len(raw_rows) < 5 or max((len(row) for row in raw_rows), default=0) != 2:
        return raw_rows, cleaned_rows, None

    raw_parts_by_row = [_split_stacked_cell_lines(row[1], cleaned=False) for row in raw_rows]
    cleaned_parts_by_row = [_split_stacked_cell_lines(row[1], cleaned=True) for row in raw_rows]
    value_stack_rows: list[int] = []
    for row_idx, parts in enumerate(cleaned_parts_by_row):
        if len(parts) < 4:
            continue
        numeric_like_count = sum(_looks_like_stacked_numeric_value(part) for part in parts)
        if numeric_like_count >= max(4, int(len(parts) * 0.8)):
            value_stack_rows.append(row_idx)

    if len(value_stack_rows) < max(3, len(raw_rows) // 5):
        return raw_rows, cleaned_rows, None

    width_counts: dict[int, int] = {}
    for row_idx in value_stack_rows:
        width = len(cleaned_parts_by_row[row_idx])
        width_counts[width] = width_counts.get(width, 0) + 1
    expected_width = max(width_counts, key=lambda width: (width_counts[width], width))
    if expected_width < 4 or expected_width > 24:
        return raw_rows, cleaned_rows, None
    if width_counts[expected_width] < max(3, len(value_stack_rows) // 2):
        return raw_rows, cleaned_rows, None

    first_value_row_idx = min(row_idx for row_idx in value_stack_rows if len(cleaned_parts_by_row[row_idx]) == expected_width)
    header_stack_rows = [
        row_idx
        for row_idx, parts in enumerate(cleaned_parts_by_row[:first_value_row_idx])
        if parts
        and (
            len(parts) == 1
            or len(parts) == expected_width
            or expected_width % len(parts) == 0
            or len(parts) % expected_width == 0
        )
    ]
    if not header_stack_rows:
        return raw_rows, cleaned_rows, None

    repaired_raw_rows: list[list[str]] = []
    repaired_cleaned_rows: list[list[str]] = []
    repeated_header_rows: list[int] = []
    padded_or_truncated_rows: list[int] = []
    for row_idx, row in enumerate(raw_rows):
        raw_parts = raw_parts_by_row[row_idx]
        cleaned_parts = cleaned_parts_by_row[row_idx]
        if len(raw_parts) == expected_width:
            expanded_raw = raw_parts
            expanded_cleaned = cleaned_parts
        elif row_idx < first_value_row_idx and len(raw_parts) > expected_width and len(raw_parts) % expected_width == 0:
            chunk_size = len(raw_parts) // expected_width
            expanded_raw = [
                clean_text(" ".join(raw_parts[start : start + chunk_size]))
                for start in range(0, len(raw_parts), chunk_size)
            ]
            expanded_cleaned = [
                clean_text(" ".join(cleaned_parts[start : start + chunk_size]))
                for start in range(0, len(cleaned_parts), chunk_size)
            ]
        elif row_idx < first_value_row_idx and len(raw_parts) == 1:
            expanded_raw = raw_parts * expected_width
            expanded_cleaned = cleaned_parts * expected_width
            repeated_header_rows.append(row_idx)
        elif row_idx < first_value_row_idx and raw_parts and expected_width % len(raw_parts) == 0:
            repeat_count = expected_width // len(raw_parts)
            expanded_raw = [part for part in raw_parts for _ in range(repeat_count)]
            expanded_cleaned = [part for part in cleaned_parts for _ in range(repeat_count)]
            repeated_header_rows.append(row_idx)
        else:
            expanded_raw = [*raw_parts[:expected_width], *["" for _ in range(max(0, expected_width - len(raw_parts)))]]
            expanded_cleaned = [
                *cleaned_parts[:expected_width],
                *["" for _ in range(max(0, expected_width - len(cleaned_parts)))],
            ]
            if raw_parts and len(raw_parts) != expected_width:
                padded_or_truncated_rows.append(row_idx)
        repaired_raw_rows.append([row[0], *expanded_raw])
        repaired_cleaned_rows.append([cleaned_rows[row_idx][0], *expanded_cleaned])

    return repaired_raw_rows, repaired_cleaned_rows, {
        "from_col_idx": 1,
        "created_value_columns": expected_width,
        "value_stack_row_indices": value_stack_rows,
        "first_value_row_idx": first_value_row_idx,
        "header_stack_row_indices": header_stack_rows,
        "repeated_header_row_indices": repeated_header_rows,
        "padded_or_truncated_row_indices": padded_or_truncated_rows,
        "evidence": {
            "row_count": len(raw_rows),
            "value_stack_row_count": len(value_stack_rows),
            "modal_stack_width": expected_width,
            "modal_stack_width_row_count": width_counts[expected_width],
            "header_stack_row_count": len(header_stack_rows),
        },
    }


def _repair_sparse_stub_label_column(
    raw_rows: list[list[str]],
    cleaned_rows: list[list[str]],
) -> tuple[list[list[str]], list[list[str]], dict[str, object] | None]:
    """Drop a sparse structural stub column when the next column is the true label column."""
    if not raw_rows or not raw_rows[0] or len(raw_rows[0]) < 4 or len(raw_rows) < 8:
        return raw_rows, cleaned_rows, None

    row_count = len(cleaned_rows)
    first_col_nonempty = 0
    first_col_value_like = 0
    second_col_nonempty = 0
    second_col_label_like = 0
    second_col_value_like = 0
    stub_only_rows: list[int] = []
    shifted_label_rows: list[int] = []
    merged_label_rows: list[int] = []
    right_value_rows = 0

    for row_idx, row in enumerate(cleaned_rows):
        first = clean_text(row[0])
        second = clean_text(row[1])
        right_cells = [clean_text(cell) for cell in row[2:]]
        populated_right = [cell for cell in right_cells if cell]
        right_value_like = sum(
            detect_value_pattern(cell).pattern != "unknown" or any(char.isdigit() for char in cell)
            for cell in populated_right
        )
        has_right_values = bool(populated_right) and right_value_like >= max(1, len(populated_right) // 2)

        if first:
            first_col_nonempty += 1
            if detect_value_pattern(first).pattern != "unknown" or any(char.isdigit() for char in first):
                first_col_value_like += 1
        if second:
            second_col_nonempty += 1
            if _looks_like_label_cell(second):
                second_col_label_like += 1
            if detect_value_pattern(second).pattern != "unknown":
                second_col_value_like += 1
        if has_right_values:
            right_value_rows += 1
        if first and not second and not populated_right:
            stub_only_rows.append(row_idx)
        if not first and _looks_like_label_cell(second) and has_right_values:
            shifted_label_rows.append(row_idx)
        if _looks_like_label_cell(first) and _looks_like_label_cell(second) and has_right_values:
            merged_label_rows.append(row_idx)

    if not (
        first_col_nonempty <= max(4, row_count // 5)
        and first_col_value_like == 0
        and len(stub_only_rows) >= 1
        and len(shifted_label_rows) >= max(4, row_count // 3)
        and second_col_nonempty >= max(5, row_count // 2)
        and second_col_label_like >= max(4, second_col_nonempty // 2)
        and second_col_value_like <= max(1, second_col_nonempty // 10)
        and right_value_rows >= max(4, row_count // 3)
    ):
        return raw_rows, cleaned_rows, None

    repaired_raw_rows: list[list[str]] = []
    repaired_cleaned_rows: list[list[str]] = []
    for row_idx, row in enumerate(raw_rows):
        cleaned_row = cleaned_rows[row_idx]
        if row_idx in merged_label_rows:
            merged_raw = clean_text(f"{row[0]} {row[1]}")
            merged_cleaned = clean_text(f"{cleaned_row[0]} {cleaned_row[1]}")
            repaired_raw_rows.append([merged_raw, *row[2:]])
            repaired_cleaned_rows.append([merged_cleaned, *cleaned_row[2:]])
            continue
        if row_idx in stub_only_rows:
            repaired_raw_rows.append(["", *["" for _ in row[2:]]])
            repaired_cleaned_rows.append(["", *["" for _ in cleaned_row[2:]]])
            continue
        repaired_raw_rows.append([row[1], *row[2:]])
        repaired_cleaned_rows.append([cleaned_row[1], *cleaned_row[2:]])

    return repaired_raw_rows, repaired_cleaned_rows, {
        "from_col_idx": 0,
        "label_col_idx": 1,
        "removed_stub_row_indices": stub_only_rows,
        "shifted_label_row_count": len(shifted_label_rows),
        "merged_label_row_indices": merged_label_rows,
        "evidence": {
            "row_count": row_count,
            "first_col_nonempty": first_col_nonempty,
            "second_col_nonempty": second_col_nonempty,
            "shifted_label_row_count": len(shifted_label_rows),
            "right_value_row_count": right_value_rows,
        },
    }


def _repair_split_row_label_field_columns(
    raw_rows: list[list[str]],
    cleaned_rows: list[list[str]],
) -> tuple[list[list[str]], list[list[str]], dict[str, object] | None]:
    """Merge two adjacent row-label field columns when values clearly start to their right."""
    if not raw_rows or not raw_rows[0] or len(raw_rows[0]) < 4 or len(raw_rows) < 8:
        return raw_rows, cleaned_rows, None

    row_count = len(cleaned_rows)
    shifted_label_rows: list[int] = []
    merged_label_rows: list[int] = []
    parent_like_rows = 0
    right_value_rows = 0
    second_col_nonempty = 0
    second_col_label_like = 0
    second_col_value_like = 0

    for row_idx, row in enumerate(cleaned_rows):
        first = clean_text(row[0])
        second = clean_text(row[1])
        right_cells = [clean_text(cell) for cell in row[2:]]
        has_right_data = _has_data_like_values(right_cells)
        right_value_rows += int(has_right_data)
        if second:
            second_col_nonempty += 1
            second_col_label_like += int(_looks_like_label_cell(second))
            second_col_value_like += int(detect_value_pattern(second).pattern not in {"unknown", "p_value"})
        if not first and second and has_right_data:
            shifted_label_rows.append(row_idx)
        if _looks_like_label_cell(first) and _looks_like_label_cell(second):
            if has_right_data:
                merged_label_rows.append(row_idx)
            else:
                parent_like_rows += 1

    label_fragment_rows = len(merged_label_rows) + parent_like_rows
    has_shifted_label_support = len(shifted_label_rows) >= max(4, row_count // 5)
    has_merged_label_support = (
        len(merged_label_rows) >= max(4, row_count // 5)
        and label_fragment_rows >= max(6, row_count // 4)
    )
    if not (
        (has_shifted_label_support or has_merged_label_support)
        and right_value_rows >= max(5, row_count // 3)
        and second_col_nonempty >= max(6, row_count // 3)
        and second_col_label_like >= max(4, second_col_nonempty // 2)
        and second_col_value_like <= max(2, second_col_nonempty // 8)
        and label_fragment_rows >= 2
    ):
        return raw_rows, cleaned_rows, None

    repaired_raw_rows: list[list[str]] = []
    repaired_cleaned_rows: list[list[str]] = []
    shifted_count = 0
    merged_rows: list[int] = []
    for row_idx, row in enumerate(raw_rows):
        cleaned_row = cleaned_rows[row_idx]
        first_clean = clean_text(cleaned_row[0])
        second_clean = clean_text(cleaned_row[1])
        right_clean = [clean_text(cell) for cell in cleaned_row[2:]]
        if first_clean and second_clean:
            merged_raw = clean_text(f"{row[0]} {row[1]}")
            merged_cleaned = clean_text(f"{cleaned_row[0]} {cleaned_row[1]}")
            repaired_raw_rows.append([merged_raw, *row[2:]])
            repaired_cleaned_rows.append([merged_cleaned, *cleaned_row[2:]])
            merged_rows.append(row_idx)
            continue
        if not first_clean and second_clean and _has_data_like_values(right_clean):
            repaired_raw_rows.append([row[1], *row[2:]])
            repaired_cleaned_rows.append([cleaned_row[1], *cleaned_row[2:]])
            shifted_count += 1
            continue
        repaired_raw_rows.append([row[0], *row[2:]])
        repaired_cleaned_rows.append([cleaned_row[0], *cleaned_row[2:]])

    return repaired_raw_rows, repaired_cleaned_rows, {
        "from_col_idx": 1,
        "to_col_idx": 0,
        "shifted_label_row_count": shifted_count,
        "merged_label_row_indices": merged_rows,
        "evidence": {
            "row_count": row_count,
            "second_col_nonempty": second_col_nonempty,
            "second_col_label_like": second_col_label_like,
            "shifted_label_row_count": len(shifted_label_rows),
            "merged_label_row_count": len(merged_label_rows),
            "parent_like_row_count": parent_like_rows,
            "right_value_row_count": right_value_rows,
        },
    }


def normalize_extracted_table(table: ExtractedTable) -> NormalizedTable:
    """Convert a raw extracted table into the normalized intermediate schema."""
    raw_rows = [["" for _ in range(table.n_cols)] for _ in range(table.n_rows)]
    for cell in table.cells:
        if cell.row_idx < table.n_rows and cell.col_idx < table.n_cols:
            raw_rows[cell.row_idx][cell.col_idx] = cell.text
    if not raw_rows:
        dropped_leading_cols = 0
        dropped_trailing_cols = 0
    else:
        if raw_rows[0] and len(raw_rows[0]) >= 2:
            first_column = [row[0] for row in raw_rows]
            second_column = [row[1] for row in raw_rows]
            first_noninformative = sum(_is_noninformative_cell(value) for value in first_column)
            first_meaningful = sum(_looks_like_label_cell(value) for value in first_column)
            second_label_like = sum(_looks_like_label_cell(value) for value in second_column)
            row_count = len(raw_rows)
            dropped_leading_cols = int(
                first_noninformative / row_count >= 0.85
                and first_meaningful <= max(1, row_count // 10)
                and second_label_like >= max(3, row_count // 3)
            )
        else:
            dropped_leading_cols = 0
        rows_after_leading = [row[dropped_leading_cols:] for row in raw_rows]
        if rows_after_leading and rows_after_leading[0] and len(rows_after_leading[0]) >= 2:
            last_column = [row[-1] for row in rows_after_leading]
            previous_column = [row[-2] for row in rows_after_leading]
            last_noninformative = sum(_is_noninformative_cell(value) for value in last_column)
            previous_informative = sum(not _is_noninformative_cell(value) for value in previous_column)
            row_count = len(rows_after_leading)
            dropped_trailing_cols = int(
                last_noninformative / row_count >= 0.9
                and previous_informative >= max(2, row_count // 4)
            )
        else:
            dropped_trailing_cols = 0
        raw_rows = [row[:-dropped_trailing_cols] for row in rows_after_leading] if dropped_trailing_cols else rows_after_leading
    source_col_indices: list[int | None] = list(range(dropped_leading_cols, table.n_cols - dropped_trailing_cols))
    cleaned_rows = [[clean_text(cell) for cell in row] for row in raw_rows]
    embedded_label_count_repair: dict[str, object] | None = None
    raw_rows, cleaned_rows, embedded_label_count_repair = _repair_embedded_label_count_cells(
        raw_rows,
        cleaned_rows,
    )
    sparse_stub_label_column_repair: dict[str, object] | None = None
    if dropped_leading_cols == 0:
        raw_rows, cleaned_rows, sparse_stub_label_column_repair = _repair_sparse_stub_label_column(
            raw_rows,
            cleaned_rows,
        )
        if sparse_stub_label_column_repair is not None:
            dropped_leading_cols = 1
            source_col_indices = [None, *source_col_indices[2:]]
    split_row_label_field_repair: dict[str, object] | None = None
    if sparse_stub_label_column_repair is None:
        raw_rows, cleaned_rows, split_row_label_field_repair = _repair_split_row_label_field_columns(
            raw_rows,
            cleaned_rows,
        )
        if split_row_label_field_repair is not None:
            source_col_indices = [None, *source_col_indices[2:]]
    merged_split_label_columns: list[dict[str, int]] = []
    if raw_rows and len(raw_rows[0]) >= 3:
        candidate_split_label_rows = [
            row_idx
            for row_idx, row in enumerate(cleaned_rows)
            if _looks_like_label_cell(row[0])
            and (
                _looks_like_label_cell(row[1])
                or COUNT_PCT_STYLE_PATTERN.search(row[1]) is not None
                or row[1] == "(%)"
            )
            and (
                _has_data_like_values(row[2:])
                or (row[1] == "(%)" and any(clean_text(cell) for cell in row[2:]))
            )
        ]
        second_column_value_like_count = sum(
            detect_value_pattern(cleaned_rows[row_idx][1]).pattern != "unknown"
            or any(char.isdigit() for char in cleaned_rows[row_idx][1])
            for row_idx in candidate_split_label_rows
        )
        if len(candidate_split_label_rows) >= 3 and second_column_value_like_count <= max(1, len(candidate_split_label_rows) // 4):
            merged_row_count = 0
            for row_idx in candidate_split_label_rows:
                raw_rows[row_idx][0] = f"{raw_rows[row_idx][0]} {raw_rows[row_idx][1]}".strip()
                cleaned_rows[row_idx][0] = clean_text(f"{cleaned_rows[row_idx][0]} {cleaned_rows[row_idx][1]}")
                raw_rows[row_idx][1] = ""
                cleaned_rows[row_idx][1] = ""
                merged_row_count += 1
            merged_split_label_columns.append(
                {"from_col_idx": 1, "to_col_idx": 0, "merged_row_count": merged_row_count}
            )
    extra_wide_value_column_repair: dict[str, object] | None = None
    raw_rows, cleaned_rows, extra_wide_value_column_repair = _repair_extra_wide_value_column(
        raw_rows,
        cleaned_rows,
    )
    if extra_wide_value_column_repair is not None:
        source_col_indices = [source_col_indices[0], *[None for _ in range(len(raw_rows[0]) - 1)]]
    vertical_label_continuation_repair: dict[str, object] | None = None
    raw_rows, cleaned_rows, vertical_label_continuation_repair = _repair_vertical_label_continuations(
        raw_rows,
        cleaned_rows,
    )
    raw_bounds = table.metadata.get("row_bounds")
    if isinstance(raw_bounds, list) and len(raw_bounds) == table.n_rows:
        row_bounds: list[tuple[float, float]] | None = []
        for item in raw_bounds:
            if not isinstance(item, (list, tuple)) or len(item) != 2:
                row_bounds = None
                break
            row_bounds.append((float(item[0]), float(item[1])))
    else:
        row_bounds = None
    raw_rules = table.metadata.get("horizontal_rules")
    horizontal_rules = [float(value) for value in raw_rules] if isinstance(raw_rules, list) else None
    header_row_bounds = None if extra_wide_value_column_repair is not None else row_bounds
    header_horizontal_rules = None if extra_wide_value_column_repair is not None else horizontal_rules
    header_rows, body_rows, header_detection = detect_header_rows_with_metadata(
        cleaned_rows,
        row_bounds=header_row_bounds,
        horizontal_rules=header_horizontal_rules,
    )
    if extra_wide_value_column_repair is not None:
        repaired_header_rows = [
            row_idx
            for row_idx in extra_wide_value_column_repair.get("header_stack_row_indices", [])
            if isinstance(row_idx, int) and 0 <= row_idx < len(cleaned_rows)
        ]
        if repaired_header_rows:
            header_rows = repaired_header_rows
            body_rows = [row_idx for row_idx in range(len(cleaned_rows)) if row_idx not in set(header_rows)]
            header_detection = {
                **header_detection,
                "source": "extra_wide_value_column_boundary",
                "extra_wide_header_rows": repaired_header_rows,
                "extra_wide_first_value_row_idx": extra_wide_value_column_repair.get("first_value_row_idx"),
            }
    first_matrix_row_idx = _first_dense_numeric_matrix_row(cleaned_rows)
    if (
        extra_wide_value_column_repair is None
        and first_matrix_row_idx is not None
        and 2 < first_matrix_row_idx <= 5
        and len(header_rows) < first_matrix_row_idx
    ):
        repaired_header_rows = [row_idx for row_idx in range(first_matrix_row_idx) if any(clean_text(cell) for cell in cleaned_rows[row_idx])]
        while len(repaired_header_rows) > 1:
            first_row = cleaned_rows[repaired_header_rows[0]]
            later_counts = [sum(bool(clean_text(cell)) for cell in cleaned_rows[row_idx]) for row_idx in repaired_header_rows[1:]]
            if sum(bool(clean_text(cell)) for cell in first_row) <= 2 and max(later_counts, default=0) >= max(3, len(first_row) // 2):
                repaired_header_rows = repaired_header_rows[1:]
                continue
            break
        if len(repaired_header_rows) > len(header_rows):
            header_rows = repaired_header_rows
            body_rows = [row_idx for row_idx in range(first_matrix_row_idx, len(cleaned_rows))]
            header_detection = {
                **header_detection,
                "source": "value_matrix_boundary",
                "value_matrix_header_rows": repaired_header_rows,
                "value_matrix_first_value_row_idx": first_matrix_row_idx,
            }
    suppressed_stub_row_indices = (
        set(sparse_stub_label_column_repair.get("removed_stub_row_indices", []))
        if sparse_stub_label_column_repair is not None
        else set()
    )
    suppressed_continuation_row_indices = (
        set(vertical_label_continuation_repair.get("removed_continuation_row_indices", []))
        if vertical_label_continuation_repair is not None
        else set()
    )
    suppressed_row_indices = suppressed_stub_row_indices | suppressed_continuation_row_indices
    body_rows = [row_idx for row_idx in body_rows if row_idx not in suppressed_row_indices]
    split_uncertainty_column_repairs: list[dict[str, int]] = []
    raw_rows, cleaned_rows, split_uncertainty_column_repairs = _repair_split_uncertainty_columns(
        raw_rows,
        cleaned_rows,
        body_rows,
    )
    trailing_nondata_column_repair: dict[str, int] | None = None
    raw_rows, cleaned_rows, trailing_nondata_column_repair = _drop_trailing_nondata_column(
        raw_rows,
        cleaned_rows,
        body_rows,
    )
    if split_uncertainty_column_repairs or trailing_nondata_column_repair is not None:
        header_rows, body_rows, header_detection = detect_header_rows_with_metadata(
            cleaned_rows,
            row_bounds=header_row_bounds,
            horizontal_rules=header_horizontal_rules,
        )
        body_rows = [row_idx for row_idx in body_rows if row_idx not in suppressed_row_indices]
    first_column_bboxes: dict[int, tuple[float, float, float, float]] = {}
    x0_values: list[float] = []
    first_column_text_x0_by_row: dict[int, float] = {}
    raw_text_x0_by_row = table.metadata.get("first_column_text_x0_by_row")
    if dropped_leading_cols == 0 and isinstance(raw_text_x0_by_row, dict):
        for row_idx_key, value in raw_text_x0_by_row.items():
            try:
                first_column_text_x0_by_row[int(row_idx_key)] = float(value)
            except (TypeError, ValueError):
                continue
    for cell in table.cells:
        if cell.col_idx != dropped_leading_cols or cell.bbox is None or cell.row_idx >= table.n_rows:
            continue
        first_column_bboxes[cell.row_idx] = cell.bbox
        x0_values.append(cell.bbox[0])
    base_x0 = min(x0_values) if x0_values else None
    body_text_x0_values = [
        first_column_text_x0_by_row[row_idx]
        for row_idx in body_rows
        if row_idx in first_column_text_x0_by_row
    ]
    base_text_x0 = min(body_text_x0_values) if body_text_x0_values else None
    row_views = [
        build_row_signature(
            row_idx,
            raw_rows[row_idx],
            first_cell_bbox=first_column_bboxes.get(row_idx),
            base_x0=base_x0,
            first_cell_text_x0=first_column_text_x0_by_row.get(row_idx),
            base_text_x0=base_text_x0,
        )
        for row_idx in body_rows
    ]
    provisional_table = NormalizedTable(
        table_id=table.table_id,
        title=table.title,
        caption=table.caption,
        header_rows=header_rows,
        body_rows=body_rows,
        row_views=row_views,
        n_rows=table.n_rows,
        n_cols=len(raw_rows[0]) if raw_rows else 0,
        metadata={},
    )
    count_pct_rows: set[int] = set()
    for block in group_variable_blocks(provisional_table):
        parent_label = clean_text(block.variable_label).lower()
        if COUNT_PCT_STYLE_PATTERN.search(parent_label):
            count_pct_rows.update(block.level_row_indices or [block.variable_row_idx])
    merged_columns: list[dict[str, int]] = []
    for col_idx in range(1, len(raw_rows[0]) if raw_rows else 0):
        supporting_rows = 0
        nonempty_body_values = 0
        disqualifying_values = 0
        for row_idx in body_rows:
            right = cleaned_rows[row_idx][col_idx]
            if not right:
                continue
            nonempty_body_values += 1
            if (
                row_idx in count_pct_rows
                and PERCENT_FRAGMENT_PATTERN.fullmatch(right)
                and detect_value_pattern(cleaned_rows[row_idx][col_idx - 1]).pattern == "n_only"
            ):
                supporting_rows += 1
            else:
                disqualifying_values += 1
        if supporting_rows < 2 or supporting_rows * 2 < nonempty_body_values or disqualifying_values > 1:
            continue
        merged_row_count = 0
        for row_idx in range(len(raw_rows)):
            left_clean = cleaned_rows[row_idx][col_idx - 1]
            right_clean = cleaned_rows[row_idx][col_idx]
            if row_idx in header_rows:
                if not left_clean and right_clean:
                    raw_rows[row_idx][col_idx - 1] = raw_rows[row_idx][col_idx]
                    cleaned_rows[row_idx][col_idx - 1] = right_clean
                    raw_rows[row_idx][col_idx] = ""
                    cleaned_rows[row_idx][col_idx] = ""
                continue
            if (
                row_idx in count_pct_rows
                and PERCENT_FRAGMENT_PATTERN.fullmatch(right_clean)
                and detect_value_pattern(left_clean).pattern == "n_only"
            ):
                raw_rows[row_idx][col_idx - 1] = f"{raw_rows[row_idx][col_idx - 1]} {raw_rows[row_idx][col_idx]}".strip()
                cleaned_rows[row_idx][col_idx - 1] = clean_text(f"{left_clean} {right_clean}")
                raw_rows[row_idx][col_idx] = ""
                cleaned_rows[row_idx][col_idx] = ""
                merged_row_count += 1
        merged_columns.append({"from_col_idx": col_idx, "to_col_idx": col_idx - 1, "merged_row_count": merged_row_count})
    dropped_repaired_cols: list[int] = []
    if raw_rows:
        keep_indices = [col_idx for col_idx in range(len(raw_rows[0])) if any(cleaned_rows[row_idx][col_idx] for row_idx in range(len(cleaned_rows)))]
        dropped_repaired_cols = [col_idx for col_idx in range(len(raw_rows[0])) if col_idx not in keep_indices]
        if dropped_repaired_cols:
            raw_rows = [[row[col_idx] for col_idx in keep_indices] for row in raw_rows]
            cleaned_rows = [[row[col_idx] for col_idx in keep_indices] for row in cleaned_rows]
            source_col_indices = [source_col_indices[col_idx] for col_idx in keep_indices]
            header_rows, body_rows, header_detection = detect_header_rows_with_metadata(
                cleaned_rows,
                row_bounds=header_row_bounds,
                horizontal_rules=header_horizontal_rules,
            )
            body_rows = [row_idx for row_idx in body_rows if row_idx not in suppressed_row_indices]
            row_views = [
                build_row_signature(
                    row_idx,
                    raw_rows[row_idx],
                    first_cell_bbox=first_column_bboxes.get(row_idx),
                    base_x0=base_x0,
                    first_cell_text_x0=first_column_text_x0_by_row.get(row_idx),
                    base_text_x0=base_text_x0,
                )
                for row_idx in body_rows
            ]
    trailing_nondata_after_drop: dict[str, int] | None = None
    raw_rows, cleaned_rows, trailing_nondata_after_drop = _drop_trailing_nondata_column(
        raw_rows,
        cleaned_rows,
        body_rows,
    )
    if trailing_nondata_after_drop is not None:
        source_col_indices = source_col_indices[:-1]
        trailing_nondata_column_repair = trailing_nondata_after_drop
        header_rows, body_rows, header_detection = detect_header_rows_with_metadata(
            cleaned_rows,
            row_bounds=header_row_bounds,
            horizontal_rules=header_horizontal_rules,
        )
        body_rows = [row_idx for row_idx in body_rows if row_idx not in suppressed_row_indices]
        row_views = [
            build_row_signature(
                row_idx,
                raw_rows[row_idx],
                first_cell_bbox=first_column_bboxes.get(row_idx),
                base_x0=base_x0,
                first_cell_text_x0=first_column_text_x0_by_row.get(row_idx),
                base_text_x0=base_text_x0,
            )
            for row_idx in body_rows
        ]
    sparse_nonmatrix_column_repairs: list[dict[str, int]] = []
    raw_rows, cleaned_rows, sparse_nonmatrix_column_repairs = _drop_sparse_nonmatrix_value_columns(
        raw_rows,
        cleaned_rows,
        body_rows,
    )
    if sparse_nonmatrix_column_repairs:
        dropped_sparse_cols = {repair["dropped_col_idx"] for repair in sparse_nonmatrix_column_repairs}
        source_col_indices = [source for col_idx, source in enumerate(source_col_indices) if col_idx not in dropped_sparse_cols]
        header_rows, body_rows, header_detection = detect_header_rows_with_metadata(
            cleaned_rows,
            row_bounds=header_row_bounds,
            horizontal_rules=header_horizontal_rules,
        )
        body_rows = [row_idx for row_idx in body_rows if row_idx not in suppressed_row_indices]
        row_views = [
            build_row_signature(
                row_idx,
                raw_rows[row_idx],
                first_cell_bbox=first_column_bboxes.get(row_idx),
                base_x0=base_x0,
                first_cell_text_x0=first_column_text_x0_by_row.get(row_idx),
                base_text_x0=base_text_x0,
            )
            for row_idx in body_rows
        ]
        raw_rows, cleaned_rows, trailing_nondata_after_drop = _drop_trailing_nondata_column(
            raw_rows,
            cleaned_rows,
            body_rows,
        )
        if trailing_nondata_after_drop is not None:
            source_col_indices = source_col_indices[:-1]
            trailing_nondata_column_repair = trailing_nondata_after_drop
            header_rows, body_rows, header_detection = detect_header_rows_with_metadata(
                cleaned_rows,
                row_bounds=header_row_bounds,
                horizontal_rules=header_horizontal_rules,
            )
            body_rows = [row_idx for row_idx in body_rows if row_idx not in suppressed_row_indices]
            row_views = [
                build_row_signature(
                    row_idx,
                    raw_rows[row_idx],
                    first_cell_bbox=first_column_bboxes.get(row_idx),
                    base_x0=base_x0,
                    first_cell_text_x0=first_column_text_x0_by_row.get(row_idx),
                    base_text_x0=base_text_x0,
                )
                for row_idx in body_rows
            ]
    indent_levels = [row_view.indent_level for row_view in row_views if row_view.indent_level is not None]
    if len(indent_levels) < 3:
        indentation_informative = False
    else:
        baseline = min(indent_levels)
        meaningful_offsets = [level - baseline for level in indent_levels if level - baseline >= 2]
        indentation_informative = len(meaningful_offsets) >= 2 and len(set(indent_levels)) >= 2
    text_cleaning_provenance = summarize_text_cleaning_provenance(raw_rows)

    metadata = {
        **table.metadata,
        "source_page_num": table.page_num,
        "extraction_backend": table.extraction_backend,
        "cleaned_rows": cleaned_rows,
        "dropped_leading_cols": dropped_leading_cols,
        "dropped_trailing_cols": dropped_trailing_cols,
        "source_col_indices": source_col_indices,
        "column_repairs": {
            "merged_columns": merged_columns,
            "split_uncertainty_columns": split_uncertainty_column_repairs,
            "merged_split_label_columns": merged_split_label_columns,
            "embedded_label_count_cells": embedded_label_count_repair,
            "sparse_stub_label_column": sparse_stub_label_column_repair,
            "split_row_label_field_columns": split_row_label_field_repair,
            "vertical_label_continuations": vertical_label_continuation_repair,
            "extra_wide_value_column": extra_wide_value_column_repair,
            "trailing_nondata_column": trailing_nondata_column_repair,
            "sparse_nonmatrix_value_columns": sparse_nonmatrix_column_repairs,
            "dropped_empty_columns_after_repair": dropped_repaired_cols,
        },
        "header_detection": header_detection,
        "indentation_informative": indentation_informative,
        "text_cleaning_provenance": text_cleaning_provenance,
    }
    return NormalizedTable(
        table_id=table.table_id,
        title=table.title,
        caption=table.caption,
        header_rows=header_rows,
        body_rows=body_rows,
        row_views=row_views,
        n_rows=table.n_rows,
        n_cols=len(raw_rows[0]) if raw_rows else 0,
        metadata=metadata,
    )


def normalize_extracted_tables(tables: list[ExtractedTable]) -> list[NormalizedTable]:
    """Normalize a list of extracted tables while preserving input order."""
    return [normalize_extracted_table(table) for table in tables]
