"""Helpers for cell text annotation artifacts."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from statistics import median

from table1_parser.context.paper_positioned_document import build_paper_positioned_document
from table1_parser.marker_glyphs import glyph_fields
from table1_parser.page_furniture_mask import filter_positioned_items_for_page_furniture
from table1_parser.schemas import (
    CellTextAnnotation,
    CellTextAnnotationTable,
    ExtractedTable,
    PaperPageFurniture,
    PaperPositionedDocument,
    PositionedSpanReference,
    TableCell,
    TablePositionedEvidence,
)


MARKER_SYMBOLS = {"*", "†", "‡", "§", "¶", "#", "|", "{", "}"}
INLINE_MARKER_PREFIX_PATTERN = re.compile(r"^[<>=≤≥\d.,%()\s+\-±−×]+$")


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
    paper_positioned_document: PaperPositionedDocument | None = None,
) -> list[CellTextAnnotationTable]:
    """Build cell text annotation artifacts using shared positioned character geometry."""
    page_chars_by_page: dict[int, list[dict[str, object]]] = {}
    diagnostic: str | None = None
    positioned_document = paper_positioned_document or build_paper_positioned_document(pdf_path)
    if positioned_document.page_count <= 0:
        diagnostic = "char_geometry_unavailable"
    for page in positioned_document.pages:
        line_id_by_key = {
            (line.block_index, line.line_index): line.line_id
            for line in page.lines
            if line.block_index is not None and line.line_index is not None
        }
        page_chars: list[dict[str, object]] = []
        for char in page.chars:
            char_record = char.model_dump(mode="json", exclude_none=True)
            source_line_id = line_id_by_key.get((char.block_index, char.line_index))
            if source_line_id is not None:
                char_record["source_line_id"] = source_line_id
            page_chars.append(char_record)
        page_chars_by_page[page.page_num], _metadata = filter_positioned_items_for_page_furniture(
            page_chars,
            paper_page_furniture,
            page_num=page.page_num,
        )
    if diagnostic is None and not any(page_chars_by_page.values()):
        diagnostic = "char_geometry_unavailable"

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
        diagnostics: list[str] = []
        annotations: list[CellTextAnnotation] = []
        cells_with_bbox = [cell for cell in table.cells if cell.bbox is not None]
        page_num = table.page_num
        page_chars = list(page_chars_by_page.get(page_num, []))
        raw_evidence = table.metadata.get("table_positioned_evidence")
        evidence: TablePositionedEvidence | None = None
        if isinstance(raw_evidence, dict):
            try:
                evidence = TablePositionedEvidence.model_validate(raw_evidence)
            except (TypeError, ValueError):
                diagnostics.append("table_positioned_evidence_invalid")
        else:
            diagnostics.append("table_positioned_evidence_missing")
        page_chars_by_index = {
            int(char["char_index"]): char
            for char in page_chars
            if isinstance(char.get("char_index"), int)
        }
        positioned_chars: list[Mapping[str, object]] = []
        if evidence is not None:
            if len(evidence.char_indices) != len(evidence.canonical_char_bboxes):
                diagnostics.append("canonical_char_reference_length_mismatch")
            missing_source_count = 0
            for char_index, bbox in zip(
                evidence.char_indices,
                evidence.canonical_char_bboxes,
                strict=False,
            ):
                source_char = page_chars_by_index.get(char_index)
                if source_char is None:
                    missing_source_count += 1
                    continue
                canonical_char = dict(source_char)
                canonical_char.update(
                    {
                        "x0": float(bbox[0]),
                        "top": float(bbox[1]),
                        "x1": float(bbox[2]),
                        "bottom": float(bbox[3]),
                        "char_height": float(bbox[3]) - float(bbox[1]),
                    }
                )
                positioned_chars.append(canonical_char)
            if missing_source_count:
                diagnostics.append(
                    f"canonical_char_sources_missing:{missing_source_count}"
                )
        if not cells_with_bbox:
            diagnostics.append("cell_bboxes_missing")
        if not page_chars:
            diagnostics.append("char_geometry_unavailable")
        elif evidence is not None and not positioned_chars:
            diagnostics.append("canonical_char_geometry_unavailable")

        if cells_with_bbox and positioned_chars:
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
                    annotations.append(
                        _annotation_from_group(
                            table.table_id,
                            len(annotations),
                            cell,
                            chars,
                            group,
                        )
                    )
                    group = [item]
                if group:
                    annotations.append(
                        _annotation_from_group(
                            table.table_id,
                            len(annotations),
                            cell,
                            chars,
                            group,
                        )
                    )

        metadata: dict[str, object] = {
            "source": "paper_positioned_document_char_geometry",
            "coordinate_frame": "paper_text_orientation_group",
            "marker_occurrence_count": len(annotations),
            "diagnostics": diagnostics,
        }

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
    table_id: str,
    annotation_index: int,
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
    font_sizes = sorted(
        {
            float(item[2]["font_size"])
            for item in group
            if isinstance(item[2].get("font_size"), (int, float))
        }
    )
    source_char_indices = sorted(
        {
            int(item[2]["char_index"])
            for item in group
            if isinstance(item[2].get("char_index"), int)
        }
    )
    source_span_pairs = sorted(
        {
            (str(item[2]["source_line_id"]), int(item[2]["span_index"]))
            for item in group
            if isinstance(item[2].get("source_line_id"), str)
            and isinstance(item[2].get("span_index"), int)
        }
    )
    metadata: dict[str, object] = {"source": "pymupdf_char_geometry"}
    if fonts:
        metadata["fonts"] = fonts
    if raw_text != text:
        metadata["raw_text"] = raw_text
    return CellTextAnnotation(
        annotation_id=f"{table_id}:marker:{annotation_index}",
        row_idx=cell.row_idx,
        col_idx=cell.col_idx,
        text=text,
        glyph_key=glyph_fields(text)[1],
        annotation_type=annotation_type,
        text_latex=text_latex,
        bbox=(left, top, right, bottom),
        attached_to_text=attached_to_text,
        source_cell_id=f"{table_id}:r{cell.row_idx}:c{cell.col_idx}",
        source_char_indices=source_char_indices,
        source_span_references=[
            PositionedSpanReference(line_id=line_id, span_index=span_index)
            for line_id, span_index in source_span_pairs
        ],
        font_names=fonts,
        font_sizes=font_sizes,
        confidence=confidence,
        metadata=metadata,
    )
