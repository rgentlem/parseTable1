"""Build paper-level bibliography and reference-link artifacts."""

from __future__ import annotations

import re
from dataclasses import dataclass
from collections.abc import Sequence
from pathlib import Path

from table1_parser.schemas import (
    BibliographyEntry,
    BibliographyReferenceMention,
    FootnoteAnchor,
    FootnoteDefinition,
    PaperBibliography,
    PaperSection,
    PaperTextLine,
    PaperTextStream,
)
from table1_parser.reference_sections import (
    INLINE_REFERENCE_START_PATTERN,
    REFERENCE_HEADING_LINE_PATTERN,
    reference_start_text,
)
from table1_parser.text_cleaning import clean_text


LOW_BIBLIOGRAPHY_ENTRY_COUNT_THRESHOLD = 10
LONG_BIBLIOGRAPHY_ENTRY_VISUAL_LINE_THRESHOLD = 12
LONG_BIBLIOGRAPHY_ENTRY_TEXT_LENGTH_THRESHOLD = 1800
MAX_REFERENCE_NUMBER = 300
REFERENCE_LABEL_RELATIVE_X_TOLERANCE = 18.0
REFERENCE_ROW_Y_TOLERANCE = 3.5
REFERENCE_LOCAL_COLUMN_GAP_THRESHOLD = 60.0
REFERENCE_CONTINUATION_MAX_VERTICAL_GAP = 48.0
HANGING_INDENT_ENTRY_START_X_TOLERANCE = 4.0
HANGING_INDENT_CONTINUATION_MIN_INDENT = 7.0
HANGING_INDENT_MIN_ENTRY_COUNT = 3
INVISIBLE_TEXT_CHARS_PATTERN = re.compile(r"[\u200b\u200c\u200d\ufeff]")
REFERENCE_HEADING_PATTERN = re.compile(r"\b(?:references?|bibliography|works cited)\b", re.IGNORECASE)
REFERENCE_LIST_CUE_PATTERN = re.compile(
    r"\b(?:references?|bibliography|works cited)\b\s+(?=(?:\[\s*)?\d{1,3}(?:\s*\])?[.)]?\s+[A-Z])",
    re.IGNORECASE,
)
BIBLIOGRAPHY_CONTENT_CUE_PATTERN = re.compile(
    r"\b(?:18|19|20)\d{2}\b|\bdoi\b|\bpmid\b|\bpubmed\b|https?://",
    re.IGNORECASE,
)
REFERENCE_ENTRY_START_PATTERN = re.compile(
    r"(?P<prefix>^|\s+-\s+|\s+)\s*(?:\[\s*)?(?P<label>\d{1,3})(?:\s*\])?[.)]?\s+(?=[A-Za-z])"
)
REFERENCE_TABLE_ROW_SPLIT_PATTERN = re.compile(r"\s+(?=\|(?:\d{1,3}|---|\|))")
REFERENCE_TABLE_START_PATTERN = re.compile(r"\s+\|\d{1,3}\|")
REFERENCE_ROW_START_PATTERN = re.compile(
    r"^(?:\[\s*(?P<bracket_label>\d{1,3})\s*\]|(?P<label>\d{1,3})(?:[.)])?)\s+(?P<body>\S.*)$"
)
REFERENCE_LABEL_ONLY_PATTERN = re.compile(
    r"^(?:\[\s*(?P<bracket_label>\d{1,3})\s*\]|(?P<label>\d{1,3})(?:[.)])?)$"
)
REFERENCE_PAGE_NUMBER_ROW_PATTERN = re.compile(r"^\d{1,4}$")
UNNUMBERED_REFERENCE_START_PATTERN = re.compile(r"^[A-Za-z][^\s]*")
REFERENCE_LEADING_ARTIFACT_ZERO_PATTERN = re.compile(r"^0\s+(?=\d{1,3}[.)]\s)")
REFERENCE_LEADING_PAGE_ARTIFACT_PATTERN = re.compile(r"^\d{3,4}\s+(?=\d{1,3}[.)]\s)")
TERMINAL_NON_REFERENCE_PATTERN = re.compile(
    r"^(?:"
    r"acknowledg(?:e)?ments?|author contributions?|"
    r"competing interests?|conflicts? of interest|data availability|"
    r"funding|supplementary (?:information|materials?)|"
    r"correspondence|submitted|received|accepted|published online|"
    r"disclaimer(?:/publisher\s*[’']?\s*s note)?|publisher\s*[’']?\s*s note|"
    r"table\s+\d+|fig(?:ure)?\.?\s+\d+"
    r")\b",
    re.IGNORECASE,
)
BIBLIOGRAPHY_SECTION_STOP_HEADING_PATTERN = re.compile(
    r"^(?:"
    r"abbreviations?|acknowledg(?:e)?ments?|author contributions?|"
    r"competing interests?|conflicts? of interest|data availability|"
    r"declarations?|ethics approval(?: and consent to participate)?|"
    r"funding|supplementary (?:information|materials?)|appendix|appendices"
    r")\s*[:.]?$",
    re.IGNORECASE,
)
BIBLIOGRAPHY_TRAILING_SECTION_MARKER_PATTERN = re.compile(
    r"\s+(?:"
    r"acknowledg(?:e)?ments?|author contributions?|"
    r"competing interests?|conflicts? of interest|data availability|"
    r"funding|supplementary (?:information|materials?)"
    r")\s*:|\s+publisher\s*[’']?\s*s note\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class _BibliographyVisualRow:
    """One visual text row inside a reference section."""

    text: str
    segment_texts: list[str]
    line_ids: list[str]
    page_num: int
    column_index: int
    bbox: tuple[float, float, float, float]
    relative_x0: float
    role: str


@dataclass(frozen=True)
class _ReferenceRowStart:
    """Detected bibliography label and same-row body text."""

    label_raw: str
    reference_number: int
    body_text: str


@dataclass
class _ActiveBibliographyEntry:
    """Mutable bibliography entry while layout rows are being assembled."""

    label_raw: str
    reference_number: int | None
    parts: list[str]
    rows: list[_BibliographyVisualRow]


def build_paper_bibliography(
    paper_id: str,
    source_pdf: str,
    paper_sections: Sequence[PaperSection],
    footnote_anchors: Sequence[FootnoteAnchor],
    footnote_definitions: Sequence[FootnoteDefinition],
    bibliography_entries: Sequence[BibliographyEntry] | None = None,
) -> PaperBibliography:
    """Build a paper-level bibliography artifact with linked table reference markers."""
    entries = (
        list(bibliography_entries)
        if bibliography_entries is not None
        else build_bibliography_entries_from_sections(paper_sections)
    )
    reference_mentions = build_bibliography_reference_mentions_from_footnote_anchors(
        footnote_anchors,
        footnote_definitions,
        entries,
    )
    extraction_metadata = bibliography_extraction_metadata(entries, reference_mentions)
    return PaperBibliography(
        paper_id=paper_id,
        source_pdf=Path(source_pdf).name,
        entries=entries,
        reference_mentions=reference_mentions,
        metadata={
            "source_artifacts": [
                "paper_sections.json",
                "paper_text_stream.json",
                "paper_page_furniture.json",
                "cell_text_annotations.json",
                "paper_footnotes.json",
            ],
            "entry_count": len(entries),
            "reference_mention_count": len(reference_mentions),
            "resolved_reference_mention_count": sum(
                mention.link_status == "resolved" for mention in reference_mentions
            ),
            "ambiguous_reference_mention_count": sum(
                mention.link_status == "ambiguous" for mention in reference_mentions
            ),
            "unresolved_reference_mention_count": sum(
                mention.link_status == "unresolved" for mention in reference_mentions
            ),
            **extraction_metadata,
        },
    )


def build_bibliography_entries_from_text_stream(
    paper_text_stream: PaperTextStream,
) -> list[BibliographyEntry]:
    """Parse bibliography entries from positioned layout text."""
    if not paper_text_stream.lines:
        return []

    candidate_entry_sets: list[list[BibliographyEntry]] = []
    for line_index, line in enumerate(paper_text_stream.lines):
        start_text = reference_start_text(line.text)
        heading_match = REFERENCE_HEADING_LINE_PATTERN.match(start_text)
        inline_match = INLINE_REFERENCE_START_PATTERN.match(start_text)
        if inline_match is None and (
            heading_match is None
            or not _line_has_reference_section_heading_layout(line, paper_text_stream)
        ):
            continue
        inline_body = inline_match.group("body") if inline_match is not None else None
        entries = _build_bibliography_entries_from_layout_region(
            paper_text_stream,
            start_line_index=line_index,
            inline_body=inline_body,
            heading=inline_match.group("heading") if inline_match is not None else start_text,
        )
        if entries and _bibliography_entries_have_reference_list_shape(entries):
            candidate_entry_sets.append(entries)

    if not candidate_entry_sets:
        return []
    return max(
        candidate_entry_sets,
        key=lambda entries: (
            len(entries),
            sum(entry.reference_number is not None for entry in entries),
            max((entry.reference_number or 0 for entry in entries), default=0),
            -sum(len(entry.clean_text) for entry in entries),
        ),
    )


def _line_has_reference_section_heading_layout(
    line: PaperTextLine,
    paper_text_stream: PaperTextStream,
) -> bool:
    """Return whether a reference-heading text line has section-heading layout."""
    if line.role != "heading" and "layout_section_heading" not in line.notes:
        return False
    page = next(
        (page for page in paper_text_stream.pages if page.page_num == line.page_num),
        None,
    )
    if page is None:
        return True
    page_width = max(float(page.page_width), 1.0)
    column_bands = page.column_bands or [(0.0, page_width)]
    column_index = min(max(line.column_index, 0), len(column_bands) - 1)
    band_left, band_right = column_bands[column_index]
    same_column_lines = [
        stream_line
        for stream_line in paper_text_stream.lines
        if stream_line.page_num == line.page_num and stream_line.column_index == line.column_index
    ]
    content_left = min((float(stream_line.bbox[0]) for stream_line in same_column_lines), default=float(band_left))
    content_right = max((float(stream_line.bbox[2]) for stream_line in same_column_lines), default=float(band_right))
    band_width = max(float(band_right) - float(band_left), 1.0)
    left, _top, right, _bottom = line.bbox
    line_center = (float(left) + float(right)) / 2.0
    content_center = (content_left + content_right) / 2.0
    content_width = max(content_right - content_left, band_width)
    left_aligned = float(left) <= content_left + max(24.0, content_width * 0.06)
    centered_heading = abs(line_center - content_center) <= max(32.0, content_width * 0.12)
    return left_aligned or centered_heading or "full_width_line" in line.notes


def _bibliography_entries_have_reference_list_shape(entries: Sequence[BibliographyEntry]) -> bool:
    """Return whether extracted candidate entries look like a bibliography."""
    if not entries:
        return False
    numbered_entries = [entry for entry in entries if entry.reference_number is not None]
    if numbered_entries:
        reference_numbers = sorted(
            entry.reference_number
            for entry in numbered_entries
            if entry.reference_number is not None
        )
        return len(numbered_entries) >= 2 and reference_numbers[0] == 1
    cue_count = sum(
        bool(BIBLIOGRAPHY_CONTENT_CUE_PATTERN.search(entry.clean_text))
        for entry in entries
    )
    return len(entries) >= LOW_BIBLIOGRAPHY_ENTRY_COUNT_THRESHOLD and cue_count >= 3


def build_bibliography_entries_from_sections(
    paper_sections: Sequence[PaperSection],
) -> list[BibliographyEntry]:
    """Parse numbered bibliography entries from markdown-derived paper sections."""
    entries: list[BibliographyEntry] = []
    seen_entry_ids: set[str] = set()
    for section in paper_sections:
        section_text = clean_text(section.content)
        if not section_text:
            continue
        reference_region = section_text
        confidence = 0.72
        notes: list[str] = []
        heading = clean_text(section.heading or "")
        if section.role_hint == "references_like" or REFERENCE_HEADING_PATTERN.search(heading):
            confidence = 0.9
            notes.append("section_heading_reference_like")
        else:
            cue_match = REFERENCE_LIST_CUE_PATTERN.search(section_text)
            if cue_match is None:
                continue
            reference_region = section_text[cue_match.end():]
            notes.append("inline_reference_list_cue")
        table_entries = _build_bibliography_entries_from_reference_table_region(
            reference_region,
            section=section,
            confidence=confidence,
        )
        entry_matches = []
        next_expected_label: int | None = None
        for match in REFERENCE_ENTRY_START_PATTERN.finditer(reference_region):
            label_value = int(match.group("label"))
            if next_expected_label is None or label_value == next_expected_label:
                entry_matches.append(match)
                next_expected_label = label_value + 1
        if not entry_matches:
            for table_entry in table_entries:
                if table_entry.entry_id not in seen_entry_ids:
                    seen_entry_ids.add(table_entry.entry_id)
                    entries.append(table_entry)
            continue
        if len(entry_matches) < 2 or int(entry_matches[0].group("label")) != 1:
            for table_entry in table_entries:
                if table_entry.entry_id not in seen_entry_ids:
                    seen_entry_ids.add(table_entry.entry_id)
                    entries.append(table_entry)
            continue
        for entry_index, match in enumerate(entry_matches):
            table_match = REFERENCE_TABLE_START_PATTERN.search(reference_region, match.end())
            next_match_start = (
                entry_matches[entry_index + 1].start()
                if entry_index + 1 < len(entry_matches)
                else len(reference_region)
            )
            if table_match is not None and table_match.start() < next_match_start:
                next_match_start = table_match.start()
            label_raw = match.group("label")
            raw_text = reference_region[match.end():next_match_start].strip(" -\n\t")
            clean_entry_text = clean_text(raw_text)
            if not clean_entry_text:
                continue
            base_entry_id = f"bib:{int(label_raw)}"
            entry_id = base_entry_id
            duplicate_index = 1
            while entry_id in seen_entry_ids:
                duplicate_index += 1
                entry_id = f"{base_entry_id}:{duplicate_index}"
            seen_entry_ids.add(entry_id)
            entries.append(
                BibliographyEntry(
                    entry_id=entry_id,
                    label_raw=label_raw,
                    label_key=bibliography_label_key(label_raw),
                    reference_number=int(label_raw),
                    raw_text=raw_text,
                    clean_text=clean_entry_text,
                    source_section_id=section.section_id,
                    heading=section.heading,
                    role_hint=section.role_hint,
                    confidence=confidence,
                    notes=notes,
                )
            )
        for table_entry in table_entries:
            if table_entry.entry_id not in seen_entry_ids:
                seen_entry_ids.add(table_entry.entry_id)
                entries.append(table_entry)
    entries.sort(key=lambda entry: (entry.reference_number is None, entry.reference_number or 0, entry.entry_id))
    return entries


def build_bibliography_reference_mentions_from_footnote_anchors(
    footnote_anchors: Sequence[FootnoteAnchor],
    footnote_definitions: Sequence[FootnoteDefinition],
    bibliography_entries: Sequence[BibliographyEntry],
) -> list[BibliographyReferenceMention]:
    """Promote numeric table-cell anchors without local footnotes into bibliography references."""
    entries_by_label_key: dict[str, list[BibliographyEntry]] = {}
    for entry in bibliography_entries:
        if entry.reference_number is None:
            continue
        entries_by_label_key.setdefault(entry.label_key, []).append(entry)
    mentions: list[BibliographyReferenceMention] = []
    for anchor in footnote_anchors:
        if (
            anchor.glyph_kind != "number"
            or anchor.source_scope != "table_cell"
            or _has_local_footnote_definition(anchor, footnote_definitions)
        ):
            continue
        candidate_entries = entries_by_label_key.get(anchor.glyph_key, [])
        if len(candidate_entries) == 1:
            link_status = "resolved"
            entry_id = candidate_entries[0].entry_id
            confidence = min(anchor.confidence, candidate_entries[0].confidence, 0.86)
            notes = ["numeric_table_cell_marker_linked_to_bibliography_entry"]
        elif len(candidate_entries) > 1:
            link_status = "ambiguous"
            entry_id = None
            confidence = min(anchor.confidence, max(entry.confidence for entry in candidate_entries), 0.55)
            notes = ["multiple_bibliography_entries_with_same_label"]
        else:
            link_status = "unresolved"
            entry_id = None
            confidence = 0.0
            notes = ["no_bibliography_entry_for_numeric_table_cell_marker"]
        mentions.append(
            BibliographyReferenceMention(
                mention_id=f"bibref:{anchor.anchor_id}",
                label_raw=anchor.glyph_raw,
                label_key=anchor.glyph_key,
                source_scope="table_cell",
                source_id=anchor.source_id,
                source_artifact=anchor.source_artifact or "paper_footnotes.json",
                page_num=anchor.page_num,
                table_id=anchor.table_id,
                row_idx=anchor.row_idx,
                col_idx=anchor.col_idx,
                source_role=anchor.source_role,
                attached_to_text=anchor.attached_to_text,
                text_context=anchor.text_context,
                bbox=anchor.bbox,
                link_status=link_status,
                entry_id=entry_id,
                candidate_entry_ids=[entry.entry_id for entry in candidate_entries],
                confidence=confidence,
                notes=notes,
            )
        )
    return mentions


def bibliography_label_key(label_raw: str) -> str:
    """Return the canonical bibliography label key used for citation linking."""
    return f"number:{int(label_raw.strip())}"


def paper_bibliography_to_payload(bibliography: PaperBibliography) -> dict[str, object]:
    """Serialize a paper bibliography artifact as a JSON-friendly record."""
    return bibliography.model_dump(mode="json")


def bibliography_extraction_metadata(
    entries: Sequence[BibliographyEntry],
    reference_mentions: Sequence[BibliographyReferenceMention],
) -> dict[str, object]:
    """Return sanity diagnostics for the bibliography extraction result."""
    diagnostics: list[str] = []
    numbered_entries = [entry for entry in entries if entry.reference_number is not None]
    unnumbered_entry_count = len(entries) - len(numbered_entries)
    reference_numbers = sorted({entry.reference_number for entry in numbered_entries if entry.reference_number is not None})
    missing_reference_numbers: list[int] = []
    if reference_numbers:
        missing_reference_numbers = [
            value
            for value in range(reference_numbers[0], reference_numbers[-1] + 1)
            if value not in reference_numbers
        ]
    entry_line_counts = {
        entry.entry_id: entry.visual_line_count
        for entry in entries
        if entry.visual_line_count > 0
    }
    long_entry_ids = [
        entry.entry_id
        for entry in entries
        if (
            entry.visual_line_count >= LONG_BIBLIOGRAPHY_ENTRY_VISUAL_LINE_THRESHOLD
            or len(entry.clean_text) >= LONG_BIBLIOGRAPHY_ENTRY_TEXT_LENGTH_THRESHOLD
        )
    ]
    mention_numbers = [
        int(mention.label_raw)
        for mention in reference_mentions
        if mention.label_raw.strip().isdigit()
    ]
    max_mention_number = max(mention_numbers, default=0)
    max_reference_number = max(reference_numbers, default=0)
    if not entries:
        diagnostics.append("no_bibliography_entries_extracted")
    elif len(entries) < LOW_BIBLIOGRAPHY_ENTRY_COUNT_THRESHOLD:
        diagnostics.append("low_bibliography_entry_count")
    if missing_reference_numbers:
        diagnostics.append("nonsequential_bibliography_labels")
    if long_entry_ids:
        diagnostics.append("long_bibliography_entry_possible_collapse")
    if max_mention_number > max_reference_number and numbered_entries:
        diagnostics.append("reference_mentions_exceed_extracted_bibliography")
    elif max_mention_number and entries and not numbered_entries:
        diagnostics.append("numeric_reference_mentions_without_numbered_bibliography")

    if numbered_entries and unnumbered_entry_count:
        numbering_style = "mixed"
    elif numbered_entries:
        numbering_style = "numbered"
    elif unnumbered_entry_count:
        numbering_style = "unnumbered"
    else:
        numbering_style = "none"

    return {
        "bibliography_extraction_status": (
            "empty" if not entries else ("warning" if diagnostics else "ok")
        ),
        "bibliography_extraction_diagnostics": diagnostics,
        "bibliography_entry_source_artifacts": sorted(
            {entry.source_artifact for entry in entries}
        ),
        "bibliography_numbering_style": numbering_style,
        "numbered_entry_count": len(numbered_entries),
        "unnumbered_entry_count": unnumbered_entry_count,
        "min_reference_number": min(reference_numbers, default=None),
        "max_reference_number": max_reference_number or None,
        "missing_reference_numbers": missing_reference_numbers,
        "max_observed_reference_mention_number": max_mention_number or None,
        "entry_visual_line_counts": entry_line_counts,
        "max_entry_visual_line_count": max(entry_line_counts.values(), default=0),
        "long_entry_ids": long_entry_ids,
        "low_entry_count_threshold": LOW_BIBLIOGRAPHY_ENTRY_COUNT_THRESHOLD,
        "long_entry_visual_line_threshold": LONG_BIBLIOGRAPHY_ENTRY_VISUAL_LINE_THRESHOLD,
    }


def _build_bibliography_entries_from_layout_region(
    paper_text_stream: PaperTextStream,
    *,
    start_line_index: int,
    inline_body: str | None,
    heading: str,
) -> list[BibliographyEntry]:
    region_lines: list[PaperTextLine] = []
    start_line = paper_text_stream.lines[start_line_index]
    above_heading_right_label_x0s = [
        float(line.bbox[0])
        for line in paper_text_stream.lines
        if (
            line.page_num == start_line.page_num
            and float(line.bbox[1]) < float(start_line.bbox[1]) - 3.0
            and float(line.bbox[0]) >= float(start_line.bbox[0]) + 100.0
            and _line_starts_with_reference_label(line.text)
        )
    ]
    above_heading_right_reference_x0 = min(above_heading_right_label_x0s, default=None)
    if inline_body:
        region_lines.append(
            start_line.model_copy(
                update={
                    "line_id": f"{start_line.line_id}:reference-body",
                    "raw_text": inline_body,
                    "text": inline_body,
                    "role": "body",
                }
            )
        )
    for line_index, line in enumerate(paper_text_stream.lines):
        if line_index == start_line_index or line.page_num < start_line.page_num:
            continue
        if line.page_num == start_line.page_num and float(line.bbox[2]) < float(start_line.bbox[0]) - 6.0:
            continue
        if (
            line.page_num == start_line.page_num
            and float(line.bbox[1]) < float(start_line.bbox[1]) - 3.0
            and (
                above_heading_right_reference_x0 is None
                or float(line.bbox[0]) < above_heading_right_reference_x0 - 20.0
            )
        ):
            continue
        region_lines.append(line)
    visual_rows = _build_bibliography_visual_rows(region_lines)
    left_edges_by_column = _hanging_indent_left_edges_by_column(visual_rows)
    entries: list[BibliographyEntry] = []
    seen_entry_ids: set[str] = set()
    active_entry: _ActiveBibliographyEntry | None = None
    expected_reference_number: int | None = None

    for row in visual_rows:
        row_text = _normalized_reference_text(row.text)
        row_start = _row_starts_bibliography_entry(row)
        is_unnumbered_start = (
            expected_reference_number is None
            and _hanging_indent_row_starts_entry(row, left_edges_by_column)
        )
        if active_entry is not None and TERMINAL_NON_REFERENCE_PATTERN.match(row_text):
            break
        if (
            active_entry is not None
            and BIBLIOGRAPHY_SECTION_STOP_HEADING_PATTERN.match(row_text)
            and row_start is None
            and not is_unnumbered_start
        ):
            break
        if (
            active_entry is not None
            and active_entry.rows
            and row.page_num != active_entry.rows[-1].page_num
            and row.role == "heading"
            and row_start is None
            and not is_unnumbered_start
        ):
            break
        midrow_start = _expected_reference_start_within_row(row, expected_reference_number)
        if (
            active_entry is not None
            and active_entry.reference_number is not None
            and midrow_start is not None
        ):
            prefix_text = clean_text(row.text[: midrow_start.start_index])
            if prefix_text:
                active_entry.parts.append(prefix_text)
            active_entry.rows.append(row)
            entry = _bibliography_entry_from_active_layout_entry(
                active_entry,
                seen_entry_ids,
                heading=heading,
            )
            if entry is not None:
                entries.append(entry)
            body_text, stop_after_entry_start = _strip_trailing_section_text(midrow_start.body_text)
            active_entry = _ActiveBibliographyEntry(
                label_raw=midrow_start.label_raw,
                reference_number=midrow_start.reference_number,
                parts=[body_text] if body_text else [],
                rows=[row],
            )
            expected_reference_number = midrow_start.reference_number + 1
            if stop_after_entry_start:
                break
            continue
        if row_start is not None and _is_expected_layout_reference_start(row_start, expected_reference_number):
            if active_entry is not None:
                entry = _bibliography_entry_from_active_layout_entry(
                    active_entry,
                    seen_entry_ids,
                    heading=heading,
                )
                if entry is not None:
                    entries.append(entry)
            body_text, stop_after_entry_start = _strip_trailing_section_text(row_start.body_text)
            active_entry = _ActiveBibliographyEntry(
                label_raw=row_start.label_raw,
                reference_number=row_start.reference_number,
                parts=[body_text] if body_text else [],
                rows=[row],
            )
            expected_reference_number = row_start.reference_number + 1
            if stop_after_entry_start:
                break
            continue
        if is_unnumbered_start:
            if active_entry is not None:
                entry = _bibliography_entry_from_active_layout_entry(
                    active_entry,
                    seen_entry_ids,
                    heading=heading,
                )
                if entry is not None:
                    entries.append(entry)
            body_text, stop_after_entry_start = _strip_trailing_section_text(row.text)
            active_entry = _ActiveBibliographyEntry(
                label_raw="",
                reference_number=None,
                parts=[body_text] if body_text else [],
                rows=[row],
            )
            expected_reference_number = None
            if stop_after_entry_start:
                break
            continue
        if active_entry is None:
            continue
        if _has_large_same_column_continuation_gap(active_entry, row):
            continue
        active_entry.rows.append(row)
        if row.text:
            row_body_text, stop_after_continuation = _strip_trailing_section_text(row.text)
            if stop_after_continuation:
                if row_body_text:
                    active_entry.parts.append(row_body_text)
                break
            active_entry.parts.append(row.text)

    if active_entry is not None:
        entry = _bibliography_entry_from_active_layout_entry(
            active_entry,
            seen_entry_ids,
            heading=heading,
        )
        if entry is not None:
            entries.append(entry)

    if (
        entries
        and not any(entry.reference_number is not None for entry in entries)
        and len(entries) < HANGING_INDENT_MIN_ENTRY_COUNT
    ):
        return []
    return entries


def _build_bibliography_visual_rows(lines: Sequence[PaperTextLine]) -> list[_BibliographyVisualRow]:
    grouped_lines: dict[int, list[PaperTextLine]] = {}
    for line in lines:
        grouped_lines.setdefault(line.page_num, []).append(line)

    rows: list[_BibliographyVisualRow] = []
    for page_num, page_lines in sorted(grouped_lines.items()):
        page_column_groups = _group_lines_by_reference_columns(page_lines)
        page_rows: list[_BibliographyVisualRow] = []
        for local_column_index, page_column_lines in page_column_groups:
            page_rows.extend(_build_bibliography_visual_rows_for_column(page_column_lines, local_column_index, page_num))
        max_column_index = max((column_index for column_index, _ in page_column_groups), default=0)
        rows.extend(_split_embedded_reference_label_rows(page_rows, max_column_index=max_column_index))
    return sorted(rows, key=lambda row: (row.page_num, row.column_index, float(row.bbox[1]), float(row.bbox[0])))


def _build_bibliography_visual_rows_for_column(
    lines: Sequence[PaperTextLine],
    column_index: int,
    page_num: int,
) -> list[_BibliographyVisualRow]:
    if not lines:
        return []
    rows: list[_BibliographyVisualRow] = []
    ordered_lines = sorted(
        lines,
        key=lambda line: (_bbox_center_y(line.bbox), float(line.bbox[0])),
    )
    grouped_rows: list[list[PaperTextLine]] = []
    active_row: list[PaperTextLine] = []
    active_center_y: float | None = None
    for line in ordered_lines:
        center_y = _bbox_center_y(line.bbox)
        if (
            active_row
            and active_center_y is not None
            and abs(center_y - active_center_y) > REFERENCE_ROW_Y_TOLERANCE
        ):
            grouped_rows.append(active_row)
            active_row = []
            active_center_y = None
        active_row.append(line)
        if active_center_y is None:
            active_center_y = center_y
        else:
            active_center_y = (active_center_y + center_y) / 2.0
    if active_row:
        grouped_rows.append(active_row)

    column_min_x = min(
        float(line.bbox[0])
        for row_lines in grouped_rows
        for line in row_lines
    )
    for row_lines in grouped_rows:
        sorted_row_lines = sorted(row_lines, key=lambda line: float(line.bbox[0]))
        segment_texts = [line.text for line in sorted_row_lines if line.text]
        bbox = _union_bboxes([line.bbox for line in sorted_row_lines])
        rows.append(
            _BibliographyVisualRow(
                text=clean_text(" ".join(segment_texts)),
                segment_texts=segment_texts,
                line_ids=[line.line_id for line in sorted_row_lines],
                page_num=page_num,
                column_index=column_index,
                bbox=bbox,
                relative_x0=float(bbox[0]) - column_min_x,
                role="heading" if any(line.role == "heading" for line in sorted_row_lines) else "body",
            )
        )
    return rows


def _group_lines_by_reference_columns(
    lines: Sequence[PaperTextLine],
) -> list[tuple[int, list[PaperTextLine]]]:
    if len(lines) < 8:
        return [(0, list(lines))]
    column_candidate_lines = [
        line
        for line in lines
        if not REFERENCE_PAGE_NUMBER_ROW_PATTERN.match(_normalized_reference_text(line.text))
    ]
    label_x_starts = sorted(
        float(line.bbox[0])
        for line in lines
        if _line_starts_with_reference_label(line.text)
    )
    label_clusters = _cluster_reference_label_x_starts(label_x_starts)
    if len(label_clusters) >= 2:
        centers = [sum(cluster) / len(cluster) for cluster in label_clusters]
        boundaries = [
            centers[index + 1] - 6.0
            for index in range(len(centers) - 1)
        ]
        column_lines: list[list[PaperTextLine]] = [[] for _ in centers]
        for line in lines:
            column_index = sum(float(line.bbox[0]) >= boundary for boundary in boundaries)
            column_lines[column_index].append(line)
        if all(len(group) >= 4 for group in column_lines):
            return [
                (column_index, group)
                for column_index, group in enumerate(column_lines)
                if group
            ]

    x_start_groups: list[list[float]] = []
    for x_start in sorted(float(line.bbox[0]) for line in column_candidate_lines):
        if x_start_groups and x_start - x_start_groups[-1][-1] >= REFERENCE_LOCAL_COLUMN_GAP_THRESHOLD:
            x_start_groups.append([])
        if not x_start_groups:
            x_start_groups.append([])
        x_start_groups[-1].append(x_start)
    if len(x_start_groups) <= 1 or any(len(group) < 4 for group in x_start_groups):
        return [(0, list(lines))]

    boundaries = [
        (max(left_group) + min(right_group)) / 2.0
        for left_group, right_group in zip(x_start_groups, x_start_groups[1:])
    ]
    column_lines: list[list[PaperTextLine]] = [[] for _ in x_start_groups]
    for line in lines:
        column_index = sum(float(line.bbox[0]) >= boundary for boundary in boundaries)
        column_lines[column_index].append(line)
    if any(len(group) < 4 for group in column_lines):
        return [(0, list(lines))]
    return [
        (column_index, group)
        for column_index, group in enumerate(column_lines)
        if group
    ]


def _cluster_reference_label_x_starts(label_x_starts: Sequence[float]) -> list[list[float]]:
    clusters: list[list[float]] = []
    for x_start in sorted(label_x_starts):
        if not clusters or x_start - clusters[-1][-1] > 35.0:
            clusters.append([x_start])
            continue
        clusters[-1].append(x_start)
    return [
        cluster
        for cluster in clusters
        if len(cluster) >= 1
    ]


def _line_starts_with_reference_label(text: str) -> bool:
    line_text = _strip_reference_leading_artifacts(_normalized_reference_text(text))
    label_match = REFERENCE_LABEL_ONLY_PATTERN.match(line_text)
    row_match = REFERENCE_ROW_START_PATTERN.match(line_text)
    label_raw = None
    if label_match is not None:
        label_raw = _reference_label_match_value(label_match)
    elif row_match is not None:
        label_raw = _reference_label_match_value(row_match)
    if label_raw is None:
        return False
    return 0 < int(label_raw) <= MAX_REFERENCE_NUMBER


def _reference_label_match_value(match: re.Match[str]) -> str:
    return match.group("label") or match.group("bracket_label")


def _split_embedded_reference_label_rows(
    rows: Sequence[_BibliographyVisualRow],
    *,
    max_column_index: int,
) -> list[_BibliographyVisualRow]:
    split_rows: list[_BibliographyVisualRow] = []
    embedded_label_pattern = re.compile(r"(?<![\d.])(?P<label>\d{1,3})[.)]\s+(?=[A-Z])")
    for row in rows:
        row_text = _strip_reference_leading_artifacts(_normalized_reference_text(row.text))
        match = None
        for candidate in embedded_label_pattern.finditer(row_text):
            if candidate.start() > 0 and int(candidate.group("label")) <= MAX_REFERENCE_NUMBER:
                match = candidate
                break
        if match is None or row.column_index >= max_column_index:
            split_rows.append(row)
            continue
        prefix_text = clean_text(row_text[: match.start()])
        suffix_text = clean_text(row_text[match.start():])
        if not prefix_text or not suffix_text:
            split_rows.append(row)
            continue
        split_rows.append(
            _BibliographyVisualRow(
                text=prefix_text,
                segment_texts=[prefix_text],
                line_ids=row.line_ids,
                page_num=row.page_num,
                column_index=row.column_index,
                bbox=row.bbox,
                relative_x0=row.relative_x0,
                role=row.role,
            )
        )
        split_rows.append(
            _BibliographyVisualRow(
                text=suffix_text,
                segment_texts=[suffix_text],
                line_ids=row.line_ids,
                page_num=row.page_num,
                column_index=row.column_index + 1,
                bbox=row.bbox,
                relative_x0=0.0,
                role=row.role,
            )
        )
    return split_rows


@dataclass(frozen=True)
class _ReferenceMidrowStart:
    """Expected bibliography label found after previous-column continuation text."""

    label_raw: str
    reference_number: int
    body_text: str
    start_index: int


def _expected_reference_start_within_row(
    row: _BibliographyVisualRow,
    expected_reference_number: int | None,
) -> _ReferenceMidrowStart | None:
    if expected_reference_number is None or expected_reference_number > MAX_REFERENCE_NUMBER:
        return None
    row_text = _normalized_reference_text(row.text)
    if _strip_reference_leading_artifacts(row_text) != row_text:
        return None
    label_raw = str(expected_reference_number)
    pattern = re.compile(
        rf"(?<![\d.])(?P<label>{re.escape(label_raw)})(?:\s*\])?[.)]\s+(?P<body>[A-Z][^\n]*)"
    )
    match = pattern.search(row_text)
    if match is None or match.start() == 0:
        return None
    prefix_text = clean_text(row_text[: match.start()])
    if not prefix_text:
        return None
    return _ReferenceMidrowStart(
        label_raw=label_raw,
        reference_number=expected_reference_number,
        body_text=clean_text(match.group("body")),
        start_index=match.start(),
    )


def _row_starts_bibliography_entry(row: _BibliographyVisualRow) -> _ReferenceRowStart | None:
    if row.relative_x0 > REFERENCE_LABEL_RELATIVE_X_TOLERANCE:
        return None
    if row.segment_texts:
        first_segment = _normalized_reference_text(row.segment_texts[0])
        first_match = REFERENCE_LABEL_ONLY_PATTERN.match(first_segment)
        if first_match is not None:
            label_raw = _reference_label_match_value(first_match)
            reference_number = int(label_raw)
            if reference_number <= MAX_REFERENCE_NUMBER:
                body_text = clean_text(" ".join(row.segment_texts[1:]))
                return _ReferenceRowStart(label_raw, reference_number, body_text)
    row_text = _strip_reference_leading_artifacts(_normalized_reference_text(row.text))
    match = REFERENCE_ROW_START_PATTERN.match(row_text)
    if match is None:
        return None
    label_raw = _reference_label_match_value(match)
    reference_number = int(label_raw)
    if reference_number > MAX_REFERENCE_NUMBER:
        return None
    return _ReferenceRowStart(label_raw, reference_number, clean_text(match.group("body")))


def _is_expected_layout_reference_start(
    row_start: _ReferenceRowStart,
    expected_reference_number: int | None,
) -> bool:
    if expected_reference_number is None:
        return row_start.reference_number == 1
    return row_start.reference_number == expected_reference_number


def _has_large_same_column_continuation_gap(
    active_entry: _ActiveBibliographyEntry,
    row: _BibliographyVisualRow,
) -> bool:
    if not active_entry.rows:
        return False
    previous_row = active_entry.rows[-1]
    if previous_row.page_num != row.page_num or previous_row.column_index != row.column_index:
        return False
    vertical_gap = float(row.bbox[1]) - float(previous_row.bbox[3])
    return vertical_gap > REFERENCE_CONTINUATION_MAX_VERTICAL_GAP


def _hanging_indent_left_edges_by_column(
    visual_rows: Sequence[_BibliographyVisualRow],
) -> dict[tuple[int, int], float]:
    rows_by_column: dict[tuple[int, int], list[_BibliographyVisualRow]] = {}
    for row in visual_rows:
        if _is_ignorable_bibliography_visual_row(row):
            continue
        if row.role == "heading":
            continue
        row_text = _normalized_reference_text(row.text)
        if (
            TERMINAL_NON_REFERENCE_PATTERN.match(row_text)
            or BIBLIOGRAPHY_SECTION_STOP_HEADING_PATTERN.match(row_text)
        ):
            continue
        rows_by_column.setdefault((row.page_num, row.column_index), []).append(row)

    left_edges_by_column: dict[tuple[int, int], float] = {}
    total_start_like_rows = 0
    total_continuation_like_rows = 0
    for column_key, rows in rows_by_column.items():
        if len(rows) < 2:
            continue
        x_positions = sorted(float(row.bbox[0]) for row in rows)
        left_edge = min(x_positions)
        start_like_rows = sum(
            abs(float(row.bbox[0]) - left_edge) <= HANGING_INDENT_ENTRY_START_X_TOLERANCE
            for row in rows
        )
        continuation_like_rows = sum(
            float(row.bbox[0]) - left_edge >= HANGING_INDENT_CONTINUATION_MIN_INDENT
            for row in rows
        )
        if start_like_rows >= 1 and continuation_like_rows >= 1:
            left_edges_by_column[column_key] = left_edge
            total_start_like_rows += start_like_rows
            total_continuation_like_rows += continuation_like_rows

    if total_start_like_rows < HANGING_INDENT_MIN_ENTRY_COUNT or total_continuation_like_rows < HANGING_INDENT_MIN_ENTRY_COUNT:
        return {}
    return left_edges_by_column


def _hanging_indent_row_starts_entry(
    row: _BibliographyVisualRow,
    left_edges_by_column: dict[tuple[int, int], float],
) -> bool:
    if row.role == "heading" or _is_ignorable_bibliography_visual_row(row):
        return False
    left_edge = left_edges_by_column.get((row.page_num, row.column_index))
    if left_edge is None:
        return False
    row_text = _normalized_reference_text(row.text)
    if (
        TERMINAL_NON_REFERENCE_PATTERN.match(row_text)
        or BIBLIOGRAPHY_SECTION_STOP_HEADING_PATTERN.match(row_text)
        or _row_starts_bibliography_entry(row) is not None
    ):
        return False
    if abs(float(row.bbox[0]) - left_edge) > HANGING_INDENT_ENTRY_START_X_TOLERANCE:
        return False
    return bool(UNNUMBERED_REFERENCE_START_PATTERN.match(row_text))


def _is_ignorable_bibliography_visual_row(row: _BibliographyVisualRow) -> bool:
    row_text = _normalized_reference_text(row.text)
    return not row_text or bool(REFERENCE_PAGE_NUMBER_ROW_PATTERN.match(row_text))


def _strip_trailing_section_text(text: str) -> tuple[str, bool]:
    trailing_section_match = BIBLIOGRAPHY_TRAILING_SECTION_MARKER_PATTERN.search(text)
    if trailing_section_match is None:
        return text, False
    return clean_text(text[: trailing_section_match.start()]), True


def _bibliography_entry_from_active_layout_entry(
    active_entry: _ActiveBibliographyEntry,
    seen_entry_ids: set[str],
    *,
    heading: str,
) -> BibliographyEntry | None:
    clean_entry_text = clean_text(" ".join(part for part in active_entry.parts if part))
    if not clean_entry_text:
        return None
    if active_entry.reference_number is None:
        unnumbered_index = sum(entry_id.startswith("bib:unnum:") for entry_id in seen_entry_ids) + 1
        base_entry_id = f"bib:unnum:{unnumbered_index}"
        label_key = f"unnumbered:{unnumbered_index}"
        notes = ["layout_text_stream_entries", "hanging_indent_entries", "unnumbered_bibliography_entries"]
        confidence = 0.88
    else:
        base_entry_id = f"bib:{active_entry.reference_number}"
        label_key = bibliography_label_key(active_entry.label_raw)
        notes = ["layout_text_stream_entries"]
        confidence = 0.92
    entry_id = base_entry_id
    duplicate_index = 1
    while entry_id in seen_entry_ids:
        duplicate_index += 1
        entry_id = f"{base_entry_id}:{duplicate_index}"
    seen_entry_ids.add(entry_id)
    page_nums = sorted({row.page_num for row in active_entry.rows})
    bbox = _union_bboxes([row.bbox for row in active_entry.rows]) if len(page_nums) == 1 else None
    return BibliographyEntry(
        entry_id=entry_id,
        label_raw=active_entry.label_raw,
        label_key=label_key,
        reference_number=active_entry.reference_number,
        raw_text=clean_entry_text,
        clean_text=clean_entry_text,
        heading=clean_text(heading),
        role_hint="references_like",
        source_artifact="paper_text_stream.json",
        source_line_ids=[
            line_id
            for row in active_entry.rows
            for line_id in row.line_ids
        ],
        page_nums=page_nums,
        bbox=bbox,
        visual_line_count=len(active_entry.rows),
        confidence=confidence,
        notes=notes,
    )


def _build_bibliography_entries_from_reference_table_region(
    reference_region: str,
    *,
    section: PaperSection,
    confidence: float,
) -> list[BibliographyEntry]:
    """Parse markdown-table bibliography rows into separate entries."""
    chunks = REFERENCE_TABLE_ROW_SPLIT_PATTERN.split(reference_region)
    active_labels_by_side: dict[int, str] = {}
    entry_parts_by_label: dict[str, list[str]] = {}
    entry_order: list[str] = []
    for chunk in chunks:
        row_text = chunk.strip()
        if not row_text.startswith("|"):
            continue
        row_inner = row_text
        if row_inner.startswith("|"):
            row_inner = row_inner[1:]
        if row_inner.endswith("|"):
            row_inner = row_inner[:-1]
        cells = [
            clean_text(cell.replace("<br>", " "))
            for cell in row_inner.split("|")
        ]
        if not cells or all(not cell or set(cell) <= {"-"} for cell in cells):
            continue
        for side, label_idx in enumerate(range(0, len(cells), 2)):
            text_idx = label_idx + 1
            if text_idx >= len(cells):
                continue
            label_text = cells[label_idx].strip() if label_idx < len(cells) else ""
            body_text = cells[text_idx].strip()
            if label_text.isdigit():
                active_labels_by_side[side] = label_text
                if label_text not in entry_parts_by_label:
                    entry_parts_by_label[label_text] = []
                    entry_order.append(label_text)
                if body_text:
                    entry_parts_by_label[label_text].append(body_text)
                continue
            if body_text and side in active_labels_by_side:
                entry_parts_by_label[active_labels_by_side[side]].append(body_text)
    entries: list[BibliographyEntry] = []
    for label_raw in entry_order:
        clean_entry_text = clean_text(" ".join(entry_parts_by_label[label_raw]))
        if not clean_entry_text:
            continue
        entries.append(
            BibliographyEntry(
                entry_id=f"bib:{int(label_raw)}",
                label_raw=label_raw,
                label_key=bibliography_label_key(label_raw),
                reference_number=int(label_raw),
                raw_text=clean_entry_text,
                clean_text=clean_entry_text,
                source_section_id=section.section_id,
                heading=section.heading,
                role_hint=section.role_hint,
                confidence=min(confidence, 0.78),
                notes=["reference_table_rows"],
            )
        )
    return entries


def _has_local_footnote_definition(
    anchor: FootnoteAnchor,
    definitions: Sequence[FootnoteDefinition],
) -> bool:
    """Return whether a table-cell marker has a same-table or same-visual footnote definition."""
    for definition in definitions:
        if definition.glyph_key != anchor.glyph_key:
            continue
        if anchor.table_id is not None and anchor.table_id == definition.table_id:
            return True
        if anchor.visual_id is not None and anchor.visual_id == definition.visual_id:
            return True
    return False


def _normalized_reference_text(text: str) -> str:
    return clean_text(INVISIBLE_TEXT_CHARS_PATTERN.sub("", text))


def _strip_reference_leading_artifacts(text: str) -> str:
    without_zero = REFERENCE_LEADING_ARTIFACT_ZERO_PATTERN.sub("", text)
    return REFERENCE_LEADING_PAGE_ARTIFACT_PATTERN.sub("", without_zero)


def _bbox_center_y(bbox: tuple[float, float, float, float]) -> float:
    return (float(bbox[1]) + float(bbox[3])) / 2.0


def _union_bboxes(
    bboxes: Sequence[tuple[float, float, float, float]],
) -> tuple[float, float, float, float]:
    return (
        min(float(bbox[0]) for bbox in bboxes),
        min(float(bbox[1]) for bbox in bboxes),
        max(float(bbox[2]) for bbox in bboxes),
        max(float(bbox[3]) for bbox in bboxes),
    )
