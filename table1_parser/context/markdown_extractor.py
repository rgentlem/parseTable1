"""PyMuPDF4LLM-backed paper markdown extraction."""

from __future__ import annotations

import contextlib
import io
import re

from table1_parser.paper_page_furniture import normalize_page_furniture_text
from table1_parser.schemas import PaperPageFurniture
from table1_parser.text_cleaning import repair_extractor_glyph_failures


MARKDOWN_DECORATION_PATTERN = re.compile(r"[*_`]+")
MARKDOWN_LINE_PREFIX_PATTERN = re.compile(r"^\s{0,3}(?:#{1,6}\s+|[-+*]\s+)")


def extract_paper_markdown(
    pdf_path: str,
    *,
    paper_page_furniture: PaperPageFurniture | None = None,
) -> str:
    """Extract markdown for a PDF while suppressing library stdout."""
    try:
        import pymupdf4llm
    except ModuleNotFoundError as exc:
        raise ModuleNotFoundError("pymupdf4llm is required for paper markdown extraction.") from exc
    stdout_buffer = io.StringIO()
    with contextlib.redirect_stdout(stdout_buffer):
        markdown = pymupdf4llm.to_markdown(pdf_path)
    repaired_markdown = repair_extractor_glyph_failures(str(markdown or ""))
    if paper_page_furniture is None:
        return repaired_markdown
    return filter_markdown_page_furniture(repaired_markdown, paper_page_furniture)


def filter_markdown_page_furniture(markdown: str, paper_page_furniture: PaperPageFurniture) -> str:
    """Remove markdown lines that match repeated page-furniture text clusters."""
    if not markdown or not paper_page_furniture.clusters:
        return markdown

    exact_cluster_keys: set[str] = set()
    wildcard_patterns: list[re.Pattern[str]] = []
    for cluster in paper_page_furniture.clusters:
        key = " ".join(cluster.normalized_text_key.split())
        if not key:
            continue
        if "<page_num>" in key:
            escaped_key = re.escape(key).replace(re.escape("<page_num>"), r"\d+")
            wildcard_patterns.append(re.compile(rf"^{escaped_key}$"))
            continue
        exact_cluster_keys.add(key)

    if not exact_cluster_keys and not wildcard_patterns:
        return markdown

    filtered_lines: list[str] = []
    for line in markdown.splitlines():
        normalized_line = normalize_page_furniture_text(_normalize_markdown_line(line))
        if normalized_line and (
            normalized_line in exact_cluster_keys
            or any(pattern.match(normalized_line) for pattern in wildcard_patterns)
        ):
            continue
        filtered_lines.append(line)
    return "\n".join(filtered_lines)


def _normalize_markdown_line(line: str) -> str:
    """Return a simple text key for comparing markdown lines with page-furniture clusters."""
    unwrapped = MARKDOWN_LINE_PREFIX_PATTERN.sub("", line.strip())
    unwrapped = MARKDOWN_DECORATION_PATTERN.sub("", unwrapped)
    return " ".join(unwrapped.split())
