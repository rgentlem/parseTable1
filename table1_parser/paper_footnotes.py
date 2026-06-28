"""Build paper-level footnote anchor artifacts."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence
from pathlib import Path

from table1_parser.context.visual_references import parse_visual_label, visual_id_for
from table1_parser.extract.pymupdf_page_adapter import open_pymupdf_document
from table1_parser.schemas import (
    CellTextAnnotationTable,
    ColumnHeaderSchema,
    ExtractedTable,
    FootnoteAnchor,
    FootnoteDefinition,
    FootnoteDefinitionCandidateLine,
    FootnoteGlyphKind,
    FootnoteLink,
    PaperFootnotes,
    PaperPageFurniture,
)
from table1_parser.text_cleaning import clean_text


TEXT_MARKER_PATTERN = re.compile(r"(?P<glyph>[*﹡＊†‡§¶#|]|[⁰¹²³⁴⁵⁶⁷⁸⁹₀₁₂₃₄₅₆₇₈₉]+)(?=$|[\s.,;:)])")
DEFINITION_LINE_START_PATTERN = re.compile(
    r"^\s*(?:[A-Za-z]|\d+(?!\.\d)|[*﹡＊†‡§¶#|]|[⁰¹²³⁴⁵⁶⁷⁸⁹₀₁₂₃₄₅₆₇₈₉]+)[\s.)\]:;,\-–—]+\S"
)
DEFINITION_MARKER_PATTERN = re.compile(
    r"(?:^|(?<=[.;]\s))"
    r"(?P<glyph>[A-Za-z]|\d+(?!\.\d)|[*﹡＊†‡§¶#|]|[⁰¹²³⁴⁵⁶⁷⁸⁹₀₁₂₃₄₅₆₇₈₉]+)"
    r"[\s.)\]:;,\-–—]+"
    r"(?P<body>\S.*?)(?=(?:[.;]\s+(?:[A-Za-z]|\d+(?!\.\d)|[*﹡＊†‡§¶#|]|[⁰¹²³⁴⁵⁶⁷⁸⁹₀₁₂₃₄₅₆₇₈₉]+)[\s.)\]:;,\-–—]+\S)|$)"
)
CANONICAL_SYMBOL_KEYS = {
    "†": "dagger",
    "‡": "double_dagger",
    "§": "section",
    "¶": "paragraph",
    "#": "number_sign",
    "|": "vertical_bar",
}
PAGE_NOTE_FOOTER_HEIGHT = 60.0


def build_paper_footnote_anchor_inventory(
    paper_id: str,
    source_pdf: str,
    cell_text_annotations: Sequence[CellTextAnnotationTable],
    extracted_tables: Sequence[ExtractedTable] | None = None,
    column_header_schemas: Sequence[ColumnHeaderSchema] | None = None,
    paper_page_furniture: PaperPageFurniture | None = None,
) -> PaperFootnotes:
    """Build a paper-level footnote artifact populated with anchor records only."""
    anchors: list[FootnoteAnchor] = []
    diagnostics: list[str] = []
    suppressed_anchor_count = 0
    suppressed_anchor_cluster_ids: set[str] = set()
    schemas_by_table_id = {schema.table_id: schema for schema in column_header_schemas or []}
    extracted_by_table_id = {table.table_id: table for table in extracted_tables or []}
    visual_id_by_table_id = _table_visual_ids(extracted_tables or [])

    for table_position, annotation_table in enumerate(cell_text_annotations):
        schema = schemas_by_table_id.get(annotation_table.table_id)
        header_rows = set(schema.header_rows_considered) if schema is not None else set()
        row_label_cols = set()
        if schema is not None:
            if schema.label_col_idx is not None:
                row_label_cols.add(schema.label_col_idx)
            row_label_cols.update(leaf.col_idx for leaf in schema.leaves if leaf.is_row_label_column)
        for annotation_index, annotation in enumerate(annotation_table.annotations):
            glyph_raw = annotation.text.strip()
            if not glyph_raw:
                continue
            page_num = annotation_table.page_num or (
                extracted_by_table_id.get(annotation_table.table_id).page_num
                if annotation_table.table_id in extracted_by_table_id
                else 1
            )
            if str(annotation_table.metadata.get("coordinate_frame") or "page") == "page":
                overlapping_cluster_ids = page_furniture_cluster_ids_for_bbox(
                    paper_page_furniture,
                    page_num,
                    annotation.bbox,
                )
                if overlapping_cluster_ids:
                    suppressed_anchor_count += 1
                    suppressed_anchor_cluster_ids.update(overlapping_cluster_ids)
                    continue
            glyph_kind, glyph_key, glyph_codepoints = glyph_fields(glyph_raw)
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
    if paper_page_furniture is not None:
        source_artifacts.append("paper_page_furniture.json")
    return PaperFootnotes(
        paper_id=paper_id,
        source_pdf=Path(source_pdf).name,
        anchors=anchors,
        definitions=[],
        links=[],
        metadata={
            "source_artifacts": source_artifacts,
            "diagnostics": diagnostics,
            "anchor_count": len(anchors),
            "page_furniture_anchor_suppression_count": suppressed_anchor_count,
            "page_furniture_suppressed_anchor_cluster_ids": sorted(suppressed_anchor_cluster_ids),
            "definitions_status": "not_built",
            "links_status": "not_built",
        },
    )


def build_paper_footnote_definition_lines_from_pdf(pdf_path: str) -> list[FootnoteDefinitionCandidateLine]:
    """Collect positioned page text lines that may contain footnote definitions."""
    try:
        document = open_pymupdf_document(pdf_path)
    except Exception:  # noqa: BLE001
        return []

    lines: list[FootnoteDefinitionCandidateLine] = []
    try:
        page_count = int(getattr(document, "page_count", 0))
        for page_index in range(page_count):
            page_num = page_index + 1
            try:
                page = document.load_page(page_index)
                page_dict = page.get_text("dict") or {}
            except Exception:  # noqa: BLE001
                continue
            page_rect = getattr(page, "rect", None)
            page_height = None
            if page_rect is not None:
                if hasattr(page_rect, "height"):
                    page_height = float(page_rect.height)
                elif all(hasattr(page_rect, attr) for attr in ("y0", "y1")):
                    page_height = float(page_rect.y1) - float(page_rect.y0)
            line_index = 0
            for block in page_dict.get("blocks", []):
                for page_line in block.get("lines", []):
                    span_text_parts: list[str] = []
                    bbox_parts: list[tuple[float, float, float, float]] = []
                    for span in page_line.get("spans", []):
                        span_text = str(span.get("text", "")).strip()
                        bbox_value = span.get("bbox")
                        if span_text:
                            span_text_parts.append(span_text)
                        if all(hasattr(bbox_value, attr) for attr in ("x0", "y0", "x1", "y1")):
                            bbox_parts.append(
                                (
                                    float(bbox_value.x0),
                                    float(bbox_value.y0),
                                    float(bbox_value.x1),
                                    float(bbox_value.y1),
                                )
                            )
                        elif isinstance(bbox_value, (list, tuple)) and len(bbox_value) == 4:
                            bbox_parts.append(tuple(float(part) for part in bbox_value))
                    raw_text = " ".join(span_text_parts).strip()
                    current_line_index = line_index
                    line_index += 1
                    if not raw_text or not bbox_parts or DEFINITION_LINE_START_PATTERN.search(raw_text) is None:
                        continue
                    bbox = (
                        min(part[0] for part in bbox_parts),
                        min(part[1] for part in bbox_parts),
                        max(part[2] for part in bbox_parts),
                        max(part[3] for part in bbox_parts),
                    )
                    lines.append(
                        FootnoteDefinitionCandidateLine(
                            line_id=f"page-{page_num}-line-{current_line_index}",
                            page_num=page_num,
                            raw_text=raw_text,
                            source_scope="body_text",
                            source_id=f"page-{page_num}-line-{current_line_index}",
                            bbox=bbox,
                            page_height=page_height,
                            line_index=current_line_index,
                            source_artifact="pymupdf_page_text_lines",
                        )
                    )
    finally:
        close = getattr(document, "close", None)
        if callable(close):
            close()
    return lines


def filter_footnote_definition_lines_for_page_furniture(
    definition_lines: Sequence[FootnoteDefinitionCandidateLine],
    paper_page_furniture: PaperPageFurniture | None,
) -> tuple[list[FootnoteDefinitionCandidateLine], dict[str, object]]:
    """Drop candidate definition lines that overlap repeated page furniture."""
    filtered_lines: list[FootnoteDefinitionCandidateLine] = []
    suppressed_cluster_ids: set[str] = set()
    suppressed_count = 0
    for line in definition_lines:
        overlapping_cluster_ids = page_furniture_cluster_ids_for_bbox(
            paper_page_furniture,
            line.page_num,
            line.bbox,
        )
        if overlapping_cluster_ids:
            suppressed_count += 1
            suppressed_cluster_ids.update(overlapping_cluster_ids)
            continue
        filtered_lines.append(line)
    return filtered_lines, {
        "page_furniture_definition_line_suppression_count": suppressed_count,
        "page_furniture_suppressed_definition_cluster_ids": sorted(suppressed_cluster_ids),
    }


def build_paper_footnote_definition_candidates(
    definition_lines: Sequence[FootnoteDefinitionCandidateLine],
    extracted_tables: Sequence[ExtractedTable] | None = None,
) -> list[FootnoteDefinition]:
    """Extract candidate footnote definition records from local note text."""
    definitions: list[FootnoteDefinition] = []
    table_bboxes: dict[str, tuple[float, float, float, float]] = {}
    tables_by_id = {table.table_id: table for table in extracted_tables or []}
    visual_id_by_table_id = _table_visual_ids(extracted_tables or [])
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
            ):
                source_scope = "page_note"
                confidence = confidence if confidence is not None else 0.65
        if source_scope == "body_text":
            notes.append("definition_line_skipped:not_local_note_scope")
            continue
        confidence = confidence if confidence is not None else 0.8
        for match in DEFINITION_MARKER_PATTERN.finditer(raw_text):
            glyph_raw = match.group("glyph").strip()
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
                    source_scope=source_scope,
                    source_id=source_id,
                    page_num=line.page_num,
                    raw_text=raw_text,
                    clean_text=clean_text(raw_text),
                    definition_text=definition_text,
                    confidence=confidence,
                    table_id=table_id,
                    visual_id=visual_id,
                    bbox=line.bbox,
                    line_index=line.line_index if line.line_index is not None else line_index,
                    source_artifact=line.source_artifact,
                    notes=notes,
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
                glyph_raw = match.group("glyph").strip()
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


def link_paper_footnotes(footnotes: PaperFootnotes) -> PaperFootnotes:
    """Link footnote anchors to definitions by glyph and local scope."""
    definitions_by_glyph: dict[str, list[FootnoteDefinition]] = {}
    for definition in footnotes.definitions:
        definitions_by_glyph.setdefault(definition.glyph_key, []).append(definition)

    links: list[FootnoteLink] = []
    for anchor_index, anchor in enumerate(footnotes.anchors):
        candidates = definitions_by_glyph.get(anchor.glyph_key, [])
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
            if anchor.table_id is not None and anchor.table_id == definition.table_id:
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


def page_furniture_cluster_ids_for_bbox(
    paper_page_furniture: PaperPageFurniture | None,
    page_num: int | None,
    bbox: tuple[float, float, float, float] | None,
) -> list[str]:
    """Return repeated page-furniture cluster IDs whose page bbox overlaps `bbox`."""
    if paper_page_furniture is None or page_num is None or bbox is None:
        return []
    left, top, right, bottom = bbox
    if right <= left or bottom <= top:
        return []
    cluster_ids: set[str] = set()
    for region in paper_page_furniture.ignored_regions:
        if region.page_num != page_num:
            continue
        region_left, region_top, region_right, region_bottom = region.bbox
        if min(right, region_right) > max(left, region_left) and min(bottom, region_bottom) > max(top, region_top):
            cluster_ids.add(region.cluster_id)
    return sorted(cluster_ids)


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


def _table_visual_ids(extracted_tables: Sequence[ExtractedTable]) -> dict[str, str]:
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
    return visual_id_by_table_id
