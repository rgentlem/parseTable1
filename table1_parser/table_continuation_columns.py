"""Column compatibility checks for explicitly identified table continuations."""

from __future__ import annotations

import re
from collections import defaultdict
from statistics import median
from typing import Any

from table1_parser.schemas import ExtractedTable, NormalizedTable, TableProfile
from table1_parser.schemas.table_continuation_column_check import (
    ColumnCoordinateMapEntry,
    ColumnCoordinateProfile,
    TableContinuationColumnCheck,
)


TABLE_NUMBER_PATTERN = re.compile(r"\btable\s*(\d+)\b", re.IGNORECASE)
CONTINUATION_PATTERN = re.compile(r"\bcont(?:inued)?\.?\b|\(\s*continued\s*\)", re.IGNORECASE)
SAMPLE_SIZE_PATTERN = re.compile(r"\(?\s*n\s*=\s*[0-9,]+\s*\)?", re.IGNORECASE)
MARKUP_PATTERN = re.compile(r"[*_`]+")
SPACE_PATTERN = re.compile(r"\s+")


def build_table_continuation_column_checks(
    normalized_tables: list[NormalizedTable],
    extracted_tables: list[ExtractedTable] | None = None,
    table_profiles: list[TableProfile] | None = None,
    table_categories: list[str | None] | None = None,
) -> list[TableContinuationColumnCheck]:
    """Build column-compatibility diagnostics for explicit demographic-table continuations."""
    checks: list[TableContinuationColumnCheck] = []
    latest_fragment_by_number: dict[int, int] = {}

    for table_index, table in enumerate(normalized_tables):
        continuation_number = _clear_continuation_table_number(table)
        if continuation_number is None:
            table_number = _table_number(table)
            if table_number is not None:
                latest_fragment_by_number[table_number] = table_index
            continue

        base_index = latest_fragment_by_number.get(continuation_number)
        if base_index is None:
            for prior_index in range(table_index - 1, -1, -1):
                if _table_number(normalized_tables[prior_index]) == continuation_number:
                    base_index = prior_index
                    break

        if not _continuation_pair_is_demographic(
            table_profiles,
            table_categories,
            base_index,
            table_index,
        ):
            latest_fragment_by_number[continuation_number] = table_index
            continue

        checks.append(
            _build_column_check(
                check_id=f"table_continuation_column_check_{len(checks)}",
                table_number=continuation_number,
                normalized_tables=normalized_tables,
                extracted_tables=extracted_tables,
                table_profiles=table_profiles,
                table_categories=table_categories,
                base_index=base_index,
                continuation_index=table_index,
            )
        )
        latest_fragment_by_number[continuation_number] = table_index

    return checks


def table_continuation_column_checks_to_payload(
    checks: list[TableContinuationColumnCheck],
) -> list[dict[str, object]]:
    """Serialize continuation column checks as JSON-friendly records."""
    return [check.model_dump(mode="json") for check in checks]


def _build_column_check(
    *,
    check_id: str,
    table_number: int,
    normalized_tables: list[NormalizedTable],
    extracted_tables: list[ExtractedTable] | None,
    table_profiles: list[TableProfile] | None,
    table_categories: list[str | None] | None,
    base_index: int | None,
    continuation_index: int,
) -> TableContinuationColumnCheck:
    continuation_table = normalized_tables[continuation_index]
    continuation_extracted = _extracted_table_at(extracted_tables, continuation_index)
    continuation_profile = _build_coordinate_profile(continuation_table, continuation_extracted)

    if base_index is None:
        return TableContinuationColumnCheck(
            check_id=check_id,
            table_number=table_number,
            continuation_table_index=continuation_index,
            continuation_table_id=continuation_table.table_id,
            continuation_page_num=_source_page_num(continuation_table),
            continuation_n_cols=continuation_table.n_cols,
            continuation_table_family=_table_family_at(table_profiles, continuation_index),
            continuation_table_category=_table_category_at(table_categories, continuation_index),
            header_signature_status="missing_base",
            continuation_column_signature=_column_signature(continuation_table),
            coordinate_status="missing",
            overall_status="no_parent",
            confidence=0.0,
            continuation_coordinate_profile=continuation_profile,
            diagnostics=["explicit_continuation_has_no_prior_fragment_for_table_number"],
        )

    base_table = normalized_tables[base_index]
    base_extracted = _extracted_table_at(extracted_tables, base_index)
    base_profile = _build_coordinate_profile(base_table, base_extracted)
    base_signature = _column_signature(base_table)
    continuation_signature = _column_signature(continuation_table)
    signature_status = _header_signature_status(base_signature, continuation_signature)
    normalized_column_count_match = base_table.n_cols == continuation_table.n_cols
    coordinate_status, column_map, coordinate_diagnostics = _compare_coordinate_profiles(base_profile, continuation_profile)
    diagnostics = [*coordinate_diagnostics]

    if not normalized_column_count_match:
        diagnostics.append(
            f"normalized_column_count_mismatch:base={base_table.n_cols}:continuation={continuation_table.n_cols}"
        )
    if signature_status == "mismatch":
        diagnostics.append(
            f"header_signature_mismatch:base={base_signature}:continuation={continuation_signature}"
        )

    overall_status = "incompatible"
    confidence = 0.2
    if normalized_column_count_match and coordinate_status == "compatible":
        overall_status = "compatible"
        confidence = 0.95 if signature_status in {"match", "missing_continuation"} else 0.82
    elif normalized_column_count_match and coordinate_status == "possibly_compatible":
        overall_status = "possibly_compatible"
        confidence = 0.75 if signature_status in {"match", "missing_continuation"} else 0.6
    elif normalized_column_count_match and coordinate_status in {"missing", "partial"} and signature_status == "match":
        overall_status = "possibly_compatible"
        confidence = 0.65
    elif normalized_column_count_match and coordinate_status == "missing" and signature_status == "missing_continuation":
        overall_status = "possibly_compatible"
        confidence = 0.45

    return TableContinuationColumnCheck(
        check_id=check_id,
        table_number=table_number,
        base_table_index=base_index,
        continuation_table_index=continuation_index,
        base_table_id=base_table.table_id,
        continuation_table_id=continuation_table.table_id,
        base_page_num=_source_page_num(base_table),
        continuation_page_num=_source_page_num(continuation_table),
        base_n_cols=base_table.n_cols,
        continuation_n_cols=continuation_table.n_cols,
        base_table_family=_table_family_at(table_profiles, base_index),
        continuation_table_family=_table_family_at(table_profiles, continuation_index),
        base_table_category=_table_category_at(table_categories, base_index),
        continuation_table_category=_table_category_at(table_categories, continuation_index),
        normalized_column_count_match=normalized_column_count_match,
        header_signature_status=signature_status,
        base_column_signature=base_signature,
        continuation_column_signature=continuation_signature,
        coordinate_status=coordinate_status,
        overall_status=overall_status,
        confidence=confidence,
        column_map=column_map,
        base_coordinate_profile=base_profile,
        continuation_coordinate_profile=continuation_profile,
        diagnostics=diagnostics,
    )


def _continuation_pair_is_demographic(
    table_profiles: list[TableProfile] | None,
    table_categories: list[str | None] | None,
    base_index: int | None,
    continuation_index: int,
) -> bool:
    if table_categories is not None:
        return _table_category_at(table_categories, base_index) == "demographic_description" or (
            _table_category_at(table_categories, continuation_index) == "demographic_description"
        )
    if table_profiles is None:
        return True
    return _table_family_at(table_profiles, base_index) == "descriptive_characteristics" or (
        _table_family_at(table_profiles, continuation_index) == "descriptive_characteristics"
    )


def _table_family_at(table_profiles: list[TableProfile] | None, table_index: int | None) -> str | None:
    if table_profiles is None or table_index is None or table_index >= len(table_profiles):
        return None
    return table_profiles[table_index].table_family


def _table_category_at(table_categories: list[str | None] | None, table_index: int | None) -> str | None:
    if table_categories is None or table_index is None or table_index >= len(table_categories):
        return None
    return table_categories[table_index]


def _clear_continuation_table_number(table: NormalizedTable) -> int | None:
    metadata_number = table.metadata.get("continuation_of_table_number")
    if isinstance(metadata_number, int):
        if table.metadata.get("is_continuation") is True or _has_continuation_text(table):
            return metadata_number

    text = " ".join(part for part in [table.title, table.caption] if part)
    if not CONTINUATION_PATTERN.search(text):
        rows = table.metadata.get("cleaned_rows")
        if isinstance(rows, list) and rows:
            first_row_text = " ".join(str(cell) for cell in rows[0] if cell)
            if not CONTINUATION_PATTERN.search(first_row_text):
                return None
        else:
            return None

    match = TABLE_NUMBER_PATTERN.search(text)
    if match is not None:
        return int(match.group(1))
    table_number = _table_number(table)
    return table_number if table_number is not None else None


def _has_continuation_text(table: NormalizedTable) -> bool:
    text = " ".join(part for part in [table.title, table.caption] if part)
    if CONTINUATION_PATTERN.search(text):
        return True
    rows = table.metadata.get("cleaned_rows")
    if isinstance(rows, list) and rows:
        first_row_text = " ".join(str(cell) for cell in rows[0] if cell)
        return bool(CONTINUATION_PATTERN.search(first_row_text))
    return False


def _table_number(table: NormalizedTable) -> int | None:
    metadata_number = table.metadata.get("table_number")
    if isinstance(metadata_number, int):
        return metadata_number
    text = " ".join(part for part in [table.title, table.caption] if part)
    match = TABLE_NUMBER_PATTERN.search(text)
    return int(match.group(1)) if match is not None else None


def _source_page_num(table: NormalizedTable) -> int | None:
    value = table.metadata.get("source_page_num")
    return value if isinstance(value, int) and value >= 1 else None


def _extracted_table_at(
    extracted_tables: list[ExtractedTable] | None,
    table_index: int,
) -> ExtractedTable | None:
    if extracted_tables is None or table_index >= len(extracted_tables):
        return None
    return extracted_tables[table_index]


def _column_signature(table: NormalizedTable) -> list[str]:
    rows = table.metadata.get("cleaned_rows")
    if not isinstance(rows, list):
        return []
    header_rows = table.header_rows or list(range(min(2, len(rows))))
    usable_header_rows: list[list[str]] = []
    for row_idx in header_rows:
        if row_idx >= len(rows) or not isinstance(rows[row_idx], list):
            continue
        cleaned_row = [str(cell) for cell in rows[row_idx]]
        nonempty = [cell for cell in cleaned_row if cell.strip()]
        if len(nonempty) == 1 and CONTINUATION_PATTERN.search(nonempty[0]):
            continue
        usable_header_rows.append(cleaned_row)
    if not usable_header_rows:
        return []
    width = max(len(row) for row in usable_header_rows)
    signature: list[str] = []
    for col_idx in range(width):
        pieces = [row[col_idx] for row in usable_header_rows if col_idx < len(row) and row[col_idx].strip()]
        signature.append(_normalize_header_cell(" ".join(pieces)))
    return signature


def _normalize_header_cell(text: str) -> str:
    normalized = MARKUP_PATTERN.sub("", text)
    normalized = normalized.replace("\u00a0", " ").replace("\u2009", " ").replace("\u202f", " ")
    normalized = SAMPLE_SIZE_PATTERN.sub("", normalized)
    normalized = SPACE_PATTERN.sub(" ", normalized).strip().lower()
    normalized = normalized.strip(" .,:;")
    normalized = re.sub(r"\bp\s*[-–—]?\s*value\b", "p_value", normalized)
    normalized = re.sub(r"\bvariables?\b|\bcharacteristics?\b", "variable", normalized)
    return SPACE_PATTERN.sub(" ", normalized).strip()


def _header_signature_status(base_signature: list[str], continuation_signature: list[str]) -> str:
    if not base_signature and not continuation_signature:
        return "missing_both"
    if not base_signature:
        return "missing_base"
    if not continuation_signature:
        return "missing_continuation"
    return "match" if base_signature == continuation_signature else "mismatch"


def _build_coordinate_profile(
    normalized_table: NormalizedTable,
    extracted_table: ExtractedTable | None,
) -> ColumnCoordinateProfile:
    warnings: list[str] = []
    column_bboxes, source = _column_bboxes_from_extracted(extracted_table)
    if not column_bboxes:
        column_bboxes, source = _column_bboxes_from_metadata(normalized_table)

    if not column_bboxes:
        return ColumnCoordinateProfile(
            table_id=normalized_table.table_id,
            normalized_n_cols=normalized_table.n_cols,
            coordinate_n_cols=0,
            coordinate_source="none",
            evidence_quality="missing",
            warnings=["no_cell_bounding_boxes_available"],
        )

    selected_columns = _selected_original_columns(normalized_table, max(column_bboxes) + 1)
    if len(selected_columns) != normalized_table.n_cols:
        warnings.append(
            f"coordinate_column_count_differs_from_normalized_grid:coordinates={len(selected_columns)}:"
            f"normalized={normalized_table.n_cols}"
        )
    repairs = normalized_table.metadata.get("column_repairs")
    if isinstance(repairs, dict) and repairs.get("extra_wide_value_column"):
        warnings.append("coordinate_profile_unreliable_after_extra_wide_value_column_repair")
    if isinstance(repairs, dict) and repairs.get("split_row_label_field_columns"):
        warnings.append("coordinate_profile_approximate_after_split_row_label_field_repair")

    column_metrics: list[tuple[float, float, float, float] | None] = []
    for original_col_idx in selected_columns:
        bboxes = column_bboxes.get(original_col_idx, [])
        if not bboxes:
            column_metrics.append(None)
            continue
        left = median([bbox[0] for bbox in bboxes])
        right = median([bbox[2] for bbox in bboxes])
        center = (left + right) / 2.0
        width = max(0.0, right - left)
        column_metrics.append((left, center, right, width))

    present_metrics = [metric for metric in column_metrics if metric is not None]
    if not present_metrics:
        return ColumnCoordinateProfile(
            table_id=normalized_table.table_id,
            normalized_n_cols=normalized_table.n_cols,
            coordinate_n_cols=0,
            coordinate_source=source,
            evidence_quality="missing",
            warnings=[*warnings, "no_selected_columns_have_bounding_boxes"],
        )

    table_bbox = _bbox_from_value(normalized_table.metadata.get("bbox"))
    table_left = table_bbox[0] if table_bbox is not None else min(metric[0] for metric in present_metrics)
    table_right = table_bbox[2] if table_bbox is not None else max(metric[2] for metric in present_metrics)
    table_width = table_right - table_left
    if table_width <= 0:
        table_left = min(metric[0] for metric in present_metrics)
        table_right = max(metric[2] for metric in present_metrics)
        table_width = max(1.0, table_right - table_left)

    normalized_lefts: list[float | None] = []
    normalized_centers: list[float | None] = []
    normalized_rights: list[float | None] = []
    normalized_widths: list[float | None] = []
    for metric in column_metrics:
        if metric is None:
            normalized_lefts.append(None)
            normalized_centers.append(None)
            normalized_rights.append(None)
            normalized_widths.append(None)
            continue
        left, center, right, width = metric
        normalized_lefts.append(round((left - table_left) / table_width, 5))
        normalized_centers.append(round((center - table_left) / table_width, 5))
        normalized_rights.append(round((right - table_left) / table_width, 5))
        normalized_widths.append(round(width / table_width, 5))

    coordinate_n_cols = sum(center is not None for center in normalized_centers)
    evidence_quality = "strong" if coordinate_n_cols == normalized_table.n_cols and not warnings else "partial"
    return ColumnCoordinateProfile(
        table_id=normalized_table.table_id,
        normalized_n_cols=normalized_table.n_cols,
        coordinate_n_cols=coordinate_n_cols,
        coordinate_source=source,
        evidence_quality=evidence_quality,
        table_left=round(table_left, 4),
        table_right=round(table_right, 4),
        normalized_lefts=normalized_lefts,
        normalized_centers=normalized_centers,
        normalized_rights=normalized_rights,
        normalized_widths=normalized_widths,
        warnings=warnings,
    )


def _column_bboxes_from_extracted(
    extracted_table: ExtractedTable | None,
) -> tuple[dict[int, list[tuple[float, float, float, float]]], str]:
    if extracted_table is None:
        return {}, "none"
    column_bboxes: dict[int, list[tuple[float, float, float, float]]] = defaultdict(list)
    for cell in extracted_table.cells:
        if cell.bbox is not None:
            column_bboxes[cell.col_idx].append(cell.bbox)
    return dict(column_bboxes), "extracted_cells"


def _column_bboxes_from_metadata(
    normalized_table: NormalizedTable,
) -> tuple[dict[int, list[tuple[float, float, float, float]]], str]:
    table_cells = normalized_table.metadata.get("table_cells")
    if not isinstance(table_cells, list):
        return {}, "none"
    column_bboxes: dict[int, list[tuple[float, float, float, float]]] = defaultdict(list)
    for row in table_cells:
        if not isinstance(row, list):
            continue
        for col_idx, cell in enumerate(row):
            bbox = _bbox_from_value(cell)
            if bbox is not None:
                column_bboxes[col_idx].append(bbox)
    return dict(column_bboxes), "metadata_table_cells"


def _selected_original_columns(normalized_table: NormalizedTable, raw_n_cols: int) -> list[int]:
    dropped_leading_cols = _nonnegative_int(normalized_table.metadata.get("dropped_leading_cols"))
    dropped_trailing_cols = _nonnegative_int(normalized_table.metadata.get("dropped_trailing_cols"))
    right_bound = max(dropped_leading_cols, raw_n_cols - dropped_trailing_cols)
    selected_columns = list(range(dropped_leading_cols, right_bound))
    repairs = normalized_table.metadata.get("column_repairs")
    if isinstance(repairs, dict):
        dropped_after_repair = repairs.get("dropped_empty_columns_after_repair")
        if isinstance(dropped_after_repair, list):
            selected_columns = [
                original_col_idx
                for normalized_position, original_col_idx in enumerate(selected_columns)
                if normalized_position not in {idx for idx in dropped_after_repair if isinstance(idx, int)}
            ]
    return selected_columns


def _nonnegative_int(value: object) -> int:
    return value if isinstance(value, int) and value >= 0 else 0


def _bbox_from_value(value: Any) -> tuple[float, float, float, float] | None:
    if isinstance(value, dict) and all(key in value for key in ("x0", "top", "x1", "bottom")):
        try:
            return (float(value["x0"]), float(value["top"]), float(value["x1"]), float(value["bottom"]))
        except (TypeError, ValueError):
            return None
    if isinstance(value, (list, tuple)) and len(value) == 4:
        try:
            return tuple(float(part) for part in value)
        except (TypeError, ValueError):
            return None
    return None


def _compare_coordinate_profiles(
    base_profile: ColumnCoordinateProfile,
    continuation_profile: ColumnCoordinateProfile,
) -> tuple[str, list[ColumnCoordinateMapEntry], list[str]]:
    diagnostics: list[str] = []
    if base_profile.evidence_quality == "missing" or continuation_profile.evidence_quality == "missing":
        diagnostics.append(
            "coordinate_evidence_missing:"
            f"base={base_profile.evidence_quality}:continuation={continuation_profile.evidence_quality}"
        )
        return "missing", [], diagnostics

    if base_profile.normalized_n_cols != continuation_profile.normalized_n_cols:
        diagnostics.append(
            "coordinate_comparison_skipped_for_normalized_column_count_mismatch:"
            f"base={base_profile.normalized_n_cols}:continuation={continuation_profile.normalized_n_cols}"
        )
        return "incompatible", [], diagnostics

    column_map: list[ColumnCoordinateMapEntry] = []
    center_deltas: list[float] = []
    width_deltas: list[float] = []
    for col_idx in range(base_profile.normalized_n_cols):
        base_center = _value_at(base_profile.normalized_centers, col_idx)
        continuation_center = _value_at(continuation_profile.normalized_centers, col_idx)
        base_width = _value_at(base_profile.normalized_widths, col_idx)
        continuation_width = _value_at(continuation_profile.normalized_widths, col_idx)
        if base_center is None or continuation_center is None:
            column_map.append(
                ColumnCoordinateMapEntry(
                    base_col_idx=col_idx,
                    continuation_col_idx=col_idx,
                    base_center=base_center,
                    continuation_center=continuation_center,
                    base_width=base_width,
                    continuation_width=continuation_width,
                    status="missing_evidence",
                )
            )
            continue
        center_delta = round(abs(base_center - continuation_center), 5)
        width_delta = (
            round(abs(base_width - continuation_width), 5)
            if base_width is not None and continuation_width is not None
            else None
        )
        center_deltas.append(center_delta)
        if width_delta is not None:
            width_deltas.append(width_delta)
        if center_delta <= 0.04 and (width_delta is None or width_delta <= 0.08):
            status = "matched"
        elif center_delta <= 0.08 and (width_delta is None or width_delta <= 0.15):
            status = "possibly_matched"
        else:
            status = "mismatched"
        column_map.append(
            ColumnCoordinateMapEntry(
                base_col_idx=col_idx,
                continuation_col_idx=col_idx,
                base_center=base_center,
                continuation_center=continuation_center,
                center_delta=center_delta,
                base_width=base_width,
                continuation_width=continuation_width,
                width_delta=width_delta,
                status=status,
            )
        )

    if not center_deltas:
        diagnostics.append("coordinate_evidence_partial:no_comparable_column_centers")
        return "partial", column_map, diagnostics

    max_center_delta = max(center_deltas)
    max_width_delta = max(width_deltas) if width_deltas else 0.0
    diagnostics.append(f"coordinate_delta:max_center={max_center_delta}:max_width={max_width_delta}")
    if all(entry.status == "matched" for entry in column_map):
        return "compatible", column_map, diagnostics
    if all(entry.status in {"matched", "possibly_matched"} for entry in column_map):
        return "possibly_compatible", column_map, diagnostics
    return "incompatible", column_map, diagnostics


def _value_at(values: list[float | None], index: int) -> float | None:
    return values[index] if index < len(values) else None
