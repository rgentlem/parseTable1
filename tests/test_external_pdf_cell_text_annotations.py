"""Real-PDF smoke tests for cell-text annotation artifacts."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from table1_parser import cli


REPO_ROOT = Path(__file__).resolve().parents[1]
R_SCRIPT = REPO_ROOT / "R" / "inspect_paper_outputs.R"
EXTERNAL_TESTPAPERS_DIR = Path("/Users/robert/Projects/Epiconnector/testpapers")


def _r_dependencies_available() -> bool:
    if shutil.which("Rscript") is None:
        return False
    result = subprocess.run(
        ["Rscript", "-e", 'quit(status = if (requireNamespace("jsonlite", quietly = TRUE)) 0 else 1)'],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0


def test_external_metabolic_cell_text_annotations_are_visible_in_r(tmp_path) -> None:
    """The real metabolic paper should expose persisted annotations through R."""
    pdf_path = EXTERNAL_TESTPAPERS_DIR / "papers_from_johnny" / "metabolic.pdf"
    if not pdf_path.exists():
        pytest.skip(f"External test paper not found: {pdf_path}")
    if not _r_dependencies_available():
        pytest.skip("Rscript with jsonlite is required for this smoke test.")

    output_dir = tmp_path / "outputs"
    exit_code = cli.main(["parse", str(pdf_path), "--outdir", str(output_dir)])

    paper_dir = output_dir / "papers" / "metabolic"
    annotations_path = paper_dir / "cell_text_annotations.json"
    assert exit_code == 0
    assert annotations_path.exists()

    annotation_tables = json.loads(annotations_path.read_text(encoding="utf-8"))
    assert any(table.get("annotations") for table in annotation_tables)

    result = subprocess.run(
        [
            "Rscript",
            "-e",
            (
                f'source("{R_SCRIPT}"); '
                f'outputs <- load_paper_outputs("{paper_dir}"); '
                "df <- cell_text_annotations_df(outputs, table_number = 1L); "
                'cat(nrow(df), "\\n"); '
                'cat(any(df$annotation_type == "superscript"), "\\n"); '
                f'x <- show_cell_text_annotations("{paper_dir}", table_number = 1L); '
                'cat(nrow(x), "\\n")'
            ),
        ],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "Cell text annotations for table_number=1" in result.stdout
    assert "TRUE" in result.stdout


def test_external_rotated_tables_use_local_annotation_geometry(tmp_path) -> None:
    """Real rotated tables should transform char geometry before annotation matching."""
    pdf_paths = [
        EXTERNAL_TESTPAPERS_DIR
        / "papers_from_laha"
        / "Journal of Periodontology - 2015 - Eke - Update on Prevalence of Periodontitis in Adults in the United States  NHANES 2009.pdf",
        EXTERNAL_TESTPAPERS_DIR
        / "papers_from_laha"
        / "Ethnic Differences in the Relationship Between Insulin Sensitivity and Insulin Response.pdf",
    ]
    missing = [pdf_path for pdf_path in pdf_paths if not pdf_path.exists()]
    if missing:
        pytest.skip(f"External test paper not found: {missing[0]}")

    output_dir = tmp_path / "outputs"
    rotated_table_count = 0
    annotated_rotated_table_count = 0
    for pdf_path in pdf_paths:
        exit_code = cli.main(["parse", str(pdf_path), "--outdir", str(output_dir)])
        paper_dir = output_dir / "papers" / pdf_path.stem
        extracted_tables = json.loads((paper_dir / "extracted_tables.json").read_text(encoding="utf-8"))
        annotation_tables = json.loads((paper_dir / "cell_text_annotations.json").read_text(encoding="utf-8"))

        assert exit_code == 0
        for table_index, extracted_table in enumerate(extracted_tables):
            metadata = extracted_table.get("metadata") or {}
            coordinate_frame = metadata.get("geometry_coordinate_frame")
            if coordinate_frame == "page" or not metadata.get("geometry_transform_applied"):
                continue
            rotated_table_count += 1
            annotation_metadata = annotation_tables[table_index].get("metadata") or {}
            diagnostics = annotation_metadata.get("diagnostics") or []
            assert annotation_metadata.get("coordinate_frame") == coordinate_frame
            assert annotation_metadata.get("geometry_transform_applied") is True
            assert annotation_metadata.get("geometry_transform_source_bbox")
            assert annotation_metadata.get("rotation_direction") in {"vertical_text_up", "vertical_text_down"}
            assert not any(str(item).startswith("unsupported_coordinate_frame") for item in diagnostics)
            assert "cell_bboxes_missing" not in diagnostics
            if annotation_tables[table_index].get("annotations"):
                annotated_rotated_table_count += 1

    assert rotated_table_count >= 1
    assert annotated_rotated_table_count >= 1
