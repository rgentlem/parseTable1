"""Build paper-level footnote anchor artifacts."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence
from pathlib import Path
from statistics import median

from table1_parser.context.visual_references import (
    VISUAL_OBJECT_DOI_PATTERN,
    parse_visual_label,
    visual_id_for,
)
from table1_parser.marker_glyphs import glyph_fields
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
    FootnoteLink,
    PaperFootnotes,
    PaperTextStream,
    ResolvedTableSet,
    TableBoundaryProposal,
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


def build_paper_footnote_anchor_inventory(
    paper_id: str,
    source_pdf: str,
    cell_text_annotations: Sequence[CellTextAnnotationTable],
    extracted_tables: Sequence[ExtractedTable] | None = None,
    column_header_schemas: Sequence[ColumnHeaderSchema] | None = None,
    resolved_table_set: ResolvedTableSet | None = None,
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
    visual_id_by_table_id = _table_visual_ids(extracted_tables or [], resolved_table_set)

    for annotation_table in cell_text_annotations:
        schema = schemas_by_table_id.get(annotation_table.table_id)
        header_rows = set(schema.header_rows_considered) if schema is not None else set()
        row_label_cols = set()
        if schema is not None:
            if schema.label_col_idx is not None:
                row_label_cols.add(schema.label_col_idx)
            row_label_cols.update(leaf.col_idx for leaf in schema.leaves if leaf.is_row_label_column)
        leaves_by_col_idx = {leaf.col_idx: leaf for leaf in schema.leaves} if schema is not None else {}
        for annotation in annotation_table.annotations:
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
            notes.append(
                f"cell_text_annotation_type:{annotation.annotation_type}"
            )
            if annotation.annotation_id is None:
                diagnostics.append(
                    f"missing_annotation_id:{annotation_table.table_id}:"
                    f"r{annotation.row_idx}:c{annotation.col_idx}"
                )
                continue
            anchors.append(
                FootnoteAnchor(
                    anchor_id=annotation.annotation_id,
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
    resolved_table_set: ResolvedTableSet | None = None,
    paper_text_stream: PaperTextStream | None = None,
    table_boundary_proposals: Sequence[TableBoundaryProposal] | None = None,
    table_regions: Sequence[TableRegion] | None = None,
) -> list[FootnoteDefinitionCandidateLine]:
    """Project positioned lines from the footer boundary accepted by TableRegion."""
    if paper_text_stream is None:
        return []
    visual_id_by_table_id = _table_visual_ids(extracted_tables, resolved_table_set)
    proposal_by_table_id = {
        proposal.table_id: proposal for proposal in table_boundary_proposals or []
    }
    region_by_table_id = {region.table_id: region for region in table_regions or []}
    lines_by_id = {line.line_id: line for line in paper_text_stream.lines}
    page_heights = {page.page_num: page.page_height for page in paper_text_stream.pages}

    footer_lines: list[FootnoteDefinitionCandidateLine] = []
    for table_position, table in enumerate(extracted_tables):
        proposal = proposal_by_table_id.get(table.table_id)
        if proposal is None:
            continue
        region = region_by_table_id.get(table.table_id)
        footer_rules = [
            candidate
            for candidate in proposal.boundary_candidates
            if "body_footer" in candidate.possible_roles
            and candidate.following_text_line_ids
        ]
        footer_line_ids: list[str] = []
        if len(footer_rules) == 1:
            footer_line_ids = footer_rules[0].following_text_line_ids
        elif region is not None and region.footer_note_rows:
            footer_bounds = [
                proposal.canonical_row_bounds[row_idx]
                for row_idx in region.footer_note_rows
                if row_idx < len(proposal.canonical_row_bounds)
            ]
            table_bbox = proposal.canonical_table_bbox
            if footer_bounds and table_bbox is not None:
                footer_line_ids = [
                    line.line_id
                    for line in paper_text_stream.lines
                    if line.page_num == table.page_num
                    and line.canonical_bbox is not None
                    and any(
                        top - 1.0
                        <= (line.canonical_bbox[1] + line.canonical_bbox[3]) / 2.0
                        <= bottom + 1.0
                        for top, bottom in footer_bounds
                    )
                    and max(
                        0.0,
                        min(line.canonical_bbox[2], table_bbox[2])
                        - max(line.canonical_bbox[0], table_bbox[0]),
                    )
                    / max(line.canonical_bbox[2] - line.canonical_bbox[0], 1.0)
                    >= 0.25
                ]
        if not footer_line_ids:
            continue
        group = []
        for line_id in footer_line_ids:
            line = lines_by_id.get(line_id)
            if line is None:
                group = []
                break
            if VISUAL_OBJECT_DOI_PATTERN.fullmatch(clean_text(line.raw_text)):
                break
            group.append(line)
        if not group:
            continue

        raw_parts: list[str] = []
        line_offsets: list[tuple[object, int]] = []
        for line in group:
            line_text = clean_text(line.raw_text)
            if not line_text:
                continue
            line_offsets.append(
                (line, sum(len(part) for part in raw_parts) + len(raw_parts))
            )
            raw_parts.append(line_text)
        raw_text = " ".join(raw_parts)
        if not raw_text:
            continue

        marker_evidence: list[FootnoteDefinitionMarkerEvidence] = []
        for line, line_offset in line_offsets:
            span_offsets: list[tuple[dict[str, object], int, int]] = []
            span_offset = 0
            for span in sorted(
                line.spans,
                key=lambda item: float((item.get("bbox") or (0.0, 0.0, 0.0, 0.0))[0]),
            ):
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
                if len(glyph_raw) != 1 or not (
                    glyph_raw.isalnum() or glyph_raw in "*﹡＊†‡§¶#|{}"
                ):
                    continue
                span_size = float(span["font_size"])
                bbox = span["bbox"]
                span_center = (float(bbox[1]) + float(bbox[3])) / 2.0
                if not (
                    span_size <= main_size * 0.86
                    and span_center <= main_center - main_size * 0.12
                ):
                    continue
                evidence_start = line_offset + start
                evidence_end = line_offset + end
                prefix = raw_text[:evidence_start].rstrip()
                suffix = raw_text[evidence_end:].lstrip()
                physical_line_start = not str(line.raw_text)[:start].strip()
                if not physical_line_start and prefix and prefix[-1] not in ".;:,)]":
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
                            "source_text_line_id": line.line_id,
                            "physical_line_start": physical_line_start,
                        },
                        notes=[
                            "smaller_raised_span_at_definition_boundary",
                            *(
                                ["marker_at_physical_line_start"]
                                if physical_line_start
                                else []
                            ),
                        ],
                    )
                )

        structured_marker = bool(
            marker_evidence
            or _has_extracted_footer_definition_start(raw_text)
            or TEXTUAL_ASTERISK_DEFINITION_PATTERN.search(raw_text)
        )

        group_bbox = (
            min(float(line.bbox[0]) for line in group),
            min(float(line.bbox[1]) for line in group),
            max(float(line.bbox[2]) for line in group),
            max(float(line.bbox[3]) for line in group),
        )
        group_line_indices = [
            line.line_index for line in group if line.line_index is not None
        ]
        notes = [
            "table_region_accepted_raw_positioned_footer_lines",
            "footer_ownership_accepted_by_table_region",
        ]
        if structured_marker:
            notes.append("structured_definition_marker")
        notes.extend(f"source_text_line_id:{line.line_id}" for line in group)
        footer_lines.append(
            FootnoteDefinitionCandidateLine(
                line_id=f"page-{table.page_num}-accepted-footer-{table_position}",
                page_num=table.page_num,
                raw_text=raw_text,
                source_scope="table_note",
                source_id=f"{table.table_id}:raw_positioned_footer_lines",
                table_id=table.table_id,
                visual_id=visual_id_by_table_id.get(table.table_id),
                bbox=group_bbox,
                page_height=page_heights.get(table.page_num),
                line_index=(
                    min(group_line_indices) if group_line_indices else table_position
                ),
                source_artifact="paper_text_stream.json",
                confidence=0.9 if structured_marker else 0.82,
                marker_evidence=marker_evidence,
                notes=notes,
            )
        )
    return footer_lines


def build_paper_footnote_footers_from_text_stream_lines(
    footer_lines: Sequence[FootnoteDefinitionCandidateLine],
) -> list[FootnoteFooter]:
    """Build reviewable table-footer regions from paper text-stream line groups."""
    existing_keys: set[tuple[str | None, str]] = set()
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
                detection_basis="table_region_raw_positioned_footer_band",
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
    resolved_table_set: ResolvedTableSet | None = None,
) -> list[FootnoteDefinition]:
    """Extract candidate footnote definition records from local note text."""
    definitions: list[FootnoteDefinition] = []
    visual_id_by_table_id = _table_visual_ids(extracted_tables or [], resolved_table_set)

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
            caption_text = TABLE_CAPTION_ROW_PATTERN.sub("", raw_text, count=1).strip()
            definition_start = next(
                (
                    match.start("glyph")
                    for match in DEFINITION_BLOCK_MARKER_PATTERN.finditer(caption_text)
                    if match.start() > 0
                    and match.group("prefix").rstrip() in {".", ";", ":", ","}
                ),
                None,
            )
            if definition_start is None:
                continue
            for glyph_raw, definition_text, _marker_evidence in _parse_definition_markers(
                caption_text[definition_start:]
            ):
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
    resolved_table_set: ResolvedTableSet | None = None,
) -> PaperFootnotes:
    """Link footnote anchors to definitions by glyph and local scope."""
    definitions_by_glyph: dict[str, list[FootnoteDefinition]] = {}
    for definition in footnotes.definitions:
        definitions_by_glyph.setdefault(definition.glyph_key, []).append(definition)

    bibliography_label_keys = bibliography_label_keys or set()
    continuation_scope_by_table_id: dict[str, str] = {}
    for resolved_table in resolved_table_set.resolved_tables if resolved_table_set is not None else []:
        if resolved_table.resolution_type != "integrated_continuation":
            continue
        for source_table_id in resolved_table.source_table_ids:
            continuation_scope_by_table_id[source_table_id] = resolved_table.table_id

    links: list[FootnoteLink] = []
    for anchor_index, anchor in enumerate(footnotes.anchors):
        candidates = definitions_by_glyph.get(anchor.glyph_key, [])
        anchor_continuation_scope = (
            continuation_scope_by_table_id.get(anchor.table_id)
            if anchor.table_id is not None
            else None
        )
        if (
            anchor.glyph_kind == "number"
            and anchor.source_scope == "table_cell"
        ):
            local_candidates = [
                definition
                for definition in candidates
                if (anchor.table_id is not None and anchor.table_id == definition.table_id)
                or (
                    anchor_continuation_scope is not None
                    and definition.table_id is not None
                    and continuation_scope_by_table_id.get(definition.table_id)
                    == anchor_continuation_scope
                )
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
            elif (
                anchor_continuation_scope is not None
                and definition.table_id is not None
                and continuation_scope_by_table_id.get(definition.table_id)
                == anchor_continuation_scope
            ) or (
                (anchor.table_id is None or definition.table_id is None)
                and anchor.visual_id is not None
                and anchor.visual_id == definition.visual_id
            ):
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
    resolved_table_set: ResolvedTableSet | None = None,
) -> dict[str, str]:
    visual_id_by_table_id: dict[str, str] = {}
    rejected_table_ids = {
            source_table.source_table_id
            for source_table in resolved_table_set.source_tables
            if source_table.role == "rejected_continuation"
    } if resolved_table_set is not None else set()
    for table in extracted_tables:
        if table.table_id in rejected_table_ids:
            continue
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
    for resolved_table in resolved_table_set.resolved_tables if resolved_table_set is not None else []:
        if resolved_table.resolution_type != "integrated_continuation":
            continue
        visual_id = (
            visual_id_for("table", str(resolved_table.logical_table_number))
            if resolved_table.logical_table_number is not None
            else next(
                (
                    visual_id_by_table_id[table_id]
                    for table_id in resolved_table.source_table_ids
                    if table_id in visual_id_by_table_id
                ),
                None,
            )
        )
        if visual_id is None:
            continue
        for table_id in resolved_table.source_table_ids:
            visual_id_by_table_id[table_id] = visual_id
    return visual_id_by_table_id
