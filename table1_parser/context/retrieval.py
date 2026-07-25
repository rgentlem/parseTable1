"""Deterministic per-table retrieval from paper markdown sections."""

from __future__ import annotations

import re

from table1_parser.context.visual_references import parse_visual_label, section_paragraphs, visual_id_for
from table1_parser.normalize.text_normalizer import normalize_label_text
from table1_parser.schemas import PaperSection, PaperVisual, PaperVisualReference, RetrievedPassage, TableContext, TableDefinition
from table1_parser.text_cleaning import clean_text


TABLE_NUMBER_PATTERN = re.compile(r"\bTable\s+(\d+)\b", re.IGNORECASE)


def build_table_contexts(
    sections: list[PaperSection],
    table_definitions: list[TableDefinition],
    entity_table_ids: set[str],
    paper_visual_inventory: list[PaperVisual] | None = None,
    paper_references: list[PaperVisualReference] | None = None,
) -> list[TableContext]:
    """Build per-table retrieval bundles from parsed sections and table definitions."""
    return [
        build_table_context(table_index, definition, sections, paper_visual_inventory, paper_references)
        for table_index, definition in enumerate(table_definitions)
        if definition.table_id in entity_table_ids
    ]


def build_table_context(
    table_index: int,
    definition: TableDefinition,
    sections: list[PaperSection],
    paper_visual_inventory: list[PaperVisual] | None = None,
    paper_references: list[PaperVisualReference] | None = None,
) -> TableContext:
    """Build one per-table context bundle."""
    table_label = None
    for text in (definition.title, definition.caption):
        match = TABLE_NUMBER_PATTERN.search(text or "")
        if match is not None:
            table_label = f"Table {match.group(1)}"
            break
    row_terms = _dedupe(
        [
            variable.variable_label
            for variable in definition.variables
            if clean_text(variable.variable_label)
        ]
    )
    column_terms = _dedupe(
        [
            column.column_label
            for column in definition.column_definition.columns
            if clean_text(column.column_label) and column.inferred_role not in {"overall", "p_value", "smd"}
        ]
    )
    grouping_terms = _dedupe(
        [
            term
            for term in [
                definition.column_definition.grouping_label or "",
                definition.column_definition.grouping_name or "",
            ]
            if clean_text(term)
        ]
    )
    methods_sections = [section.section_id for section in sections if section.role_hint == "methods_like"]
    results_sections = [section.section_id for section in sections if section.role_hint == "results_like"]
    ranked: list[tuple[float, RetrievedPassage]] = []
    search_terms = row_terms + column_terms + grouping_terms
    normalized_terms = {normalize_label_text(term).lower() for term in search_terms if normalize_label_text(term)}
    for section in sections:
        paragraphs = section_paragraphs(section)
        for paragraph_index, paragraph in enumerate(paragraphs):
            lowered = paragraph.lower()
            if table_label and table_label.lower() in lowered:
                passage_text = _reference_anchor_text(
                    section.section_id,
                    paragraph_index,
                    table_label,
                    paper_references or [],
                ) or paragraph
                ranked.append(
                    (
                        1.0,
                        _passage(
                            section,
                            paragraph_index,
                            passage_text,
                            "table_reference",
                            1.0,
                        ),
                    )
                )
                continue
            if normalized_terms:
                normalized_paragraph = normalize_label_text(paragraph).lower()
                score = sum(term in normalized_paragraph for term in normalized_terms if term) / len(normalized_terms)
            else:
                score = 0.0
            if score <= 0.0:
                continue
            if section.role_hint == "methods_like":
                ranked.append(
                    (
                        score + 0.2,
                        _passage(
                            section,
                            paragraph_index,
                            paragraph,
                            "methods_term_match",
                            round(score + 0.2, 4),
                        ),
                    )
                )
            elif section.role_hint == "results_like":
                ranked.append(
                    (
                        score + 0.1,
                        _passage(
                            section,
                            paragraph_index,
                            paragraph,
                            "results_term_match",
                            round(score + 0.1, 4),
                        ),
                    )
                )
    passages: list[RetrievedPassage] = []
    seen_passage_text: set[str] = set()
    for passage in [passage for _, passage in sorted(ranked, key=lambda item: -item[0])][:8]:
        if passage.text in seen_passage_text:
            continue
        seen_passage_text.add(passage.text)
        passages.append(passage)
    reference_ids: list[str] = []
    resolved_visual_ids: list[str] = []
    table_visual_ids = _table_visual_ids(definition, table_label, paper_visual_inventory or [])
    table_label_key = parse_visual_label(table_label or "") if table_label else None
    expected_visual_id = (
        visual_id_for("table", table_label_key[1])
        if table_label_key is not None and table_label_key[0] == "table"
        else None
    )
    for reference in paper_references or []:
        label_matches = expected_visual_id is not None and reference.reference_label.lower() == (table_label or "").lower()
        resolved_matches = reference.resolved_visual_id is not None and reference.resolved_visual_id in table_visual_ids
        if not (label_matches or resolved_matches):
            continue
        if reference.reference_id not in reference_ids:
            reference_ids.append(reference.reference_id)
        if reference.resolved_visual_id and reference.resolved_visual_id not in resolved_visual_ids:
            resolved_visual_ids.append(reference.resolved_visual_id)
    return TableContext(
        table_id=definition.table_id,
        table_index=table_index,
        table_label=table_label,
        title=definition.title,
        caption=definition.caption,
        row_terms=row_terms,
        column_terms=column_terms,
        grouping_terms=grouping_terms,
        methods_like_section_ids=methods_sections,
        results_like_section_ids=results_sections,
        passages=passages,
        reference_ids=reference_ids,
        resolved_visual_ids=resolved_visual_ids,
    )


def _passage(
    section: PaperSection,
    paragraph_index: int,
    paragraph: str,
    match_type: str,
    score: float,
) -> RetrievedPassage:
    """Build one retrieved passage model."""
    return RetrievedPassage(
        passage_id=f"{section.section_id}_p{paragraph_index}",
        section_id=section.section_id,
        heading=section.heading,
        text=paragraph,
        match_type=match_type,
        score=score,
    )


def _dedupe(values: list[str]) -> list[str]:
    """Deduplicate strings while preserving order."""
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        cleaned = clean_text(value)
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        deduped.append(cleaned)
    return deduped


def _table_visual_ids(
    definition: TableDefinition,
    table_label: str | None,
    paper_visual_inventory: list[PaperVisual],
) -> set[str]:
    visual_ids = {
        visual.visual_id
        for visual in paper_visual_inventory
        if visual.visual_kind == "table" and visual.source_table_id == definition.table_id
    }
    parsed = parse_visual_label(table_label or "")
    if parsed is not None and parsed[0] == "table":
        visual_ids.add(visual_id_for("table", parsed[1]))
    return visual_ids


def _reference_anchor_text(
    section_id: str | None,
    paragraph_index: int,
    table_label: str,
    paper_references: list[PaperVisualReference],
) -> str | None:
    for reference in paper_references:
        if (
            reference.section_id == section_id
            and reference.paragraph_index == paragraph_index
            and reference.reference_label.lower() == table_label.lower()
        ):
            return reference.anchor_text
    return None
