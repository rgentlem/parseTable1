"""Join canonical paper blocks to raw positioned line evidence."""

from __future__ import annotations

from collections.abc import Iterator
from types import SimpleNamespace
from typing import Any, cast

from table1_parser.context.paper_positioned_document import canonical_bbox_for_orientation
from table1_parser.schemas import PaperPositionedDocument


def iter_paper_document_lines(
    paper_document: dict[str, object],
    positioned_document: PaperPositionedDocument,
) -> Iterator[SimpleNamespace]:
    """Yield non-persisted joins in canonical block and line order."""
    blocks = cast(list[dict[str, Any]], paper_document["blocks"])
    pages = cast(list[dict[str, Any]], paper_document["pages"])
    source_lines = {
        line.line_id: line for page in positioned_document.pages for line in page.lines
    }
    groups = {
        group["group_id"]: group
        for page in pages
        for group in page["orientation_groups"]
    }
    for block in blocks:
        line_ids = cast(list[str], block["line_ids"])
        line_texts = str(block["text"]).split("\n")
        if len(line_ids) != len(line_texts):
            raise ValueError(f"Canonical block text does not match its line IDs: {block['block_id']}")
        group = groups[block["orientation_group_id"]]
        for line_id, text in zip(line_ids, line_texts):
            source = source_lines[line_id]
            notes = list(source.notes)
            if source.has_bold:
                notes.append("has_bold_text")
            if block["orientation"] != "upright":
                notes.append(f"orientation_group:{block['orientation']}")
            if block["role"] == "heading":
                notes.append("layout_section_heading")
            yield SimpleNamespace(
                line_id=line_id,
                page_num=block["page_num"],
                block_index=source.block_index,
                line_index=source.line_index,
                raw_text=source.raw_text,
                text=text,
                bbox=source.bbox,
                canonical_bbox=canonical_bbox_for_orientation(
                    source.bbox,
                    orientation=block["orientation"],
                    orientation_source_bbox=group["source_bbox"],
                ),
                orientation=block["orientation"],
                orientation_group_id=block["orientation_group_id"],
                column_index=block["column_index"],
                column_count=block["column_count"],
                role=block["role"],
                dominant_font=source.dominant_font,
                dominant_font_size=source.dominant_font_size,
                spans=[span.model_dump(mode="json") for span in source.spans],
                notes=notes,
            )
