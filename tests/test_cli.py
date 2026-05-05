"""CLI tests for the command-line interface."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from table1_parser import cli
from table1_parser.llm.client import LLMConfigurationError
from table1_parser.llm.variable_plausibility_schemas import LLMVariablePlausibilityTableReview
from table1_parser.schemas import (
    ColumnDefinition,
    ColumnHeaderSchema,
    DefinedColumn,
    ExtractedTable,
    LLMVariablePlausibilityCallRecord,
    NormalizedTable,
    PaperSection,
    ParsedTable,
    RowView,
    TableCell,
    TableContext,
    TableDefinition,
    TableProfile,
)


def _build_extracted_table() -> ExtractedTable:
    return ExtractedTable(
        table_id="tbl-1",
        source_pdf="paper.pdf",
        page_num=1,
        title="Table 1",
        caption="Baseline characteristics",
        n_rows=3,
        n_cols=3,
        cells=[
            TableCell(row_idx=0, col_idx=0, text="Variable"),
            TableCell(row_idx=0, col_idx=1, text="Overall"),
            TableCell(row_idx=0, col_idx=2, text="P-value"),
            TableCell(row_idx=1, col_idx=0, text="Age, years"),
            TableCell(row_idx=1, col_idx=1, text="52.1"),
            TableCell(row_idx=1, col_idx=2, text="0.03"),
            TableCell(row_idx=2, col_idx=0, text="Male"),
            TableCell(row_idx=2, col_idx=1, text="34"),
            TableCell(row_idx=2, col_idx=2, text="0.10"),
        ],
        extraction_backend="pymupdf4llm",
    )


def _build_estimate_table() -> ExtractedTable:
    return ExtractedTable(
        table_id="tbl-est",
        source_pdf="paper.pdf",
        page_num=1,
        title="Table 3. Adjusted hazard ratios for CKD progression",
        caption="Multivariable regression results",
        n_rows=3,
        n_cols=3,
        cells=[
            TableCell(row_idx=0, col_idx=0, text="Variable"),
            TableCell(row_idx=0, col_idx=1, text="Adjusted HR (95% CI)"),
            TableCell(row_idx=0, col_idx=2, text="P-value"),
            TableCell(row_idx=1, col_idx=0, text="Proteinuria"),
            TableCell(row_idx=1, col_idx=1, text="1.42 (1.10, 1.83)"),
            TableCell(row_idx=1, col_idx=2, text="<0.001"),
            TableCell(row_idx=2, col_idx=0, text="eGFR"),
            TableCell(row_idx=2, col_idx=1, text="0.78 (0.65, 0.94)"),
            TableCell(row_idx=2, col_idx=2, text="0.01"),
        ],
        extraction_backend="pymupdf4llm",
    )


def _patch_paper_context(monkeypatch) -> None:
    monkeypatch.setattr(cli, "extract_paper_markdown", lambda _: "# Methods\nExample study population.")
    monkeypatch.setattr(
        cli,
        "parse_markdown_sections",
        lambda _: [
            PaperSection(
                section_id="section_0",
                order=0,
                heading="Methods",
                level=1,
                role_hint="methods_like",
                content="Example study population.",
            )
        ],
    )
    monkeypatch.setattr(
        cli,
        "build_table_contexts",
        lambda sections, definitions, paper_visual_inventory=None, paper_references=None: [
            TableContext(
                table_id=definitions[0].table_id,
                table_index=0,
                table_label="Table 1",
                title=definitions[0].title,
                caption=definitions[0].caption,
                methods_like_section_ids=[sections[0].section_id],
            )
        ],
    )


def test_cli_extract_stub_prints_not_implemented(capsys) -> None:
    """The extract command should fail gracefully on a missing PDF."""
    exit_code = cli.main(["extract", "paper.pdf"])

    captured = capsys.readouterr()

    assert exit_code == 1
    assert "error" in captured.err


def test_cli_parse_writes_available_stage_outputs_in_one_pass(tmp_path, monkeypatch, capsys) -> None:
    """The parse command should write deterministic stage outputs from one extraction pass."""
    monkeypatch.chdir(tmp_path)
    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_text("placeholder")
    calls = {"extract": 0}

    class FakeExtractor:
        def extract(self, _: str) -> list[ExtractedTable]:
            calls["extract"] += 1
            return [_build_extracted_table()]

    monkeypatch.setattr(cli, "build_extractor", lambda _: FakeExtractor())
    _patch_paper_context(monkeypatch)

    exit_code = cli.main(["parse", str(pdf_path)])

    captured = capsys.readouterr()
    extracted_path = tmp_path / "outputs" / "papers" / "paper" / "extracted_tables.json"
    normalized_path = tmp_path / "outputs" / "papers" / "paper" / "normalized_tables.json"
    column_header_schema_path = tmp_path / "outputs" / "papers" / "paper" / "column_header_schemas.json"
    table1_continuation_groups_path = tmp_path / "outputs" / "papers" / "paper" / "table1_continuation_groups.json"
    table_continuation_column_checks_path = (
        tmp_path / "outputs" / "papers" / "paper" / "table_continuation_column_checks.json"
    )
    merged_table1_path = tmp_path / "outputs" / "papers" / "paper" / "merged_table1_tables.json"
    table_profile_path = tmp_path / "outputs" / "papers" / "paper" / "table_profiles.json"
    table_definition_path = tmp_path / "outputs" / "papers" / "paper" / "table_definitions.json"
    continued_variable_integrations_path = (
        tmp_path / "outputs" / "papers" / "paper" / "continued_variable_integrations.json"
    )
    parsed_path = tmp_path / "outputs" / "papers" / "paper" / "parsed_tables.json"
    processing_status_path = tmp_path / "outputs" / "papers" / "paper" / "table_processing_status.json"
    parse_quality_reports_path = tmp_path / "outputs" / "papers" / "paper" / "parse_quality_reports.json"
    paper_markdown_path = tmp_path / "outputs" / "papers" / "paper" / "paper_markdown.md"
    paper_sections_path = tmp_path / "outputs" / "papers" / "paper" / "paper_sections.json"
    paper_visual_inventory_path = tmp_path / "outputs" / "papers" / "paper" / "paper_visual_inventory.json"
    paper_references_path = tmp_path / "outputs" / "papers" / "paper" / "paper_references.json"
    paper_variable_inventory_path = tmp_path / "outputs" / "papers" / "paper" / "paper_variable_inventory.json"
    paper_table_inventory_path = tmp_path / "outputs" / "papers" / "paper" / "paper_table_inventory.json"
    table_context_path = tmp_path / "outputs" / "papers" / "paper" / "table_contexts" / "table_0_context.json"

    assert exit_code == 0
    assert calls["extract"] == 1
    assert extracted_path.exists()
    assert normalized_path.exists()
    assert column_header_schema_path.exists()
    assert table1_continuation_groups_path.exists()
    assert table_continuation_column_checks_path.exists()
    assert merged_table1_path.exists()
    assert table_profile_path.exists()
    assert table_definition_path.exists()
    assert continued_variable_integrations_path.exists()
    assert parsed_path.exists()
    assert processing_status_path.exists()
    assert parse_quality_reports_path.exists()
    assert paper_markdown_path.exists()
    assert paper_sections_path.exists()
    assert paper_visual_inventory_path.exists()
    assert paper_references_path.exists()
    assert paper_variable_inventory_path.exists()
    assert paper_table_inventory_path.exists()
    assert table_context_path.exists()
    assert json.loads(extracted_path.read_text(encoding="utf-8"))[0]["table_id"] == "tbl-1"
    assert json.loads(normalized_path.read_text(encoding="utf-8"))[0]["table_id"] == "tbl-1"
    column_schema_payload = json.loads(column_header_schema_path.read_text(encoding="utf-8"))
    assert ColumnHeaderSchema.model_validate(column_schema_payload[0]).table_id == "tbl-1"
    assert column_schema_payload[0]["leaves"][1]["leaf_label"] == "Overall"
    assert json.loads(table1_continuation_groups_path.read_text(encoding="utf-8")) == []
    assert json.loads(table_continuation_column_checks_path.read_text(encoding="utf-8")) == []
    assert json.loads(merged_table1_path.read_text(encoding="utf-8")) == []
    assert json.loads(table_profile_path.read_text(encoding="utf-8"))[0]["table_id"] == "tbl-1"
    assert json.loads(table_definition_path.read_text(encoding="utf-8"))[0]["table_id"] == "tbl-1"
    assert json.loads(continued_variable_integrations_path.read_text(encoding="utf-8")) == []
    assert json.loads(parsed_path.read_text(encoding="utf-8"))[0]["table_id"] == "tbl-1"
    assert json.loads(processing_status_path.read_text(encoding="utf-8"))[0]["table_id"] == "tbl-1"
    parse_quality_payload = json.loads(parse_quality_reports_path.read_text(encoding="utf-8"))
    assert parse_quality_payload[0]["table_id"] == "tbl-1"
    assert parse_quality_payload[0]["summary"]["total_body_rows"] == 2
    assert "column_diagnostics" in parse_quality_payload[0]
    assert paper_markdown_path.read_text(encoding="utf-8") == "# Methods\nExample study population."
    assert json.loads(paper_sections_path.read_text(encoding="utf-8"))[0]["section_id"] == "section_0"
    visual_payload = json.loads(paper_visual_inventory_path.read_text(encoding="utf-8"))
    assert visual_payload[0]["visual_id"] == "paper_visual:table:1"
    assert visual_payload[0]["reference_check_status"] == "no_text_reference"
    assert json.loads(paper_references_path.read_text(encoding="utf-8")) == []
    assert json.loads(paper_variable_inventory_path.read_text(encoding="utf-8"))["paper_id"] == "paper"
    table_inventory_payload = json.loads(paper_table_inventory_path.read_text(encoding="utf-8"))
    assert table_inventory_payload["paper_id"] == "paper"
    assert table_inventory_payload["tables"][0]["table_id"] == "tbl-1"
    assert table_inventory_payload["tables"][0]["table_category"] == "demographic_description"
    assert json.loads(table_context_path.read_text(encoding="utf-8"))["table_id"] == "tbl-1"
    assert captured.out == ""


def test_cli_parse_marks_descriptive_tables_with_empty_definitions_as_failed(tmp_path, monkeypatch, capsys) -> None:
    """Descriptive tables with zero variables or usable columns should write failed processing status."""
    monkeypatch.chdir(tmp_path)
    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_text("placeholder")

    normalized_table = NormalizedTable(
        table_id="tbl-1",
        title="Table 1",
        caption="Baseline characteristics",
        header_rows=[0],
        body_rows=[1, 2],
        row_views=[
            RowView(
                row_idx=1,
                raw_cells=["Age, years", "52.1"],
                first_cell_raw="Age, years",
                first_cell_normalized="Age years",
                first_cell_alpha_only="Age years",
                nonempty_cell_count=2,
                numeric_cell_count=1,
                has_trailing_values=True,
                indent_level=0,
                likely_role="unknown",
            ),
            RowView(
                row_idx=2,
                raw_cells=["Male", "34"],
                first_cell_raw="Male",
                first_cell_normalized="Male",
                first_cell_alpha_only="Male",
                nonempty_cell_count=2,
                numeric_cell_count=1,
                has_trailing_values=True,
                indent_level=0,
                likely_role="unknown",
            ),
        ],
        n_rows=3,
        n_cols=2,
        metadata={"cleaned_rows": [["Variable", "Overall"], ["Age, years", "52.1"], ["Male", "34"]]},
    )

    class FakeExtractor:
        def extract(self, _: str) -> list[ExtractedTable]:
            return [_build_extracted_table()]

    monkeypatch.setattr(cli, "build_extractor", lambda _: FakeExtractor())
    monkeypatch.setattr(cli, "normalize_extracted_tables", lambda tables: [normalized_table])
    monkeypatch.setattr(
        cli,
        "build_table_profiles",
        lambda tables: [
            TableProfile(
                table_id="tbl-1",
                title="Table 1",
                caption="Baseline characteristics",
                table_family="descriptive_characteristics",
                family_confidence=0.9,
                evidence=["title_or_caption_mentions_characteristics"],
                notes=[],
            )
        ],
    )
    monkeypatch.setattr(
        cli,
        "build_table_definitions",
        lambda tables, column_schemas=None: [
            TableDefinition(
                table_id="tbl-1",
                title="Table 1",
                caption="Baseline characteristics",
                variables=[],
                column_definition=ColumnDefinition(
                    columns=[DefinedColumn(col_idx=1, column_name="overall", column_label="Overall", inferred_role="unknown")]
                ),
                notes=[],
                overall_confidence=None,
            )
        ],
    )
    monkeypatch.setattr(
        cli,
        "build_parsed_tables",
        lambda tables, definitions: [
            ParsedTable(
                table_id="tbl-1",
                title="Table 1",
                caption="Baseline characteristics",
                variables=[],
                columns=[],
                values=[],
                notes=[],
                overall_confidence=None,
            )
        ],
    )
    _patch_paper_context(monkeypatch)

    exit_code = cli.main(["parse", str(pdf_path)])

    captured = capsys.readouterr()
    processing_status_path = tmp_path / "outputs" / "papers" / "paper" / "table_processing_status.json"
    table_definition_path = tmp_path / "outputs" / "papers" / "paper" / "table_definitions.json"
    parsed_path = tmp_path / "outputs" / "papers" / "paper" / "parsed_tables.json"
    processing_status_payload = json.loads(processing_status_path.read_text(encoding="utf-8"))
    table_definition_payload = json.loads(table_definition_path.read_text(encoding="utf-8"))
    parsed_payload = json.loads(parsed_path.read_text(encoding="utf-8"))

    assert exit_code == 0
    assert captured.out == ""
    assert processing_status_payload[0]["status"] == "failed"
    assert processing_status_payload[0]["failure_stage"] == "table_definition"
    assert processing_status_payload[0]["failure_reason"] == "no_variables_for_descriptive_table"
    assert "parse_failed:no_variables_for_descriptive_table" in table_definition_payload[0]["notes"]
    assert "parse_failed:no_variables_for_descriptive_table" in parsed_payload[0]["notes"]


def test_cli_review_variable_plausibility_writes_review_output_when_available(tmp_path, monkeypatch, capsys) -> None:
    """The review command should write the variable-plausibility artifact when configuration is available."""
    monkeypatch.chdir(tmp_path)
    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_text("placeholder")

    class FakeExtractor:
        def extract(self, _: str) -> list[ExtractedTable]:
            return [_build_extracted_table()]

    class FakeReviewParser:
        def __init__(self, client: object) -> None:
            self.client = client

        def review_with_monitoring(self, definition: object, *, table_index: int, table_family: str | None = None, trace_dir=None) -> object:
            result = LLMVariablePlausibilityTableReview(
                table_id=definition.table_id,
                variables=[],
                notes=["review"],
                overall_plausibility=0.9,
            )
            return SimpleNamespace(
                result=result,
                error=None,
                monitoring=LLMVariablePlausibilityCallRecord(
                    table_id=definition.table_id,
                    table_index=table_index,
                    table_family=table_family,
                    eligible_for_review=True,
                    status="success",
                    elapsed_seconds=0.25,
                    trace_dir=str(trace_dir) if trace_dir is not None else None,
                    prompt_char_count=100,
                ),
            )

    monkeypatch.setattr(cli, "build_extractor", lambda _: FakeExtractor())
    _patch_paper_context(monkeypatch)
    monkeypatch.setattr(cli, "build_llm_client", lambda settings=None: object())
    monkeypatch.setattr(cli, "LLMVariablePlausibilityTableReviewParser", FakeReviewParser)

    exit_code = cli.main(["review-variable-plausibility", str(pdf_path)])

    captured = capsys.readouterr()
    review_path = tmp_path / "outputs" / "papers" / "paper" / "table_variable_plausibility_llm.json"

    assert exit_code == 0
    assert review_path.exists()
    assert json.loads(review_path.read_text(encoding="utf-8"))[0]["table_id"] == "tbl-1"
    assert captured.out == ""


def test_cli_review_variable_plausibility_warns_and_writes_empty_review_when_configuration_is_missing(
    tmp_path,
    monkeypatch,
    capsys,
) -> None:
    """The review command should warn and continue when LLM configuration is unavailable."""
    monkeypatch.chdir(tmp_path)
    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_text("placeholder")

    class FakeExtractor:
        def extract(self, _: str) -> list[ExtractedTable]:
            return [_build_extracted_table()]

    monkeypatch.setattr(cli, "build_extractor", lambda _: FakeExtractor())
    _patch_paper_context(monkeypatch)
    monkeypatch.setattr(
        cli,
        "build_llm_client",
        lambda settings=None: (_ for _ in ()).throw(LLMConfigurationError("OPENAI_API_KEY is required when LLM_PROVIDER=openai.")),
    )

    exit_code = cli.main(["review-variable-plausibility", str(pdf_path)])

    captured = capsys.readouterr()
    review_path = tmp_path / "outputs" / "papers" / "paper" / "table_variable_plausibility_llm.json"

    assert exit_code == 0
    assert json.loads(review_path.read_text(encoding="utf-8")) == []
    assert captured.out == ""
    assert "Variable-plausibility LLM review skipped:" in captured.err


def test_cli_review_variable_plausibility_skips_estimate_result_tables(tmp_path, monkeypatch, capsys) -> None:
    """Estimate-result tables should not be sent to the variable-plausibility reviewer."""
    monkeypatch.chdir(tmp_path)
    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_text("placeholder")
    review_calls = {"count": 0}

    class FakeExtractor:
        def extract(self, _: str) -> list[ExtractedTable]:
            return [_build_estimate_table()]

    class FakeReviewParser:
        def __init__(self, client: object) -> None:
            self.client = client

        def review_with_monitoring(self, definition: object, *, table_index: int, table_family: str | None = None, trace_dir=None) -> object:
            review_calls["count"] += 1
            return SimpleNamespace(
                result=None,
                error=None,
                monitoring=LLMVariablePlausibilityCallRecord(
                    table_id=definition.table_id,
                    table_index=table_index,
                    table_family=table_family,
                    eligible_for_review=True,
                    status="success",
                ),
            )

    monkeypatch.setattr(cli, "build_extractor", lambda _: FakeExtractor())
    _patch_paper_context(monkeypatch)
    monkeypatch.setattr(cli, "build_llm_client", lambda settings=None: object())
    monkeypatch.setattr(cli, "LLMVariablePlausibilityTableReviewParser", FakeReviewParser)

    exit_code = cli.main(["review-variable-plausibility", str(pdf_path)])

    captured = capsys.readouterr()
    review_path = tmp_path / "outputs" / "papers" / "paper" / "table_variable_plausibility_llm.json"
    profile_path = tmp_path / "outputs" / "papers" / "paper" / "table_profiles.json"

    assert exit_code == 0
    assert review_calls["count"] == 0
    assert json.loads(review_path.read_text(encoding="utf-8")) == []
    assert json.loads(profile_path.read_text(encoding="utf-8"))[0]["table_family"] == "estimate_results"
    assert captured.out == ""


def test_cli_review_variable_plausibility_writes_debug_monitoring_when_llm_debug_enabled(
    tmp_path,
    monkeypatch,
    capsys,
) -> None:
    """Variable-plausibility debug artifacts should be written only when LLM_DEBUG is enabled."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("LLM_DEBUG", "true")
    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_text("placeholder")

    class FakeExtractor:
        def extract(self, _: str) -> list[ExtractedTable]:
            return [_build_extracted_table()]

    class FakeReviewParser:
        def __init__(self, client: object) -> None:
            self.client = client

        def review_with_monitoring(self, definition: object, *, table_index: int, table_family: str | None = None, trace_dir=None) -> object:
            if trace_dir is not None:
                trace_path = Path(trace_dir)
                trace_path.mkdir(parents=True, exist_ok=True)
                (trace_path / "variable_plausibility_llm_input.json").write_text("{}", encoding="utf-8")
                (trace_path / "variable_plausibility_llm_output.json").write_text("{}", encoding="utf-8")
                (trace_path / "variable_plausibility_llm_review.json").write_text("{}", encoding="utf-8")
                (trace_path / "variable_plausibility_llm_metrics.json").write_text("{}", encoding="utf-8")
            return SimpleNamespace(
                result=LLMVariablePlausibilityTableReview(
                    table_id=definition.table_id,
                    variables=[],
                    notes=["review"],
                    overall_plausibility=0.9,
                ),
                error=None,
                monitoring=LLMVariablePlausibilityCallRecord(
                    table_id=definition.table_id,
                    table_index=table_index,
                    table_family=table_family,
                    eligible_for_review=True,
                    status="success",
                    elapsed_seconds=0.5,
                    trace_dir=str(trace_dir) if trace_dir is not None else None,
                    prompt_char_count=120,
                    output_variable_count=0,
                ),
            )

    monkeypatch.setattr(cli, "build_extractor", lambda _: FakeExtractor())
    _patch_paper_context(monkeypatch)
    monkeypatch.setattr(cli, "build_llm_client", lambda settings=None: object())
    monkeypatch.setattr(cli, "LLMVariablePlausibilityTableReviewParser", FakeReviewParser)

    exit_code = cli.main(["review-variable-plausibility", str(pdf_path)])

    captured = capsys.readouterr()
    debug_root = tmp_path / "outputs" / "papers" / "paper" / "llm_variable_plausibility_debug"
    monitoring_paths = sorted(debug_root.glob("*/llm_variable_plausibility_monitoring.json"))

    assert exit_code == 0
    assert len(monitoring_paths) == 1
    monitoring_payload = json.loads(monitoring_paths[0].read_text(encoding="utf-8"))
    assert monitoring_payload["items"][0]["status"] == "success"
    assert captured.out == ""


def test_cli_extract_writes_default_output_file(tmp_path, monkeypatch, capsys) -> None:
    """The extract command should write JSON under outputs/papers/<paper>/ by default."""
    monkeypatch.chdir(tmp_path)
    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_text("placeholder")

    class FakeExtractor:
        def extract(self, _: str) -> list[object]:
            return []

    monkeypatch.setattr(cli, "build_extractor", lambda _: FakeExtractor())

    exit_code = cli.main(["extract", str(pdf_path)])

    captured = capsys.readouterr()
    output_path = tmp_path / "outputs" / "papers" / "paper" / "extracted_tables.json"
    assert exit_code == 0
    assert captured.out == ""
    assert json.loads(output_path.read_text(encoding="utf-8")) == []


def test_cli_extract_stdout_preserves_json_output(tmp_path, monkeypatch, capsys) -> None:
    """The extract command should still support explicit stdout JSON output."""
    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_text("placeholder")

    class FakeTable:
        def model_dump(self, mode: str = "json") -> dict[str, object]:
            return {"table_id": "tbl-1", "mode": mode}

    class FakeExtractor:
        def extract(self, _: str) -> list[object]:
            return [FakeTable()]

    monkeypatch.setattr(cli, "build_extractor", lambda _: FakeExtractor())

    exit_code = cli.main(["extract", str(pdf_path), "--stdout"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert json.loads(captured.out) == [{"table_id": "tbl-1", "mode": "json"}]


def test_cli_normalize_writes_default_output_file(tmp_path, monkeypatch, capsys) -> None:
    """The normalize command should write JSON under outputs/papers/<paper>/ by default."""
    monkeypatch.chdir(tmp_path)
    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_text("placeholder")

    class FakeExtractor:
        def extract(self, _: str) -> list[ExtractedTable]:
            return [_build_extracted_table()]

    monkeypatch.setattr(cli, "build_extractor", lambda _: FakeExtractor())

    exit_code = cli.main(["normalize", str(pdf_path)])

    captured = capsys.readouterr()
    output_path = tmp_path / "outputs" / "papers" / "paper" / "normalized_tables.json"
    payload = json.loads(output_path.read_text(encoding="utf-8"))

    assert exit_code == 0
    assert captured.out == ""
    assert payload[0]["table_id"] == "tbl-1"
    assert payload[0]["header_rows"] == [0]
    assert payload[0]["body_rows"] == [1, 2]


def test_cli_normalize_stdout_preserves_json_output(tmp_path, monkeypatch, capsys) -> None:
    """The normalize command should support explicit stdout JSON output."""
    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_text("placeholder")

    class FakeExtractor:
        def extract(self, _: str) -> list[ExtractedTable]:
            return [_build_extracted_table()]

    monkeypatch.setattr(cli, "build_extractor", lambda _: FakeExtractor())

    exit_code = cli.main(["normalize", str(pdf_path), "--stdout"])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 0
    assert payload[0]["table_id"] == "tbl-1"
    assert payload[0]["row_views"][0]["first_cell_normalized"] == "Age years"
