"""Deterministic row classification on top of NormalizedTable row views."""

from __future__ import annotations

import re
from collections.abc import Sequence

from table1_parser.heuristics.column_role_detector import detect_column_roles
from table1_parser.heuristics.level_detector import is_common_level_label, is_likely_level_row
from table1_parser.heuristics.models import RowClassification
from table1_parser.heuristics.value_pattern_detector import detect_value_pattern
from table1_parser.schemas import NormalizedTable, RowView
from table1_parser.text_cleaning import clean_text


CATEGORICAL_PARENT_CUE_PATTERN = re.compile(
    r"(?:n\s*\(%\)|no\.\s*\(%\)|\bpercent\b|\bcategory\b|\blevel\b)",
    re.IGNORECASE,
)
COUNT_LABEL_PATTERN = re.compile(r"^(?:n|number|no\.?)$", re.IGNORECASE)
INLINE_CATEGORY_SUMMARY_PATTERN = re.compile(r"\b(?:male|female)\b", re.IGNORECASE)
INDICATOR_VARIABLE_LABEL_PATTERN = re.compile(r"(?:=|[._]cat\b|\bindicator\b)", re.IGNORECASE)
NA_LIKE_VALUE_PATTERN = re.compile(r"^(?:N/?A|NR|not reported)$", re.IGNORECASE)
CONTINUOUS_TEXT_CUE_PATTERN = re.compile(
    r"(?:\bmean\b|\bsd\b|\bmedian\b|\biqr\b|mean\s*[±+-]\s*sd|mean\s*\(\s*sd\s*\))",
    re.IGNORECASE,
)
DECIMAL_SUMMARY_PATTERN = re.compile(
    r"^\s*[<>]?\d+\.\d+\s*(?:\(\s*[<>]?\d+(?:\.\d+)?(?:\s*[,/-]\s*[<>]?\d+(?:\.\d+)?)?\s*\))?\s*$"
)
INTERVAL_SUMMARY_PATTERN = re.compile(
    r"^-?\d+(?:\.\d+)?\s*[\(\[]\s*-?\d+(?:\.\d+)?\s*,\s*-?\d+(?:\.\d+)?\s*[\)\]]$"
)
INTEGER_VALUE_PATTERN = re.compile(r"^\s*\d+\s*$")
COUNT_LIKE_VALUE_PATTERN = re.compile(r"^\s*\d[\d,]*\s*$")


def _trailing_cells(row_view: RowView) -> list[str]:
    """Return populated trailing cells after the first label column."""
    return [clean_text(cell) for cell in row_view.raw_cells[1:] if clean_text(cell)]


def _has_categorical_parent_cue(row_view: RowView) -> bool:
    """Return whether the row text explicitly signals a categorical parent."""
    label_text = " ".join(clean_text(cell) for cell in row_view.raw_cells[:3] if clean_text(cell))
    return bool(CATEGORICAL_PARENT_CUE_PATTERN.search(label_text))


def _summary_like_trailing_count(trailing_cells: Sequence[str]) -> int:
    """Count trailing cells that look like summary statistics rather than category counts."""
    return sum(
        "±" in cell
        or detect_value_pattern(cell).pattern in {"mean_sd", "median_iqr"}
        or bool(DECIMAL_SUMMARY_PATTERN.match(cell))
        for cell in trailing_cells
    )


def _has_strong_continuous_cue(row_view: RowView) -> bool:
    """Return whether the row explicitly names a summary-statistic format."""
    return bool(CONTINUOUS_TEXT_CUE_PATTERN.search(row_view.first_cell_raw))


def _has_strong_continuous_layout(row_view: RowView) -> bool:
    """Return whether the row strongly resembles a one-line continuous summary."""
    return _has_strong_continuous_cue(row_view) or _summary_like_trailing_count(_trailing_cells(row_view)) >= 2


def _looks_like_indented_numeric_matrix_level(
    row_view: RowView,
    parent_row_view: RowView | None,
    statistic_col_indices: set[int] | None,
) -> bool:
    """Return whether an indented row looks like a level in a numeric matrix table."""
    if not _is_more_indented(row_view, parent_row_view):
        return False
    label = row_view.first_cell_normalized
    if not label or _has_strong_continuous_cue(row_view):
        return False
    if "," in row_view.first_cell_raw or "(" in row_view.first_cell_raw or ")" in row_view.first_cell_raw:
        return False
    word_count = len(label.split())
    if word_count > 5 or len(label) > 48:
        return False
    trailing_cells = [
        clean_text(row_view.raw_cells[col_idx])
        for col_idx in range(1, len(row_view.raw_cells))
        if col_idx not in (statistic_col_indices or set()) and clean_text(row_view.raw_cells[col_idx])
    ]
    if len(trailing_cells) < 2:
        return False
    value_like_count = sum(
        (any(char.isdigit() for char in cell) and not any(char.isalpha() for char in cell))
        or NA_LIKE_VALUE_PATTERN.fullmatch(cell) is not None
        for cell in trailing_cells
    )
    return value_like_count >= max(2, int(len(trailing_cells) * 0.6))


def _is_more_indented(row_view: RowView, reference_row: RowView | None) -> bool:
    """Return whether a row is more indented than a nearby reference row."""
    return (
        reference_row is not None
        and row_view.indent_level is not None
        and reference_row.indent_level is not None
        and row_view.indent_level > reference_row.indent_level
    )


def indentation_is_informative(table: NormalizedTable) -> bool:
    """Return whether indentation should influence heuristics for this table."""
    configured = table.metadata.get("indentation_informative")
    if isinstance(configured, bool):
        return configured
    indent_levels = [row_view.indent_level for row_view in table.row_views if row_view.indent_level is not None]
    if len(indent_levels) < 3:
        return False
    baseline = min(indent_levels)
    meaningful_offsets = [level - baseline for level in indent_levels if level - baseline >= 2]
    if len(meaningful_offsets) < 2:
        return False
    return len(set(indent_levels)) >= 2


def _looks_scalar_count_row(
    row_view: RowView,
    child_level_count: int = 0,
    has_categorical_parent_cue: bool = False,
) -> bool:
    """Return whether a short label with integer counts should behave as a one-row variable."""
    label = row_view.first_cell_normalized
    trailing_cells = _trailing_cells(row_view)
    integer_only_count = sum(bool(INTEGER_VALUE_PATTERN.match(cell)) for cell in trailing_cells)
    word_count = len(label.split())
    return (
        row_view.has_trailing_values
        and bool(trailing_cells)
        and child_level_count == 0
        and not has_categorical_parent_cue
        and not _has_strong_continuous_layout(row_view)
        and not is_common_level_label(label)
        and word_count <= 2
        and len(label) <= 16
        and integer_only_count == len(trailing_cells)
    )


def classify_row(
    row_view: RowView,
    previous_classification: str | None = None,
    previous_row_view: RowView | None = None,
    active_parent_row_view: RowView | None = None,
    active_parent_level_count: int = 0,
    active_parent_requires_indented_levels: bool = False,
    next_row_view: RowView | None = None,
    following_row_views: Sequence[RowView] | None = None,
    indentation_informative: bool = True,
    statistic_col_indices: set[int] | None = None,
) -> RowClassification:
    """Classify a normalized body row conservatively."""
    label = row_view.first_cell_normalized
    word_count = len(label.split())
    trailing_cells = _trailing_cells(row_view)
    trailing_numeric = sum(any(char.isdigit() for char in cell) for cell in row_view.raw_cells[1:] if cell)
    populated_trailing_col_indices = {
        col_idx
        for col_idx in range(1, len(row_view.raw_cells))
        if clean_text(row_view.raw_cells[col_idx])
    }
    non_statistic_col_indices = {
        col_idx for col_idx in range(1, len(row_view.raw_cells)) if col_idx not in (statistic_col_indices or set())
    }
    non_statistic_trailing_cells = [
        clean_text(row_view.raw_cells[col_idx])
        for col_idx in range(1, len(row_view.raw_cells))
        if clean_text(row_view.raw_cells[col_idx]) and col_idx not in (statistic_col_indices or set())
    ]
    has_only_statistic_values = bool(populated_trailing_col_indices) and bool(statistic_col_indices) and populated_trailing_col_indices.issubset(statistic_col_indices)
    has_statistic_values = bool(populated_trailing_col_indices.intersection(statistic_col_indices or set()))
    has_data_and_statistic_values = bool(non_statistic_trailing_cells) and has_statistic_values
    all_non_statistic_columns_populated = bool(non_statistic_col_indices) and non_statistic_col_indices.issubset(populated_trailing_col_indices)
    next_is_level_like = bool(
        next_row_view and is_likely_level_row(next_row_view, statistic_col_indices=statistic_col_indices)
    )
    categorical_parent_cue = _has_categorical_parent_cue(row_view)
    explicit_indicator_label = INDICATOR_VARIABLE_LABEL_PATTERN.search(row_view.first_cell_raw) is not None
    child_level_count = 0
    for next_row in following_row_views or []:
        if is_likely_level_row(next_row, statistic_col_indices=statistic_col_indices):
            child_level_count += 1
            continue
        if (
            child_level_count > 0
            or not next_row.has_trailing_values
            or _has_categorical_parent_cue(next_row)
            or _has_strong_continuous_cue(next_row)
        ):
            break
    indented_child_level_count = (
        sum(
            1
            for next_row in following_row_views or []
            if is_likely_level_row(next_row, statistic_col_indices=statistic_col_indices)
            and _is_more_indented(next_row, row_view)
        )
        if indentation_informative
        else 0
    )
    indented_numeric_matrix_child_level_count = 0
    if indentation_informative:
        for next_row in following_row_views or []:
            if not _is_more_indented(next_row, row_view):
                if indented_numeric_matrix_child_level_count > 0:
                    break
                continue
            if _looks_like_indented_numeric_matrix_level(next_row, row_view, statistic_col_indices):
                indented_numeric_matrix_child_level_count += 1
                continue
            if indented_numeric_matrix_child_level_count > 0:
                break
    strong_continuous_layout = _has_strong_continuous_layout(row_view)
    sparse_trailing = len(trailing_cells) <= 1
    more_indented_than_previous = indentation_informative and _is_more_indented(row_view, previous_row_view)
    looks_n_count_row = (
        row_view.has_trailing_values
        and bool(trailing_cells)
        and COUNT_LABEL_PATTERN.fullmatch(label.strip()) is not None
        and sum(bool(COUNT_LIKE_VALUE_PATTERN.match(cell)) for cell in trailing_cells) >= max(1, len(trailing_cells) - 1)
        and child_level_count <= 1
        and not categorical_parent_cue
        and not strong_continuous_layout
    )
    looks_inline_category_summary = (
        row_view.has_trailing_values
        and bool(trailing_cells)
        and INLINE_CATEGORY_SUMMARY_PATTERN.search(row_view.first_cell_raw) is not None
        and ("%" in row_view.first_cell_raw or "=" in row_view.first_cell_raw)
        and child_level_count == 0
        and previous_classification not in {"variable_header", "level_row"}
        and not strong_continuous_layout
    )
    has_continuous_cue = (
        bool(CONTINUOUS_TEXT_CUE_PATTERN.search(row_view.first_cell_raw))
        or bool(CONTINUOUS_TEXT_CUE_PATTERN.search(" ".join(trailing_cells)))
        or (
            bool(trailing_cells)
            and _summary_like_trailing_count(trailing_cells) >= max(1, len(trailing_cells) // 2 + 1)
        )
    )
    non_statistic_trailing_patterns = [
        detect_value_pattern(cell).pattern for cell in non_statistic_trailing_cells
    ]
    count_like_non_stat_count = sum(
        pattern in {"count_pct", "n_only"} for pattern in non_statistic_trailing_patterns
    )
    p_value_non_stat_count = sum(pattern == "p_value" for pattern in non_statistic_trailing_patterns)
    interval_non_stat_count = sum(
        bool(INTERVAL_SUMMARY_PATTERN.fullmatch(cell)) for cell in non_statistic_trailing_cells
    )
    count_like_level_row = is_likely_level_row(row_view, statistic_col_indices=statistic_col_indices)
    top_level_common_level_indicator = (
        is_common_level_label(label)
        and previous_classification not in {"variable_header", "level_row"}
        and active_parent_row_view is None
        and child_level_count == 0
    )
    looks_like_interval_summary_row = (
        row_view.has_trailing_values
        and len(non_statistic_trailing_cells) >= 2
        and all_non_statistic_columns_populated
        and interval_non_stat_count == len(non_statistic_trailing_cells)
        and has_data_and_statistic_values
        and not categorical_parent_cue
        and not is_common_level_label(label)
    )
    non_data_parent_trailing = (
        bool(trailing_cells)
        and trailing_numeric == 0
        and count_like_non_stat_count == 0
        and not strong_continuous_layout
        and not any(any(char.isalpha() for char in cell) for cell in trailing_cells)
    )
    looks_like_binary_variable_row = (
        row_view.has_trailing_values
        and len(non_statistic_trailing_cells) >= 2
        and count_like_non_stat_count >= 2
        and count_like_non_stat_count + p_value_non_stat_count == len(non_statistic_trailing_patterns)
        and (not categorical_parent_cue or explicit_indicator_label)
        and not strong_continuous_layout
        and not has_continuous_cue
        and not has_only_statistic_values
        and (not is_common_level_label(label) or top_level_common_level_indicator)
        and not looks_n_count_row
        and (
            active_parent_row_view is None
            or explicit_indicator_label
            or (
                indentation_informative
                and active_parent_level_count >= 1
                and active_parent_requires_indented_levels
                and not _is_more_indented(row_view, active_parent_row_view)
            )
        )
    )
    looks_like_indented_count_level_continuation = (
        row_view.has_trailing_values
        and indentation_informative
        and active_parent_row_view is not None
        and active_parent_requires_indented_levels
        and _is_more_indented(row_view, active_parent_row_view)
        and len(non_statistic_trailing_patterns) >= 2
        and count_like_non_stat_count >= len(non_statistic_trailing_patterns) - 1
        and not categorical_parent_cue
        and not strong_continuous_layout
        and not has_only_statistic_values
    )
    looks_like_level_continuation = (
        row_view.has_trailing_values
        and not categorical_parent_cue
        and not strong_continuous_layout
        and (
            not has_data_and_statistic_values
            or previous_classification in {"variable_header", "level_row"}
        )
        and not has_only_statistic_values
        and (count_like_level_row or looks_like_indented_count_level_continuation)
        and not looks_like_binary_variable_row
        and not _looks_scalar_count_row(
            row_view,
            child_level_count=child_level_count,
            has_categorical_parent_cue=categorical_parent_cue,
        )
        and not (sparse_trailing and child_level_count >= 2 and trailing_numeric > 0)
    )
    looks_like_indented_numeric_matrix_level_continuation = (
        indentation_informative
        and previous_classification in {"variable_header", "level_row"}
        and active_parent_row_view is not None
        and row_view.has_trailing_values
        and _looks_like_indented_numeric_matrix_level(row_view, active_parent_row_view, statistic_col_indices)
    )

    if looks_like_binary_variable_row:
        return RowClassification(
            row_idx=row_view.row_idx,
            classification="binary_variable_row",
            confidence=0.9,
        )

    if looks_like_interval_summary_row:
        return RowClassification(
            row_idx=row_view.row_idx,
            classification="continuous_variable_row",
            confidence=0.9,
        )

    if (
        previous_classification in {"variable_header", "level_row"}
        and looks_like_level_continuation
        and not (
            indentation_informative
            and active_parent_requires_indented_levels
            and active_parent_row_view is not None
            and not _is_more_indented(row_view, active_parent_row_view)
        )
    ):
        return RowClassification(
            row_idx=row_view.row_idx,
            classification="level_row",
            confidence=0.94 if more_indented_than_previous else (0.92 if is_common_level_label(label) else 0.78),
        )

    if looks_like_indented_numeric_matrix_level_continuation:
        return RowClassification(
            row_idx=row_view.row_idx,
            classification="level_row",
            confidence=0.86,
        )

    if strong_continuous_layout and row_view.has_trailing_values:
        return RowClassification(
            row_idx=row_view.row_idx,
            classification="continuous_variable_row",
            confidence=0.92,
        )

    if looks_n_count_row:
        return RowClassification(
            row_idx=row_view.row_idx,
            classification="continuous_variable_row",
            confidence=0.84,
        )

    if looks_inline_category_summary:
        return RowClassification(
            row_idx=row_view.row_idx,
            classification="continuous_variable_row",
            confidence=0.82,
        )

    if (
        is_common_level_label(label)
        and count_like_level_row
        and not has_only_statistic_values
        and not has_data_and_statistic_values
    ):
        return RowClassification(
            row_idx=row_view.row_idx,
            classification="level_row",
            confidence=0.9,
        )

    if categorical_parent_cue or (
        sparse_trailing
        and child_level_count >= 1
        and (not row_view.has_trailing_values or trailing_numeric > 0 or non_data_parent_trailing)
    ) or (
        not strong_continuous_layout and child_level_count >= 2
        and (not row_view.has_trailing_values or trailing_numeric > 0 or non_data_parent_trailing)
    ) or (
        sparse_trailing
        and indented_child_level_count >= 2
    ) or (
        sparse_trailing
        and indented_numeric_matrix_child_level_count >= 2
    ):
        return RowClassification(
            row_idx=row_view.row_idx,
            classification="variable_header",
            confidence=(
                0.9
                if categorical_parent_cue and child_level_count >= 2
                else (0.88 if indented_child_level_count >= 2 or indented_numeric_matrix_child_level_count >= 2 else 0.84)
            ),
        )

    if (
        row_view.has_trailing_values
        and bool(trailing_cells)
        and (strong_continuous_layout or child_level_count < 2)
        and not categorical_parent_cue
        and has_continuous_cue
        and (
            trailing_numeric >= max(2, len(trailing_cells) // 2 + 1)
            or (len(trailing_cells) == 1 and "(" in trailing_cells[0])
        )
        and not is_common_level_label(label)
    ):
        return RowClassification(
            row_idx=row_view.row_idx,
            classification="continuous_variable_row",
            confidence=0.88,
        )

    if _looks_scalar_count_row(
        row_view,
        child_level_count=child_level_count,
        has_categorical_parent_cue=categorical_parent_cue,
    ):
        return RowClassification(
            row_idx=row_view.row_idx,
            classification="continuous_variable_row",
            confidence=0.8,
        )

    if not row_view.has_trailing_values:
        if next_is_level_like:
            return RowClassification(
                row_idx=row_view.row_idx,
                classification="variable_header",
                confidence=0.86,
            )
        if word_count <= 5 and not is_common_level_label(label):
            return RowClassification(
                row_idx=row_view.row_idx,
                classification="section_header",
                confidence=0.72,
            )

    if row_view.has_trailing_values and trailing_numeric > 0 and trailing_numeric <= 2 and next_is_level_like:
        return RowClassification(
            row_idx=row_view.row_idx,
            classification="variable_header",
            confidence=0.78,
        )

    if (
        previous_classification == "variable_header"
        and row_view.has_trailing_values
        and trailing_numeric > 0
        and word_count <= 4
        and not has_only_statistic_values
    ):
        return RowClassification(
            row_idx=row_view.row_idx,
            classification="level_row",
            confidence=0.7,
        )

    return RowClassification(row_idx=row_view.row_idx, classification="unknown", confidence=0.45)


def classify_rows(table: NormalizedTable) -> list[RowClassification]:
    """Classify all normalized body rows in order."""
    classifications: list[RowClassification] = []
    indentation_informative = indentation_is_informative(table)
    statistic_col_indices = {
        guess.col_idx for guess in detect_column_roles(table) if guess.role in {"p_value", "smd"}
    }
    active_parent_row_view: RowView | None = None
    active_parent_level_count = 0
    active_parent_requires_indented_levels = False
    for index, row_view in enumerate(table.row_views):
        previous = classifications[-1].classification if classifications else None
        previous_row = table.row_views[index - 1] if index > 0 else None
        next_row = table.row_views[index + 1] if index + 1 < len(table.row_views) else None
        classification = classify_row(
            row_view,
            previous_classification=previous,
            previous_row_view=previous_row,
            active_parent_row_view=active_parent_row_view,
            active_parent_level_count=active_parent_level_count,
            active_parent_requires_indented_levels=active_parent_requires_indented_levels,
            next_row_view=next_row,
            following_row_views=table.row_views[index + 1 :],
            indentation_informative=indentation_informative,
            statistic_col_indices=statistic_col_indices,
        )
        classifications.append(classification)
        if classification.classification == "variable_header":
            active_parent_row_view = row_view
            active_parent_level_count = 0
            active_parent_requires_indented_levels = False
        elif classification.classification == "level_row":
            active_parent_level_count += 1
            if (
                indentation_informative
                and active_parent_row_view is not None
                and _is_more_indented(row_view, active_parent_row_view)
            ):
                active_parent_requires_indented_levels = True
        else:
            active_parent_row_view = None
            active_parent_level_count = 0
            active_parent_requires_indented_levels = False
    return classifications
