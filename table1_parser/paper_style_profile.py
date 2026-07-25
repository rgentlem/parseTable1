"""Infer paper-level reference, footnote, and caption style conventions."""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Sequence

from table1_parser.context.paper_document import iter_paper_document_lines
from table1_parser.schemas import (
    BibliographyEntry,
    PaperBibliography,
    PaperFootnotes,
    PaperStyleCheck,
    PaperStyleDimension,
    PaperStyleEvidence,
    PaperStyleProfile,
    PaperPositionedDocument,
    PaperVisual,
    PaperVisualReference,
)
from table1_parser.text_cleaning import clean_text


MAX_EVIDENCE_PER_DIMENSION = 12
FIGURE_CAPTION_LINE_PATTERN = re.compile(r"^(?:Fig\.?|Figure)\s+[A-Za-z]?\d+[A-Za-z]?\b", re.IGNORECASE)
VISUAL_NUMBER_PATTERN = re.compile(r"\b(?:Table|Tables|Fig\.?|Figs\.?|Figure|Figures)\s+[A-Za-z]?\d", re.IGNORECASE)
BRACKETED_NUMERIC_MARKER_PATTERN = re.compile(r"^\[\s*\d+\s*\]$")
PARENTHETICAL_NUMERIC_MARKER_PATTERN = re.compile(r"^\(\s*\d+\s*\)$")
DEFINITION_PREFIX_PATTERN = re.compile(
    r"^\s*(?P<prefix>(?:\[[^\]]+\])|(?:\([^)]+\))|(?:\S{1,4}))(?P<sep>[:.)]|\s)"
)


def build_paper_style_profile(
    *,
    paper_id: str,
    source_pdf: str,
    paper_document: dict[str, object],
    paper_positioned_document: PaperPositionedDocument,
    paper_footnotes: PaperFootnotes,
    paper_bibliography: PaperBibliography,
    paper_visual_inventory: Sequence[PaperVisual],
    paper_references: Sequence[PaperVisualReference],
) -> PaperStyleProfile:
    """Build a deterministic style profile from existing paper-level artifacts."""
    document_lines = list(
        iter_paper_document_lines(paper_document, paper_positioned_document)
    )
    footnote_marker_style = _footnote_marker_style(paper_footnotes)
    bibliography_reference_style = _bibliography_reference_style(paper_bibliography)
    table_caption_placement = _table_caption_placement(paper_visual_inventory)
    figure_caption_evidence = _figure_caption_evidence(paper_visual_inventory, document_lines)
    visual_reference_style = _visual_reference_style(paper_references)
    return PaperStyleProfile(
        paper_id=paper_id,
        source_pdf=source_pdf,
        footnote_marker_style=footnote_marker_style,
        bibliography_reference_style=bibliography_reference_style,
        table_caption_placement=table_caption_placement,
        figure_caption_evidence=figure_caption_evidence,
        visual_reference_style=visual_reference_style,
        checks=_style_checks(
            paper_bibliography=paper_bibliography,
            paper_footnotes=paper_footnotes,
            paper_references=paper_references,
            footnote_marker_style=footnote_marker_style,
            bibliography_reference_style=bibliography_reference_style,
            table_caption_placement=table_caption_placement,
            figure_caption_evidence=figure_caption_evidence,
            visual_reference_style=visual_reference_style,
        ),
        metadata={
            "source_artifacts": [
                "paper_document.json",
                "paper_positioned_document.json",
                "paper_footnotes.json",
                "paper_bibliography.json",
                "paper_visual_inventory.json",
                "paper_references.json",
            ],
            "table_count": sum(
                visual.visual_kind == "table" for visual in paper_visual_inventory
            ),
            "visual_count": len(paper_visual_inventory),
            "visual_reference_count": len(paper_references),
        },
    )


def paper_style_profile_to_payload(profile: PaperStyleProfile) -> dict[str, object]:
    """Serialize a paper style profile as a JSON-friendly record."""
    return profile.model_dump(mode="json")


def _footnote_marker_style(paper_footnotes: PaperFootnotes) -> PaperStyleDimension:
    count_by_style: Counter[str] = Counter()
    count_by_source: Counter[str] = Counter()
    glyph_kind_counts: Counter[str] = Counter()
    source_scope_counts: Counter[str] = Counter()
    link_status_counts: Counter[str] = Counter()
    definition_format_counts: Counter[str] = Counter()
    evidence: list[PaperStyleEvidence] = []

    for anchor in paper_footnotes.anchors:
        style = _footnote_style_from_glyph_kind(anchor.glyph_kind)
        count_by_style[style] += 1
        count_by_source["anchors"] += 1
        glyph_kind_counts[anchor.glyph_kind] += 1
        source_scope_counts[anchor.source_scope] += 1
        if len(evidence) < MAX_EVIDENCE_PER_DIMENSION:
            evidence.append(
                PaperStyleEvidence(
                    evidence_id=f"footnote-anchor:{anchor.anchor_id}",
                    style=style,
                    source_artifact=anchor.source_artifact or "paper_footnotes.json",
                    source_id=anchor.anchor_id,
                    page_num=anchor.page_num,
                    table_id=anchor.table_id,
                    text=anchor.glyph_raw,
                    notes=[f"source_scope:{anchor.source_scope}", *anchor.notes[:3]],
                )
            )

    for definition in paper_footnotes.definitions:
        style = _footnote_style_from_glyph_kind(definition.glyph_kind)
        count_by_style[style] += 1
        count_by_source["definitions"] += 1
        glyph_kind_counts[definition.glyph_kind] += 1
        source_scope_counts[definition.source_scope] += 1
        definition_format_counts[_definition_marker_format(definition.raw_text)] += 1
        if len(evidence) < MAX_EVIDENCE_PER_DIMENSION:
            evidence.append(
                PaperStyleEvidence(
                    evidence_id=f"footnote-definition:{definition.definition_id}",
                    style=style,
                    source_artifact=definition.source_artifact or "paper_footnotes.json",
                    source_id=definition.definition_id,
                    page_num=definition.page_num,
                    table_id=definition.table_id,
                    text=definition.raw_text,
                    notes=[f"source_scope:{definition.source_scope}", *definition.notes[:3]],
                )
            )

    for link in paper_footnotes.links:
        link_status_counts[link.link_status] += 1

    notes: list[str] = []
    if not paper_footnotes.anchors and not paper_footnotes.definitions:
        notes.append("no_footnote_anchor_or_definition_evidence")
    if link_status_counts.get("unresolved", 0):
        notes.append(f"unresolved_footnote_links:{link_status_counts['unresolved']}")
    if link_status_counts.get("ambiguous", 0):
        notes.append(f"ambiguous_footnote_links:{link_status_counts['ambiguous']}")

    return _dimension_from_counts(
        "footnote_marker_style",
        count_by_style,
        count_by_source=count_by_source,
        secondary_counts={
            "glyph_kind": glyph_kind_counts,
            "source_scope": source_scope_counts,
            "link_status": link_status_counts,
            "definition_marker_format": definition_format_counts,
        },
        evidence=evidence,
        notes=notes,
    )


def _bibliography_reference_style(paper_bibliography: PaperBibliography) -> PaperStyleDimension:
    entries = list(paper_bibliography.entries)
    numbered_count = sum(entry.reference_number is not None for entry in entries)
    unnumbered_count = len(entries) - numbered_count
    count_by_style: Counter[str] = Counter()
    count_by_source: Counter[str] = Counter()
    label_format_counts: Counter[str] = Counter()
    mention_status_counts: Counter[str] = Counter()
    evidence: list[PaperStyleEvidence] = []

    if numbered_count and unnumbered_count:
        count_by_style["mixed_reference_list"] = len(entries)
    elif numbered_count:
        count_by_style["numbered_reference_list"] = numbered_count
    elif unnumbered_count:
        count_by_style["unnumbered_reference_list"] = unnumbered_count
    count_by_source["bibliography_entries"] = len(entries)

    for entry in entries:
        label_format_counts[_bibliography_label_format(entry)] += 1
        if len(evidence) < MAX_EVIDENCE_PER_DIMENSION:
            style = (
                "numbered_reference_list"
                if entry.reference_number is not None
                else "unnumbered_reference_list"
            )
            evidence.append(
                PaperStyleEvidence(
                    evidence_id=f"bibliography-entry:{entry.entry_id}",
                    style=style,
                    source_artifact=entry.source_artifact,
                    source_id=entry.entry_id,
                    page_num=entry.page_nums[0] if entry.page_nums else None,
                    text=entry.label_raw or entry.clean_text[:120],
                    notes=[f"heading:{entry.heading}"] if entry.heading else [],
                )
            )

    for mention in paper_bibliography.reference_mentions:
        mention_status_counts[mention.link_status] += 1
        label_format_counts[_reference_mention_format(mention.label_raw)] += 1
        count_by_source["reference_mentions"] += 1

    notes: list[str] = []
    diagnostics = paper_bibliography.metadata.get("bibliography_extraction_diagnostics", [])
    if isinstance(diagnostics, list):
        notes.extend(str(diagnostic) for diagnostic in diagnostics[:6])
    if not entries:
        notes.append("no_bibliography_entries")
    if unnumbered_count and paper_bibliography.reference_mentions:
        notes.append("numeric_reference_mentions_with_unnumbered_reference_list")

    return _dimension_from_counts(
        "bibliography_reference_style",
        count_by_style,
        count_by_source=count_by_source,
        secondary_counts={
            "bibliography_label_format": label_format_counts,
            "reference_mention_link_status": mention_status_counts,
        },
        evidence=evidence,
        notes=notes,
    )


def _table_caption_placement(
    paper_visual_inventory: Sequence[PaperVisual],
) -> PaperStyleDimension:
    count_by_style: Counter[str] = Counter()
    count_by_source: Counter[str] = Counter()
    caption_source_counts: Counter[str] = Counter()
    evidence: list[PaperStyleEvidence] = []
    table_visuals = [
        visual for visual in paper_visual_inventory if visual.visual_kind == "table"
    ]
    for visual in table_visuals:
        placement = next(
            (
                note.removeprefix("caption_placement:")
                for note in visual.notes
                if note.startswith("caption_placement:")
            ),
            "unknown",
        )
        caption_source_counts[visual.caption_source] += 1
        count_by_source["paper_document_table_entity"] += 1
        count_by_style[placement] += 1
        if len(evidence) < MAX_EVIDENCE_PER_DIMENSION:
            evidence.append(
                PaperStyleEvidence(
                    evidence_id=f"table-caption:{visual.visual_id}",
                    style=placement,
                    source_artifact="paper_document.json",
                    source_id=next(
                        (
                            note.removeprefix("table_entity_id:")
                            for note in visual.notes
                            if note.startswith("table_entity_id:")
                        ),
                        visual.visual_id,
                    ),
                    page_num=visual.page_num,
                    table_id=visual.source_table_id,
                    text=visual.caption,
                    notes=[f"caption_source:{visual.caption_source}"],
                )
            )

    return _dimension_from_counts(
        "table_caption_placement",
        count_by_style,
        count_by_source=count_by_source,
        secondary_counts={"caption_source": caption_source_counts},
        evidence=evidence,
        notes=[] if table_visuals else ["no_table_entities"],
    )


def _figure_caption_evidence(
    paper_visual_inventory: Sequence[PaperVisual],
    document_lines: Sequence[object],
) -> PaperStyleDimension:
    count_by_style: Counter[str] = Counter()
    count_by_source: Counter[str] = Counter()
    label_format_counts: Counter[str] = Counter()
    evidence: list[PaperStyleEvidence] = []

    for visual in paper_visual_inventory:
        if visual.visual_kind != "figure":
            continue
        style = "caption_detected_geometry_unavailable" if visual.caption else "figure_without_caption_text"
        count_by_style[style] += 1
        count_by_source[visual.caption_source] += 1
        label_format_counts[_figure_label_format(visual.caption or visual.label)] += 1
        if len(evidence) < MAX_EVIDENCE_PER_DIMENSION:
            evidence.append(
                PaperStyleEvidence(
                    evidence_id=f"figure-caption:{visual.visual_id}",
                    style=style,
                    source_artifact="paper_visual_inventory.json",
                    source_id=visual.visual_id,
                    page_num=visual.page_num,
                    text=visual.caption,
                    notes=[f"caption_source:{visual.caption_source}"],
                )
            )

    if not count_by_style:
        for line in document_lines:
            if not FIGURE_CAPTION_LINE_PATTERN.match(line.text):
                continue
            count_by_style["caption_text_detected_geometry_unavailable"] += 1
            count_by_source["paper_document"] += 1
            label_format_counts[_figure_label_format(line.text)] += 1
            if len(evidence) < MAX_EVIDENCE_PER_DIMENSION:
                evidence.append(
                    PaperStyleEvidence(
                        evidence_id=f"figure-caption-line:{line.line_id}",
                        style="caption_text_detected_geometry_unavailable",
                        source_artifact="paper_document.json",
                        source_id=line.line_id,
                        page_num=line.page_num,
                        text=line.text,
                    )
                )

    return _dimension_from_counts(
        "figure_caption_evidence",
        count_by_style,
        count_by_source=count_by_source,
        secondary_counts={"figure_label_format": label_format_counts},
        evidence=evidence,
        notes=["figure_geometry_not_extracted"] if count_by_style else ["no_figure_caption_evidence"],
    )


def _visual_reference_style(paper_references: Sequence[PaperVisualReference]) -> PaperStyleDimension:
    count_by_style: Counter[str] = Counter()
    count_by_source: Counter[str] = Counter()
    kind_counts: Counter[str] = Counter()
    resolution_counts: Counter[str] = Counter()
    evidence: list[PaperStyleEvidence] = []

    for reference in paper_references:
        style = _visual_reference_format(reference.matched_text)
        count_by_style[style] += 1
        count_by_source["paper_references"] += 1
        kind_counts[reference.reference_kind] += 1
        resolution_counts[reference.resolution_status] += 1
        if len(evidence) < MAX_EVIDENCE_PER_DIMENSION:
            evidence.append(
                PaperStyleEvidence(
                    evidence_id=f"visual-reference:{reference.reference_id}",
                    style=style,
                    source_artifact="paper_references.json",
                    source_id=reference.reference_id,
                    text=reference.matched_text,
                    notes=[f"kind:{reference.reference_kind}", f"resolution_status:{reference.resolution_status}"],
                )
            )

    return _dimension_from_counts(
        "visual_reference_style",
        count_by_style,
        count_by_source=count_by_source,
        secondary_counts={
            "visual_kind": kind_counts,
            "resolution_status": resolution_counts,
        },
        evidence=evidence,
        notes=[] if paper_references else ["no_visual_reference_evidence"],
    )


def _style_checks(
    *,
    paper_bibliography: PaperBibliography,
    paper_footnotes: PaperFootnotes,
    paper_references: Sequence[PaperVisualReference],
    footnote_marker_style: PaperStyleDimension,
    bibliography_reference_style: PaperStyleDimension,
    table_caption_placement: PaperStyleDimension,
    figure_caption_evidence: PaperStyleDimension,
    visual_reference_style: PaperStyleDimension,
) -> list[PaperStyleCheck]:
    numbered_entries = sum(entry.reference_number is not None for entry in paper_bibliography.entries)
    unnumbered_entries = len(paper_bibliography.entries) - numbered_entries
    bibliography_style = bibliography_reference_style.likely_style
    bibliography_evidence = bibliography_reference_style.evidence[:3]
    if bibliography_style == "numbered_reference_list":
        if numbered_entries > 0 and unnumbered_entries == 0:
            bibliography_status = "pass"
            bibliography_message = (
                f"Predicted numbered/indexed references and {numbered_entries}/"
                f"{len(paper_bibliography.entries)} bibliography entries have reference_number."
            )
        elif numbered_entries > 0:
            bibliography_status = "warning"
            bibliography_message = (
                f"Predicted numbered/indexed references, but {unnumbered_entries} bibliography entries "
                "lack reference_number."
            )
        else:
            bibliography_status = "fail"
            bibliography_message = "Predicted numbered/indexed references, but no bibliography entry has reference_number."
    elif bibliography_style == "unnumbered_reference_list":
        bibliography_status = "pass" if unnumbered_entries > 0 and numbered_entries == 0 else "warning"
        bibliography_message = (
            f"Predicted unnumbered/hanging-indent references with {unnumbered_entries} unnumbered "
            f"and {numbered_entries} numbered bibliography entries."
        )
    elif bibliography_style == "mixed_reference_list":
        bibliography_status = "warning"
        bibliography_message = (
            f"Predicted mixed bibliography numbering with {numbered_entries} numbered "
            f"and {unnumbered_entries} unnumbered entries."
        )
    else:
        bibliography_status = "warning" if paper_bibliography.entries else "not_applicable"
        bibliography_message = (
            "No dominant bibliography numbering style was inferred."
            if paper_bibliography.entries
            else "No bibliography entries were available for numbering alignment."
        )

    link_status_counts = Counter(link.link_status for link in paper_footnotes.links)
    unresolved = link_status_counts.get("unresolved", 0)
    ambiguous = link_status_counts.get("ambiguous", 0)
    if unresolved == 0 and ambiguous == 0:
        footnote_status = "pass"
        footnote_message = (
            f"Footnote marker style {footnote_marker_style.likely_style} has "
            f"{link_status_counts.get('resolved', 0)} resolved links, with no unresolved or ambiguous links."
        )
    else:
        footnote_status = "warning"
        footnote_message = (
            f"Footnote marker style {footnote_marker_style.likely_style} still has "
            f"{unresolved} unresolved and {ambiguous} ambiguous links."
        )

    table_caption_counts = table_caption_placement.count_by_style
    table_caption_total = sum(table_caption_counts.values())
    unknown_table_captions = table_caption_counts.get("unknown", 0)
    if table_caption_total == 0:
        table_caption_status = "not_applicable"
        table_caption_message = "No extracted tables were available for caption placement checks."
    elif unknown_table_captions == 0:
        table_caption_status = "pass"
        table_caption_message = f"Caption placement was inferred for all {table_caption_total} extracted tables."
    else:
        table_caption_status = "warning"
        table_caption_message = (
            f"Caption placement is unknown for {unknown_table_captions}/"
            f"{table_caption_total} extracted tables."
        )

    figure_caption_counts = figure_caption_evidence.count_by_style
    figure_caption_total = sum(figure_caption_counts.values())
    if figure_caption_total == 0:
        figure_status = "not_applicable"
        figure_message = "No figure caption evidence was available."
    else:
        figure_status = "warning"
        figure_message = (
            f"{figure_caption_total} figure caption observations exist, but figure geometry is not extracted, "
            "so above/below placement cannot be checked yet."
        )

    reference_resolution_counts = Counter(reference.resolution_status for reference in paper_references)
    unresolved_references = reference_resolution_counts.get("unresolved", 0)
    ambiguous_references = reference_resolution_counts.get("ambiguous", 0)
    if not paper_references:
        visual_reference_status = "not_applicable"
        visual_reference_message = "No table or figure prose references were detected."
    elif unresolved_references == 0 and ambiguous_references == 0:
        visual_reference_status = "pass"
        visual_reference_message = "Detected visual-reference wording resolved without unresolved or ambiguous mentions."
    else:
        visual_reference_status = "warning"
        visual_reference_message = (
            f"Visual-reference style {visual_reference_style.likely_style} has "
            f"{unresolved_references} unresolved and {ambiguous_references} ambiguous prose mentions."
        )

    return [
        PaperStyleCheck(
            check_id="bibliography_numbering_alignment",
            check_type="bibliography_reference_style",
            status=bibliography_status,
            message=bibliography_message,
            evidence=bibliography_evidence,
        ),
        PaperStyleCheck(
            check_id="footnote_link_coverage",
            check_type="footnote_marker_style",
            status=footnote_status,
            message=footnote_message,
            evidence=footnote_marker_style.evidence[:3],
        ),
        PaperStyleCheck(
            check_id="table_caption_placement_coverage",
            check_type="table_caption_placement",
            status=table_caption_status,
            message=table_caption_message,
            evidence=table_caption_placement.evidence[:3],
        ),
        PaperStyleCheck(
            check_id="figure_caption_geometry_availability",
            check_type="figure_caption_evidence",
            status=figure_status,
            message=figure_message,
            evidence=figure_caption_evidence.evidence[:3],
        ),
        PaperStyleCheck(
            check_id="visual_reference_resolution_coverage",
            check_type="visual_reference_style",
            status=visual_reference_status,
            message=visual_reference_message,
            evidence=visual_reference_style.evidence[:3],
        ),
    ]


def _dimension_from_counts(
    dimension: str,
    count_by_style: Counter[str],
    *,
    count_by_source: Counter[str],
    secondary_counts: dict[str, Counter[str]],
    evidence: list[PaperStyleEvidence],
    notes: list[str],
) -> PaperStyleDimension:
    total = sum(count_by_style.values())
    if total == 0:
        likely_style = "unknown"
        confidence = 0.0
    else:
        likely_style, likely_count = count_by_style.most_common(1)[0]
        confidence = likely_count / total
        if len(count_by_style) > 1 and confidence < 0.7:
            likely_style = "mixed"
    return PaperStyleDimension(
        dimension=dimension,
        likely_style=likely_style,
        confidence=round(confidence, 3),
        count_by_style=dict(sorted(count_by_style.items())),
        count_by_source=dict(sorted(count_by_source.items())),
        secondary_counts={
            name: dict(sorted(counter.items()))
            for name, counter in sorted(secondary_counts.items())
            if counter
        },
        evidence=evidence,
        notes=notes,
    )


def _footnote_style_from_glyph_kind(glyph_kind: str) -> str:
    if glyph_kind == "number":
        return "numeric_markers"
    if glyph_kind == "letter":
        return "letter_markers"
    if glyph_kind == "symbol":
        return "symbol_markers"
    if glyph_kind == "asterisk":
        return "asterisk_markers"
    return "unknown_markers"


def _definition_marker_format(raw_text: str) -> str:
    match = DEFINITION_PREFIX_PATTERN.match(raw_text)
    if match is None:
        return "embedded_or_unmarked_definition"
    prefix = match.group("prefix").strip()
    separator = match.group("sep")
    if prefix.startswith("[") and prefix.endswith("]"):
        return "bracketed_marker_definition"
    if prefix.startswith("(") and prefix.endswith(")"):
        return "parenthesized_marker_definition"
    if separator == ":":
        return "colon_marker_definition"
    if separator in {".", ")"}:
        return "punctuated_marker_definition"
    return "space_marker_definition"


def _bibliography_label_format(entry: BibliographyEntry) -> str:
    label = entry.label_raw.strip()
    if entry.reference_number is None:
        return "hanging_indent_unnumbered"
    if BRACKETED_NUMERIC_MARKER_PATTERN.match(label):
        return "bracketed_numeric_label"
    if PARENTHETICAL_NUMERIC_MARKER_PATTERN.match(label):
        return "parenthesized_numeric_label"
    if label.endswith("."):
        return "dotted_numeric_label"
    if label.endswith(")"):
        return "right_parenthesis_numeric_label"
    return "bare_or_offset_numeric_label"


def _reference_mention_format(label_raw: str) -> str:
    label = label_raw.strip()
    if BRACKETED_NUMERIC_MARKER_PATTERN.match(label):
        return "bracketed_numeric_mention"
    if PARENTHETICAL_NUMERIC_MARKER_PATTERN.match(label):
        return "parenthesized_numeric_mention"
    if label.isdigit():
        return "bare_numeric_mention"
    return "other_numeric_mention"


def _figure_label_format(text: str) -> str:
    cleaned = clean_text(text)
    if re.match(r"^Fig\.?\s+", cleaned, re.IGNORECASE):
        return "figure_abbreviation_label"
    if re.match(r"^Figure\s+", cleaned, re.IGNORECASE):
        return "figure_full_word_label"
    return "unknown_figure_label"


def _visual_reference_format(text: str) -> str:
    cleaned = clean_text(text)
    if re.match(r"^Tables\b", cleaned, re.IGNORECASE):
        return "plural_table_reference"
    if re.match(r"^Table\b", cleaned, re.IGNORECASE):
        return "table_full_word_reference"
    if re.match(r"^Figs?\.?\b", cleaned, re.IGNORECASE):
        return "figure_abbreviation_reference"
    if re.match(r"^Figures\b", cleaned, re.IGNORECASE):
        return "plural_figure_reference"
    if re.match(r"^Figure\b", cleaned, re.IGNORECASE):
        return "figure_full_word_reference"
    if VISUAL_NUMBER_PATTERN.search(cleaned):
        return "other_visual_reference"
    return "unknown_visual_reference"
