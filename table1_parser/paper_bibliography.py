"""Build paper-level bibliography and reference-link artifacts."""

from __future__ import annotations

import re
from collections.abc import Sequence
from pathlib import Path

from table1_parser.schemas import (
    BibliographyEntry,
    BibliographyReferenceMention,
    FootnoteAnchor,
    FootnoteDefinition,
    PaperBibliography,
    PaperSection,
)
from table1_parser.text_cleaning import clean_text


REFERENCE_HEADING_PATTERN = re.compile(r"\b(?:references?|bibliography|works cited)\b", re.IGNORECASE)
REFERENCE_LIST_CUE_PATTERN = re.compile(
    r"\b(?:references?|bibliography|works cited)\b\s+(?=(?:\[\s*)?\d{1,3}(?:\s*\])?[.)]?\s+[A-Z])",
    re.IGNORECASE,
)
REFERENCE_ENTRY_START_PATTERN = re.compile(
    r"(?P<prefix>^|\s+-\s+|\s+)\s*(?:\[\s*)?(?P<label>\d{1,3})(?:\s*\])?[.)]?\s+(?=[A-Za-z])"
)
REFERENCE_TABLE_ROW_SPLIT_PATTERN = re.compile(r"\s+(?=\|(?:\d{1,3}|---|\|))")
REFERENCE_TABLE_START_PATTERN = re.compile(r"\s+\|\d{1,3}\|")


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
    return PaperBibliography(
        paper_id=paper_id,
        source_pdf=Path(source_pdf).name,
        entries=entries,
        reference_mentions=reference_mentions,
        metadata={
            "source_artifacts": ["paper_sections.json", "cell_text_annotations.json", "paper_footnotes.json"],
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
        },
    )


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
    entries.sort(key=lambda entry: (entry.reference_number, entry.entry_id))
    return entries


def build_bibliography_reference_mentions_from_footnote_anchors(
    footnote_anchors: Sequence[FootnoteAnchor],
    footnote_definitions: Sequence[FootnoteDefinition],
    bibliography_entries: Sequence[BibliographyEntry],
) -> list[BibliographyReferenceMention]:
    """Promote numeric table-cell anchors without local footnotes into bibliography references."""
    entries_by_label_key: dict[str, list[BibliographyEntry]] = {}
    for entry in bibliography_entries:
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


def _build_bibliography_entries_from_reference_table_region(
    reference_region: str,
    *,
    section: PaperSection,
    confidence: float,
) -> list[BibliographyEntry]:
    """Parse two-column markdown-table bibliography rows into separate entries."""
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
        for side, label_idx, text_idx in ((0, 0, 1), (1, 2, 3)):
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
