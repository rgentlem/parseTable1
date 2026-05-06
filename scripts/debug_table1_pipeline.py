#!/usr/bin/env python3
"""Usage: python scripts/debug_table1_pipeline.py path/to/file.pdf"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _bootstrap_repo_root() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))


_bootstrap_repo_root()

from table1_parser.config import Settings
from table1_parser.extract import build_extractor
from table1_parser.heuristics import classify_rows, detect_column_roles, group_variable_blocks
from table1_parser.heuristics.value_pattern_detector import detect_value_pattern
from table1_parser.normalize import normalize_extracted_table


def main() -> int:
    parser = argparse.ArgumentParser(description="Debug one extracted table through normalization and heuristics.")
    parser.add_argument("pdf_path", help="Path to a PDF file.")
    parser.add_argument("--table-index", type=int, default=0, help="Extracted table index to inspect.")
    args = parser.parse_args()

    extractor = build_extractor(Settings().default_extraction_backend)
    tables = extractor.extract(args.pdf_path)
    print("\nDetected tables:", len(tables))
    if not tables:
        return 0
    if args.table_index < 0 or args.table_index >= len(tables):
        print(f"Invalid table index {args.table_index}; found {len(tables)} table(s).")
        return 1

    table = tables[args.table_index]
    print("\nExtracted table size:", table.n_rows, "rows x", table.n_cols, "cols")
    normalized = normalize_extracted_table(table)

    print("\nHeader rows:")
    for row in normalized.header_rows:
        print(row)

    print("\nBody rows:")
    for row_idx in normalized.body_rows[:10]:
        print(normalized.metadata.get("cleaned_rows", [])[row_idx])

    print("\nRow signatures:")
    for row_view in normalized.row_views:
        print(
            row_view.row_idx,
            "| raw:", row_view.first_cell_raw,
            "| norm:", row_view.first_cell_normalized,
            "| alpha:", row_view.first_cell_alpha_only,
            "| numeric:", row_view.numeric_cell_count,
            "| trailing:", row_view.has_trailing_values,
        )

    print("\nRow classifications")
    row_classes = classify_rows(normalized)
    for row_class in row_classes:
        print(row_class)

    print("\nVariable groups")
    for group in group_variable_blocks(normalized, row_classes):
        print(group)

    print("\nColumn roles")
    for role in detect_column_roles(normalized):
        print(role)

    print("\nValue pattern examples")
    for row_idx in normalized.body_rows:
        row = normalized.metadata.get("cleaned_rows", [])[row_idx]
        for cell in row[1:]:
            if cell:
                print(cell, "->", detect_value_pattern(cell))
                break
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
