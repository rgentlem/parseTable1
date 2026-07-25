"""Build paper-level inventories of actual table and figure visuals."""

from __future__ import annotations

import re

from table1_parser.context.paper_document import iter_paper_document_lines
from table1_parser.context.visual_references import (
    VISUAL_OBJECT_DOI_PATTERN,
    parse_visual_label,
    visual_id_for,
)
from table1_parser.schemas import (
    ExtractedTable,
    PaperSection,
    PaperPositionedDocument,
    PaperVisual,
    TableDefinition,
)
from table1_parser.text_cleaning import clean_text


FIGURE_CAPTION_PATTERN = re.compile(
    r"(?:^|(?<=[.;]\s))(?P<label>(?:Fig\.?|Figure)\s*(?P<number>[A-Za-z]?\d+[A-Za-z]?))\b"
    r"(?:(?:[.:]\s*)|(?:\s+(?=(?-i:[A-Z]))))"
    r"(?P<caption>.*?)(?=(?:\s+(?:Fig\.?|Figure)\s*[A-Za-z]?\d+[A-Za-z]?"
    r"(?:(?:[.:]\s*)|(?:\s+(?=(?-i:[A-Z])))))|$)",
    re.IGNORECASE,
)


def build_table_visuals(
    paper_document: dict[str, object],
    extracted_tables: list[ExtractedTable],
    table_definitions: list[TableDefinition],
) -> list[PaperVisual]:
    """Build table visuals only from canonical table entities."""
    blocks_by_id = {
        str(block["block_id"]): block for block in paper_document["blocks"]
    }
    extracted_by_id = {table.table_id: table for table in extracted_tables}
    definitions_by_id = {definition.table_id: definition for definition in table_definitions}
    visuals_by_id: dict[str, PaperVisual] = {}
    for entity in paper_document["entities"]:
        if entity["kind"] != "table":
            continue
        evidence = entity.get("evidence") or {}
        resolved_table_id = str(evidence.get("resolved_table_id") or "")
        source_table_ids = [
            str(content_ref["artifact_id"])
            for component in entity["components"]
            if component["role"] == "content"
            for content_ref in component["content_refs"]
            if content_ref["artifact_kind"] == "extracted_table"
        ]
        source_tables = [
            extracted_by_id[table_id]
            for table_id in source_table_ids
            if table_id in extracted_by_id
        ]
        definition = definitions_by_id.get(resolved_table_id)
        caption_blocks = [
            blocks_by_id[str(block_id)]
            for component in entity["components"]
            if component["role"] == "caption"
            for block_id in component["block_ids"]
        ]
        caption = clean_text(" ".join(str(block["text"]) for block in caption_blocks))
        candidate_texts = [
            caption,
            *[table.title for table in source_tables],
            *[table.caption for table in source_tables],
            definition.title if definition is not None else None,
            definition.caption if definition is not None else None,
        ]
        parsed = next((parsed for text in candidate_texts if text and (parsed := parse_visual_label(text))), None)
        logical_table_number = evidence.get("logical_table_number")
        if parsed is None and logical_table_number is not None:
            number = str(logical_table_number)
            parsed = ("table", number, f"Table {number}")
        if parsed is None:
            raise ValueError(f"Table entity has no resolvable label: {entity['entity_id']}.")
        visual_kind, number, label = parsed
        if visual_kind != "table":
            raise ValueError(f"Table entity resolved to a non-table label: {entity['entity_id']}.")
        visual_id = visual_id_for("table", number)
        if visual_id in visuals_by_id:
            raise ValueError(f"Table entities share visual identity {visual_id}.")
        caption_placements = [
            str(placement) for placement in evidence.get("caption_placements", [])
        ]
        visuals_by_id[visual_id] = PaperVisual(
            visual_id=visual_id,
            visual_kind="table",
            label=label,
            number=number,
            caption=caption or None,
            caption_source="pdf_caption",
            page_num=(int(caption_blocks[0]["page_num"]) if caption_blocks else None),
            source_table_id=resolved_table_id or None,
            source="paper_document_table_entity",
            confidence=0.98,
            notes=[
                f"table_entity_id:{entity['entity_id']}",
                *[f"source_extracted_table_id:{table_id}" for table_id in source_table_ids],
                *[f"caption_placement:{placement}_table" for placement in caption_placements],
            ],
        )
    return list(visuals_by_id.values())


def build_figure_visuals(sections: list[PaperSection]) -> list[PaperVisual]:
    """Build paper visual records from conservative figure-caption matches."""
    visuals_by_id: dict[str, PaperVisual] = {}
    for section in sections:
        for match in FIGURE_CAPTION_PATTERN.finditer(section.content):
            parsed = parse_visual_label(match.group("label"))
            if parsed is None:
                continue
            visual_kind, number, label = parsed
            if visual_kind != "figure":
                continue
            visual_id = visual_id_for("figure", number)
            caption = clean_text(match.group(0))
            if visual_id in visuals_by_id:
                existing = visuals_by_id[visual_id]
                notes = [*existing.notes]
                duplicate_note = f"duplicate_caption_section:{section.section_id}"
                if duplicate_note not in notes:
                    notes.append(duplicate_note)
                visuals_by_id[visual_id] = existing.model_copy(update={"notes": notes})
                continue
            visuals_by_id[visual_id] = PaperVisual(
                visual_id=visual_id,
                visual_kind="figure",
                label=label,
                number=number,
                caption=caption,
                caption_source="markdown_caption",
                source="markdown_caption",
                confidence=0.8,
                notes=[f"caption_section_id:{section.section_id}"],
            )
    return list(visuals_by_id.values())


def build_paper_visual_inventory(
    extracted_tables: list[ExtractedTable],
    table_definitions: list[TableDefinition],
    sections: list[PaperSection],
    paper_document: dict[str, object] | None = None,
    paper_positioned_document: PaperPositionedDocument | None = None,
) -> list[PaperVisual]:
    """Build the paper-level inventory of actual table and figure visuals."""
    if paper_document is None:
        raise ValueError("PaperDocument is required to build the visual inventory.")
    visuals_by_id: dict[str, PaperVisual] = {}
    for visual in [
        *build_table_visuals(paper_document, extracted_tables, table_definitions),
        *build_figure_visuals(sections),
    ]:
        if visual.visual_id in visuals_by_id:
            existing = visuals_by_id[visual.visual_id]
            notes = [*existing.notes, *[note for note in visual.notes if note not in existing.notes]]
            visuals_by_id[visual.visual_id] = existing.model_copy(update={"notes": notes})
        else:
            visuals_by_id[visual.visual_id] = visual
    text_lines = (
        list(iter_paper_document_lines(paper_document, paper_positioned_document))
        if paper_document is not None and paper_positioned_document is not None
        else []
    )
    table_entity_line_ids_by_visual_id: dict[str, set[str]] = {}
    blocks_by_id = {
        str(block["block_id"]): block for block in paper_document["blocks"]
    }
    for entity in paper_document["entities"]:
        if entity["kind"] != "table":
            continue
        entity_visual = next(
            (
                visual
                for visual in visuals_by_id.values()
                if f"table_entity_id:{entity['entity_id']}" in visual.notes
            ),
            None,
        )
        if entity_visual is None:
            raise ValueError(f"Table entity has no visual: {entity['entity_id']}.")
        table_entity_line_ids_by_visual_id[entity_visual.visual_id] = {
            str(line_id)
            for component in entity["components"]
            for block_id in component["block_ids"]
            for line_id in blocks_by_id[str(block_id)]["line_ids"]
        }
    for line_index, line in enumerate(text_lines):
        match = VISUAL_OBJECT_DOI_PATTERN.fullmatch(clean_text(line.raw_text))
        if match is None:
            continue
        visual_kind = "table" if match.group("object_kind").lower() == "t" else "figure"
        visual_id = visual_id_for(visual_kind, str(int(match.group("object_number"))))
        visual = visuals_by_id.get(visual_id)
        if (
            visual_kind == "table"
            and line.line_id not in table_entity_line_ids_by_visual_id.get(visual_id, set())
        ):
            continue
        preceding_line = text_lines[line_index - 1] if line_index > 0 else None
        if (
            visual is None
            and visual_kind == "figure"
            and preceding_line is not None
            and preceding_line.page_num == line.page_num
            and preceding_line.orientation == line.orientation
            and abs(preceding_line.bbox[0] - line.bbox[0]) <= 1.0
            and preceding_line.bbox[3] <= line.bbox[1]
        ):
            for caption_index in range(line_index - 1, -1, -1):
                caption_line = text_lines[caption_index]
                if caption_line.page_num != line.page_num:
                    break
                caption_match = FIGURE_CAPTION_PATTERN.match(clean_text(caption_line.raw_text))
                parsed = parse_visual_label(caption_match.group("label")) if caption_match is not None else None
                if parsed is None or parsed[0] != "figure" or visual_id_for(*parsed[:2]) != visual_id:
                    continue
                caption = clean_text(
                    " ".join(item.raw_text for item in text_lines[caption_index:line_index])
                )
                visual = PaperVisual(
                    visual_id=visual_id,
                    visual_kind="figure",
                    label=parsed[2],
                    number=parsed[1],
                    caption=caption,
                    caption_source="pdf_caption",
                    page_num=line.page_num,
                    source="paper_document",
                    confidence=0.95,
                    notes=[f"caption_source_line_id:{caption_line.line_id}"],
                )
                visuals_by_id[visual_id] = visual
                break
        if visual is None:
            continue
        doi = match.group("doi")
        if visual.doi is not None and visual.doi != doi:
            notes = [*visual.notes, f"conflicting_visual_object_doi:{doi}"]
            visuals_by_id[visual_id] = visual.model_copy(
                update={"doi": None, "doi_source_line_id": None, "notes": notes}
            )
            continue
        if visual.doi is None and not any(
            note.startswith("conflicting_visual_object_doi:") for note in visual.notes
        ):
            visuals_by_id[visual_id] = visual.model_copy(
                update={"doi": doi, "doi_source_line_id": line.line_id}
            )
    return sorted(
        visuals_by_id.values(),
        key=lambda visual: (
            int(match.group(1)) if (match := re.match(r"^(\d+)(.*)$", visual.number)) is not None else 10**9,
            match.group(2) if match is not None else visual.number,
            visual.visual_kind,
        ),
    )
