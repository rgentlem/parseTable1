"""Document-context extraction and retrieval helpers."""

from table1_parser.context.paper_document_builder import build_paper_document
from table1_parser.context.paper_positioned_document import build_paper_positioned_document
from table1_parser.context.retrieval import (
    build_table_contexts,
)
from table1_parser.context.section_parser import (
    build_paper_sections_from_document,
    paper_sections_to_payload,
)
from table1_parser.context.table_mentions import build_paper_table_mentions, paper_table_mentions_to_payload
from table1_parser.context.variable_inventory import (
    build_paper_variable_inventory,
    paper_variable_inventory_to_payload,
)
from table1_parser.context.visual_inventory import (
    build_figure_visuals,
    build_paper_visual_inventory,
    build_table_visuals,
)
from table1_parser.context.visual_references import annotate_visual_reference_checks, collect_paper_visual_references

__all__ = [
    "build_table_contexts",
    "build_paper_document",
    "build_paper_positioned_document",
    "build_paper_sections_from_document",
    "build_paper_table_mentions",
    "build_figure_visuals",
    "build_paper_visual_inventory",
    "build_paper_variable_inventory",
    "build_table_visuals",
    "annotate_visual_reference_checks",
    "collect_paper_visual_references",
    "paper_variable_inventory_to_payload",
    "paper_sections_to_payload",
    "paper_table_mentions_to_payload",
]
