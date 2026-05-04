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
STACKED_CELL_LINE_PATTERN = re.compile(r"(?:\r\n|\r|\n)+")


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
    return bool(cleaned) and bool(ALPHA_PATTERN.search(cleaned)) and len(cleaned) >= 2


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
        if parts and (len(parts) == 1 or len(parts) == expected_width or expected_width % len(parts) == 0)
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

    if not (
        len(shifted_label_rows) >= max(4, row_count // 5)
        and right_value_rows >= max(6, row_count // 3)
        and second_col_nonempty >= max(6, row_count // 3)
        and second_col_label_like >= max(4, second_col_nonempty // 2)
        and second_col_value_like <= max(2, second_col_nonempty // 8)
        and (len(merged_label_rows) + parent_like_rows) >= 2
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
    cleaned_rows = [[clean_text(cell) for cell in row] for row in raw_rows]
    sparse_stub_label_column_repair: dict[str, object] | None = None
    if dropped_leading_cols == 0:
        raw_rows, cleaned_rows, sparse_stub_label_column_repair = _repair_sparse_stub_label_column(
            raw_rows,
            cleaned_rows,
        )
        if sparse_stub_label_column_repair is not None:
            dropped_leading_cols = 1
    split_row_label_field_repair: dict[str, object] | None = None
    if sparse_stub_label_column_repair is None:
        raw_rows, cleaned_rows, split_row_label_field_repair = _repair_split_row_label_field_columns(
            raw_rows,
            cleaned_rows,
        )
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
            and any(clean_text(cell) for cell in row[2:])
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
    suppressed_stub_row_indices = (
        set(sparse_stub_label_column_repair.get("removed_stub_row_indices", []))
        if sparse_stub_label_column_repair is not None
        else set()
    )
    body_rows = [row_idx for row_idx in body_rows if row_idx not in suppressed_stub_row_indices]
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
            header_rows, body_rows, header_detection = detect_header_rows_with_metadata(
                cleaned_rows,
                row_bounds=header_row_bounds,
                horizontal_rules=header_horizontal_rules,
            )
            body_rows = [row_idx for row_idx in body_rows if row_idx not in suppressed_stub_row_indices]
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
        "column_repairs": {
            "merged_columns": merged_columns,
            "merged_split_label_columns": merged_split_label_columns,
            "sparse_stub_label_column": sparse_stub_label_column_repair,
            "split_row_label_field_columns": split_row_label_field_repair,
            "extra_wide_value_column": extra_wide_value_column_repair,
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
