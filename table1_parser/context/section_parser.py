"""Block-based paper section construction."""

from __future__ import annotations

from typing import Any, cast

from table1_parser.schemas import PaperSection
from table1_parser.text_cleaning import clean_text


ABSTRACT_HINTS = ("abstract",)
METHODS_HINTS = (
    "method",
    "materials and methods",
    "patients and methods",
    "study design",
    "study population",
    "measurement",
    "covariate",
    "exposure",
    "statistical analysis",
)
RESULTS_HINTS = ("result", "findings")
DISCUSSION_HINTS = ("discussion",)
CONCLUSION_HINTS = ("conclusion", "conclusions", "summary")
REFERENCES_HINTS = ("reference", "references", "bibliography", "works cited")


def build_paper_sections_from_document(
    paper_document: dict[str, object],
) -> list[PaperSection]:
    """Build sections by assigning each body block to its preceding heading block."""
    blocks = cast(list[dict[str, Any]], paper_document["blocks"])
    sections: list[PaperSection] = []
    heading_block: dict[str, Any] | None = None
    body_blocks: list[dict[str, Any]] = []
    for block in blocks:
        if block["role"] != "heading":
            body_blocks.append(block)
            continue
        if heading_block is not None or body_blocks:
            sections.append(
                _build_section(
                    len(sections),
                    clean_text(heading_block["text"]) if heading_block is not None else None,
                    2 if heading_block is not None else 0,
                    [body_block["text"] for body_block in body_blocks],
                    heading_block_id=(heading_block["block_id"] if heading_block is not None else None),
                    body_block_ids=[body_block["block_id"] for body_block in body_blocks],
                )
            )
        heading_block = block
        body_blocks = []
    if heading_block is not None or body_blocks:
        sections.append(
            _build_section(
                len(sections),
                clean_text(heading_block["text"]) if heading_block is not None else None,
                2 if heading_block is not None else 0,
                [body_block["text"] for body_block in body_blocks],
                heading_block_id=(heading_block["block_id"] if heading_block is not None else None),
                body_block_ids=[body_block["block_id"] for body_block in body_blocks],
            )
        )
    return sections or [PaperSection(section_id="section_0", order=0)]


def paper_sections_to_payload(sections: list[PaperSection]) -> list[dict[str, object]]:
    """Serialize paper sections as JSON-friendly dictionaries."""
    return [section.model_dump(mode="json") for section in sections]


def _build_section(
    order: int,
    heading: str | None,
    level: int,
    lines: list[str],
    *,
    heading_block_id: str | None,
    body_block_ids: list[str],
) -> PaperSection:
    """Build one section object from heading and collected lines."""
    content = clean_text("\n".join(lines))
    lowered = clean_text(heading or "").lower()
    return PaperSection(
        section_id=f"section_{order}",
        order=order,
        heading=heading,
        level=level,
        role_hint=(
            "abstract_like"
            if any(token in lowered for token in ABSTRACT_HINTS)
            else (
                "methods_like"
                if any(token in lowered for token in METHODS_HINTS)
                else (
                    "results_like"
                    if any(token in lowered for token in RESULTS_HINTS)
                    else (
                        "discussion_like"
                        if any(token in lowered for token in DISCUSSION_HINTS)
                        else (
                            "conclusion_like"
                            if any(token in lowered for token in CONCLUSION_HINTS)
                            else ("references_like" if any(token in lowered for token in REFERENCES_HINTS) else "other")
                        )
                    )
                )
            )
        ),
        content=content,
        heading_block_id=heading_block_id,
        body_block_ids=body_block_ids,
    )
