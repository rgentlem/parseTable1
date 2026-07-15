"""Tests for shared positioned-document extraction."""

from pathlib import Path

import pymupdf

from table1_parser.context.paper_positioned_document import (
    build_paper_positioned_document,
)


def test_positioned_document_preserves_text_outside_page_box(tmp_path: Path) -> None:
    """Source text crossing the page box must remain complete in every text view."""
    pdf_path = tmp_path / "off_page_text.pdf"
    source_text = "Total Periodontitis 47.8+/-2.5"
    document = pymupdf.open()
    page = document.new_page(width=200, height=100)
    page.insert_text((20, 2), source_text, fontsize=12)
    document.save(pdf_path)
    document.close()

    positioned = build_paper_positioned_document(str(pdf_path))

    assert positioned.pages[0].lines[0].raw_text == source_text
    assert [word.text for word in positioned.pages[0].words] == [
        "Total",
        "Periodontitis",
        "47.8+/-2.5",
    ]
    assert "".join(char.text for char in positioned.pages[0].chars) == source_text
    assert positioned.pages[0].lines[0].bbox[1] < 0
