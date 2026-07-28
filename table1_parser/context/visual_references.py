"""Deterministic paper-level table and figure reference collection."""

from __future__ import annotations

import re

from table1_parser.schemas import PaperSection, PaperVisual, PaperVisualReference
from table1_parser.text_cleaning import clean_text


PARAGRAPH_SPLIT_PATTERN = re.compile(r"\n\s*\n")
EMBEDDED_MARKDOWN_TABLE_START_PATTERN = re.compile(
    r"\bTable\s+[A-Za-z]?\d+[A-Za-z]?\b(?=.{0,240}\|)",
    re.IGNORECASE,
)
SENTENCE_BOUNDARY_PATTERN = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9])")
VISUAL_LABEL_PATTERN = re.compile(
    r"\b(?P<kind>Table|Tables|Fig\.?|Figs\.?|Figure|Figures)\s*"
    r"(?P<number>(?=[A-Za-z0-9.]*\d)[A-Za-z0-9]+(?:\.[A-Za-z0-9]+)*)\b",
    re.IGNORECASE,
)
VISUAL_REFERENCE_PATTERN = re.compile(
    r"\b(?P<kind>Table|Tables|Fig\.?|Figs\.?|Figure|Figures)\s*"
    r"(?P<numbers>(?=[A-Za-z0-9.]*\d)[A-Za-z0-9]+(?:\.[A-Za-z0-9]+)*"
    r"(?:\s*(?:,|and|&)\s*(?=[A-Za-z0-9.]*\d)"
    r"[A-Za-z0-9]+(?:\.[A-Za-z0-9]+)*){0,8})\b",
    re.IGNORECASE,
)
VISUAL_OBJECT_DOI_PATTERN = re.compile(
    r"^(?:doi\s*:|https?://(?:dx\.)?doi\.org/)"
    r"(?P<doi>10\.\d{4,9}/\S+\.(?P<object_kind>[tg])(?P<object_number>\d+))$",
    re.IGNORECASE,
)
REFERENCE_NUMBER_PATTERN = re.compile(
    r"(?=[A-Za-z0-9.]*\d)[A-Za-z0-9]+(?:\.[A-Za-z0-9]+)*"
)
TEXT_REFERENCE_CUE_PATTERN = re.compile(
    r"\b(?:shown|presented|reported|summari[sz]ed|listed|described|displayed|provided|given|seen)\s+in\s*$"
    r"|\b(?:see|refer\s+to|according\s+to)\s*$",
    re.IGNORECASE,
)
SUPPLEMENTARY_PATTERN = re.compile(r"\b(?:supplementary|supplemental|supplement|appendix)\b", re.IGNORECASE)


def normalize_visual_label(label: str) -> str | None:
    """Return a canonical visual key such as `table:1` or `figure:2A`."""
    parsed = parse_visual_label(label)
    if parsed is None:
        return None
    visual_kind, number, _ = parsed
    return f"{visual_kind}:{number}"


def parse_visual_label(label: str) -> tuple[str, str, str] | None:
    """Parse a table or figure label into kind, number, and canonical display label."""
    match = VISUAL_LABEL_PATTERN.search(clean_text(label))
    if match is None:
        return None
    visual_kind = "table" if match.group("kind").lower().startswith("table") else "figure"
    number = _canonical_number(match.group("number"))
    display_label = f"{'Table' if visual_kind == 'table' else 'Figure'} {number}"
    return visual_kind, number, display_label


def visual_id_for(visual_kind: str, number: str) -> str:
    """Return the stable paper visual ID for a canonical visual kind and number."""
    return f"paper_visual:{visual_kind}:{_canonical_number(number)}"


def collect_paper_visual_references(
    sections: list[PaperSection],
    visuals: list[PaperVisual],
) -> list[PaperVisualReference]:
    """Collect and resolve prose references to tables and figures from paper sections."""
    visual_ids_by_key: dict[str, list[str]] = {}
    for visual in visuals:
        key = f"{visual.visual_kind}:{_canonical_number(visual.number)}"
        visual_ids_by_key.setdefault(key, []).append(visual.visual_id)

    references: list[PaperVisualReference] = []
    for section in sections:
        for paragraph_index, paragraph in enumerate(section_paragraphs(section)):
            reference_index = 0
            for match in VISUAL_REFERENCE_PATTERN.finditer(paragraph):
                visual_kind = "table" if match.group("kind").lower().startswith("table") else "figure"
                for number_match in REFERENCE_NUMBER_PATTERN.finditer(match.group("numbers")):
                    number = _canonical_number(number_match.group(0))
                    anchor_text, anchor_start = reference_anchor_text(
                        paragraph,
                        match.start(),
                        match.end(),
                    )
                    reference_label = f"{'Table' if visual_kind == 'table' else 'Figure'} {number}"
                    key = f"{visual_kind}:{number}"
                    candidate_visual_ids = visual_ids_by_key.get(key, [])
                    if len(candidate_visual_ids) == 1:
                        resolved_visual_id = candidate_visual_ids[0]
                        resolution_status = "resolved"
                        resolution_notes: list[str] = []
                    elif len(candidate_visual_ids) > 1:
                        resolved_visual_id = None
                        resolution_status = "ambiguous"
                        resolution_notes = [f"candidate_visual_ids:{','.join(candidate_visual_ids)}"]
                    else:
                        resolved_visual_id = None
                        resolution_status = (
                            "external_or_bibliographic" if section.role_hint == "references_like" else "unresolved"
                        )
                        resolution_notes = (
                            ["reference_found_in_references_like_section"]
                            if section.role_hint == "references_like"
                            else []
                        )
                    references.append(
                        PaperVisualReference(
                            reference_id=f"paper_ref:{section.section_id}:p{paragraph_index}:r{reference_index}",
                            reference_kind=visual_kind,
                            reference_label=reference_label,
                            reference_number=number,
                            matched_text=match.group(0),
                            section_id=section.section_id,
                            heading=section.heading,
                            role_hint=section.role_hint,
                            paragraph_index=paragraph_index,
                            start_char=match.start() - anchor_start,
                            end_char=match.end() - anchor_start,
                            anchor_text=anchor_text,
                            resolved_visual_id=resolved_visual_id,
                            resolution_status=resolution_status,
                            resolution_notes=resolution_notes,
                        )
                    )
                    reference_index += 1
    return references


def annotate_visual_reference_checks(
    visuals: list[PaperVisual],
    references: list[PaperVisualReference],
) -> list[PaperVisual]:
    """Annotate each visual with whether it has at least one non-self text reference."""
    references_by_visual_id: dict[str, list[PaperVisualReference]] = {}
    for reference in references:
        if reference.resolution_status == "resolved" and reference.resolved_visual_id is not None:
            references_by_visual_id.setdefault(reference.resolved_visual_id, []).append(reference)

    annotated: list[PaperVisual] = []
    for visual in visuals:
        if _is_supplementary_visual(visual):
            annotated.append(
                visual.model_copy(
                    update={
                        "text_reference_ids": [],
                        "reference_check_status": "supplementary_exempt",
                        "reference_check_notes": ["supplementary_visual_exempt_from_text_reference_requirement"],
                    }
                )
            )
            continue
        text_reference_ids = [
            reference.reference_id
            for reference in references_by_visual_id.get(visual.visual_id, [])
            if not _is_self_visual_reference(reference)
        ]
        if text_reference_ids:
            annotated.append(
                visual.model_copy(
                    update={
                        "text_reference_ids": text_reference_ids,
                        "reference_check_status": "referenced_in_text",
                        "reference_check_notes": [],
                    }
                )
            )
        else:
            annotated.append(
                visual.model_copy(
                    update={
                        "text_reference_ids": [],
                        "reference_check_status": "no_text_reference",
                        "reference_check_notes": ["no_non_self_text_reference_found"],
                    }
                )
            )
    return annotated


def section_paragraphs(section: PaperSection) -> list[str]:
    """Return cleaned prose chunks for one block-derived section, excluding embedded table bodies."""
    if not section.content:
        return []
    chunks: list[str] = []
    for part in PARAGRAPH_SPLIT_PATTERN.split(section.content):
        cleaned = clean_text(part)
        if not cleaned:
            continue
        for table_start in EMBEDDED_MARKDOWN_TABLE_START_PATTERN.finditer(cleaned):
            prefix = clean_text(cleaned[max(0, table_start.start() - 120) : table_start.start()])
            if TEXT_REFERENCE_CUE_PATTERN.search(prefix):
                continue
            if _looks_like_markdown_table_text(cleaned[table_start.start() :]):
                cleaned = clean_text(cleaned[: table_start.start()])
                break
        if cleaned and not _looks_like_markdown_table_text(cleaned):
            chunks.append(cleaned)
    return chunks


def reference_anchor_text(paragraph: str, start_char: int, end_char: int, sentence_window: int = 1) -> tuple[str, int]:
    """Return a compact sentence-window anchor and its start offset in the paragraph."""
    spans = _sentence_spans(paragraph)
    sentence_index = next(
        (
            index
            for index, (sentence_start, sentence_end) in enumerate(spans)
            if sentence_start <= start_char < sentence_end
        ),
        None,
    )
    if sentence_index is None:
        return paragraph, 0
    window_start_index = max(0, sentence_index - sentence_window)
    window_end_index = min(len(spans) - 1, sentence_index + sentence_window)
    window_start = spans[window_start_index][0]
    window_end = spans[window_end_index][1]
    return paragraph[window_start:window_end].strip(), window_start


def _canonical_number(number: str) -> str:
    """Canonicalize a table or figure number while preserving letter suffixes."""
    return clean_text(number).upper()


def _is_self_visual_reference(reference: PaperVisualReference) -> bool:
    """Return whether a resolved reference is likely the visual caption/body itself."""
    prefix = reference.anchor_text[: reference.start_char]
    local_prefix = clean_text(prefix[-120:])
    if TEXT_REFERENCE_CUE_PATTERN.search(local_prefix):
        return False
    local_suffix = clean_text(reference.anchor_text[reference.end_char : reference.end_char + 240])
    if reference.start_char <= 20:
        return True
    if reference.reference_kind == "table" and reference.anchor_text.count("|") >= 8:
        return True
    if re.match(r"^[\s.:;-]+[A-Z]", local_suffix):
        return True
    return False


def _is_supplementary_visual(visual: PaperVisual) -> bool:
    """Return whether a visual should be exempt from in-text reference checks."""
    if visual.number.upper().startswith("S"):
        return True
    searchable = " ".join(part for part in [visual.label, visual.caption or "", *visual.notes] if part)
    return SUPPLEMENTARY_PATTERN.search(searchable) is not None


def _looks_like_markdown_table_text(text: str) -> bool:
    """Return whether text is dominated by markdown table syntax."""
    return text.count("|") >= 8 or "|---|" in text or re.search(r"\|\s*-{3,}\s*\|", text) is not None


def _sentence_spans(text: str) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    start = 0
    for boundary in SENTENCE_BOUNDARY_PATTERN.finditer(text):
        end = boundary.start()
        if text[start:end].strip():
            spans.append((start, end))
        start = boundary.end()
    if text[start:].strip():
        spans.append((start, len(text)))
    return spans or [(0, len(text))]
