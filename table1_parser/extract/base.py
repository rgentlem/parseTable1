"""Base interface for table extraction backends."""

from __future__ import annotations

from abc import ABC, abstractmethod

from collections.abc import Sequence

from table1_parser.schemas import (
    BibliographyEntry,
    ExtractedTable,
    PaperPageFurniture,
    PaperPositionedDocument,
    PaperTableMention,
    PaperTextStream,
)


class BaseExtractor(ABC):
    """Abstract interface implemented by all table extraction backends."""

    @abstractmethod
    def extract(
        self,
        pdf_path: str,
        *,
        paper_page_furniture: PaperPageFurniture | None = None,
        paper_positioned_document: PaperPositionedDocument | None = None,
        paper_table_mentions: Sequence[PaperTableMention] | None = None,
        paper_text_stream: PaperTextStream | None = None,
        bibliography_entries: Sequence[BibliographyEntry] | None = None,
    ) -> list[ExtractedTable]:
        """Extract tables from a PDF into canonical extracted-table models."""
