"""Internal table-grid candidate used before canonical extraction is finalized."""

from __future__ import annotations

from table1_parser.schemas import ExtractedTable


class ProvisionalExtractedTable(ExtractedTable):
    """Unpersisted positioned grid awaiting canonical row and column selection."""
