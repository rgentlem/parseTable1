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
BRACKETED_SUMMARY_PATTERN = re.compile(r"^[<>]?\s*-?\d+(?:\.\d+)?\s*[\[\(±].*$")


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


def _looks_like_data_value_cell(value: str) -> bool:
    """Return whether a cell resembles a table value rather than a split label fragment."""
    cleaned = clean_text(value)
    if not cleaned:
        return False
    if detect_value_pattern(cleaned).pattern != "unknown":
        return True
    if BRACKETED_SUMMARY_PATTERN.fullmatch(cleaned):
        return True
    digit_count = sum(char.isdigit() for char in cleaned)
    if digit_count == 0:
        return False
    alpha_count = sum(char.isalpha() for char in cleaned)
    if alpha_count == 0:
        return True
    if cleaned.startswith(("<", ">")) and digit_count > 0:
        return True
    punctuation_count = sum(char in "[]()%±,./<>=-" for char in cleaned)
    return punctuation_count >= 2 and alpha_count <= max(2, digit_count // 2)


def _looks_like_parenthetical_label_fragment(value: str) -> bool:
    """Return whether a short parenthetical token is more likely a label suffix than a data value."""
    cleaned = clean_text(value)
    if not (cleaned.startswith("(") and cleaned.endswith(")")):
        return False
    if "%" in cleaned or "," in cleaned or "±" in cleaned:
        return False
    return any(char.isdigit() for char in cleaned)


def _merge_leading_label_fragments(
    raw_rows: list[list[str]],
    cleaned_rows: list[list[str]],
    body_rows: list[int],
) -> int:
    """Merge leading text fragments back into the first label cell on body rows."""
    offset_value_rows = 0
    for row_idx in body_rows:
        if row_idx >= len(cleaned_rows):
            continue
        row = cleaned_rows[row_idx]
        first_value_col_idx = next(
            (
                col_idx
                for col_idx in range(1, len(row))
                if _looks_like_data_value_cell(row[col_idx])
                and not _looks_like_parenthetical_label_fragment(row[col_idx])
            ),
            None,
        )
        if first_value_col_idx is not None and first_value_col_idx >= 2:
            offset_value_rows += 1
    if offset_value_rows < 2:
        return 0

    repaired_row_count = 0
    for row_idx in body_rows:
        if row_idx >= len(cleaned_rows):
            continue
        row = cleaned_rows[row_idx]
        if len(row) <= 2:
            continue
        first_value_col_idx = next(
            (
                col_idx
                for col_idx in range(1, len(row))
                if _looks_like_data_value_cell(row[col_idx])
                and not _looks_like_parenthetical_label_fragment(row[col_idx])
            ),
            None,
        )
        leading_limit = first_value_col_idx if first_value_col_idx is not None else len(row)
        if leading_limit <= 1:
            continue
        leading_fragments = [
            raw_rows[row_idx][col_idx]
            for col_idx in range(leading_limit)
            if clean_text(raw_rows[row_idx][col_idx])
        ]
        if len(leading_fragments) <= 1:
            continue
        merged_label = " ".join(fragment.strip() for fragment in leading_fragments if fragment.strip()).strip()
        if not merged_label:
            continue
        raw_rows[row_idx][0] = merged_label
        cleaned_rows[row_idx][0] = clean_text(merged_label)
        for col_idx in range(1, leading_limit):
            raw_rows[row_idx][col_idx] = ""
            cleaned_rows[row_idx][col_idx] = ""
        repaired_row_count += 1
    return repaired_row_count


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
    header_rows, body_rows, header_detection = detect_header_rows_with_metadata(
        cleaned_rows,
        row_bounds=row_bounds,
        horizontal_rules=horizontal_rules,
    )
    leading_label_fragment_repairs = _merge_leading_label_fragments(
        raw_rows,
        cleaned_rows,
        body_rows,
    )
    first_column_bboxes: dict[int, tuple[float, float, float, float]] = {}
    x0_values: list[float] = []
    for cell in table.cells:
        if cell.col_idx != dropped_leading_cols or cell.bbox is None or cell.row_idx >= table.n_rows:
            continue
        first_column_bboxes[cell.row_idx] = cell.bbox
        x0_values.append(cell.bbox[0])
    base_x0 = min(x0_values) if x0_values else None
    row_views = [
        build_row_signature(
            row_idx,
            raw_rows[row_idx],
            first_cell_bbox=first_column_bboxes.get(row_idx),
            base_x0=base_x0,
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
                row_bounds=row_bounds,
                horizontal_rules=horizontal_rules,
            )
            row_views = [
                build_row_signature(
                    row_idx,
                    raw_rows[row_idx],
                    first_cell_bbox=first_column_bboxes.get(row_idx),
                    base_x0=base_x0,
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
            "leading_label_fragment_repairs": leading_label_fragment_repairs,
            "merged_columns": merged_columns,
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
