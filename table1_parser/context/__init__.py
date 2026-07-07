"""Document-context extraction and retrieval helpers."""

from table1_parser.context.markdown_extractor import extract_paper_markdown
from table1_parser.context.paper_text_stream import (
    build_paper_text_stream,
    paper_text_stream_to_markdown,
)
from table1_parser.context.retrieval import (
    build_table_contexts,
)
from table1_parser.context.section_parser import parse_markdown_sections, paper_sections_to_payload
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
    "build_paper_text_stream",
    "build_paper_table_mentions",
    "build_figure_visuals",
    "build_paper_visual_inventory",
    "build_paper_variable_inventory",
    "build_table_visuals",
    "annotate_visual_reference_checks",
    "collect_paper_visual_references",
    "extract_paper_markdown",
    "paper_text_stream_to_markdown",
    "paper_variable_inventory_to_payload",
    "paper_sections_to_payload",
    "paper_table_mentions_to_payload",
    "parse_markdown_sections",
]
