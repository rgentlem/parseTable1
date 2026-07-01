"""Helpers for cell text annotation artifacts."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from statistics import median
from table1_parser.extract.layout_fallback import normalize_positioned_geometry_for_rotation
from table1_parser.extract.pymupdf_page_adapter import extract_page_chars, open_pymupdf_document
from table1_parser.page_furniture_mask import filter_positioned_items_for_page_furniture
from table1_parser.schemas import CellTextAnnotation, CellTextAnnotationTable, ExtractedTable, PaperPageFurniture, TableCell


MARKER_SYMBOLS = {"*", "†", "‡", "§", "¶", "#", "|", "{", "}"}
INLINE_MARKER_PREFIX_PATTERN = re.compile(r"^[<>=≤≥\d.,%()\s+\-±−×]+$")
SUPPORTED_TRANSFORMED_FRAMES = {
    "page_sideways_transformed",
    "table_local_rotated_normalized",
    "table_local_rotated_transposed_normalized",
}


def cell_text_annotation_tables_to_payload(
    tables: list[CellTextAnnotationTable],
) -> list[dict[str, object]]:
    """Serialize cell text annotation tables as JSON-friendly records."""
    return [table.model_dump(mode="json") for table in tables]


def build_cell_text_annotation_tables_from_pdf(
    pdf_path: str,
    extracted_tables: Sequence[ExtractedTable],
    *,
    paper_page_furniture: PaperPageFurniture | None = None,
) -> list[CellTextAnnotationTable]:
    """Build cell text annotation artifacts using PyMuPDF character geometry."""
    page_chars_by_page: dict[int, list[dict[str, object]]] = {}
    diagnostic: str | None = None
    try:
        document = open_pymupdf_document(pdf_path)
    except Exception:  # noqa: BLE001
        document = None
        diagnostic = "char_geometry_unavailable"
    if document is not None:
        try:
            page_count = int(getattr(document, "page_count", 0))
            for page_index in range(page_count):
                page_num = page_index + 1
                page = document.load_page(page_index)
                page_chars_by_page[page_num], _metadata = filter_positioned_items_for_page_furniture(
                    extract_page_chars(page, page_num=page_num),
                    paper_page_furniture,
                    page_num=page_num,
                )
        except Exception:  # noqa: BLE001
            page_chars_by_page = {}
            diagnostic = "char_geometry_unavailable"
        finally:
            close = getattr(document, "close", None)
            if callable(close):
                close()

    tables = build_cell_text_annotation_tables(extracted_tables, page_chars_by_page)
    if diagnostic is None:
        return tables
    return [
        table.model_copy(
            update={
                "metadata": {
                    **table.metadata,
                    "diagnostics": sorted({*table.metadata.get("diagnostics", []), diagnostic}),
                }
            }
        )
        for table in tables
    ]


def build_cell_text_annotation_tables(
    extracted_tables: Sequence[ExtractedTable],
    page_chars_by_page: Mapping[int, Sequence[Mapping[str, object]]],
) -> list[CellTextAnnotationTable]:
    """Match positioned chars into extracted table cells and detect small markers."""
    annotation_tables: list[CellTextAnnotationTable] = []
    for table in extracted_tables:
        coordinate_frame = str(table.metadata.get("geometry_coordinate_frame") or "page")
        diagnostics: list[str] = []
        annotations: list[CellTextAnnotation] = []
        cells_with_bbox = [cell for cell in table.cells if cell.bbox is not None]
        page_num = table.page_num
        page_chars = list(page_chars_by_page.get(page_num, []))
        positioned_chars: list[Mapping[str, object]] = page_chars
        coordinate_frame_supported = coordinate_frame == "page"
        transform_applied = False
        transform_transposed = False
        transform_bbox: tuple[float, float, float, float] | None = None
        rotation_direction = ""
        if coordinate_frame in SUPPORTED_TRANSFORMED_FRAMES:
            transform_bbox_value = table.metadata.get("geometry_transform_source_bbox")
            if isinstance(transform_bbox_value, (list, tuple)) and len(transform_bbox_value) == 4:
                transform_bbox = tuple(float(part) for part in transform_bbox_value)
            elif transform_bbox_value is not None:
                diagnostics.append("geometry_transform_source_bbox_invalid")
            rotation_direction = str(table.metadata.get("rotation_direction") or "")
            transform_applied = bool(table.metadata.get("geometry_transform_applied"))
            transform_transposed = bool(table.metadata.get("geometry_transform_transposed"))
            if not transform_applied:
                diagnostics.append("geometry_transform_not_applied")
            if transform_bbox is None:
                diagnostics.append("geometry_transform_source_bbox_missing")
            if rotation_direction not in {"vertical_text_up", "vertical_text_down"}:
                diagnostics.append("rotation_direction_missing")
            if (
                page_chars
                and transform_applied
                and transform_bbox is not None
                and rotation_direction in {"vertical_text_up", "vertical_text_down"}
            ):
                source_left, source_top, source_right, source_bottom = transform_bbox
                clipped_chars = [
                    dict(char)
                    for char in page_chars
                    if float(char["x0"]) >= source_left - 2.0
                    and float(char["x1"]) <= source_right + 2.0
                    and float(char["top"]) >= source_top - 2.0
                    and float(char["bottom"]) <= source_bottom + 2.0
                ]
                if clipped_chars:
                    _, transformed_chars, _, _ = normalize_positioned_geometry_for_rotation(
                        words=[],
                        chars=clipped_chars,
                        rule_segments=[],
                        bbox=transform_bbox,
                        rotation_direction=rotation_direction,
                    )
                    positioned_chars = transformed_chars
                    coordinate_frame_supported = True
                else:
                    diagnostics.append("transformed_char_geometry_unavailable")
        elif coordinate_frame != "page":
            diagnostics.append(f"unsupported_coordinate_frame:{coordinate_frame}")
        if not cells_with_bbox:
            diagnostics.append("cell_bboxes_missing")
        if not page_chars:
            diagnostics.append("char_geometry_unavailable")

        if coordinate_frame_supported and cells_with_bbox and positioned_chars:
            for cell in cells_with_bbox:
                assert cell.bbox is not None
                left, top, right, bottom = cell.bbox
                chars = [
                    dict(char)
                    for char in positioned_chars
                    if left - 0.75 <= (float(char["x0"]) + float(char["x1"])) / 2.0 <= right + 0.75
                    and top - 0.75 <= (float(char["top"]) + float(char["bottom"])) / 2.0 <= bottom + 0.75
                    and str(char.get("text", "")).strip()
                ]
                if len(chars) < 2:
                    continue
                chars = sorted(chars, key=lambda char: float(char["x0"]))
                heights = [float(char.get("char_height", float(char["bottom"]) - float(char["top"]))) for char in chars]
                main_height = median(heights)
                main_centers = [
                    (float(char["top"]) + float(char["bottom"])) / 2.0
                    for char, height in zip(chars, heights, strict=True)
                    if height >= main_height * 0.9
                ]
                if not main_centers or main_height <= 0.0:
                    continue
                main_center = median(main_centers)
                candidate_items: list[tuple[int, str, Mapping[str, object]]] = []
                for index, (char, height) in enumerate(zip(chars, heights, strict=True)):
                    text = str(char.get("text", "")).strip()
                    if len(text) != 1 or not (text.isalnum() or text in MARKER_SYMBOLS):
                        continue
                    center = (float(char["top"]) + float(char["bottom"])) / 2.0
                    annotation_type = ""
                    if height <= main_height * 0.86 and center <= main_center - main_height * 0.16:
                        annotation_type = "superscript"
                    elif height <= main_height * 0.86 and center >= main_center + main_height * 0.16:
                        annotation_type = "subscript"
                    elif index > 0 and (index + 1 >= len(chars) or not str(chars[index + 1].get("text", "")).strip()):
                        previous = chars[index - 1]
                        gap = float(char["x0"]) - float(previous["x1"])
                        previous_height = float(
                            previous.get("char_height", float(previous["bottom"]) - float(previous["top"]))
                        )
                        prefix = "".join(str(prefix_char.get("text", "")) for prefix_char in chars[:index]).strip()
                        if gap <= max(2.5, previous_height * 0.35) and (
                            text in MARKER_SYMBOLS
                            or (
                                text.isalpha()
                                and any(marker in prefix for marker in ".%)")
                                and INLINE_MARKER_PREFIX_PATTERN.fullmatch(prefix)
                            )
                        ):
                            annotation_type = "inline_marker"
                    if annotation_type:
                        candidate_items.append((index, annotation_type, char))

                group: list[tuple[int, str, Mapping[str, object]]] = []
                for item in candidate_items:
                    if not group or (
                        item[1] == group[-1][1]
                        and item[0] == group[-1][0] + 1
                        and float(item[2]["x0"]) - float(group[-1][2]["x1"]) <= max(3.0, main_height * 0.45)
                    ):
                        group.append(item)
                        continue
                    annotations.append(_annotation_from_group(cell, chars, group))
                    group = [item]
                if group:
                    annotations.append(_annotation_from_group(cell, chars, group))

        metadata: dict[str, object] = {
            "source": "pymupdf_char_geometry",
            "coordinate_frame": coordinate_frame,
            "diagnostics": diagnostics,
        }
        if coordinate_frame in SUPPORTED_TRANSFORMED_FRAMES:
            metadata.update(
                {
                    "geometry_transform_applied": transform_applied,
                    "geometry_transform_transposed": transform_transposed,
                    "geometry_transform_source_bbox": transform_bbox,
                    "rotation_direction": rotation_direction or None,
                }
            )

        annotation_tables.append(
            CellTextAnnotationTable(
                table_id=table.table_id,
                page_num=table.page_num,
                n_rows=table.n_rows,
                n_cols=table.n_cols,
                annotations=annotations,
                metadata=metadata,
            )
        )
    return annotation_tables


def _annotation_from_group(
    cell: TableCell,
    chars: Sequence[Mapping[str, object]],
    group: Sequence[tuple[int, str, Mapping[str, object]]],
) -> CellTextAnnotation:
    text = "".join(str(item[2].get("text", "")) for item in group)
    annotation_type = group[0][1]
    left = min(float(item[2]["x0"]) for item in group)
    top = min(float(item[2]["top"]) for item in group)
    right = max(float(item[2]["x1"]) for item in group)
    bottom = max(float(item[2]["bottom"]) for item in group)
    first_index = group[0][0]
    attached_to_text = "".join(str(char.get("text", "")) for char in chars[:first_index]).strip() or None
    text_latex = None
    escaped = text.replace("\\", "\\textbackslash{}").replace("{", "\\{").replace("}", "\\}")
    if annotation_type == "superscript":
        text_latex = f"^{{{escaped}}}"
    elif annotation_type == "subscript":
        text_latex = f"_{{{escaped}}}"
    confidence = 0.9 if annotation_type in {"superscript", "subscript"} else 0.65
    fonts = sorted(
        {
            str(item[2].get("font"))
            for item in group
            if item[2].get("font") is not None
        }
    )
    raw_text = "".join(str(item[2].get("raw_text", item[2].get("text", ""))) for item in group)
    metadata: dict[str, object] = {"source": "pymupdf_char_geometry"}
    if fonts:
        metadata["fonts"] = fonts
    if raw_text != text:
        metadata["raw_text"] = raw_text
    return CellTextAnnotation(
        row_idx=cell.row_idx,
        col_idx=cell.col_idx,
        text=text,
        annotation_type=annotation_type,
        text_latex=text_latex,
        bbox=(left, top, right, bottom),
        attached_to_text=attached_to_text,
        confidence=confidence,
        metadata=metadata,
    )
