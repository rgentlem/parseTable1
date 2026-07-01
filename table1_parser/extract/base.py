"""Base interface for table extraction backends."""

from __future__ import annotations

from abc import ABC, abstractmethod

from table1_parser.schemas import ExtractedTable, PaperPageFurniture


class BaseExtractor(ABC):
    """Abstract interface implemented by all table extraction backends."""

    @abstractmethod
    def extract(
        self,
        pdf_path: str,
        *,
        paper_page_furniture: PaperPageFurniture | None = None,
    ) -> list[ExtractedTable]:
        """Extract tables from a PDF into canonical extracted-table models."""
