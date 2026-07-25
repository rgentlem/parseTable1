"""Private in-memory evidence used before final paper ownership."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class PaperDiscoveryState:
    """Canonical blocks and decisions needed by pre-final table discovery."""

    pages: list[dict[str, object]]
    blocks: list[dict[str, object]]
    prose_line_ids: frozenset[str]
    bibliography_block_ids: frozenset[str]
