"""Build paper-level footnote anchor artifacts."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping, Sequence
from pathlib import Path
from statistics import median

from table1_parser.context.visual_references import parse_visual_label, visual_id_for
from table1_parser.extract.pymupdf_page_adapter import (
    extract_page_chars,
    open_pymupdf_document,
)
from table1_parser.page_furniture_mask import filter_positioned_items_for_page_furniture
from table1_parser.schemas import (
    CellTextAnnotationTable,
    ColumnHeaderSchema,
    ExtractedTable,
    FootnoteAnchor,
    FootnoteDefinition,
    FootnoteDefinitionCandidateLine,
    FootnoteDefinitionMarkerEvidence,
    FootnoteFooter,
    FootnoteFooterRow,
    FootnoteGlyphKind,
    FootnoteInferredMeaning,
    FootnoteLink,
    PaperFootnotes,
    PaperPageFurniture,
    Table1ContinuationGroup,
    TableCell,
)
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
    rf"(?P<glyph>{DEFINITION_SYMBOL_MARKER_TOKEN_PATTERN}|[a-z](?=(?:[A-Z][a-z]|P\s*[<=>≤≥])))"
    rf"\s*(?=\S)"
)
TEXTUAL_ASTERISK_DEFINITION_PATTERN = re.compile(
    r"\b(?:the\s+)?(?:asterisk|star)\s+(?:indicates?|denotes?|represents?|marks?)\b",
    re.IGNORECASE,
)
TABLE_CAPTION_ROW_PATTERN = re.compile(r"^\s*(?:Table|Figure)\s+[A-Za-z]?\d+[A-Za-z]?\s*[:.]", re.IGNORECASE)
CANONICAL_SYMBOL_KEYS = {
    "†": "dagger",
    "‡": "double_dagger",
    "§": "section",
    "¶": "paragraph",
    "#": "number_sign",
    "|": "vertical_bar",
}
PAGE_NOTE_FOOTER_HEIGHT = 60.0
P_VALUE_STAR_THRESHOLDS: dict[int, tuple[float, str]] = {
    1: (0.1, "10^-1"),
    2: (0.01, "10^-2"),
    3: (0.001, "10^-3"),
}


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
            "definitions_status": "not_built",
            "links_status": "not_built",
        },
    )


def build_paper_footnote_definition_blocks_from_pdf(
    pdf_path: str,
    *,
    paper_page_furniture: PaperPageFurniture | None = None,
) -> list[FootnoteDefinitionCandidateLine]:
    """Collect positioned contiguous page text blocks that may contain footnote definitions."""
    try:
        document = open_pymupdf_document(pdf_path)
    except Exception:  # noqa: BLE001
        return []

    blocks: list[FootnoteDefinitionCandidateLine] = []
    try:
        page_count = int(getattr(document, "page_count", 0))
        for page_index in range(page_count):
            page_num = page_index + 1
            try:
                page = document.load_page(page_index)
            except Exception:  # noqa: BLE001
                continue
            page_rect = getattr(page, "rect", None)
            page_height = None
            if page_rect is not None:
                if hasattr(page_rect, "height"):
                    page_height = float(page_rect.height)
                elif all(hasattr(page_rect, attr) for attr in ("y0", "y1")):
                    page_height = float(page_rect.y1) - float(page_rect.y0)
            page_chars, _mask_metadata = filter_positioned_items_for_page_furniture(
                extract_page_chars(page, page_num=page_num),
                paper_page_furniture,
                page_num=page_num,
            )
            if page_chars:
                blocks.extend(
                    _definition_blocks_from_positioned_chars(
                        page_chars,
                        page_num=page_num,
                        page_height=page_height,
                    )
                )
    finally:
        close = getattr(document, "close", None)
        if callable(close):
            close()
    return blocks


def _definition_blocks_from_positioned_chars(
    page_chars: Sequence[Mapping[str, object]],
    *,
    page_num: int,
    page_height: float | None,
) -> list[FootnoteDefinitionCandidateLine]:
    """Build definition candidate blocks from normalized PyMuPDF character records."""
    chars_by_block: dict[int, list[Mapping[str, object]]] = {}
    for char in page_chars:
        block_index_value = char.get("block_index")
        if not isinstance(block_index_value, int):
            continue
        chars_by_block.setdefault(block_index_value, []).append(char)

    blocks: list[FootnoteDefinitionCandidateLine] = []
    for block_index, block_chars in sorted(chars_by_block.items()):
        raw_text, positioned_chars = _text_and_positioned_chars_for_block(block_chars)
        if not raw_text or not positioned_chars:
            continue
        marker_evidence = _definition_marker_evidence_from_positioned_chars(raw_text, positioned_chars)
        if not marker_evidence and not _has_definition_candidate_text(raw_text):
            continue
        bbox = (
            min(float(char["x0"]) for char in positioned_chars),
            min(float(char["top"]) for char in positioned_chars),
            max(float(char["x1"]) for char in positioned_chars),
            max(float(char["bottom"]) for char in positioned_chars),
        )
        blocks.append(
            FootnoteDefinitionCandidateLine(
                line_id=f"page-{page_num}-block-{block_index}",
                page_num=page_num,
                raw_text=raw_text,
                source_scope="body_text",
                source_id=f"page-{page_num}-block-{block_index}",
                bbox=bbox,
                page_height=page_height,
                line_index=block_index,
                source_artifact="pymupdf_page_text_blocks",
                marker_evidence=marker_evidence,
                notes=["contiguous_pdf_text_block"],
            )
        )
    return blocks


def _text_and_positioned_chars_for_block(
    block_chars: Sequence[Mapping[str, object]],
) -> tuple[str, list[dict[str, object]]]:
    """Return block text plus character records with text offsets."""
    chars_by_line: dict[int, list[Mapping[str, object]]] = {}
    for char in block_chars:
        line_index_value = char.get("line_index")
        line_index = line_index_value if isinstance(line_index_value, int) else 0
        chars_by_line.setdefault(line_index, []).append(char)

    text_parts: list[str] = []
    positioned_chars: list[dict[str, object]] = []
    offset = 0
    for line_chars in (chars_by_line[line_index] for line_index in sorted(chars_by_line)):
        ordered_line_chars = sorted(line_chars, key=lambda char: int(char.get("char_index", 0)))
        while ordered_line_chars and not str(ordered_line_chars[0].get("text", "")).strip():
            ordered_line_chars = ordered_line_chars[1:]
        while ordered_line_chars and not str(ordered_line_chars[-1].get("text", "")).strip():
            ordered_line_chars = ordered_line_chars[:-1]
        if not ordered_line_chars:
            continue
        if text_parts:
            text_parts.append(" ")
            offset += 1
        for char in ordered_line_chars:
            text = str(char.get("text", ""))
            if not text:
                continue
            text_parts.append(text)
            positioned_char = dict(char)
            positioned_char["text_start"] = offset
            offset += len(text)
            positioned_char["text_end"] = offset
            positioned_chars.append(positioned_char)
    return "".join(text_parts).strip(), positioned_chars


def _definition_marker_evidence_from_positioned_chars(
    raw_text: str,
    positioned_chars: Sequence[Mapping[str, object]],
) -> list[FootnoteDefinitionMarkerEvidence]:
    """Find raised/smaller marker glyphs that start local definition text."""
    chars_by_line: dict[int, list[Mapping[str, object]]] = {}
    for char in positioned_chars:
        line_index_value = char.get("line_index")
        line_index = line_index_value if isinstance(line_index_value, int) else 0
        chars_by_line.setdefault(line_index, []).append(char)

    evidence: list[FootnoteDefinitionMarkerEvidence] = []
    for line_chars in chars_by_line.values():
        visible_chars = [char for char in line_chars if str(char.get("text", "")).strip()]
        if len(visible_chars) < 2:
            continue
        heights = [float(char.get("char_height", float(char["bottom"]) - float(char["top"]))) for char in visible_chars]
        main_height = median(heights)
        if main_height <= 0.0:
            continue
        main_centers = [
            (float(char["top"]) + float(char["bottom"])) / 2.0
            for char, height in zip(visible_chars, heights, strict=True)
            if height >= main_height * 0.9
        ]
        if not main_centers:
            continue
        main_center = median(main_centers)
        for char, height in zip(visible_chars, heights, strict=True):
            glyph_raw = str(char.get("text", "")).strip()
            if len(glyph_raw) != 1 or not (glyph_raw.isalnum() or glyph_raw in "*﹡＊†‡§¶#|{}"):
                continue
            center = (float(char["top"]) + float(char["bottom"])) / 2.0
            if not (height <= main_height * 0.86 and center <= main_center - main_height * 0.16):
                continue
            start = int(char.get("text_start", 0))
            end = int(char.get("text_end", start + len(glyph_raw)))
            prefix = raw_text[:start].rstrip()
            suffix = raw_text[end:].lstrip()
            if prefix and prefix[-1] not in ".;:,)]":
                continue
            if not suffix:
                continue
            evidence.append(
                FootnoteDefinitionMarkerEvidence(
                    glyph_raw=glyph_raw,
                    evidence_type="superscript_definition_marker",
                    text_start=start,
                    text_end=end,
                    confidence=0.9,
                    bbox=(
                        float(char["x0"]),
                        float(char["top"]),
                        float(char["x1"]),
                        float(char["bottom"]),
                    ),
                    metadata={
                        "font": char.get("font"),
                        "font_size": char.get("font_size"),
                        "char_height": height,
                        "line_main_height": main_height,
                        "line_main_center": main_center,
                    },
                    notes=["smaller_raised_glyph_at_definition_boundary"],
                )
            )
    return sorted(evidence, key=lambda item: (item.text_start, item.text_end))


def build_paper_footnote_definition_lines_from_pdf(
    pdf_path: str,
    *,
    paper_page_furniture: PaperPageFurniture | None = None,
) -> list[FootnoteDefinitionCandidateLine]:
    """Collect positioned page text blocks that may contain footnote definitions."""
    return build_paper_footnote_definition_blocks_from_pdf(
        pdf_path,
        paper_page_furniture=paper_page_furniture,
    )


def _has_definition_candidate_text(raw_text: str) -> bool:
    """Return true when flattened text has a portable definition-start signal."""
    return (
        DEFINITION_LINE_START_PATTERN.search(raw_text) is not None
        or DEFINITION_LINE_EMBEDDED_PATTERN.search(raw_text) is not None
        or DEFINITION_BLOCK_MARKER_PATTERN.search(raw_text) is not None
        or TEXTUAL_ASTERISK_DEFINITION_PATTERN.search(raw_text) is not None
    )


def _has_extracted_footer_definition_start(row_text: str) -> bool:
    """Return true when a confirmed footer row can open a definition block."""
    return (
        DEFINITION_LINE_START_PATTERN.search(row_text) is not None
        or DEFINITION_LINE_EMBEDDED_PATTERN.search(row_text) is not None
        or EXTRACTED_FOOTER_MARKER_EVIDENCE_PATTERN.search(row_text) is not None
    )


def find_table_footer_definition_blocks(
    definition_blocks: Sequence[FootnoteDefinitionCandidateLine],
    extracted_tables: Sequence[ExtractedTable],
    table1_continuation_groups: Sequence[Table1ContinuationGroup] | None = None,
) -> list[FootnoteDefinitionCandidateLine]:
    """Identify complete table-local footer blocks from positioned PDF text blocks."""
    table_bboxes: dict[str, tuple[float, float, float, float]] = {}
    tables_by_id = {table.table_id: table for table in extracted_tables}
    visual_id_by_table_id = _table_visual_ids(extracted_tables, table1_continuation_groups)
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

    footer_blocks: list[FootnoteDefinitionCandidateLine] = []
    for block_index, block in enumerate(definition_blocks):
        if block.source_scope != "body_text" or block.bbox is None:
            continue
        left, top, right, _ = block.bbox
        for candidate_table_id, table_bbox in table_bboxes.items():
            table = tables_by_id[candidate_table_id]
            if table.page_num != block.page_num:
                continue
            table_left, _, table_right, table_bottom = table_bbox
            next_table_top = min(
                (
                    other_bbox[1]
                    for other_table_id, other_bbox in table_bboxes.items()
                    if other_table_id != candidate_table_id
                    and tables_by_id[other_table_id].page_num == block.page_num
                    and other_bbox[1] > table_bottom
                ),
                default=None,
            )
            if next_table_top is not None and top >= next_table_top - 2.0:
                continue
            overlap = max(0.0, min(right, table_right) - max(left, table_left))
            block_width = max(right - left, 1.0)
            if top >= table_bottom - 2.0 and top - table_bottom <= 96.0 and overlap / block_width >= 0.25:
                footer_blocks.append(
                    block.model_copy(
                        update={
                            "source_scope": "table_note",
                            "source_id": f"{candidate_table_id}:footer_block:{block_index}",
                            "table_id": candidate_table_id,
                            "visual_id": visual_id_by_table_id.get(candidate_table_id),
                            "confidence": block.confidence if block.confidence is not None else 0.82,
                            "notes": [*block.notes, "table_footer_block_after_table_bbox"],
                        }
                    )
                )
                break
    return footer_blocks


def build_paper_footnote_definition_lines_from_extracted_tables(
    extracted_tables: Sequence[ExtractedTable],
    table1_continuation_groups: Sequence[Table1ContinuationGroup] | None = None,
) -> list[FootnoteDefinitionCandidateLine]:
    """Collect table-local footer definition blocks from extracted table rows."""
    lines: list[FootnoteDefinitionCandidateLine] = []
    visual_id_by_table_id = _table_visual_ids(extracted_tables, table1_continuation_groups)
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
        footer_rows, _footer_detection_basis = find_table_footer_rows(table, ordered_rows)
        if not footer_rows:
            continue

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
                    )
                )
                current_start_row_idx = None
                current_end_row_idx = None
                current_rows = []
                continue
            starts_definition = (
                _has_extracted_footer_definition_start(row_text)
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
                )
            )
    return lines


def build_paper_footnote_footers_from_extracted_tables(
    extracted_tables: Sequence[ExtractedTable],
    table1_continuation_groups: Sequence[Table1ContinuationGroup] | None = None,
) -> list[FootnoteFooter]:
    """Build reviewable table-footer regions from extracted table rows."""
    footers: list[FootnoteFooter] = []
    visual_id_by_table_id = _table_visual_ids(extracted_tables, table1_continuation_groups)
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
        footer_rows, detection_basis = find_table_footer_rows(table, ordered_rows)
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


def build_paper_footnote_footers_from_pdf_blocks(
    footer_blocks: Sequence[FootnoteDefinitionCandidateLine],
    *,
    existing_footers: Sequence[FootnoteFooter] | None = None,
) -> list[FootnoteFooter]:
    """Build reviewable table-footer regions from positioned PDF text blocks."""
    existing_keys = {
        (footer.table_id, clean_text(footer.raw_text).casefold())
        for footer in existing_footers or []
    }
    footers: list[FootnoteFooter] = []
    for block_index, block in enumerate(footer_blocks):
        if block.source_scope != "table_note" or block.table_id is None:
            continue
        raw_text = clean_text(block.raw_text)
        if not raw_text:
            continue
        footer_key = (block.table_id, raw_text.casefold())
        if footer_key in existing_keys:
            continue
        block_row_idx = block.line_index if block.line_index is not None else block_index
        notes = [
            *block.notes,
            "table_footer_block_detected_from_pdf_geometry",
            f"source_line_id:{block.line_id}",
        ]
        if block.bbox is not None:
            notes.append("bbox:" + ",".join(f"{part:.3f}" for part in block.bbox))
        footers.append(
            FootnoteFooter(
                footer_id=f"footer:pdf:{block_index}",
                table_id=block.table_id,
                visual_id=block.visual_id,
                page_num=block.page_num,
                source_artifact=block.source_artifact or "pymupdf_page_text_blocks",
                detection_basis="pdf_text_block_after_table_bbox",
                start_row_idx=block_row_idx,
                end_row_idx=block_row_idx,
                raw_text=raw_text,
                rows=[
                    FootnoteFooterRow(
                        row_idx=block_row_idx,
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
    table_bboxes: dict[str, tuple[float, float, float, float]] = {}
    tables_by_id = {table.table_id: table for table in extracted_tables or []}
    visual_id_by_table_id = _table_visual_ids(extracted_tables or [], table1_continuation_groups)
    for table in extracted_tables or []:
        cell_bboxes = [cell.bbox for cell in table.cells if cell.bbox is not None]
        if not cell_bboxes:
            continue
        table_bboxes[table.table_id] = (
            min(bbox[0] for bbox in cell_bboxes),
            min(bbox[1] for bbox in cell_bboxes),
            max(bbox[2] for bbox in cell_bboxes),
            max(bbox[3] for bbox in cell_bboxes),
        )

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
        if source_scope == "body_text" and line.bbox is not None:
            left, top, right, bottom = line.bbox
            for candidate_table_id, table_bbox in table_bboxes.items():
                table = tables_by_id[candidate_table_id]
                if table.page_num != line.page_num:
                    continue
                table_left, _, table_right, table_bottom = table_bbox
                next_table_top = min(
                    (
                        other_bbox[1]
                        for other_table_id, other_bbox in table_bboxes.items()
                        if other_table_id != candidate_table_id
                        and tables_by_id[other_table_id].page_num == line.page_num
                        and other_bbox[1] > table_bottom
                    ),
                    default=None,
                )
                if next_table_top is not None and top >= next_table_top - 2.0:
                    continue
                overlap = max(0.0, min(right, table_right) - max(left, table_left))
                line_width = max(right - left, 1.0)
                if top >= table_bottom - 2.0 and top - table_bottom <= 96.0 and overlap / line_width >= 0.25:
                    source_scope = "table_note"
                    table_id = candidate_table_id
                    visual_id = visual_id_by_table_id.get(candidate_table_id)
                    source_id = f"{candidate_table_id}:note:{line_index}"
                    confidence = confidence if confidence is not None else 0.75
                    break
            if (
                source_scope == "body_text"
                and line.page_height is not None
                and bottom >= line.page_height - PAGE_NOTE_FOOTER_HEIGHT
                and (
                    top >= line.page_height - (PAGE_NOTE_FOOTER_HEIGHT * 2)
                    or bottom - top <= PAGE_NOTE_FOOTER_HEIGHT * 1.5
                )
            ):
                source_scope = "page_note"
                confidence = confidence if confidence is not None else 0.65
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
    citation_like_anchor_ids: set[str] = set()
    numeric_row_label_anchors_without_local_definition = [
        anchor
        for anchor in footnotes.anchors
        if (
            anchor.glyph_kind == "number"
            and anchor.source_scope == "table_cell"
            and anchor.source_role == "row_label"
            and not [
                definition
                for definition in definitions_by_glyph.get(anchor.glyph_key, [])
                if (anchor.table_id is not None and anchor.table_id == definition.table_id)
                or (anchor.visual_id is not None and anchor.visual_id == definition.visual_id)
            ]
        )
    ]
    if (
        len(numeric_row_label_anchors_without_local_definition) >= 5
        and len({anchor.glyph_key for anchor in numeric_row_label_anchors_without_local_definition}) >= 5
    ):
        citation_like_anchor_ids = {
            anchor.anchor_id for anchor in numeric_row_label_anchors_without_local_definition
        }
    for anchor in footnotes.anchors:
        if (
            anchor.glyph_kind == "number"
            and anchor.source_scope == "table_cell"
            and anchor.glyph_key in bibliography_label_keys
            and not [
                definition
                for definition in definitions_by_glyph.get(anchor.glyph_key, [])
                if (anchor.table_id is not None and anchor.table_id == definition.table_id)
                or (anchor.visual_id is not None and anchor.visual_id == definition.visual_id)
            ]
        ):
            citation_like_anchor_ids.add(anchor.anchor_id)
    retained_anchors = [
        anchor for anchor in footnotes.anchors if anchor.anchor_id not in citation_like_anchor_ids
    ]

    links: list[FootnoteLink] = []
    for anchor_index, anchor in enumerate(retained_anchors):
        candidates = definitions_by_glyph.get(anchor.glyph_key, [])
        if (
            candidates
            and anchor.glyph_kind == "number"
            and anchor.source_scope == "table_cell"
        ):
            candidates = [
                definition
                for definition in candidates
                if (anchor.table_id is not None and anchor.table_id == definition.table_id)
                or (anchor.visual_id is not None and anchor.visual_id == definition.visual_id)
            ]
            if not candidates:
                links.append(
                    FootnoteLink(
                        link_id=f"link:{anchor_index}",
                        anchor_id=anchor.anchor_id,
                        glyph_key=anchor.glyph_key,
                        link_status="unresolved",
                        candidate_definition_ids=[],
                        link_basis=["numeric_table_cell_anchor_requires_local_definition"],
                        confidence=0.0,
                        notes=["possible_bibliographic_reference"],
                    )
                )
                continue
        if not candidates:
            inferred_meaning = _infer_p_value_star_meaning(anchor)
            if inferred_meaning is not None:
                links.append(
                    FootnoteLink(
                        link_id=f"link:{anchor_index}",
                        anchor_id=anchor.anchor_id,
                        glyph_key=anchor.glyph_key,
                        link_status="inferred",
                        candidate_definition_ids=[],
                        link_basis=["no_matching_glyph_key", "conventional_p_value_star"],
                        confidence=min(anchor.confidence, 0.72),
                        inferred_meaning=inferred_meaning,
                        notes=["no_explicit_definition_for_p_value_star"],
                    )
                )
                continue
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
            "anchors": retained_anchors,
            "links": links,
            "metadata": {
                **footnotes.metadata,
                "anchor_count": len(retained_anchors),
                "citation_like_anchor_suppression_count": len(citation_like_anchor_ids),
                "citation_like_suppressed_anchor_ids": sorted(citation_like_anchor_ids),
                "citation_like_suppressed_glyph_keys": sorted(
                    {
                        anchor.glyph_key
                        for anchor in footnotes.anchors
                        if anchor.anchor_id in citation_like_anchor_ids
                    }
                ),
                "link_count": len(links),
                "links_status": "built",
                "resolved_link_count": sum(link.link_status == "resolved" for link in links),
                "ambiguous_link_count": sum(link.link_status == "ambiguous" for link in links),
                "inferred_link_count": sum(link.link_status == "inferred" for link in links),
                "unresolved_link_count": sum(link.link_status == "unresolved" for link in links),
            },
        }
    )


def paper_footnotes_to_payload(footnotes: PaperFootnotes) -> dict[str, object]:
    """Serialize paper footnotes as a JSON-friendly record."""
    return footnotes.model_dump(mode="json")


def glyph_fields(glyph_raw: str) -> tuple[FootnoteGlyphKind, str, list[str]]:
    """Return normalized glyph fields for anchor and definition records."""
    glyph = glyph_raw.strip()
    codepoints = [f"U+{ord(char):04X}" for char in glyph]
    if not glyph:
        return "unknown", "unknown:", codepoints
    normalized = unicodedata.normalize("NFKC", glyph).strip()
    normalized_key = normalized.casefold()
    if normalized_key.isalpha():
        return "letter", f"letter:{normalized_key}", codepoints
    if normalized_key.isdigit():
        return "number", f"number:{normalized_key}", codepoints
    if normalized_key and all(char == "*" for char in normalized_key):
        return "asterisk", f"asterisk:{len(normalized_key)}", codepoints
    if normalized_key in CANONICAL_SYMBOL_KEYS:
        return "symbol", f"symbol:{CANONICAL_SYMBOL_KEYS[normalized_key]}", codepoints
    if any(not char.isalnum() for char in glyph):
        return "symbol", "symbol:" + ",".join(codepoints), codepoints
    return "unknown", f"unknown:{normalized_key or glyph}", codepoints


def find_table_footer_rows(
    table: ExtractedTable,
    ordered_rows: Sequence[tuple[int, list[TableCell]]],
) -> tuple[list[tuple[int, list[TableCell]]], str | None]:
    """Return table-local footer rows using existing table rule geometry when available."""
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
            if any(_row_starts_footnote_definition(row_cells) for _, row_cells in rows_below_bottom_rule):
                return rows_below_bottom_rule, "after_bottom_horizontal_rule"

    if last_value_row_idx is None:
        return [], None
    footer_rows = [(row_idx, row_cells) for row_idx, row_cells in ordered_rows if row_idx > last_value_row_idx]
    if any(_row_starts_footnote_definition(row_cells) for _, row_cells in footer_rows):
        return footer_rows, "after_last_value_matrix_row"
    return [], None


def _last_value_matrix_row_idx(
    ordered_rows: Sequence[tuple[int, list[TableCell]]],
    n_cols: int,
) -> int | None:
    """Return the last row that has enough value-like cells to precede footer rows."""
    required_value_cells = 1 if n_cols <= 3 else 2
    last_value_row_idx: int | None = None
    for row_idx, row_cells in ordered_rows:
        row_text = _row_text(row_cells)
        if _row_starts_footnote_definition(row_cells):
            continue
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


def _row_starts_footnote_definition(row_cells: Sequence[TableCell]) -> bool:
    row_text = _row_text(row_cells)
    return _has_extracted_footer_definition_start(row_text)


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
) -> FootnoteDefinitionCandidateLine:
    """Build one logical table-footer source line from one or more extracted rows."""
    row_range = (
        f"r{start_row_idx}"
        if start_row_idx == end_row_idx
        else f"r{start_row_idx}-r{end_row_idx}"
    )
    raw_text, marker_evidence = _text_and_marker_evidence_for_extracted_footer_rows(rows)
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
        for match in EXTRACTED_FOOTER_MARKER_EVIDENCE_PATTERN.finditer(cell_text):
            glyph_raw = _definition_glyph_from_marker(match.group("glyph"))
            if not glyph_raw:
                continue
            start = cell_offset + match.start("glyph")
            end = cell_offset + match.end("glyph")
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


def _infer_p_value_star_meaning(anchor: FootnoteAnchor) -> FootnoteInferredMeaning | None:
    """Infer conventional p-value star thresholds when no explicit definition exists."""
    if anchor.glyph_kind != "asterisk":
        return None
    marker_count_match = re.fullmatch(r"asterisk:(\d+)", anchor.glyph_key)
    if marker_count_match is None:
        return None
    marker_count = int(marker_count_match.group(1))
    threshold = P_VALUE_STAR_THRESHOLDS.get(marker_count)
    if threshold is None:
        return None

    attached_text = unicodedata.normalize("NFKC", anchor.attached_to_text or "")
    context_text = unicodedata.normalize("NFKC", anchor.text_context or "")
    combined_context = " ".join(part for part in (attached_text, context_text, anchor.source_id) if part)
    compact_attached = re.sub(r"\s+", "", attached_text)
    evidence: list[str] = []
    if anchor.source_role == "body_cell":
        evidence.append("body_cell_anchor")
    if re.search(r"(?i)\bp\s*[-_ ]?value\b|\bp\s*[<=>≤≥]", combined_context):
        evidence.append("explicit_p_value_text")
    if re.search(r"(?i)(?:^|[^A-Za-z])p(?:$|[^A-Za-z])", combined_context):
        evidence.append("p_value_symbol_text")
    if re.search(r"(?i)(?:^|[<=>≤≥])\s*0?\.\d+", compact_attached) or re.fullmatch(
        r"0?\.\d+", compact_attached
    ):
        evidence.append("p_value_numeric_text")
    if "body_cell_anchor" not in evidence:
        return None
    if not any(item in evidence for item in ("explicit_p_value_text", "p_value_symbol_text", "p_value_numeric_text")):
        return None

    p_value_threshold, threshold_notation = threshold
    return FootnoteInferredMeaning(
        inference_type="p_value_significance",
        inference_source="conventional_p_value_star",
        meaning_text=f"Conventional p-value significance marker: p < {threshold_notation}",
        marker_count=marker_count,
        p_value_threshold=p_value_threshold,
        threshold_notation=threshold_notation,
        evidence=evidence,
    )


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
