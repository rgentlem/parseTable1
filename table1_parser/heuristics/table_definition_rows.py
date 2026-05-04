"""Deterministic row-variable assembly for TableDefinition."""

from __future__ import annotations

import re

from table1_parser.heuristics.value_pattern_detector import detect_value_pattern
from table1_parser.heuristics.variable_grouper import group_variable_blocks
from table1_parser.normalize.text_normalizer import normalize_label_text
from table1_parser.schemas import DefinedLevel, DefinedVariable, NormalizedTable
from table1_parser.text_cleaning import clean_text


SUMMARY_SUFFIX_PATTERN = re.compile(
    r"(?:\s*,?\s*)?(?:\[\s*)?(?:n\s*\(%\)|no\.\s*\(%\)|mean\s*[±+-]?\s*\(?sd\)?|median\s*\(?iqr\)?|mean\s*\(\s*sd\s*\))(?:\s*\])?$",
    re.IGNORECASE,
)
COUNT_PCT_LABEL_PATTERN = re.compile(r"(?:n|no\.?)\s*\(\s*%\s*\)", re.IGNORECASE)
PAREN_UNITS_PATTERN = re.compile(r"\(([^()]+)\)")
KNOWN_BINARY_LEVELS = {
    frozenset({"male", "female"}),
    frozenset({"yes", "no"}),
    frozenset({"case", "control"}),
    frozenset({"present", "absent"}),
    frozenset({"positive", "negative"}),
}


def build_defined_variables(table: NormalizedTable) -> list[DefinedVariable]:
    """Build value-free variable definitions from a normalized table."""
    row_views_by_idx = {row_view.row_idx: row_view for row_view in table.row_views}
    variables: list[DefinedVariable] = []
    for block in group_variable_blocks(table):
        parent_row = row_views_by_idx[block.variable_row_idx]
        variable_label = block.variable_label
        levels = [
            DefinedLevel(
                level_name=clean_text(row_views_by_idx[row_idx].first_cell_raw),
                level_label=row_views_by_idx[row_idx].first_cell_raw,
                row_idx=row_idx,
                confidence=0.92,
            )
            for row_idx in block.level_row_indices
        ]
        cleaned = clean_text(variable_label)
        without_suffix = SUMMARY_SUFFIX_PATTERN.sub("", cleaned).strip(" ,")
        without_paren_units = PAREN_UNITS_PATTERN.sub("", without_suffix).strip(" ,")
        variable_name = normalize_label_text(without_paren_units) or normalize_label_text(cleaned)
        units_hint = None
        if "," in cleaned:
            suffix = clean_text(cleaned.rsplit(",", maxsplit=1)[-1])
            if suffix and "n (%)" not in suffix.lower() and len(suffix) <= 20:
                units_hint = suffix
        if units_hint is None:
            match = PAREN_UNITS_PATTERN.search(cleaned)
            if match is not None:
                candidate = clean_text(match.group(1))
                if candidate and candidate.lower() not in {"sd", "iqr", "%"} and len(candidate) <= 20:
                    units_hint = candidate
        if levels:
            level_data_patterns: list[str] = []
            for level in levels:
                for cell in row_views_by_idx[level.row_idx].raw_cells[1:]:
                    if not clean_text(cell):
                        continue
                    pattern = detect_value_pattern(cell).pattern
                    if pattern != "p_value":
                        level_data_patterns.append(pattern)
            if level_data_patterns and all(pattern in {"count_pct", "n_only"} for pattern in level_data_patterns):
                summary_style_hint = "count_pct" if "count_pct" in level_data_patterns else "n_only"
            else:
                summary_style_hint = None
        else:
            summary_style_hint = None
            for cell in [cell for cell in parent_row.raw_cells[1:] if clean_text(cell)]:
                pattern = detect_value_pattern(cell).pattern
                if pattern not in {"unknown", "p_value"}:
                    summary_style_hint = pattern
                    break
        one_row_count_pct_indicator = (
            not levels
            and summary_style_hint == "count_pct"
            and COUNT_PCT_LABEL_PATTERN.search(cleaned) is not None
        )
        if one_row_count_pct_indicator:
            variable_type = "binary"
        elif block.variable_kind == "continuous":
            variable_type = "continuous"
        elif block.variable_kind == "binary":
            variable_type = "binary"
        elif levels:
            level_names = {
                normalize_label_text(level.level_name).lower()
                for level in levels
                if normalize_label_text(level.level_name)
            }
            variable_type = "binary" if frozenset(level_names) in KNOWN_BINARY_LEVELS else "categorical"
        else:
            variable_type = "unknown"
        confidence = 0.55
        if variable_type == "continuous":
            confidence = 0.9
        elif variable_type == "binary":
            confidence = 0.95
        elif variable_type == "categorical":
            confidence = 0.92 if levels else 0.75
        variables.append(
            DefinedVariable(
                variable_name=variable_name,
                variable_label=variable_label,
                variable_type=variable_type,
                row_start=block.row_start,
                row_end=block.row_end,
                levels=levels,
                units_hint=units_hint,
                summary_style_hint=summary_style_hint,
                confidence=confidence,
            )
        )
    return variables
