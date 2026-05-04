"""Smoke tests for the base-R paper output inspection helpers."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
R_SCRIPT = REPO_ROOT / "R" / "inspect_paper_outputs.R"
R_COMPARE_SCRIPT = REPO_ROOT / "R" / "compare_normalized_rows_to_definition.R"
R_JSON_IO_SCRIPT = REPO_ROOT / "R" / "pt1_json_io.R"
R_OBSERVED_SCRIPT = REPO_ROOT / "R" / "observed_table_one.R"


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _make_variable(
    variable_name: str,
    variable_label: str,
    variable_type: str,
    row_start: int,
    row_end: int,
    *,
    levels: list[dict[str, object]] | None = None,
    confidence: float = 0.9,
) -> dict[str, object]:
    return {
        "variable_name": variable_name,
        "variable_label": variable_label,
        "variable_type": variable_type,
        "row_start": row_start,
        "row_end": row_end,
        "levels": levels or [],
        "confidence": confidence,
    }


def _make_column(
    col_idx: int,
    column_name: str,
    column_label: str,
    inferred_role: str,
    *,
    confidence: float = 0.9,
    grouping_variable_hint: str | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "col_idx": col_idx,
        "column_name": column_name,
        "column_label": column_label,
        "inferred_role": inferred_role,
        "confidence": confidence,
    }
    if grouping_variable_hint is not None:
        payload["grouping_variable_hint"] = grouping_variable_hint
    return payload


def _make_value(
    row_idx: int,
    col_idx: int,
    variable_name: str,
    column_name: str,
    raw_value: str,
    value_type: str,
    parsed_numeric: float,
    *,
    level_label: str | None = None,
    parsed_secondary_numeric: float | None = None,
    confidence: float = 0.9,
) -> dict[str, object]:
    return {
        "row_idx": row_idx,
        "col_idx": col_idx,
        "variable_name": variable_name,
        "level_label": level_label,
        "column_name": column_name,
        "raw_value": raw_value,
        "value_type": value_type,
        "parsed_numeric": parsed_numeric,
        "parsed_secondary_numeric": parsed_secondary_numeric,
        "confidence": confidence,
    }


def _make_parsed_table(
    table_id: str,
    title: str,
    caption: str,
    *,
    variables: list[dict[str, object]] | None = None,
    columns: list[dict[str, object]] | None = None,
    values: list[dict[str, object]] | None = None,
    notes: list[str] | None = None,
    overall_confidence: float = 0.9,
) -> dict[str, object]:
    return {
        "table_id": table_id,
        "title": title,
        "caption": caption,
        "variables": variables or [],
        "columns": columns or [],
        "values": values or [],
        "notes": notes or [],
        "overall_confidence": overall_confidence,
    }


def _make_processing_attempt(
    stage: str,
    name: str,
    *,
    considered: bool,
    ran: bool,
    succeeded: bool,
    note: str | None = None,
) -> dict[str, object]:
    return {
        "stage": stage,
        "name": name,
        "considered": considered,
        "ran": ran,
        "succeeded": succeeded,
        "note": note,
    }


def _make_processing_status(
    table_id: str,
    *,
    status: str,
    failure_stage: str | None = None,
    failure_reason: str | None = None,
    attempts: list[dict[str, object]] | None = None,
    notes: list[str] | None = None,
) -> dict[str, object]:
    return {
        "table_id": table_id,
        "status": status,
        "failure_stage": failure_stage,
        "failure_reason": failure_reason,
        "attempts": attempts or [],
        "notes": notes or [],
    }


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


def _write_sample_paper_outputs(
    paper_dir: Path,
    *,
    include_variable_review: bool,
    include_processing_status: bool = True,
) -> None:
    context_dir = paper_dir / "table_contexts"
    context_dir.mkdir(parents=True)

    extracted_tables = [
        {
            "table_id": "tbl-1",
            "source_pdf": "paper.pdf",
            "page_num": 5,
            "title": "Table 1",
            "caption": "Baseline characteristics by DKD status",
            "n_rows": 5,
            "n_cols": 3,
            "cells": [],
            "extraction_backend": "pymupdf4llm",
            "metadata": {"grid_refinement_source": "collapsed_explicit_grid_word_positions"},
        }
    ]
    normalized_tables = [
        {
            "table_id": "tbl-1",
            "title": "Table 1",
            "caption": "Baseline characteristics by DKD status",
            "header_rows": [0],
            "body_rows": [1, 2, 3, 4],
            "row_views": [],
            "n_rows": 5,
            "n_cols": 3,
            "metadata": {
                "cleaned_rows": [
                    ["Characteristic", "Overall", "DKD"],
                    ["Age, years", "52.1", "49.9"],
                    ["Sex", "", ""],
                    ["Male", "34 (45%)", "20 (40%)"],
                    ["Female", "41 (55%)", "30 (60%)"],
                ]
            },
        }
    ]
    variables = [
        _make_variable("Age years", "Age, years", "continuous", 1, 1),
        _make_variable(
            "Sex",
            "Sex",
            "categorical",
            2,
            4,
            levels=[
                {"level_name": "Male", "level_label": "Male", "row_idx": 3},
                {"level_name": "Female", "level_label": "Female", "row_idx": 4},
            ],
        ),
    ]
    columns = [
        _make_column(1, "Overall", "Overall", "overall"),
        _make_column(2, "DKD", "DKD", "group", grouping_variable_hint="DKD status"),
    ]
    table_definitions = [
        {
            "table_id": "tbl-1",
            "title": "Table 1",
            "caption": "Baseline characteristics by DKD status",
            "variables": variables,
            "column_definition": {
                "grouping_label": "DKD status",
                "grouping_name": "DKD status",
                "columns": columns,
                "confidence": 0.9,
            },
            "notes": [],
            "overall_confidence": 0.9,
        }
    ]
    parsed_tables = [
        _make_parsed_table(
            "tbl-1",
            "Table 1",
            "Baseline characteristics by DKD status",
            variables=variables,
            columns=columns,
            values=[
                _make_value(1, 1, "Age years", "Overall", "52.1", "numeric", 52.1),
                _make_value(1, 2, "Age years", "DKD", "49.9", "numeric", 49.9),
                _make_value(3, 1, "Sex", "Overall", "34 (45%)", "count_pct", 34.0, level_label="Male", parsed_secondary_numeric=45.0),
                _make_value(4, 1, "Sex", "Overall", "41 (55%)", "count_pct", 41.0, level_label="Female", parsed_secondary_numeric=55.0),
            ],
        )
    ]
    table1_continuation_groups = [
        {
            "group_id": "table1_continuation_0",
            "table_number": 1,
            "source_table_indices": [0, 1],
            "source_table_ids": ["tbl-1", "tbl-1-cont"],
            "merge_decision": "merge",
            "decision_reason": "explicit_table1_continuation_and_matching_columns",
            "confidence": 0.98,
            "column_signature_match": True,
            "column_signature": ["variable", "overall", "dkd"],
            "diagnostics": [],
            "members": [],
        }
    ]
    table_continuation_column_checks = [
        {
            "check_id": "table_continuation_column_check_0",
            "table_number": 1,
            "base_table_index": 0,
            "continuation_table_index": 1,
            "base_table_id": "tbl-1",
            "continuation_table_id": "tbl-1-cont",
            "base_page_num": 5,
            "continuation_page_num": 6,
            "base_n_cols": 3,
            "continuation_n_cols": 3,
            "base_table_family": "descriptive_characteristics",
            "continuation_table_family": "descriptive_characteristics",
            "base_table_category": "demographic_description",
            "continuation_table_category": "demographic_description",
            "normalized_column_count_match": True,
            "header_signature_status": "match",
            "base_column_signature": ["variable", "overall", "dkd"],
            "continuation_column_signature": ["variable", "overall", "dkd"],
            "coordinate_status": "compatible",
            "overall_status": "compatible",
            "confidence": 0.95,
            "column_map": [
                {
                    "base_col_idx": 0,
                    "continuation_col_idx": 0,
                    "base_center": 0.15,
                    "continuation_center": 0.16,
                    "center_delta": 0.01,
                    "base_width": 0.3,
                    "continuation_width": 0.3,
                    "width_delta": 0.0,
                    "status": "matched",
                },
                {
                    "base_col_idx": 1,
                    "continuation_col_idx": 1,
                    "base_center": 0.5,
                    "continuation_center": 0.51,
                    "center_delta": 0.01,
                    "base_width": 0.3,
                    "continuation_width": 0.3,
                    "width_delta": 0.0,
                    "status": "matched",
                },
                {
                    "base_col_idx": 2,
                    "continuation_col_idx": 2,
                    "base_center": 0.85,
                    "continuation_center": 0.86,
                    "center_delta": 0.01,
                    "base_width": 0.3,
                    "continuation_width": 0.3,
                    "width_delta": 0.0,
                    "status": "matched",
                },
            ],
            "base_coordinate_profile": {
                "table_id": "tbl-1",
                "normalized_n_cols": 3,
                "coordinate_n_cols": 3,
                "coordinate_source": "extracted_cells",
                "evidence_quality": "strong",
                "table_left": 0.0,
                "table_right": 100.0,
                "normalized_lefts": [0.0, 0.35, 0.7],
                "normalized_centers": [0.15, 0.5, 0.85],
                "normalized_rights": [0.3, 0.65, 1.0],
                "normalized_widths": [0.3, 0.3, 0.3],
                "warnings": [],
            },
            "continuation_coordinate_profile": {
                "table_id": "tbl-1-cont",
                "normalized_n_cols": 3,
                "coordinate_n_cols": 3,
                "coordinate_source": "extracted_cells",
                "evidence_quality": "strong",
                "table_left": 0.0,
                "table_right": 100.0,
                "normalized_lefts": [0.01, 0.36, 0.71],
                "normalized_centers": [0.16, 0.51, 0.86],
                "normalized_rights": [0.31, 0.66, 1.01],
                "normalized_widths": [0.3, 0.3, 0.3],
                "warnings": [],
            },
            "diagnostics": ["coordinate_delta:max_center=0.01:max_width=0.0"],
        }
    ]
    merged_table1_tables = [
        {
            **normalized_tables[0],
            "table_id": "tbl-1-merged-table1",
            "n_rows": 6,
            "metadata": {
                **normalized_tables[0]["metadata"],
                "cleaned_rows": [
                    ["Characteristic", "Overall", "DKD"],
                    ["Age, years", "52.1", "49.9"],
                    ["Sex", "", ""],
                    ["Male", "34 (45%)", "20 (40%)"],
                    ["Female", "41 (55%)", "30 (60%)"],
                    ["HbA1c, %", "5.6", "6.2"],
                ],
                "table1_continuation_merge": {
                    "group_id": "table1_continuation_0",
                    "source_table_indices": [0, 1],
                    "source_table_ids": ["tbl-1", "tbl-1-cont"],
                    "column_signature": ["variable", "overall", "dkd"],
                    "artifact_only": True,
                    "row_provenance": [
                        {"merged_row_idx": 0, "source_table_id": "tbl-1", "source_row_idx": 0},
                        {"merged_row_idx": 1, "source_table_id": "tbl-1", "source_row_idx": 1},
                        {"merged_row_idx": 2, "source_table_id": "tbl-1", "source_row_idx": 2},
                        {"merged_row_idx": 3, "source_table_id": "tbl-1", "source_row_idx": 3},
                        {"merged_row_idx": 4, "source_table_id": "tbl-1", "source_row_idx": 4},
                        {"merged_row_idx": 5, "source_table_id": "tbl-1-cont", "source_row_idx": 2},
                    ],
                },
            },
        }
    ]
    table_profiles = [
        {
            "table_id": "tbl-1",
            "table_family": "descriptive_characteristics",
            "detected_primary_outcome": None,
            "detected_exposure_or_predictor": None,
            "confidence": 0.95,
            "evidence": ["caption_mentions_baseline"],
        }
    ]
    parse_quality_reports = [
        {
            "report_timestamp": "2026-03-24T10:15:00Z",
            "source_identifier": "paper.pdf",
            "table_id": "tbl-1",
            "summary": {
                "total_body_rows": 4,
                "unknown_row_count": 0,
                "unknown_row_fraction": 0.0,
                "variable_block_count": 2,
                "recognized_value_pattern_fraction": 0.85,
                "row_warning_count": 0,
                "column_warning_count": 1,
            },
            "table_diagnostics": [
                {
                    "severity": "warning",
                    "code": "header_rule_content_disagreement",
                    "message": "Strong horizontal-rule evidence overrode content-based header detection.",
                    "row_idx": None,
                    "col_idx": None,
                }
            ],
            "row_diagnostics": [],
            "column_diagnostics": [
                {
                    "severity": "warning",
                    "code": "weak_p_value_column",
                    "message": "Column is labeled as p_value but many entries do not resemble p-values.",
                    "row_idx": None,
                    "col_idx": 3,
                }
            ],
        }
    ]
    paper_sections = [
        {
            "section_id": "section_0",
            "order": 0,
            "heading": "Methods",
            "level": 1,
            "role_hint": "methods_like",
            "content": "Example study population.",
        }
    ]
    paper_variable_inventory = {
        "paper_id": "paper",
        "mentions": [
            {
                "mention_id": "m1",
                "raw_label": "Age",
                "normalized_label": "age",
                "source_type": "text_based",
                "mention_role": "variable",
                "canonical_label": "Age",
                "section_id": "section_0",
                "heading": "Methods",
                "role_hint": "methods_like",
                "paragraph_index": 0,
                "evidence_text": "Age and sex were measured.",
                "table_id": "tbl-1",
                "table_index": 0,
                "table_label": "Table 1",
                "priority_weight": 1.0,
                "confidence": 0.9,
            }
        ],
        "candidates": [
            {
                "candidate_id": "c1",
                "preferred_label": "Age",
                "canonical_label": "Age",
                "normalized_label": "age",
                "canonical_label_source": "mention",
                "promotion_basis": "text_support",
                "alternate_labels": ["Age, years"],
                "source_types": ["text_based", "table_based"],
                "section_ids": ["section_0"],
                "section_role_hints": ["methods_like"],
                "table_ids": ["tbl-1"],
                "table_indices": [0],
                "text_support_count": 1,
                "table_support_count": 1,
                "caption_support_count": 0,
                "filtered_mention_count": 1,
                "priority_score": 0.9,
                "confidence": 0.9,
                "interpretation_status": "candidate",
            }
        ],
    }
    paper_table_inventory = {
        "paper_id": "paper",
        "tables": [
            {
                "table_id": "tbl-1",
                "table_number": 1,
                "title": "Table 1",
                "caption": "Baseline characteristics by DKD status",
                "table_category": "demographic_description",
                "category_confidence": 0.85,
                "category_evidence": ["caption_or_title_mentions_population_description"],
                "continuation_of_table_number": None,
                "table_family": "descriptive_characteristics",
                "processing_status": "ok",
                "failure_reason": None,
            },
            {
                "table_id": "layout-box",
                "table_number": None,
                "title": None,
                "caption": None,
                "table_category": "non_table_artifact",
                "category_confidence": 0.98,
                "category_evidence": ["processing_status_non_table_layout_candidate"],
                "continuation_of_table_number": None,
                "table_family": "unknown",
                "processing_status": "failed",
                "failure_reason": "non_table_layout_candidate",
            }
        ],
    }
    table_context = {
        "table_id": "tbl-1",
        "table_index": 0,
        "table_label": "Table 1",
        "title": "Table 1",
        "caption": "Baseline characteristics by DKD status",
        "passages": [
            {
                "passage_id": "p1",
                "section_id": "section_0",
                "heading": "Methods",
                "match_type": "table_reference",
                "score": 0.9,
                "text": "Table 1 shows age and sex by DKD status.",
            }
        ],
        "methods_like_section_ids": ["section_0"],
        "reference_ids": ["paper_ref:section_0:p0:r0"],
        "resolved_visual_ids": ["paper_visual:table:1"],
    }
    paper_visual_inventory = [
        {
            "visual_id": "paper_visual:table:1",
            "visual_kind": "table",
            "label": "Table 1",
            "number": "1",
            "caption": "Baseline characteristics by DKD status",
            "caption_source": "extracted_table",
            "page_num": 5,
            "artifact_path": None,
            "source_table_id": "tbl-1",
            "source": "table_extraction",
            "confidence": 0.95,
            "text_reference_ids": ["paper_ref:section_0:p0:r0"],
            "reference_check_status": "referenced_in_text",
            "reference_check_notes": [],
            "notes": [],
        },
        {
            "visual_id": "paper_visual:figure:1",
            "visual_kind": "figure",
            "label": "Figure 1",
            "number": "1",
            "caption": "Figure 1. Enrollment.",
            "caption_source": "markdown_caption",
            "page_num": None,
            "artifact_path": None,
            "source_table_id": None,
            "source": "markdown_caption",
            "confidence": 0.8,
            "text_reference_ids": [],
            "reference_check_status": "no_text_reference",
            "reference_check_notes": ["no_non_self_text_reference_found"],
            "notes": [],
        },
    ]
    paper_references = [
        {
            "reference_id": "paper_ref:section_0:p0:r0",
            "reference_kind": "table",
            "reference_label": "Table 1",
            "reference_number": "1",
            "matched_text": "Table 1",
            "section_id": "section_0",
            "heading": "Methods",
            "role_hint": "methods_like",
            "paragraph_index": 0,
            "start_char": 0,
            "end_char": 7,
            "anchor_text": "Table 1 shows age and sex by DKD status.",
            "resolved_visual_id": "paper_visual:table:1",
            "resolution_status": "resolved",
            "resolution_notes": [],
        }
    ]

    _write_json(paper_dir / "extracted_tables.json", extracted_tables)
    _write_json(paper_dir / "normalized_tables.json", normalized_tables)
    _write_json(paper_dir / "table1_continuation_groups.json", table1_continuation_groups)
    _write_json(paper_dir / "table_continuation_column_checks.json", table_continuation_column_checks)
    _write_json(paper_dir / "merged_table1_tables.json", merged_table1_tables)
    _write_json(paper_dir / "table_definitions.json", table_definitions)
    _write_json(paper_dir / "parsed_tables.json", parsed_tables)
    _write_json(paper_dir / "table_profiles.json", table_profiles)
    _write_json(paper_dir / "parse_quality_reports.json", parse_quality_reports)
    (paper_dir / "paper_markdown.md").write_text("# Methods\nExample study population.", encoding="utf-8")
    _write_json(paper_dir / "paper_sections.json", paper_sections)
    _write_json(paper_dir / "paper_visual_inventory.json", paper_visual_inventory)
    _write_json(paper_dir / "paper_references.json", paper_references)
    _write_json(paper_dir / "paper_variable_inventory.json", paper_variable_inventory)
    _write_json(paper_dir / "paper_table_inventory.json", paper_table_inventory)
    _write_json(context_dir / "table_0_context.json", table_context)

    if include_processing_status:
        _write_json(
            paper_dir / "table_processing_status.json",
            [
                _make_processing_status(
                    "tbl-1",
                    status="ok",
                    attempts=[
                        _make_processing_attempt(
                            "table_definition",
                            "deterministic_definition",
                            considered=True,
                            ran=True,
                            succeeded=True,
                            note="variables=2, usable_columns=2",
                        ),
                        _make_processing_attempt(
                            "parsed_table",
                            "deterministic_value_parse",
                            considered=True,
                            ran=True,
                            succeeded=True,
                            note="values=4",
                        ),
                    ],
                )
            ],
        )

    if include_variable_review:
        _write_json(
            paper_dir / "table_variable_plausibility_llm.json",
            [
                {
                    "table_id": "tbl-1",
                    "variables": [
                        {
                            "variable_name": "Age years",
                            "variable_label": "Age, years",
                            "variable_type": "continuous",
                            "row_start": 1,
                            "row_end": 1,
                            "levels": [],
                            "plausibility_score": 0.99,
                            "plausibility_note": None,
                        },
                        {
                            "variable_name": "Sex",
                            "variable_label": "Sex",
                            "variable_type": "categorical",
                            "row_start": 2,
                            "row_end": 4,
                            "levels": [
                                {"level_name": "Male", "level_label": "Male", "row_idx": 3},
                                {"level_name": "Female", "level_label": "Female", "row_idx": 4},
                            ],
                            "plausibility_score": 0.97,
                            "plausibility_note": "",
                        },
                    ],
                    "notes": ["Variables look coherent."],
                    "overall_plausibility": 0.98,
                }
            ],
        )


def _write_sample_variable_plausibility_debug_run(
    paper_dir: Path,
    run_id: str = "20260324T101500Z",
) -> None:
    debug_dir = paper_dir / "llm_variable_plausibility_debug" / run_id
    debug_dir.mkdir(parents=True, exist_ok=True)
    _write_json(
        debug_dir / "llm_variable_plausibility_monitoring.json",
        {
            "report_timestamp": "2026-03-24T10:15:00Z",
            "provider": "openai",
            "model": "gpt-4.1-mini",
            "items": [
                {
                    "table_id": "tbl-1",
                    "table_index": 0,
                    "table_family": "descriptive_characteristics",
                    "eligible_for_review": True,
                    "status": "success",
                    "elapsed_seconds": 0.42,
                    "prompt_char_count": 900,
                    "response_char_count": 300,
                    "deterministic_variable_count": 2,
                    "attached_level_count": 2,
                },
                {
                    "table_id": "tbl-2",
                    "table_index": 1,
                    "table_family": "estimate_results",
                    "eligible_for_review": False,
                    "status": "skipped_not_eligible",
                    "deterministic_variable_count": 1,
                    "attached_level_count": 0,
                },
            ],
        },
    )


def test_r_inspection_loads_and_shows_paper_variable_inventory(tmp_path) -> None:
    """The R helper should load and print paper-variable inventory rows."""
    if not _r_dependencies_available():
        return

    paper_dir = tmp_path / "paper_inventory" / "papers" / "paper"
    _write_sample_paper_outputs(paper_dir, include_variable_review=False, include_processing_status=True)

    result = subprocess.run(
        [
            "Rscript",
            "-e",
            (
                f'source("{R_SCRIPT}"); '
                f'show_paper_variable_candidates("{paper_dir}"); '
                f'show_paper_variable_mentions("{paper_dir}", source_type = "text_based")'
            ),
        ],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "Paper variable candidates" in result.stdout
    assert "Paper variable mentions" in result.stdout
    assert "Age" in result.stdout


def test_r_inspection_loads_and_shows_paper_table_inventory(tmp_path) -> None:
    """The R helper should load and print paper table taxonomy predictions."""
    if not _r_dependencies_available():
        return

    paper_dir = tmp_path / "paper_table_inventory" / "papers" / "paper"
    _write_sample_paper_outputs(paper_dir, include_variable_review=False, include_processing_status=True)

    result = subprocess.run(
        [
            "Rscript",
            "-e",
            (
                f'source("{R_SCRIPT}"); '
                f'outputs <- load_paper_outputs("{paper_dir}"); '
                "print(paper_table_inventory_df(outputs)); "
                f'show_paper_table_inventory("{paper_dir}")'
            ),
        ],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "Paper table inventory" in result.stdout
    assert "demographic_description" in result.stdout
    assert "non_table_artifact" in result.stdout
    assert "table_number" in result.stdout
    assert "NA" in result.stdout


def test_r_inspection_builds_named_paper_table_inventory_list(tmp_path) -> None:
    """The R helper should return one taxonomy data frame per paper directory."""
    if not _r_dependencies_available():
        return

    papers_root = tmp_path / "paper_table_inventory_list" / "papers"
    paper_a = papers_root / "paper_a"
    paper_b = papers_root / "paper_b"
    _write_sample_paper_outputs(paper_a, include_variable_review=False, include_processing_status=True)
    _write_sample_paper_outputs(paper_b, include_variable_review=False, include_processing_status=True)

    result = subprocess.run(
        [
            "Rscript",
            "-e",
            (
                f'source("{R_SCRIPT}"); '
                f'x <- paper_table_inventory_list("{papers_root}"); '
                'cat(length(x), "\\n"); '
                'cat(paste(names(x), collapse = "|"), "\\n"); '
                'cat(nrow(x[[1]]), "\\n"); '
                'cat(x[[1]]$table_category[[1]], "\\n")'
            ),
        ],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "2" in result.stdout
    assert "paper_a|paper_b" in result.stdout
    assert "demographic_description" in result.stdout


def test_r_inspection_loads_and_shows_paper_visual_references(tmp_path) -> None:
    """The R helper should load and print paper visual inventory and references."""
    if not _r_dependencies_available():
        return

    paper_dir = tmp_path / "paper_visuals" / "papers" / "paper"
    _write_sample_paper_outputs(paper_dir, include_variable_review=False, include_processing_status=True)

    result = subprocess.run(
        [
            "Rscript",
            "-e",
                (
                    f'source("{R_SCRIPT}"); '
                    f'show_paper_visuals("{paper_dir}", visual_kind = "figure"); '
                    f'show_paper_references("{paper_dir}", resolution_status = "resolved"); '
                    f'show_table_context("{paper_dir}", table_number = 1L)'
                ),
        ],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "Paper visuals" in result.stdout
    assert "Figure 1" in result.stdout
    assert "Paper references" in result.stdout
    assert "paper_ref:section_0:p0:r0" in result.stdout
    assert "Reference IDs" in result.stdout
    assert "Table context for table_number=1" in result.stdout


def test_r_inspection_loads_processing_status_and_summarizes_tables(tmp_path) -> None:
    """The R helper should summarize saved table processing status rows."""
    if not _r_dependencies_available():
        return

    paper_dir = tmp_path / "processing" / "papers" / "paper"
    _write_sample_paper_outputs(paper_dir, include_variable_review=False, include_processing_status=True)

    result = subprocess.run(
        [
            "Rscript",
            "-e",
            (
                f'source("{R_SCRIPT}"); '
                f'summarize_table_processing("{paper_dir}")'
            ),
        ],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "Table processing summary" in result.stdout
    assert "tbl-1" in result.stdout
    assert "table_number" in result.stdout
    assert "ok" in result.stdout
    assert "descriptive_characteristics" in result.stdout
    assert "quality_column_warning_count" in result.stdout


def test_r_inspection_loads_and_shows_parse_quality_reports(tmp_path) -> None:
    """The R helper should summarize and print saved parse-quality diagnostics."""
    if not _r_dependencies_available():
        return

    paper_dir = tmp_path / "parse_quality" / "papers" / "paper"
    _write_sample_paper_outputs(paper_dir, include_variable_review=False, include_processing_status=True)

    result = subprocess.run(
        [
            "Rscript",
            "-e",
                (
                    f'source("{R_SCRIPT}"); '
                    f'outputs <- load_paper_outputs("{paper_dir}"); '
                    f'print(length(outputs$parse_quality_reports)); '
                    f'show_parse_quality("{paper_dir}", table_number = 1L)'
                ),
        ],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "[1] 1" in result.stdout
    assert "Parse quality for table_number=1" in result.stdout
    assert "Table Diagnostics" in result.stdout
    assert "Column Diagnostics" in result.stdout
    assert "header_rule_content_disagreement" in result.stdout
    assert "weak_p_value_column" in result.stdout


def test_r_inspection_summarizes_and_shows_merged_table1_artifacts(tmp_path) -> None:
    """The R helper should summarize and print artifact-only merged Table 1 rows."""
    if not _r_dependencies_available():
        return

    paper_dir = tmp_path / "merged_table1" / "papers" / "paper"
    _write_sample_paper_outputs(paper_dir, include_variable_review=False, include_processing_status=True)

    result = subprocess.run(
        [
            "Rscript",
            "-e",
            (
                f'source("{R_SCRIPT}"); '
                f'summarize_table1_continuations("{paper_dir}"); '
                f'show_merged_table1("{paper_dir}", max_rows = 10L)'
            ),
        ],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "Table 1 continuation summary" in result.stdout
    assert "explicit_table1_continuation_and_matching_columns" in result.stdout
    assert "Merged Table 1" in result.stdout
    assert "tbl-1-cont:2" in result.stdout
    assert "HbA1c" in result.stdout


def test_r_inspection_shows_table_continuation_column_checks(tmp_path) -> None:
    """The R helper should summarize continuation column compatibility diagnostics."""
    if not _r_dependencies_available():
        return

    paper_dir = tmp_path / "continuation_columns" / "papers" / "paper"
    _write_sample_paper_outputs(paper_dir, include_variable_review=False, include_processing_status=True)

    result = subprocess.run(
        [
            "Rscript",
            "-e",
            (
                f'source("{R_SCRIPT}"); '
                f'outputs <- load_paper_outputs("{paper_dir}"); '
                f'print(length(outputs$table_continuation_column_checks)); '
                f'show_paper_table_inventory("{paper_dir}"); '
                f'summarize_table_continuation_column_checks("{paper_dir}"); '
                f'show_table_continuation_column_check("{paper_dir}")'
            ),
        ],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "[1] 1" in result.stdout
    assert "Continuation column checks" in result.stdout
    assert "Table continuation column checks" in result.stdout
    assert "Table continuation column check table_continuation_column_check_0" in result.stdout
    assert "overall_status" in result.stdout
    assert "compatible" in result.stdout
    assert "Column Map" in result.stdout
    assert "coordinate_delta:max_center=0.01:max_width=0.0" in result.stdout


def test_r_inspection_shows_failed_table_processing_and_structure_header(tmp_path) -> None:
    """The R helper should print failure details and deterministic structure for one table."""
    if not _r_dependencies_available():
        return

    paper_dir = tmp_path / "failed_processing" / "papers" / "paper"
    _write_sample_paper_outputs(paper_dir, include_variable_review=False, include_processing_status=True)
    _write_json(
        paper_dir / "table_processing_status.json",
        [
            _make_processing_status(
                "tbl-1",
                status="failed",
                failure_stage="parsed_table",
                failure_reason="no_values_after_parse",
                attempts=[
                    _make_processing_attempt(
                        "parsed_table",
                        "deterministic_value_parse",
                        considered=True,
                        ran=True,
                        succeeded=False,
                        note="values=0",
                    )
                ],
                notes=["parse_failed:no_values_after_parse"],
            )
        ],
    )

    result = subprocess.run(
        [
            "Rscript",
            "-e",
                (
                    f'source("{R_SCRIPT}"); '
                    f'show_table_processing("{paper_dir}", table_number = 1L); '
                    f'show_table_structure("{paper_dir}", table_number = 1L)'
                ),
        ],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "failure_reason: no_values_after_parse" in result.stdout
    assert "Table processing for table_number=1" in result.stdout
    assert "table_number: 1" in result.stdout
    assert "Rows" in result.stdout
    assert "Variables" in result.stdout
    assert "Age, years" in result.stdout


def test_r_inspection_loads_without_processing_status(tmp_path) -> None:
    """The R helper should still load and show table structure when processing status is absent."""
    if not _r_dependencies_available():
        return

    paper_dir = tmp_path / "no_processing" / "papers" / "paper"
    _write_sample_paper_outputs(paper_dir, include_variable_review=False, include_processing_status=False)

    result = subprocess.run(
        [
            "Rscript",
            "-e",
                (
                    f'source("{R_SCRIPT}"); '
                    f'show_table_structure("{paper_dir}", table_number = 1L)'
                ),
        ],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "table_id: tbl-1" in result.stdout
    assert "Columns" in result.stdout


def test_r_inspection_shows_variable_plausibility_review(tmp_path) -> None:
    """The R helper should print the saved variable-plausibility review beside the table rows."""
    if not _r_dependencies_available():
        return

    paper_dir = tmp_path / "variable_review" / "papers" / "paper"
    _write_sample_paper_outputs(paper_dir, include_variable_review=True, include_processing_status=True)

    result = subprocess.run(
        [
            "Rscript",
            "-e",
                (
                    f'source("{R_SCRIPT}"); '
                    f'x <- load_paper_outputs("{paper_dir}"); '
                    'print(llm_variable_plausibility_df(x)); '
                    f'show_llm_variable_plausibility("{paper_dir}", table_number = 1L)'
                ),
        ],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "plausibility_score" in result.stdout
    assert "table_number" in result.stdout
    assert "Variable Plausibility Review" in result.stdout
    assert "Sex" in result.stdout
    assert "levels:" in result.stdout
    assert "row  3 | Male" in result.stdout
    assert "score=0.970" in result.stdout


def test_r_compare_normalized_rows_to_definition_supports_table_number(tmp_path) -> None:
    """The standalone R helper should compare normalized labels to definition labels by paper table number."""
    if not _r_dependencies_available():
        return

    paper_dir = tmp_path / "compare_rows" / "papers" / "paper"
    (paper_dir / "table_contexts").mkdir(parents=True)

    _write_json(
        paper_dir / "extracted_tables.json",
        [
            {
                "table_id": "tbl-1",
                "source_pdf": "paper.pdf",
                "page_num": 5,
                "title": "Table 1",
                "caption": "Example one",
                "n_rows": 3,
                "n_cols": 2,
                "cells": [],
                "extraction_backend": "pymupdf4llm",
            },
            {
                "table_id": "tbl-2",
                "source_pdf": "paper.pdf",
                "page_num": 6,
                "title": "Table 2",
                "caption": "Example two",
                "n_rows": 4,
                "n_cols": 2,
                "cells": [],
                "extraction_backend": "pymupdf4llm",
            },
        ],
    )
    _write_json(
        paper_dir / "normalized_tables.json",
        [
            {
                "table_id": "tbl-1",
                "title": "Table 1",
                "caption": "Example one",
                "header_rows": [0],
                "body_rows": [1],
                "row_views": [],
                "n_rows": 2,
                "n_cols": 2,
                "metadata": {"cleaned_rows": [["Characteristic", "Overall"], ["Age, years", "52.1"]]},
            },
            {
                "table_id": "tbl-2",
                "title": "Table 2",
                "caption": "Example two",
                "header_rows": [0],
                "body_rows": [1, 2, 3],
                "row_views": [],
                "n_rows": 4,
                "n_cols": 2,
                "metadata": {
                    "cleaned_rows": [
                        ["Characteristic", "Overall"],
                        ["Body mass index (kg/m2), mean (SD)", "27.5"],
                        ["Smoking status, n (%)", ""],
                        ["Current", "12 (24%)"],
                    ]
                },
            },
        ],
    )
    _write_json(
        paper_dir / "table_definitions.json",
        [
            {
                "table_id": "tbl-1",
                "title": "Table 1",
                "caption": "Example one",
                "variables": [_make_variable("Age years", "Age, years", "continuous", 1, 1)],
                "column_definition": {"columns": [_make_column(1, "Overall", "Overall", "overall")]},
                "notes": [],
                "overall_confidence": 0.9,
            },
            {
                "table_id": "tbl-2",
                "title": "Table 2",
                "caption": "Example two",
                "variables": [
                    _make_variable("Body mass index", "Body mass index (kg/m2), mean (SD)", "continuous", 1, 1),
                    _make_variable(
                        "Smoking status",
                        "Smoking status, n (%)",
                        "categorical",
                        2,
                        3,
                        levels=[{"level_name": "Current", "level_label": "Current", "row_idx": 3}],
                    ),
                ],
                "column_definition": {"columns": [_make_column(1, "Overall", "Overall", "overall")]},
                "notes": [],
                "overall_confidence": 0.9,
            },
        ],
    )
    _write_json(
        paper_dir / "paper_sections.json",
        [
            {
                "section_id": "section_0",
                "order": 0,
                "heading": "Methods",
                "level": 1,
                "role_hint": "methods_like",
                "content": "Example study population.",
            }
        ],
    )

    result = subprocess.run(
        [
            "Rscript",
            "-e",
                (
                    f'source("{R_COMPARE_SCRIPT}"); '
                    f'compare_normalized_rows_to_definition("{paper_dir}", table_number = 2L)'
                ),
        ],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "Smoking status, n (%)" in result.stdout
    assert "Current" in result.stdout


def test_r_inspection_summarizes_llm_variable_plausibility_debug_run(tmp_path) -> None:
    """The R helper should summarize the saved variable-plausibility debug run."""
    if not _r_dependencies_available():
        return

    paper_dir = tmp_path / "plausibility_debug" / "papers" / "paper"
    _write_sample_paper_outputs(paper_dir, include_variable_review=True, include_processing_status=True)
    _write_sample_variable_plausibility_debug_run(paper_dir)

    result = subprocess.run(
        [
            "Rscript",
            "-e",
            (
                f'source("{R_SCRIPT}"); '
                f'cat(length(list_llm_variable_plausibility_debug_runs("{paper_dir}")), "\\n"); '
                f'summarize_llm_variable_plausibility_monitoring("{paper_dir}")'
            ),
        ],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "1" in result.stdout
    assert "success" in result.stdout
    assert "skipped_not_eligible" in result.stdout


def test_r_observed_table_one_from_paper_dir_includes_processing_status_provenance(tmp_path) -> None:
    """The observed-table helper should carry processing status into provenance and print failed status."""
    if not _r_dependencies_available():
        return

    paper_dir = tmp_path / "observed" / "papers" / "paper"
    _write_sample_paper_outputs(paper_dir, include_variable_review=False, include_processing_status=True)
    _write_json(
        paper_dir / "table_processing_status.json",
        [
            _make_processing_status(
                "tbl-1",
                status="failed",
                failure_stage="parsed_table",
                failure_reason="no_values_after_parse",
                notes=["parse_failed:no_values_after_parse"],
            )
        ],
    )

    result = subprocess.run(
        [
            "Rscript",
            "-e",
                (
                    f'source("{R_JSON_IO_SCRIPT}"); '
                    f'source("{R_OBSERVED_SCRIPT}"); '
                    f'x <- build_observed_table_one_from_paper_dir("{paper_dir}", table_number = 1L); '
                    'print(x); '
                    'cat(x$provenance$table_number, "\\n"); '
                    'cat(x$provenance$processing_status, "\\n"); '
                'cat(x$provenance$failure_stage, "\\n"); '
                'cat(x$provenance$failure_reason, "\\n")'
            ),
        ],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "processing status: failed" in result.stdout
    assert "\n1 \n" in result.stdout
    assert "failure_stage: parsed_table" in result.stdout
    assert "failure_reason: no_values_after_parse" in result.stdout
