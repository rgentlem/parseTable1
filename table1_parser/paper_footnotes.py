"""Build paper-level footnote anchor artifacts."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping, Sequence
from pathlib import Path
from statistics import median

from table1_parser.context.visual_references import parse_visual_label, visual_id_for
from table1_parser.marker_glyphs import glyph_fields
from table1_parser.schemas import (
    CellTextAnnotation,
    CellTextAnnotationTable,
    ColumnHeaderSchema,
    ExtractedTable,
    FootnoteAnchor,
    FootnoteDefinition,
    FootnoteDefinitionCandidateLine,
    FootnoteDefinitionMarkerEvidence,
    FootnoteFooter,
    FootnoteFooterRow,
    FootnoteLink,
    PaperFootnotes,
    PaperTextStream,
    Table1ContinuationGroup,
    TableCell,
)
from table1_parser.schemas.table_region import TableRegion
from table1_parser.text_cleaning import clean_text


TEXT_MARKER_PATTERN = re.compile(r"(?P<glyph>[*﹡＊†‡§¶#|{}]|[⁰¹²³⁴⁵⁶⁷⁸⁹₀₁₂₃₄₅₆₇₈₉]+)(?=$|[\s.,;:)])")
DEFINITION_GLYPH_PATTERN = r"[*﹡＊]+|[A-Za-z]|\d+(?!\.\d)|[†‡§¶#|{}]|[⁰¹²³⁴⁵⁶⁷⁸⁹₀₁₂₃₄₅₆₇₈₉]+"
DEFINITION_MARKER_TOKEN_PATTERN = (
    rf"\[\s*(?:{DEFINITION_GLYPH_PATTERN})\s*\]"
    rf"|\(\s*(?:{DEFINITION_GLYPH_PATTERN})\s*\)"
    rf"|(?:{DEFINITION_GLYPH_PATTERN})"
)
DEFINITION_SYMBOL_GLYPH_PATTERN = r"[*﹡＊]+|\|+|[†‡§¶#{}]"
DEFINITION_SYMBOL_MARKER_TOKEN_PATTERN = (
    rf"\[\s*(?:{DEFINITION_SYMBOL_GLYPH_PATTERN})\s*\]"
    rf"|\(\s*(?:{DEFINITION_SYMBOL_GLYPH_PATTERN})\s*\)"
    rf"|(?:{DEFINITION_SYMBOL_GLYPH_PATTERN})"
)
DEFINITION_SYMBOL_SEPARATOR_PATTERN = r"[\s.)\]:;,\-–—]+"
DEFINITION_TEXT_SEPARATOR_PATTERN = r"(?:\s+|[\s.)\]:;,\-–—]*\s+)"
DEFINITION_BODY_START_PATTERN = r"[A-Z0-9(*†‡§¶#{}]"
DEFINITION_ATTACHED_SYMBOL_BODY_START_PATTERN = r"(?=[A-Z0-9(])"
DEFINITION_LINE_START_PATTERN = re.compile(
    rf"^\s*(?:"
    rf"(?:{DEFINITION_SYMBOL_MARKER_TOKEN_PATTERN}){DEFINITION_SYMBOL_SEPARATOR_PATTERN}\S"
    rf"|(?:{DEFINITION_SYMBOL_MARKER_TOKEN_PATTERN}){DEFINITION_ATTACHED_SYMBOL_BODY_START_PATTERN}"
    rf"|(?:{DEFINITION_MARKER_TOKEN_PATTERN}){DEFINITION_TEXT_SEPARATOR_PATTERN}{DEFINITION_BODY_START_PATTERN}"
    rf")"
)
DEFINITION_LINE_EMBEDDED_PATTERN = re.compile(
    rf"(?<=[.;:]\s)(?:"
    rf"(?:{DEFINITION_SYMBOL_MARKER_TOKEN_PATTERN}){DEFINITION_SYMBOL_SEPARATOR_PATTERN}\S"
    rf"|(?:{DEFINITION_SYMBOL_MARKER_TOKEN_PATTERN}){DEFINITION_ATTACHED_SYMBOL_BODY_START_PATTERN}"
    rf"|(?:{DEFINITION_MARKER_TOKEN_PATTERN}){DEFINITION_TEXT_SEPARATOR_PATTERN}{DEFINITION_BODY_START_PATTERN}"
    rf")"
)
DEFINITION_MARKER_PATTERN = re.compile(
    r"(?:^|(?<=[.;:,]\s))"
    rf"(?P<glyph>{DEFINITION_MARKER_TOKEN_PATTERN})"
    rf"{DEFINITION_TEXT_SEPARATOR_PATTERN}"
    rf"(?P<body>\S.*?)(?=(?:[.;,]\s+(?:{DEFINITION_MARKER_TOKEN_PATTERN})[\s.)\]:;,\-–—]+\S)|$)"
)
DEFINITION_BLOCK_MARKER_PATTERN = re.compile(
    rf"(?P<prefix>^|[.;:,]\s+|[)\]]\s+)"
    rf"(?P<glyph>{DEFINITION_SYMBOL_MARKER_TOKEN_PATTERN})"
    rf"\s*(?=\S)"
)
EXTRACTED_FOOTER_MARKER_EVIDENCE_PATTERN = re.compile(
    rf"(?P<prefix>^|[.;:,]\s+|[)\]]\s+)"
    rf"(?P<glyph>{DEFINITION_SYMBOL_MARKER_TOKEN_PATTERN}|[a-z](?=P\s*[<=>≤≥]))"
    rf"\s*(?=\S)"
)
TEXTUAL_ASTERISK_DEFINITION_PATTERN = re.compile(
    r"\b(?:the\s+)?(?:asterisk|star)\s+(?:indicates?|denotes?|represents?|marks?)\b",
    re.IGNORECASE,
)
TABLE_CAPTION_ROW_PATTERN = re.compile(r"^\s*(?:Table|Figure)\s+[A-Za-z]?\d+[A-Za-z]?\s*[:.]", re.IGNORECASE)
STRUCTURAL_BOUNDARY_LINE_PATTERN = re.compile(
    r"^\s*(?:Table|Fig\.?|Figure)\s+[A-Za-z]?\d+[A-Za-z]?\b",
    re.IGNORECASE,
)


def build_paper_footnote_anchor_inventory(
    paper_id: str,
    source_pdf: str,
    cell_text_annotations: Sequence[CellTextAnnotationTable],
    extracted_tables: Sequence[ExtractedTable] | None = None,
    column_header_schemas: Sequence[ColumnHeaderSchema] | None = None,
    table1_continuation_groups: Sequence[Table1ContinuationGroup] | None = None,
) -> PaperFootnotes:
    """Build a paper-level footnote artifact populated with anchor records only."""
    anchors: list[FootnoteAnchor] = []
    diagnostics: list[str] = []
    math_unit_suppressed_anchor_count = 0
    subscript_suppressed_anchor_count = 0
    word_like_subscript_suppressed_anchor_count = 0
    non_footnote_symbol_suppressed_anchor_count = 0
    schemas_by_table_id = {schema.table_id: schema for schema in column_header_schemas or []}
    extracted_by_table_id = {table.table_id: table for table in extracted_tables or []}
    visual_id_by_table_id = _table_visual_ids(extracted_tables or [], table1_continuation_groups)

    for table_position, annotation_table in enumerate(cell_text_annotations):
        schema = schemas_by_table_id.get(annotation_table.table_id)
        header_rows = set(schema.header_rows_considered) if schema is not None else set()
        row_label_cols = set()
        if schema is not None:
            if schema.label_col_idx is not None:
                row_label_cols.add(schema.label_col_idx)
            row_label_cols.update(leaf.col_idx for leaf in schema.leaves if leaf.is_row_label_column)
        leaves_by_col_idx = {leaf.col_idx: leaf for leaf in schema.leaves} if schema is not None else {}
        for annotation_index, annotation in enumerate(annotation_table.annotations):
            glyph_raw = annotation.text.strip()
            if not glyph_raw:
                continue
            if glyph_raw in {"*", "﹡", "＊"} and annotation.attached_to_text:
                trailing_asterisks = re.search(r"([*﹡＊]+)$", annotation.attached_to_text.strip())
                if trailing_asterisks is not None:
                    glyph_raw = trailing_asterisks.group(1) + glyph_raw
            if annotation.annotation_type == "subscript":
                subscript_suppressed_anchor_count += 1
                continue
            if _is_math_unit_notation_marker(
                glyph_raw,
                annotation.annotation_type,
                annotation.attached_to_text,
            ):
                math_unit_suppressed_anchor_count += 1
                continue
            glyph_kind, glyph_key, glyph_codepoints = glyph_fields(glyph_raw)
            if glyph_key == "symbol:vertical_bar":
                non_footnote_symbol_suppressed_anchor_count += 1
                continue
            if glyph_kind == "letter" and len(unicodedata.normalize("NFKC", glyph_raw).strip()) > 1:
                word_like_subscript_suppressed_anchor_count += 1
                continue
            page_num = annotation_table.page_num or (
                extracted_by_table_id.get(annotation_table.table_id).page_num
                if annotation_table.table_id in extracted_by_table_id
                else 1
            )
            source_role = None
            notes: list[str] = []
            if schema is None:
                notes.append("source_role_unclassified:no_column_header_schema")
            elif annotation.row_idx in header_rows:
                source_role = "column_header"
            elif annotation.col_idx in row_label_cols:
                source_role = "row_label"
            else:
                source_role = "body_cell"
            anchors.append(
                FootnoteAnchor(
                    anchor_id=f"anchor:cell:{table_position}:{annotation_index}",
                    glyph_raw=glyph_raw,
                    glyph_key=glyph_key,
                    glyph_kind=glyph_kind,
                    glyph_codepoints=glyph_codepoints,
                    source_scope="table_cell",
                    source_id=f"{annotation_table.table_id}:r{annotation.row_idx}:c{annotation.col_idx}",
                    page_num=page_num,
                    confidence=annotation.confidence if annotation.confidence is not None else 0.5,
                    table_id=annotation_table.table_id,
                    visual_id=visual_id_by_table_id.get(annotation_table.table_id),
                    row_idx=annotation.row_idx,
                    col_idx=annotation.col_idx,
                    source_role=source_role,
                    text_context=(
                        leaves_by_col_idx[annotation.col_idx].leaf_label
                        if annotation.col_idx in leaves_by_col_idx
                        else None
                    ),
                    attached_to_text=annotation.attached_to_text,
                    bbox=annotation.bbox,
                    coordinate_frame=str(annotation_table.metadata.get("coordinate_frame") or "page"),
                    source_artifact="cell_text_annotations.json",
                    notes=notes,
                )
            )

    for table_position, table in enumerate(extracted_tables or []):
        for source_role, text in (("title", table.title), ("caption", table.caption)):
            if not text:
                continue
            for match_index, match in enumerate(TEXT_MARKER_PATTERN.finditer(text)):
                glyph_raw = match.group("glyph").strip()
                if not glyph_raw:
                    continue
                glyph_kind, glyph_key, glyph_codepoints = glyph_fields(glyph_raw)
                anchors.append(
                    FootnoteAnchor(
                        anchor_id=f"anchor:caption:{table_position}:{source_role}:{match_index}",
                        glyph_raw=glyph_raw,
                        glyph_key=glyph_key,
                        glyph_kind=glyph_kind,
                        glyph_codepoints=glyph_codepoints,
                        source_scope="table_caption",
                        source_id=f"{table.table_id}:{source_role}",
                        page_num=table.page_num,
                        confidence=0.65,
                        table_id=table.table_id,
                        visual_id=visual_id_by_table_id.get(table.table_id),
                        source_role=source_role,
                        text_context=text,
                        attached_to_text=text[: match.start()].strip() or None,
                        source_artifact="extracted_tables.json",
                    )
                )

    source_artifacts = ["cell_text_annotations.json", "extracted_tables.json"]
    return PaperFootnotes(
        paper_id=paper_id,
        source_pdf=Path(source_pdf).name,
        anchors=anchors,
        footers=[],
        definitions=[],
        links=[],
        metadata={
            "source_artifacts": source_artifacts,
            "diagnostics": diagnostics,
            "anchor_count": len(anchors),
            "math_unit_anchor_suppression_count": math_unit_suppressed_anchor_count,
            "subscript_anchor_suppression_count": subscript_suppressed_anchor_count,
            "word_like_subscript_anchor_suppression_count": word_like_subscript_suppressed_anchor_count,
            "non_footnote_symbol_suppression_count": non_footnote_symbol_suppressed_anchor_count,
            "definitions_status": "not_built",
            "links_status": "not_built",
        },
    )


def _has_extracted_footer_definition_start(row_text: str) -> bool:
    """Return true when a confirmed footer row can open a definition block."""
    return (
        DEFINITION_LINE_START_PATTERN.search(row_text) is not None
        or DEFINITION_LINE_EMBEDDED_PATTERN.search(row_text) is not None
        or EXTRACTED_FOOTER_MARKER_EVIDENCE_PATTERN.search(row_text) is not None
    )


def find_table_footer_definition_lines(
    extracted_tables: Sequence[ExtractedTable],
    table1_continuation_groups: Sequence[Table1ContinuationGroup] | None = None,
    paper_text_stream: PaperTextStream | None = None,
) -> list[FootnoteDefinitionCandidateLine]:
    """Identify complete table-local footer text from non-body styled lines below tables."""
    table_bboxes: dict[str, tuple[float, float, float, float]] = {}
    tables_by_id = {table.table_id: table for table in extracted_tables}
    visual_id_by_table_id = _table_visual_ids(extracted_tables, table1_continuation_groups)
    body_style = (
        paper_text_stream.metadata.get("dominant_body_text_style")
        if paper_text_stream is not None and isinstance(paper_text_stream.metadata, dict)
        else None
    )
    body_font = str(body_style.get("font", "")).strip() if isinstance(body_style, Mapping) else ""
    body_size_value = body_style.get("font_size") if isinstance(body_style, Mapping) else None
    body_size = round(float(body_size_value), 1) if isinstance(body_size_value, (int, float)) else None
    if paper_text_stream is None or not body_font or body_size is None:
        return []
    for table in extracted_tables:
        cell_bboxes = [cell.bbox for cell in table.cells if cell.bbox is not None]
        if not cell_bboxes:
            continue
        table_bboxes[table.table_id] = (
            min(bbox[0] for bbox in cell_bboxes),
            min(bbox[1] for bbox in cell_bboxes),
            max(bbox[2] for bbox in cell_bboxes),
            max(bbox[3] for bbox in cell_bboxes),
        )

    lines_by_page: dict[int, list[object]] = {}
    page_heights = {page.page_num: page.page_height for page in paper_text_stream.pages}
    for line in paper_text_stream.lines:
        lines_by_page.setdefault(line.page_num, []).append(line)

    caption_line_ids: set[str] = set()
    table_start_by_id = {table_id: bbox[1] for table_id, bbox in table_bboxes.items()}
    for table in extracted_tables:
        table_bbox = table_bboxes.get(table.table_id)
        if table_bbox is None:
            continue
        table_left, table_top, table_right, table_bottom = table_bbox
        caption_text = clean_text(" ".join(part for part in [table.title or "", table.caption or ""] if part))
        parsed_label = parse_visual_label(caption_text)
        table_number = table.metadata.get("table_number")
        label_number = str(table_number) if isinstance(table_number, int) else None
        if parsed_label is not None and parsed_label[0] == "table":
            label_number = parsed_label[1]
        label_pattern = (
            re.compile(rf"^\s*Table\s+{re.escape(label_number)}\b", re.IGNORECASE)
            if label_number is not None
            else None
        )
        caption_key = caption_text.casefold()
        for line in lines_by_page.get(table.page_num, []):
            line_text = clean_text(line.text)
            line_key = line_text.casefold()
            if not line_text:
                continue
            matches_caption = bool(label_pattern is not None and label_pattern.match(line_text))
            if not matches_caption and caption_key and len(line_key) >= 12 and line_key in caption_key:
                matches_caption = True
            if not matches_caption:
                continue
            line_left, line_top, line_right, line_bottom = line.bbox
            overlap = max(0.0, min(float(line_right), table_right) - max(float(line_left), table_left))
            if overlap <= 0.0:
                continue
            if (
                (float(line_bottom) <= table_top and table_top - float(line_bottom) <= 140.0)
                or (float(line_top) >= table_bottom and float(line_top) - table_bottom <= 140.0)
            ):
                caption_line_ids.add(line.line_id)
                table_start_by_id[table.table_id] = min(table_start_by_id[table.table_id], float(line_top))

    boundary_lines_by_page: dict[int, list[object]] = {}
    for page_num, page_lines in lines_by_page.items():
        for line in page_lines:
            line_text = clean_text(line.text)
            if line.role == "heading" or STRUCTURAL_BOUNDARY_LINE_PATTERN.match(line_text):
                boundary_lines_by_page.setdefault(page_num, []).append(line)

    footer_lines: list[FootnoteDefinitionCandidateLine] = []
    for table_position, table in enumerate(extracted_tables):
        table_bbox = table_bboxes.get(table.table_id)
        if table_bbox is None:
            continue
        table_left, _, table_right, table_bottom = table_bbox
        structural_boundary_top = min(
            (
                float(line.bbox[1])
                for line in boundary_lines_by_page.get(table.page_num, [])
                if line.line_id not in caption_line_ids
                and float(line.bbox[1]) > table_bottom
                and (
                    max(0.0, min(float(line.bbox[2]), table_right) - max(float(line.bbox[0]), table_left))
                    / max(float(line.bbox[2]) - float(line.bbox[0]), 1.0)
                    >= 0.25
                )
            ),
            default=None,
        )
        next_table_start = min(
            (
                table_start_by_id.get(other_table_id, other_bbox[1])
                for other_table_id, other_bbox in table_bboxes.items()
                if other_table_id != table.table_id
                and tables_by_id[other_table_id].page_num == table.page_num
                and table_start_by_id.get(other_table_id, other_bbox[1]) > table_bottom
            ),
            default=None,
        )
        lower_boundary = min(
            (boundary for boundary in [next_table_start, structural_boundary_top] if boundary is not None),
            default=None,
        )
        candidate_lines = []
        for line in sorted(lines_by_page.get(table.page_num, []), key=lambda item: (item.bbox[1], item.bbox[0])):
            if line.line_id in caption_line_ids:
                continue
            line_text = clean_text(line.text)
            if (
                not line_text
                or line.role == "heading"
                or TABLE_CAPTION_ROW_PATTERN.match(line_text)
                or STRUCTURAL_BOUNDARY_LINE_PATTERN.match(line_text)
            ):
                continue
            if line.dominant_font is None or line.dominant_font_size is None:
                continue
            line_style = (line.dominant_font, round(float(line.dominant_font_size), 1))
            if line_style == (body_font, body_size):
                continue
            left, top, right, bottom = line.bbox
            if float(top) < table_bottom - 2.0 or float(top) - table_bottom > 96.0:
                continue
            if lower_boundary is not None and float(top) >= lower_boundary - 2.0:
                continue
            overlap = max(0.0, min(float(right), table_right) - max(float(left), table_left))
            line_width = max(float(right) - float(left), 1.0)
            if overlap / line_width < 0.25:
                continue
            candidate_lines.append(line)

        line_groups = []
        current_group = []
        current_style: tuple[str, float] | None = None
        current_bottom: float | None = None
        for line in candidate_lines:
            line_style = (line.dominant_font or "", round(float(line.dominant_font_size or 0.0), 1))
            line_top = float(line.bbox[1])
            if (
                current_group
                and current_style == line_style
                and current_bottom is not None
                and line_top <= current_bottom + 8.0
            ):
                current_group.append(line)
                current_bottom = max(current_bottom, float(line.bbox[3]))
                continue
            if current_group:
                line_groups.append(current_group)
            current_group = [line]
            current_style = line_style
            current_bottom = float(line.bbox[3])
        if current_group:
            line_groups.append(current_group)

        for group_index, group in enumerate(line_groups):
            raw_parts: list[str] = []
            line_offsets: list[tuple[object, int]] = []
            for line in group:
                line_text = clean_text(line.raw_text)
                if not line_text:
                    continue
                if raw_parts:
                    line_offsets.append((line, sum(len(part) for part in raw_parts) + len(raw_parts)))
                else:
                    line_offsets.append((line, 0))
                raw_parts.append(line_text)
            raw_text = " ".join(raw_parts)
            if not raw_text:
                continue
            marker_evidence: list[FootnoteDefinitionMarkerEvidence] = []
            for line, line_offset in line_offsets:
                span_offsets: list[tuple[dict[str, object], int, int]] = []
                span_offset = 0
                for span in sorted(line.spans, key=lambda item: float((item.get("bbox") or (0.0, 0.0, 0.0, 0.0))[0])):
                    span_text = str(span.get("text", ""))
                    start = span_offset
                    span_offset += len(span_text)
                    span_offsets.append((span, start, span_offset))
                visible_spans = [
                    (span, start, end)
                    for span, start, end in span_offsets
                    if str(span.get("text", "")).strip()
                    and isinstance(span.get("font_size"), (int, float))
                    and isinstance(span.get("bbox"), (list, tuple))
                    and len(span.get("bbox") or ()) == 4
                ]
                if len(visible_spans) < 2 or line.dominant_font_size is None:
                    continue
                main_size = float(line.dominant_font_size)
                main_centers = [
                    (float(span["bbox"][1]) + float(span["bbox"][3])) / 2.0
                    for span, _start, _end in visible_spans
                    if float(span["font_size"]) >= main_size * 0.9
                ]
                if not main_centers:
                    continue
                main_center = median(main_centers)
                for span, start, end in visible_spans:
                    glyph_raw = str(span.get("text", "")).strip()
                    if len(glyph_raw) != 1 or not (glyph_raw.isalnum() or glyph_raw in "*﹡＊†‡§¶#|{}"):
                        continue
                    span_size = float(span["font_size"])
                    bbox = span["bbox"]
                    span_center = (float(bbox[1]) + float(bbox[3])) / 2.0
                    if not (span_size <= main_size * 0.86 and span_center <= main_center - main_size * 0.12):
                        continue
                    evidence_start = line_offset + start
                    evidence_end = line_offset + end
                    prefix = raw_text[:evidence_start].rstrip()
                    suffix = raw_text[evidence_end:].lstrip()
                    if prefix and prefix[-1] not in ".;:,)]":
                        continue
                    if not suffix:
                        continue
                    marker_evidence.append(
                        FootnoteDefinitionMarkerEvidence(
                            glyph_raw=glyph_raw,
                            evidence_type="superscript_definition_marker",
                            text_start=evidence_start,
                            text_end=evidence_end,
                            confidence=0.9,
                            bbox=(
                                float(bbox[0]),
                                float(bbox[1]),
                                float(bbox[2]),
                                float(bbox[3]),
                            ),
                            metadata={
                                "font": span.get("font"),
                                "font_size": span_size,
                                "line_dominant_font": line.dominant_font,
                                "line_dominant_font_size": main_size,
                            },
                            notes=["smaller_raised_span_at_definition_boundary"],
                        )
                    )
            group_bbox = (
                min(float(line.bbox[0]) for line in group),
                min(float(line.bbox[1]) for line in group),
                max(float(line.bbox[2]) for line in group),
                max(float(line.bbox[3]) for line in group),
            )
            group_line_indices = [line.line_index for line in group if line.line_index is not None]
            notes = ["paper_text_stream_line_style_differs_from_document_body", "table_footer_lines_after_table_bbox"]
            if next_table_start is not None:
                notes.append("bounded_by_next_extracted_table_start")
            if structural_boundary_top is not None:
                notes.append("bounded_by_structural_text_line")
            footer_lines.append(
                FootnoteDefinitionCandidateLine(
                    line_id=f"page-{table.page_num}-styled-footer-{table_position}-{group_index}",
                    page_num=table.page_num,
                    raw_text=raw_text,
                    source_scope="table_note",
                    source_id=f"{table.table_id}:footer_style_group:{group_index}",
                    table_id=table.table_id,
                    visual_id=visual_id_by_table_id.get(table.table_id),
                    bbox=group_bbox,
                    page_height=page_heights.get(table.page_num),
                    line_index=min(group_line_indices) if group_line_indices else group_index,
                    source_artifact="paper_text_stream.json",
                    confidence=0.82,
                    marker_evidence=marker_evidence,
                    notes=notes,
                )
            )
    return footer_lines


def build_paper_footnote_definition_lines_from_extracted_tables(
    extracted_tables: Sequence[ExtractedTable],
    table1_continuation_groups: Sequence[Table1ContinuationGroup] | None = None,
    table_regions: Sequence[TableRegion] | None = None,
    cell_text_annotations: Sequence[CellTextAnnotationTable] | None = None,
) -> list[FootnoteDefinitionCandidateLine]:
    """Collect table-local footer definition blocks from extracted table rows."""
    lines: list[FootnoteDefinitionCandidateLine] = []
    visual_id_by_table_id = _table_visual_ids(extracted_tables, table1_continuation_groups)
    region_by_table_id = {region.table_id: region for region in table_regions or []}
    footer_marker_annotations = _footer_marker_annotations_by_cell(cell_text_annotations or [], extracted_tables)
    for table in extracted_tables:
        rows_by_idx: dict[int, list[TableCell]] = {}
        for cell in table.cells:
            rows_by_idx.setdefault(cell.row_idx, []).append(cell)
        if not rows_by_idx:
            continue
        ordered_rows = [
            (row_idx, sorted(cells, key=lambda cell: cell.col_idx))
            for row_idx, cells in sorted(rows_by_idx.items())
        ]
        footer_rows, _footer_detection_basis = find_table_footer_rows(
            table,
            ordered_rows,
            table_region=region_by_table_id.get(table.table_id),
        )
        if not footer_rows:
            continue
        table_marker_annotations = footer_marker_annotations.get(table.table_id, {})

        current_start_row_idx: int | None = None
        current_end_row_idx: int | None = None
        current_rows: list[tuple[int, list[TableCell]]] = []

        for row_idx, row_cells in footer_rows:
            row_text = _row_text(row_cells)
            if not row_text:
                continue
            if current_start_row_idx is not None and TABLE_CAPTION_ROW_PATTERN.match(row_text):
                lines.append(
                    _table_footer_definition_line(
                        table=table,
                        visual_id=visual_id_by_table_id.get(table.table_id),
                        start_row_idx=current_start_row_idx,
                        end_row_idx=current_end_row_idx or current_start_row_idx,
                        rows=current_rows,
                        marker_annotations=table_marker_annotations,
                    )
                )
                current_start_row_idx = None
                current_end_row_idx = None
                current_rows = []
                continue
            starts_definition = (
                _has_extracted_footer_definition_start(row_text)
                or _row_has_structured_footer_marker(row_cells, table_marker_annotations)
            )
            if starts_definition:
                if current_start_row_idx is not None and current_rows:
                    lines.append(
                        _table_footer_definition_line(
                            table=table,
                            visual_id=visual_id_by_table_id.get(table.table_id),
                            start_row_idx=current_start_row_idx,
                            end_row_idx=current_end_row_idx or current_start_row_idx,
                            rows=current_rows,
                            marker_annotations=table_marker_annotations,
                        )
                    )
                current_start_row_idx = row_idx
                current_end_row_idx = row_idx
                current_rows = [(row_idx, row_cells)]
                continue
            if current_start_row_idx is not None:
                current_end_row_idx = row_idx
                current_rows.append((row_idx, row_cells))

        if current_start_row_idx is not None and current_rows:
            lines.append(
                _table_footer_definition_line(
                    table=table,
                    visual_id=visual_id_by_table_id.get(table.table_id),
                    start_row_idx=current_start_row_idx,
                    end_row_idx=current_end_row_idx or current_start_row_idx,
                    rows=current_rows,
                    marker_annotations=table_marker_annotations,
                )
            )
    return lines


def build_paper_footnote_footers_from_extracted_tables(
    extracted_tables: Sequence[ExtractedTable],
    table1_continuation_groups: Sequence[Table1ContinuationGroup] | None = None,
    table_regions: Sequence[TableRegion] | None = None,
) -> list[FootnoteFooter]:
    """Build reviewable table-footer regions from extracted table rows."""
    footers: list[FootnoteFooter] = []
    visual_id_by_table_id = _table_visual_ids(extracted_tables, table1_continuation_groups)
    region_by_table_id = {region.table_id: region for region in table_regions or []}
    for table_position, table in enumerate(extracted_tables):
        rows_by_idx: dict[int, list[TableCell]] = {}
        for cell in table.cells:
            rows_by_idx.setdefault(cell.row_idx, []).append(cell)
        if not rows_by_idx:
            continue
        ordered_rows = [
            (row_idx, sorted(cells, key=lambda cell: cell.col_idx))
            for row_idx, cells in sorted(rows_by_idx.items())
        ]
        footer_rows, detection_basis = find_table_footer_rows(
            table,
            ordered_rows,
            table_region=region_by_table_id.get(table.table_id),
        )
        if not footer_rows or detection_basis is None:
            continue
        footer_row_records = [
            FootnoteFooterRow(
                row_idx=row_idx,
                raw_cells=[cell.text for cell in row_cells],
                text=_row_text(row_cells),
            )
            for row_idx, row_cells in footer_rows
            if _row_text(row_cells)
        ]
        if not footer_row_records:
            continue
        footers.append(
            FootnoteFooter(
                footer_id=f"footer:{table_position}",
                table_id=table.table_id,
                visual_id=visual_id_by_table_id.get(table.table_id),
                page_num=table.page_num,
                detection_basis=detection_basis,
                start_row_idx=min(row.row_idx for row in footer_row_records),
                end_row_idx=max(row.row_idx for row in footer_row_records),
                raw_text=clean_text(" ".join(row.text for row in footer_row_records)),
                rows=footer_row_records,
                notes=["table_footer_rows_detected_from_extracted_table"],
            )
        )
    return footers


def build_paper_footnote_footers_from_text_stream_lines(
    footer_lines: Sequence[FootnoteDefinitionCandidateLine],
    *,
    existing_footers: Sequence[FootnoteFooter] | None = None,
) -> list[FootnoteFooter]:
    """Build reviewable table-footer regions from paper text-stream line groups."""
    existing_keys = {
        (footer.table_id, clean_text(footer.raw_text).casefold())
        for footer in existing_footers or []
    }
    footers: list[FootnoteFooter] = []
    for line_index, line in enumerate(footer_lines):
        if line.source_scope != "table_note" or line.table_id is None:
            continue
        raw_text = clean_text(line.raw_text)
        if not raw_text:
            continue
        footer_key = (line.table_id, raw_text.casefold())
        if footer_key in existing_keys:
            continue
        row_idx = line.line_index if line.line_index is not None else line_index
        notes = [
            *line.notes,
            "table_footer_lines_detected_from_text_stream_geometry",
            f"source_line_id:{line.line_id}",
        ]
        if line.bbox is not None:
            notes.append("bbox:" + ",".join(f"{part:.3f}" for part in line.bbox))
        footers.append(
            FootnoteFooter(
                footer_id=f"footer:text_stream:{line_index}",
                table_id=line.table_id,
                visual_id=line.visual_id,
                page_num=line.page_num,
                source_artifact=line.source_artifact or "paper_text_stream.json",
                detection_basis="paper_text_stream_lines_after_table_bbox",
                start_row_idx=row_idx,
                end_row_idx=row_idx,
                raw_text=raw_text,
                rows=[
                    FootnoteFooterRow(
                        row_idx=row_idx,
                        raw_cells=[raw_text],
                        text=raw_text,
                    )
                ],
                notes=notes,
            )
        )
        existing_keys.add(footer_key)
    return footers


def build_paper_footnote_definition_candidates(
    definition_lines: Sequence[FootnoteDefinitionCandidateLine],
    extracted_tables: Sequence[ExtractedTable] | None = None,
    table1_continuation_groups: Sequence[Table1ContinuationGroup] | None = None,
) -> list[FootnoteDefinition]:
    """Extract candidate footnote definition records from local note text."""
    definitions: list[FootnoteDefinition] = []
    visual_id_by_table_id = _table_visual_ids(extracted_tables or [], table1_continuation_groups)

    definition_index = 0
    for line_index, line in enumerate(definition_lines):
        raw_text = line.raw_text.strip()
        if not raw_text:
            continue
        source_scope = line.source_scope
        table_id = line.table_id
        visual_id = line.visual_id
        source_id = line.source_id or line.line_id
        notes = [*line.notes]
        confidence = line.confidence
        if source_scope == "body_text":
            notes.append("definition_line_skipped:not_local_note_scope")
            continue
        confidence = confidence if confidence is not None else 0.8
        parsed_definitions = _parse_definition_markers(raw_text, line.marker_evidence)
        for glyph_raw, definition_text, marker_evidence in parsed_definitions:
            glyph_kind, glyph_key, glyph_codepoints = glyph_fields(glyph_raw)
            definition_notes = [*notes]
            if marker_evidence is not None:
                definition_notes.append("definition_marker_from_structured_evidence")
            definitions.append(
                FootnoteDefinition(
                    definition_id=f"definition:{definition_index}",
                    glyph_raw=glyph_raw,
                    glyph_key=glyph_key,
                    glyph_kind=glyph_kind,
                    glyph_codepoints=glyph_codepoints,
                    source_scope=source_scope,
                    source_id=source_id,
                    page_num=line.page_num,
                    raw_text=raw_text,
                    clean_text=clean_text(raw_text),
                    definition_text=definition_text,
                    marker_evidence_type=marker_evidence.evidence_type if marker_evidence is not None else None,
                    marker_bbox=marker_evidence.bbox if marker_evidence is not None else None,
                    marker_confidence=marker_evidence.confidence if marker_evidence is not None else None,
                    marker_metadata=marker_evidence.metadata if marker_evidence is not None else {},
                    confidence=confidence,
                    table_id=table_id,
                    visual_id=visual_id,
                    bbox=line.bbox,
                    line_index=line.line_index if line.line_index is not None else line_index,
                    source_artifact=line.source_artifact,
                    notes=definition_notes,
                )
            )
            definition_index += 1

    for table_position, table in enumerate(extracted_tables or []):
        visual_id = visual_id_by_table_id.get(table.table_id)
        for source_role, text in (("title", table.title), ("caption", table.caption)):
            if not text:
                continue
            raw_text = text.strip()
            for match in DEFINITION_MARKER_PATTERN.finditer(raw_text):
                glyph_raw = _definition_glyph_from_marker(match.group("glyph"))
                definition_text = clean_text(match.group("body"))
                if not glyph_raw or not definition_text:
                    continue
                glyph_kind, glyph_key, glyph_codepoints = glyph_fields(glyph_raw)
                definitions.append(
                    FootnoteDefinition(
                        definition_id=f"definition:{definition_index}",
                        glyph_raw=glyph_raw,
                        glyph_key=glyph_key,
                        glyph_kind=glyph_kind,
                        glyph_codepoints=glyph_codepoints,
                        source_scope="table_caption",
                        source_id=f"{table.table_id}:{source_role}",
                        page_num=table.page_num,
                        raw_text=raw_text,
                        clean_text=clean_text(raw_text),
                        definition_text=definition_text,
                        confidence=0.65,
                        table_id=table.table_id,
                        visual_id=visual_id,
                        line_index=table_position,
                        source_artifact="extracted_tables.json",
                    )
                )
                definition_index += 1
    return definitions


def link_paper_footnotes(
    footnotes: PaperFootnotes,
    bibliography_label_keys: set[str] | None = None,
) -> PaperFootnotes:
    """Link footnote anchors to definitions by glyph and local scope."""
    definitions_by_glyph: dict[str, list[FootnoteDefinition]] = {}
    for definition in footnotes.definitions:
        definitions_by_glyph.setdefault(definition.glyph_key, []).append(definition)

    bibliography_label_keys = bibliography_label_keys or set()

    links: list[FootnoteLink] = []
    for anchor_index, anchor in enumerate(footnotes.anchors):
        candidates = definitions_by_glyph.get(anchor.glyph_key, [])
        if (
            anchor.glyph_kind == "number"
            and anchor.source_scope == "table_cell"
        ):
            local_candidates = [
                definition
                for definition in candidates
                if (anchor.table_id is not None and anchor.table_id == definition.table_id)
                or (anchor.visual_id is not None and anchor.visual_id == definition.visual_id)
            ]
            if local_candidates:
                candidates = local_candidates
            else:
                notes = ["possible_bibliographic_reference"]
                if anchor.glyph_key in bibliography_label_keys:
                    notes.append("glyph_key_present_in_bibliography")
                links.append(
                    FootnoteLink(
                        link_id=f"link:{anchor_index}",
                        anchor_id=anchor.anchor_id,
                        glyph_key=anchor.glyph_key,
                        link_status="unresolved",
                        candidate_definition_ids=[],
                        link_basis=["numeric_table_cell_anchor_requires_local_definition"],
                        confidence=0.0,
                        notes=notes,
                    )
                )
                continue
        if not candidates:
            links.append(
                FootnoteLink(
                    link_id=f"link:{anchor_index}",
                    anchor_id=anchor.anchor_id,
                    glyph_key=anchor.glyph_key,
                    link_status="unresolved",
                    candidate_definition_ids=[],
                    link_basis=["no_matching_glyph_key"],
                    confidence=0.0,
                    notes=["no_definition_for_glyph_key"],
                )
            )
            continue

        scored_candidates: list[tuple[int, float, str, FootnoteDefinition]] = []
        for definition in candidates:
            if (
                anchor.table_id is not None
                and anchor.table_id == definition.table_id
                and definition.source_artifact == "extracted_tables.json"
            ):
                scored_candidates.append((5, 0.93, "same_table_extracted_footer", definition))
            elif anchor.table_id is not None and anchor.table_id == definition.table_id:
                scored_candidates.append((4, 0.9, "same_table", definition))
            elif anchor.visual_id is not None and anchor.visual_id == definition.visual_id:
                scored_candidates.append((3, 0.82, "same_visual", definition))
            elif anchor.page_num == definition.page_num:
                scored_candidates.append((2, 0.72, "same_page", definition))
            else:
                scored_candidates.append((1, 0.5, "paper_level", definition))

        best_score = max(score for score, _, _, _ in scored_candidates)
        best_candidates = [
            (scope_confidence, scope_distance, definition)
            for score, scope_confidence, scope_distance, definition in scored_candidates
            if score == best_score
        ]
        candidate_definition_ids = [definition.definition_id for _, _, definition in best_candidates]
        scope_distance = best_candidates[0][1]
        link_basis = ["glyph_key_match", scope_distance]
        notes: list[str] = []
        lower_scope_count = len(candidates) - len(best_candidates)
        if lower_scope_count:
            notes.append(f"lower_scope_candidate_count:{lower_scope_count}")

        if len(best_candidates) == 1:
            scope_confidence, _, definition = best_candidates[0]
            confidence = min(anchor.confidence, definition.confidence, scope_confidence)
            links.append(
                FootnoteLink(
                    link_id=f"link:{anchor_index}",
                    anchor_id=anchor.anchor_id,
                    glyph_key=anchor.glyph_key,
                    link_status="resolved",
                    candidate_definition_ids=candidate_definition_ids,
                    link_basis=link_basis,
                    confidence=confidence,
                    definition_id=definition.definition_id,
                    scope_distance=scope_distance,
                    notes=notes,
                )
            )
            continue

        link_basis.append("multiple_definitions_at_best_scope")
        confidence = min(
            anchor.confidence,
            max(definition.confidence for _, _, definition in best_candidates),
            best_candidates[0][0],
            0.6,
        )
        links.append(
            FootnoteLink(
                link_id=f"link:{anchor_index}",
                anchor_id=anchor.anchor_id,
                glyph_key=anchor.glyph_key,
                link_status="ambiguous",
                candidate_definition_ids=candidate_definition_ids,
                link_basis=link_basis,
                confidence=confidence,
                scope_distance=scope_distance,
                notes=notes,
            )
        )

    return footnotes.model_copy(
        update={
            "links": links,
            "metadata": {
                **footnotes.metadata,
                "anchor_count": len(footnotes.anchors),
                "link_count": len(links),
                "links_status": "built",
                "resolved_link_count": sum(link.link_status == "resolved" for link in links),
                "ambiguous_link_count": sum(link.link_status == "ambiguous" for link in links),
                "unresolved_link_count": sum(link.link_status == "unresolved" for link in links),
            },
        }
    )


def paper_footnotes_to_payload(footnotes: PaperFootnotes) -> dict[str, object]:
    """Serialize paper footnotes as a JSON-friendly record."""
    return footnotes.model_dump(mode="json")


def _footer_marker_annotations_by_cell(
    cell_text_annotations: Sequence[CellTextAnnotationTable],
    extracted_tables: Sequence[ExtractedTable],
) -> dict[str, dict[tuple[int, int], list[CellTextAnnotation]]]:
    first_populated_cell_by_row: dict[str, dict[int, tuple[int, tuple[float, float, float, float] | None]]] = {}
    for table in extracted_tables:
        row_cells: dict[int, list[TableCell]] = {}
        for cell in table.cells:
            if clean_text(cell.text):
                row_cells.setdefault(cell.row_idx, []).append(cell)
        first_populated_cell_by_row[table.table_id] = {
            row_idx: (min(cells, key=lambda cell: cell.col_idx).col_idx, min(cells, key=lambda cell: cell.col_idx).bbox)
            for row_idx, cells in row_cells.items()
        }

    markers: dict[str, dict[tuple[int, int], list[CellTextAnnotation]]] = {}
    for annotation_table in cell_text_annotations:
        first_cells = first_populated_cell_by_row.get(annotation_table.table_id, {})
        for annotation in annotation_table.annotations:
            first_cell = first_cells.get(annotation.row_idx)
            if first_cell is None:
                continue
            first_col_idx, first_bbox = first_cell
            if annotation.col_idx != first_col_idx or annotation.annotation_type != "superscript":
                continue
            if first_bbox is not None and annotation.bbox is not None and annotation.bbox[0] > first_bbox[0] + 6.0:
                continue
            markers.setdefault(annotation_table.table_id, {}).setdefault(
                (annotation.row_idx, annotation.col_idx),
                [],
            ).append(annotation)
    return markers


def _row_has_structured_footer_marker(
    row_cells: Sequence[TableCell],
    marker_annotations: Mapping[tuple[int, int], Sequence[CellTextAnnotation]],
) -> bool:
    populated_cells = [cell for cell in row_cells if clean_text(cell.text)]
    if not populated_cells:
        return False
    first_cell = min(populated_cells, key=lambda cell: cell.col_idx)
    return any(
        _cell_has_row_start_marker_annotation(first_cell, annotation)
        for annotation in marker_annotations.get((first_cell.row_idx, first_cell.col_idx), [])
    )


def _cell_has_row_start_marker_annotation(cell: TableCell, annotation: CellTextAnnotation) -> bool:
    if annotation.annotation_type != "superscript" or not annotation.text.strip():
        return False
    if annotation.bbox is None or cell.bbox is None:
        return annotation.attached_to_text is None
    return annotation.bbox[0] <= cell.bbox[0] + 6.0


def find_table_footer_rows(
    table: ExtractedTable,
    ordered_rows: Sequence[tuple[int, list[TableCell]]],
    *,
    table_region: TableRegion | None = None,
) -> tuple[list[tuple[int, list[TableCell]]], str | None]:
    """Return table-local footer rows using existing table rule geometry when available."""
    if table_region is not None and table_region.footer_note_rows:
        footer_row_indices = set(table_region.footer_note_rows)
        footer_rows = [
            (row_idx, row_cells)
            for row_idx, row_cells in ordered_rows
            if row_idx in footer_row_indices
        ]
        if footer_rows:
            return footer_rows, "table_region_footer_note_band"
    last_value_row_idx = _last_value_matrix_row_idx(ordered_rows, table.n_cols)
    row_bounds = table.metadata.get("row_bounds")
    rules = table.metadata.get("full_width_horizontal_rules")
    if not isinstance(rules, list) or not rules:
        rules = table.metadata.get("horizontal_rules")
    if (
        last_value_row_idx is not None
        and isinstance(row_bounds, list)
        and isinstance(rules, list)
        and last_value_row_idx < len(row_bounds)
        and row_bounds
        and rules
    ):
        numeric_rules = sorted(float(rule) for rule in rules if isinstance(rule, (int, float)))
        last_value_bounds = row_bounds[last_value_row_idx]
        if isinstance(last_value_bounds, (list, tuple)) and len(last_value_bounds) == 2 and numeric_rules:
            last_value_bottom = float(last_value_bounds[1])
            footer_boundary_rules = [
                rule for rule in numeric_rules if rule >= last_value_bottom - 2.0
            ]
        else:
            footer_boundary_rules = []
        if footer_boundary_rules:
            bottom_rule = footer_boundary_rules[-1]
            rows_below_bottom_rule: list[tuple[int, list[TableCell]]] = []
            for row_idx, row_cells in ordered_rows:
                if row_idx >= len(row_bounds):
                    continue
                bounds = row_bounds[row_idx]
                if not isinstance(bounds, (list, tuple)) or len(bounds) != 2:
                    continue
                row_top = float(bounds[0])
                if row_top >= bottom_rule - 2.0:
                    rows_below_bottom_rule.append((row_idx, row_cells))
            if any(_row_text(row_cells) for _, row_cells in rows_below_bottom_rule):
                return rows_below_bottom_rule, "after_bottom_horizontal_rule"

    return [], None


def _last_value_matrix_row_idx(
    ordered_rows: Sequence[tuple[int, list[TableCell]]],
    n_cols: int,
) -> int | None:
    """Return the last row that has enough value-like cells to precede footer rows."""
    required_value_cells = 1 if n_cols <= 3 else 2
    last_value_row_idx: int | None = None
    for row_idx, row_cells in ordered_rows:
        nonempty_cells = [cell for cell in row_cells if clean_text(cell.text)]
        if not nonempty_cells:
            continue
        first_nonempty_col = min(cell.col_idx for cell in nonempty_cells)
        trailing_texts = [
            cell.text
            for cell in nonempty_cells
            if cell.col_idx > first_nonempty_col
        ]
        value_like_count = 0
        for text in trailing_texts:
            normalized = unicodedata.normalize("NFKC", clean_text(text))
            if (
                normalized
                and re.search(r"\d", normalized)
                and len(re.findall(r"[A-Za-z]", normalized)) <= 3
            ):
                value_like_count += 1
        if value_like_count >= required_value_cells:
            last_value_row_idx = row_idx
    return last_value_row_idx


def _row_text(row_cells: Sequence[TableCell]) -> str:
    """Join extracted row cells in column order without discarding marker text."""
    return clean_text(" ".join(cell.text for cell in row_cells if clean_text(cell.text)))


def _table_footer_definition_line(
    *,
    table: ExtractedTable,
    visual_id: str | None,
    start_row_idx: int,
    end_row_idx: int,
    rows: Sequence[tuple[int, Sequence[TableCell]]],
    marker_annotations: Mapping[tuple[int, int], Sequence[CellTextAnnotation]],
) -> FootnoteDefinitionCandidateLine:
    """Build one logical table-footer source line from one or more extracted rows."""
    row_range = (
        f"r{start_row_idx}"
        if start_row_idx == end_row_idx
        else f"r{start_row_idx}-r{end_row_idx}"
    )
    raw_text, marker_evidence = _text_and_marker_evidence_for_extracted_footer_rows(
        rows,
        marker_annotations=marker_annotations,
    )
    return FootnoteDefinitionCandidateLine(
        line_id=f"{table.table_id}:footer:{row_range}",
        page_num=table.page_num,
        raw_text=raw_text,
        source_scope="table_note",
        source_id=f"{table.table_id}:footer:{row_range}",
        table_id=table.table_id,
        visual_id=visual_id,
        line_index=start_row_idx,
        source_artifact="extracted_tables.json",
        confidence=0.9,
        marker_evidence=marker_evidence,
        notes=["table_footer_rows_after_value_matrix"],
    )


def _text_and_marker_evidence_for_extracted_footer_rows(
    rows: Sequence[tuple[int, Sequence[TableCell]]],
    *,
    marker_annotations: Mapping[tuple[int, int], Sequence[CellTextAnnotation]],
) -> tuple[str, list[FootnoteDefinitionMarkerEvidence]]:
    """Build footer text and marker evidence from confirmed table-footer rows."""
    text_parts: list[str] = []
    cell_offsets: list[tuple[int, str, TableCell]] = []
    offset = 0
    for _row_idx, row_cells in rows:
        ordered_cells = sorted(row_cells, key=lambda cell: cell.col_idx)
        row_text_parts: list[str] = []
        for cell in ordered_cells:
            cell_text = clean_text(cell.text)
            if not cell_text:
                continue
            if text_parts or row_text_parts:
                text_parts.append(" ")
                offset += 1
            cell_offsets.append((offset, cell_text, cell))
            text_parts.append(cell_text)
            row_text_parts.append(cell_text)
            offset += len(cell_text)

    raw_text = clean_text("".join(text_parts))
    marker_evidence: list[FootnoteDefinitionMarkerEvidence] = []
    for cell_offset, cell_text, cell in cell_offsets:
        for annotation in marker_annotations.get((cell.row_idx, cell.col_idx), []):
            if not _cell_has_row_start_marker_annotation(cell, annotation):
                continue
            glyph_raw = annotation.text.strip()
            if not glyph_raw:
                continue
            start = cell_offset
            end = cell_offset + len(glyph_raw)
            marker_evidence.append(
                FootnoteDefinitionMarkerEvidence(
                    glyph_raw=glyph_raw,
                    evidence_type="cell_text_annotation_marker",
                    text_start=start,
                    text_end=end,
                    confidence=annotation.confidence if annotation.confidence is not None else 0.9,
                    bbox=annotation.bbox,
                    metadata={
                        "row_idx": cell.row_idx,
                        "col_idx": cell.col_idx,
                        "annotation_type": annotation.annotation_type,
                        **annotation.metadata,
                    },
                    notes=["marker_from_superscript_cell_annotation"],
                )
            )
        for match in EXTRACTED_FOOTER_MARKER_EVIDENCE_PATTERN.finditer(cell_text):
            glyph_raw = _definition_glyph_from_marker(match.group("glyph"))
            if not glyph_raw:
                continue
            start = cell_offset + match.start("glyph")
            end = cell_offset + match.end("glyph")
            if any(item.text_start == start and item.text_end == end and item.glyph_raw == glyph_raw for item in marker_evidence):
                continue
            marker_evidence.append(
                FootnoteDefinitionMarkerEvidence(
                    glyph_raw=glyph_raw,
                    evidence_type="extracted_footer_marker_text",
                    text_start=start,
                    text_end=end,
                    confidence=0.72,
                    bbox=cell.bbox,
                    metadata={"row_idx": cell.row_idx, "col_idx": cell.col_idx},
                    notes=["marker_prefix_inside_confirmed_table_footer_cell"],
                )
            )
    return raw_text, sorted(marker_evidence, key=lambda item: (item.text_start, item.text_end))


def _is_math_unit_notation_marker(
    glyph_raw: str,
    annotation_type: str | None,
    attached_to_text: str | None,
) -> bool:
    """Return true for numeric super/subscripts that are better read as units or exponents."""
    glyph_kind, _, _ = glyph_fields(glyph_raw)
    if glyph_kind != "number" or annotation_type not in {"superscript", "subscript"} or not attached_to_text:
        return False

    context = unicodedata.normalize("NFKC", attached_to_text).strip()
    if not context:
        return False
    compact = re.sub(r"\s+", "", context)
    if re.search(r"(?:×|x|\*)?10$", compact, flags=re.IGNORECASE):
        return True
    if annotation_type == "superscript" and re.fullmatch(r"[A-Za-z]", compact):
        return True
    if re.search(r"(?:^|[^A-Za-z0-9])(?:m|cm|mm|kg|g|mg|ug|μg|µg|l|dl|ml|mol|mmol|umol|μmol|µmol)$", compact, flags=re.IGNORECASE):
        return True
    if "/" in compact and re.search(r"[A-Za-zµμ][A-Za-zµμ0-9.]*$", compact):
        return True
    if re.search(r"\d+(?:\.\d+)?[A-Za-zµμ]+$", compact):
        return True
    if annotation_type == "subscript" and re.search(r"[A-Z]{1,4}$", compact):
        return True
    return False


def _definition_glyph_from_marker(marker_text: str) -> str:
    """Return the visible footnote glyph from a bare, bracketed, or parenthesized marker."""
    glyph = marker_text.strip()
    if len(glyph) >= 2 and glyph[0] == "[" and glyph[-1] == "]":
        return glyph[1:-1].strip()
    if len(glyph) >= 2 and glyph[0] == "(" and glyph[-1] == ")":
        return glyph[1:-1].strip()
    return glyph


def _parse_definition_markers(
    raw_text: str,
    marker_evidence: Sequence[FootnoteDefinitionMarkerEvidence] | None = None,
) -> list[tuple[str, str, FootnoteDefinitionMarkerEvidence | None]]:
    """Parse explicit footnote definitions from one local note block."""
    evidence_items = sorted(marker_evidence or [], key=lambda item: (item.text_start, item.text_end))
    marker_candidates: list[tuple[int, int, int, int, str, FootnoteDefinitionMarkerEvidence | None]] = []
    for evidence in evidence_items:
        glyph_raw = _definition_glyph_from_marker(evidence.glyph_raw)
        if glyph_raw:
            marker_candidates.append(
                (
                    evidence.text_start,
                    evidence.text_end,
                    evidence.text_start,
                    evidence.text_end,
                    glyph_raw,
                    evidence,
                )
            )

    for match in DEFINITION_BLOCK_MARKER_PATTERN.finditer(raw_text):
        glyph_start = match.start("glyph")
        glyph_end = match.end("glyph")
        if any(
            candidate_evidence is not None
            and max(glyph_start, candidate_glyph_start) < min(glyph_end, candidate_glyph_end)
            for candidate_glyph_start, candidate_glyph_end, _, _, _, candidate_evidence in marker_candidates
        ):
            continue
        glyph_raw = _definition_glyph_from_marker(match.group("glyph"))
        if glyph_raw:
            marker_candidates.append((glyph_start, glyph_end, match.start("prefix"), match.end(), glyph_raw, None))

    if marker_candidates:
        parsed_definitions: list[tuple[str, str, FootnoteDefinitionMarkerEvidence | None]] = []
        sorted_markers = sorted(marker_candidates, key=lambda item: (item[0], item[1]))
        for match_index, marker in enumerate(sorted_markers):
            _glyph_start, _glyph_end, _boundary_start, body_start, glyph_raw, evidence = marker
            body_end = (
                sorted_markers[match_index + 1][2]
                if match_index + 1 < len(sorted_markers)
                else len(raw_text)
            )
            body_text = raw_text[body_start:body_end].strip().lstrip(".)]:;,–—- ")
            definition_text = clean_text(body_text.rstrip(" \t\n\r,;"))
            if glyph_raw and definition_text:
                parsed_definitions.append((glyph_raw, definition_text, evidence))
        return parsed_definitions

    parsed_definitions: list[tuple[str, str, FootnoteDefinitionMarkerEvidence | None]] = []
    for match in DEFINITION_MARKER_PATTERN.finditer(raw_text):
        glyph_raw = _definition_glyph_from_marker(match.group("glyph"))
        definition_text = clean_text(match.group("body"))
        if not glyph_raw or not definition_text:
            continue
        parsed_definitions.append((glyph_raw, definition_text, None))
    if not parsed_definitions and TEXTUAL_ASTERISK_DEFINITION_PATTERN.search(raw_text):
        parsed_definitions.append(("*", clean_text(raw_text), None))
    return parsed_definitions


def _table_visual_ids(
    extracted_tables: Sequence[ExtractedTable],
    table1_continuation_groups: Sequence[Table1ContinuationGroup] | None = None,
) -> dict[str, str]:
    visual_id_by_table_id: dict[str, str] = {}
    for table in extracted_tables:
        table_number = table.metadata.get("table_number") or (table.metadata.get("signals") or {}).get(
            "caption_table_number"
        )
        if table_number is None:
            parsed = next(
                (parsed for text in (table.title, table.caption) if text and (parsed := parse_visual_label(text))),
                None,
            )
            if parsed is not None and parsed[0] == "table":
                table_number = parsed[1]
        if table_number is not None:
            visual_id_by_table_id[table.table_id] = visual_id_for("table", str(table_number))
    for group in table1_continuation_groups or []:
        visual_id = visual_id_for("table", str(group.table_number))
        for table_id in group.source_table_ids:
            visual_id_by_table_id[table_id] = visual_id
    return visual_id_by_table_id
