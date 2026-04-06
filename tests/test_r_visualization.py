"""Smoke tests for the base-R visualization helper."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
R_SCRIPT = REPO_ROOT / "R" / "visualize_table_from_json.R"


def _r_dependencies_available() -> bool:
    if shutil.which("Rscript") is None:
        return False
    result = subprocess.run(
        ["Rscript", "-e", 'quit(status = if (requireNamespace("jsonlite", quietly = TRUE)) 0 else 1)'],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        check=False,
    )
    return result.returncode == 0


def test_r_visualization_supports_normalized_table_json(tmp_path) -> None:
    """The R helper should render a stored normalized-table JSON artifact."""
    if not _r_dependencies_available():
        return

    payload = [
        {
            "table_id": "tbl-normalized",
            "title": "Table 1",
            "caption": "Baseline characteristics",
            "header_rows": [0],
            "body_rows": [1, 2, 3],
            "row_views": [
                {
                    "row_idx": 1,
                    "raw_cells": ["Age, years", "52.1", "0.03"],
                    "first_cell_raw": "Age, years",
                    "first_cell_normalized": "Age years",
                    "first_cell_alpha_only": "Age years",
                    "nonempty_cell_count": 3,
                    "numeric_cell_count": 2,
                    "has_trailing_values": True,
                    "indent_level": 0,
                    "likely_role": None,
                },
                {
                    "row_idx": 2,
                    "raw_cells": ["Sex", "", ""],
                    "first_cell_raw": "Sex",
                    "first_cell_normalized": "Sex",
                    "first_cell_alpha_only": "Sex",
                    "nonempty_cell_count": 1,
                    "numeric_cell_count": 0,
                    "has_trailing_values": False,
                    "indent_level": 0,
                    "likely_role": None,
                },
                {
                    "row_idx": 3,
                    "raw_cells": ["Male", "34", ""],
                    "first_cell_raw": "Male",
                    "first_cell_normalized": "Male",
                    "first_cell_alpha_only": "Male",
                    "nonempty_cell_count": 2,
                    "numeric_cell_count": 1,
                    "has_trailing_values": True,
                    "indent_level": 2,
                    "likely_role": None,
                },
            ],
            "n_rows": 4,
            "n_cols": 3,
            "metadata": {
                "cleaned_rows": [
                    ["Variable", "Overall", "P-value"],
                    ["Age, years", "52.1", "0.03"],
                    ["Sex", "", ""],
                    ["Male", "34", ""],
                ]
            },
        }
    ]
    json_path = tmp_path / "normalized_tables.json"
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    result = subprocess.run(
        ["Rscript", str(R_SCRIPT), str(json_path)],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "Table 1" in result.stdout
    assert "Age, years" in result.stdout
    assert "Male" in result.stdout


def test_r_visualization_supports_compact_llm_payload_json(tmp_path) -> None:
    """The R helper should render one compact row-focused LLM payload trace."""
    if not _r_dependencies_available():
        return

    payload = {
        "report_timestamp": "2026-04-06T12:00:00Z",
        "table_id": "tbl-semantic",
        "payload": {
            "id": "tbl-semantic",
            "table": "Characteristics by DKD status",
            "rows": [
                {"i": 1, "label": "Age, years", "vals": True, "num": 3},
                {"i": 2, "label": "Sex"},
                {"i": 3, "label": "Male", "vals": True, "num": 2, "indent": 2},
            ],
            "vars": [
                {"label": "Age, years", "type": "continuous", "r0": 1, "r1": 1},
                {
                    "label": "Sex",
                    "type": "binary",
                    "r0": 2,
                    "r1": 4,
                    "levels": [{"i": 3, "label": "Male"}, {"i": 4, "label": "Female"}],
                },
            ],
            "passages": [{"id": "section_1_p0", "h": "Results", "t": "Table 2 shows baseline characteristics by DKD status."}],
        },
    }
    json_path = tmp_path / "table_definition_llm_input.json"
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    result = subprocess.run(
        ["Rscript", str(R_SCRIPT), str(json_path)],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "Characteristics by DKD status" in result.stdout
    assert "[1] Age, years" in result.stdout
    assert "Male" in result.stdout
