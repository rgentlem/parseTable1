"""Collect paper-level table mention evidence from the layout-aware text stream."""

from __future__ import annotations

import re
from collections.abc import Sequence

from table1_parser.schemas import PaperTableMention
from table1_parser.text_cleaning import clean_text


TABLE_MENTION_PATTERN = re.compile(
    r"\b(?P<label>Tables?\s*(?P<numbers>[A-Za-z]?\d+[A-Za-z]?"
    r"(?:\s*(?:,|and|&|-|to)\s*[A-Za-z]?\d+[A-Za-z]?){0,8}))\b",
    re.IGNORECASE,
)
TABLE_NUMBER_PATTERN = re.compile(r"[A-Za-z]?\d+[A-Za-z]?")
CAPTION_LINE_START_PATTERN = re.compile(r"^\s*Table\s*[A-Za-z]?\d+[A-Za-z]?\b(?:\s*[.:])?", re.IGNORECASE)
CONTINUATION_PATTERN = re.compile(r"\b(?:continued|continues?|cont\.)\b", re.IGNORECASE)
PROSE_CUE_BEFORE_PATTERN = re.compile(
    r"\b(?:shown|presented|reported|summari[sz]ed|listed|described|displayed|provided|given|seen)\s+in\s*$"
    r"|\b(?:see|refer\s+to|according\s+to)\s*$",
    re.IGNORECASE,
)
PROSE_VERB_AFTER_PATTERN = re.compile(
    r"^\s*(?:shows?|presents?|reports?|summari[sz]es?|lists?|describes?|displays?|provides?|gives?|"
    r"illustrates?|contains?|details?|examines?|depicts?|indicates?|reveals?)\b",
    re.IGNORECASE,
)
SUPPLEMENTARY_INFORMATION_HEADING_PATTERN = re.compile(
    r"\bsupplement(?:ary|al)?\s+information\b",
    re.IGNORECASE,
)


def build_paper_table_mentions(paper_text_stream: object) -> list[PaperTableMention]:
    """Build pre-extraction table mention records from layout-aware paper text."""
    lines = list(getattr(paper_text_stream, "lines", []) or [])
    mentions: list[PaperTableMention] = []
    active_heading = ""
    for line_index, line in enumerate(lines):
        text = clean_text(getattr(line, "text", ""))
        if not text:
            continue
        line_notes = list(getattr(line, "notes", []) or [])
        mention_text = text
        spans = [
            span
            for span in list(getattr(line, "spans", []) or [])
            if isinstance(span, dict) and str(span.get("text", ""))
        ]
        span_order_text = clean_text("".join(str(span["text"]) for span in spans))
        if (
            span_order_text
            and CAPTION_LINE_START_PATTERN.match(span_order_text)
            and not CAPTION_LINE_START_PATTERN.match(mention_text)
        ):
            mention_text = span_order_text
            line_notes.append("span_order_table_label")
        nonspace_spans = [span for span in spans if str(span["text"]).strip()]
        if len(nonspace_spans) >= 4:
            first_text = str(nonspace_spans[0]["text"]).strip()
            number_text = str(nonspace_spans[1]["text"]).strip()
            separator_text = str(nonspace_spans[2]["text"]).strip()
            number_font = str(nonspace_spans[1].get("font") or "")
            separator_font = str(nonspace_spans[2].get("font") or "")
            following_font = str(nonspace_spans[3].get("font") or "")
            if (
                first_text.lower() == "table"
                and re.fullmatch(r"[A-Za-z]?\d+[A-Za-z]?[.:]?", number_text)
                and len(separator_text) == 1
                and separator_font
                and separator_font != number_font
                and separator_font != following_font
            ):
                mention_text = clean_text(
                    " ".join(
                        [first_text, number_text]
                        + [str(span["text"]).strip() for span in nonspace_spans[3:]]
                    )
                )
                line_notes.append("isolated_table_label_separator_span")
        line_is_heading = getattr(line, "role", "body") == "heading" or "layout_section_heading" in line_notes
        in_supplementary_information = bool(
            active_heading and SUPPLEMENTARY_INFORMATION_HEADING_PATTERN.search(active_heading)
        )
        for match_index, match in enumerate(TABLE_MENTION_PATTERN.finditer(mention_text)):
            if not match.group("label"):
                continue
            previous_line = _adjacent_line(lines, line_index, -1)
            next_line = _adjacent_line(lines, line_index, 1)
            local_prefix = clean_text(mention_text[: match.start()])
            local_suffix = clean_text(mention_text[match.end() :])
            previous_text = clean_text(getattr(previous_line, "text", "")) if previous_line is not None else ""
            line_starts_with_label = (
                CAPTION_LINE_START_PATTERN.match(mention_text) is not None
                and match.start() <= 2
            )
            bold_or_heading = getattr(line, "role", "body") == "heading" or "bold_like_text" in line_notes
            cue: str | None = None
            if CONTINUATION_PATTERN.search(text):
                mention_kind = "continuation_label"
                cue = "continuation_label"
                confidence = 0.92
            elif PROSE_CUE_BEFORE_PATTERN.search(local_prefix):
                mention_kind = "prose_reference"
                cue = "same_line_prose_cue_before"
                confidence = 0.9
            elif previous_text and PROSE_CUE_BEFORE_PATTERN.search(previous_text):
                mention_kind = "prose_reference"
                cue = "previous_line_prose_cue_before"
                confidence = 0.92
            elif PROSE_VERB_AFTER_PATTERN.match(local_suffix.lstrip(" .:;-")):
                mention_kind = "prose_reference"
                cue = "same_line_prose_verb_after"
                confidence = 0.9
            elif line_starts_with_label and bold_or_heading:
                mention_kind = "caption_candidate"
                cue = "bold_or_heading_caption_line"
                confidence = 0.9
            elif line_starts_with_label and not _line_continues_previous_sentence(previous_text):
                mention_kind = "caption_candidate"
                cue = "line_initial_table_label"
                confidence = 0.74
            else:
                mention_kind = "prose_reference"
                cue = "embedded_table_reference"
                confidence = 0.72

            context_lines = [
                adjacent
                for adjacent in (previous_line, line, next_line)
                if adjacent is not None
                and (
                    adjacent is line
                    or getattr(adjacent, "page_num", None) == getattr(line, "page_num", None)
                )
            ]
            context_text = clean_text(" ".join(str(getattr(context_line, "text", "")) for context_line in context_lines))
            for table_number in _table_numbers(match.group("numbers")):
                table_mention_kind = mention_kind
                table_cue = cue
                table_confidence = confidence
                notes = _mention_notes(line_starts_with_label, bold_or_heading)
                if (
                    mention_kind == "caption_candidate"
                    and table_number.startswith("S")
                    and in_supplementary_information
                ):
                    table_mention_kind = "prose_reference"
                    table_cue = "supplementary_information_table_listing"
                    table_confidence = 0.9
                    notes.append("supplementary_information_table_listing")
                mentions.append(
                    PaperTableMention(
                        mention_id=f"paper_table_mention:{getattr(line, 'line_id', line_index)}:{match_index}:{table_number}",
                        table_number=table_number,
                        table_label=f"Table {table_number}",
                        mention_kind=table_mention_kind,
                        page_num=int(getattr(line, "page_num")),
                        line_ids=[str(getattr(context_line, "line_id")) for context_line in context_lines],
                        source_line_id=str(getattr(line, "line_id")),
                        source_line_bbox=tuple(getattr(line, "bbox")),
                        source_line_text=text,
                        context_text=context_text,
                        matched_text=match.group("label"),
                        cue=table_cue,
                        is_caption_candidate=table_mention_kind in {"caption_candidate", "continuation_label"},
                        source_line_role=str(getattr(line, "role", "body")),
                        source_line_notes=line_notes,
                        confidence=table_confidence,
                        notes=notes,
                    )
                )
        if line_is_heading:
            active_heading = text
    return mentions


def paper_table_mentions_to_payload(mentions: Sequence[PaperTableMention]) -> list[dict[str, object]]:
    """Serialize table mentions as JSON-ready dictionaries."""
    return [mention.model_dump(mode="json") for mention in mentions]


def _adjacent_line(lines: Sequence[object], line_index: int, offset: int) -> object | None:
    adjacent_index = line_index + offset
    if adjacent_index < 0 or adjacent_index >= len(lines):
        return None
    line = lines[line_index]
    adjacent = lines[adjacent_index]
    if getattr(adjacent, "page_num", None) != getattr(line, "page_num", None):
        return None
    line_group_id = getattr(line, "orientation_group_id", None)
    adjacent_group_id = getattr(adjacent, "orientation_group_id", None)
    if line_group_id is not None and adjacent_group_id != line_group_id:
        return None
    return adjacent


def _table_numbers(raw_numbers: str) -> list[str]:
    return [clean_text(match.group(0)).upper() for match in TABLE_NUMBER_PATTERN.finditer(raw_numbers)]


def _line_continues_previous_sentence(previous_text: str) -> bool:
    if not previous_text:
        return False
    return not previous_text.rstrip().endswith((".", "!", "?", ":", ";"))


def _mention_notes(line_starts_with_label: bool, bold_or_heading: bool) -> list[str]:
    notes: list[str] = []
    if line_starts_with_label:
        notes.append("line_starts_with_table_label")
    if bold_or_heading:
        notes.append("bold_or_heading_evidence")
    return notes
