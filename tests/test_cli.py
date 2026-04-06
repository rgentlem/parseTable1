"""CLI tests for the command-line interface."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from table1_parser import cli
from table1_parser.llm.client import LLMConfigurationError
from table1_parser.llm.semantic_schemas import LLMSemanticTableDefinition
from table1_parser.schemas import LLMSemanticCallRecord, PaperSection, TableContext
from table1_parser.schemas import ExtractedTable, TableCell


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


def test_cli_extract_stub_prints_not_implemented(capsys) -> None:
    """The extract command should fail gracefully on a missing PDF."""
    exit_code = cli.main(["extract", "paper.pdf"])

    captured = capsys.readouterr()

    assert exit_code == 1
    assert "error" in captured.err


def test_cli_parse_writes_available_stage_outputs_in_one_pass(tmp_path, monkeypatch, capsys) -> None:
    """The parse command should write available stage outputs from one extraction pass."""
    monkeypatch.chdir(tmp_path)
    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_text("placeholder")
    calls = {"extract": 0}

    class FakeExtractor:
        def extract(self, _: str) -> list[ExtractedTable]:
            calls["extract"] += 1
            return [_build_extracted_table()]

    monkeypatch.setattr(cli, "build_extractor", lambda _: FakeExtractor())
    monkeypatch.setattr(cli, "extract_paper_markdown", lambda _: "# Methods\nExample study population.")
    monkeypatch.setattr(
        cli,
        "parse_markdown_sections",
        lambda _: [PaperSection(section_id="section_0", order=0, heading="Methods", level=1, role_hint="methods_like", content="Example study population.")],
    )
    monkeypatch.setattr(
        cli,
        "build_table_contexts",
        lambda sections, definitions: [
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

    exit_code = cli.main(["parse", str(pdf_path), "--no-llm-semantic"])

    captured = capsys.readouterr()
    extracted_path = tmp_path / "outputs" / "papers" / "paper" / "extracted_tables.json"
    normalized_path = tmp_path / "outputs" / "papers" / "paper" / "normalized_tables.json"
    table_profile_path = tmp_path / "outputs" / "papers" / "paper" / "table_profiles.json"
    table_definition_path = tmp_path / "outputs" / "papers" / "paper" / "table_definitions.json"
    parsed_path = tmp_path / "outputs" / "papers" / "paper" / "parsed_tables.json"
    paper_markdown_path = tmp_path / "outputs" / "papers" / "paper" / "paper_markdown.md"
    paper_sections_path = tmp_path / "outputs" / "papers" / "paper" / "paper_sections.json"
    paper_variable_inventory_path = tmp_path / "outputs" / "papers" / "paper" / "paper_variable_inventory.json"
    table_context_path = tmp_path / "outputs" / "papers" / "paper" / "table_contexts" / "table_0_context.json"

    assert exit_code == 0
    assert calls["extract"] == 1
    assert extracted_path.exists()
    assert normalized_path.exists()
    assert table_profile_path.exists()
    assert table_definition_path.exists()
    assert parsed_path.exists()
    assert paper_markdown_path.exists()
    assert paper_sections_path.exists()
    assert paper_variable_inventory_path.exists()
    assert table_context_path.exists()
    assert json.loads(extracted_path.read_text(encoding="utf-8"))[0]["table_id"] == "tbl-1"
    assert json.loads(normalized_path.read_text(encoding="utf-8"))[0]["table_id"] == "tbl-1"
    assert json.loads(table_profile_path.read_text(encoding="utf-8"))[0]["table_id"] == "tbl-1"
    assert json.loads(table_definition_path.read_text(encoding="utf-8"))[0]["table_id"] == "tbl-1"
    assert json.loads(parsed_path.read_text(encoding="utf-8"))[0]["table_id"] == "tbl-1"
    assert paper_markdown_path.read_text(encoding="utf-8") == "# Methods\nExample study population."
    assert json.loads(paper_sections_path.read_text(encoding="utf-8"))[0]["section_id"] == "section_0"
    assert json.loads(paper_variable_inventory_path.read_text(encoding="utf-8"))["paper_id"] == "paper"
    assert json.loads(table_context_path.read_text(encoding="utf-8"))["table_id"] == "tbl-1"
    assert captured.out == ""
    assert "LLM semantic interpretation skipped:" not in captured.err


def test_cli_parse_writes_semantic_llm_output_when_available(tmp_path, monkeypatch, capsys) -> None:
    """The parse command should write semantic LLM table definitions when configuration is available."""
    monkeypatch.chdir(tmp_path)
    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_text("placeholder")

    class FakeExtractor:
        def extract(self, _: str) -> list[ExtractedTable]:
            return [_build_extracted_table()]

    class FakeSemanticParser:
        def __init__(self, client: object) -> None:
            self.client = client

        def parse_with_monitoring(self, table: object, definition: object, context: object, *, trace_dir=None) -> object:
            result = LLMSemanticTableDefinition(
                table_id=definition.table_id,
                variables=[],
                notes=["semantic"],
                overall_confidence=0.9,
            )
            return SimpleNamespace(
                result=result,
                error=None,
                monitoring=LLMSemanticCallRecord(
                    table_id=definition.table_id,
                    table_index=context.table_index,
                    should_run_llm_semantics=True,
                    status="success",
                    elapsed_seconds=0.25,
                    trace_dir=str(trace_dir) if trace_dir is not None else None,
                    prompt_char_count=100,
                ),
            )

    monkeypatch.setattr(cli, "build_extractor", lambda _: FakeExtractor())
    monkeypatch.setattr(cli, "extract_paper_markdown", lambda _: "# Methods\nExample study population.")
    monkeypatch.setattr(
        cli,
        "parse_markdown_sections",
        lambda _: [PaperSection(section_id="section_0", order=0, heading="Methods", level=1, role_hint="methods_like", content="Example study population.")],
    )
    monkeypatch.setattr(
        cli,
        "build_table_contexts",
        lambda sections, definitions: [
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
    monkeypatch.setattr(cli, "build_llm_client", lambda settings=None: object())
    monkeypatch.setattr(cli, "LLMSemanticTableDefinitionParser", FakeSemanticParser)

    exit_code = cli.main(["parse", str(pdf_path)])

    captured = capsys.readouterr()
    llm_path = tmp_path / "outputs" / "papers" / "paper" / "table_definitions_llm.json"

    assert exit_code == 0
    assert llm_path.exists()
    assert json.loads(llm_path.read_text(encoding="utf-8"))[0]["table_id"] == "tbl-1"
    assert captured.out == ""


def test_cli_parse_warns_and_skips_semantic_llm_when_configuration_is_missing(tmp_path, monkeypatch, capsys) -> None:
    """The parse command should warn and continue when semantic LLM config is unavailable."""
    monkeypatch.chdir(tmp_path)
    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_text("placeholder")

    class FakeExtractor:
        def extract(self, _: str) -> list[ExtractedTable]:
            return [_build_extracted_table()]

    monkeypatch.setattr(cli, "build_extractor", lambda _: FakeExtractor())
    monkeypatch.setattr(cli, "extract_paper_markdown", lambda _: "# Methods\nExample study population.")
    monkeypatch.setattr(
        cli,
        "parse_markdown_sections",
        lambda _: [PaperSection(section_id="section_0", order=0, heading="Methods", level=1, role_hint="methods_like", content="Example study population.")],
    )
    monkeypatch.setattr(
        cli,
        "build_table_contexts",
        lambda sections, definitions: [
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
    monkeypatch.setattr(
        cli,
        "build_llm_client",
        lambda settings=None: (_ for _ in ()).throw(LLMConfigurationError("OPENAI_API_KEY is required when LLM_PROVIDER=openai.")),
    )

    exit_code = cli.main(["parse", str(pdf_path)])

    captured = capsys.readouterr()
    llm_path = tmp_path / "outputs" / "papers" / "paper" / "table_definitions_llm.json"
    table_definition_path = tmp_path / "outputs" / "papers" / "paper" / "table_definitions.json"

    assert exit_code == 0
    assert table_definition_path.exists()
    assert not llm_path.exists()
    assert captured.out == ""
    assert "LLM semantic interpretation skipped:" in captured.err
    assert "Use --no-llm-semantic to suppress this warning." in captured.err


def test_cli_parse_skips_semantic_llm_for_estimate_result_tables(tmp_path, monkeypatch, capsys) -> None:
    """Estimate-result tables should route away from semantic LLM even when configuration exists."""
    monkeypatch.chdir(tmp_path)
    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_text("placeholder")
    parse_calls = {"count": 0}

    estimate_table = ExtractedTable(
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

    class FakeExtractor:
        def extract(self, _: str) -> list[ExtractedTable]:
            return [estimate_table]

    class FakeSemanticParser:
        def __init__(self, client: object) -> None:
            self.client = client

        def parse_with_monitoring(self, table: object, definition: object, context: object, *, trace_dir=None) -> object:
            parse_calls["count"] += 1
            return SimpleNamespace(
                result=LLMSemanticTableDefinition(
                    table_id=definition.table_id,
                    variables=[],
                    notes=["semantic"],
                    overall_confidence=0.9,
                ),
                error=None,
                monitoring=LLMSemanticCallRecord(
                    table_id=definition.table_id,
                    table_index=context.table_index,
                    should_run_llm_semantics=True,
                    status="success",
                    elapsed_seconds=0.25,
                    trace_dir=str(trace_dir) if trace_dir is not None else None,
                    prompt_char_count=100,
                ),
            )

    monkeypatch.setattr(cli, "build_extractor", lambda _: FakeExtractor())
    monkeypatch.setattr(cli, "extract_paper_markdown", lambda _: "# Methods\nExample study population.")
    monkeypatch.setattr(
        cli,
        "parse_markdown_sections",
        lambda _: [PaperSection(section_id="section_0", order=0, heading="Methods", level=1, role_hint="methods_like", content="Example study population.")],
    )
    monkeypatch.setattr(
        cli,
        "build_table_contexts",
        lambda sections, definitions: [
            TableContext(
                table_id=definitions[0].table_id,
                table_index=0,
                table_label="Table 3",
                title=definitions[0].title,
                caption=definitions[0].caption,
                methods_like_section_ids=[sections[0].section_id],
            )
        ],
    )
    monkeypatch.setattr(cli, "build_llm_client", lambda settings=None: object())
    monkeypatch.setattr(cli, "LLMSemanticTableDefinitionParser", FakeSemanticParser)

    exit_code = cli.main(["parse", str(pdf_path)])

    captured = capsys.readouterr()
    llm_path = tmp_path / "outputs" / "papers" / "paper" / "table_definitions_llm.json"
    profile_path = tmp_path / "outputs" / "papers" / "paper" / "table_profiles.json"

    assert exit_code == 0
    assert parse_calls["count"] == 0
    assert llm_path.exists() is False
    assert json.loads(profile_path.read_text(encoding="utf-8"))[0]["table_family"] == "estimate_results"
    assert captured.out == ""


def test_cli_parse_writes_semantic_debug_monitoring_when_llm_debug_enabled(tmp_path, monkeypatch, capsys) -> None:
    """Semantic debug artifacts should be written only when LLM_DEBUG is enabled."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("LLM_DEBUG", "true")
    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_text("placeholder")

    class FakeExtractor:
        def extract(self, _: str) -> list[ExtractedTable]:
            return [_build_extracted_table()]

    class FakeSemanticParser:
        def __init__(self, client: object) -> None:
            self.client = client

        def parse_with_monitoring(self, table: object, definition: object, context: object, *, trace_dir=None) -> object:
            if trace_dir is not None:
                trace_path = Path(trace_dir)
                trace_path.mkdir(parents=True, exist_ok=True)
                (trace_path / "table_definition_llm_input.json").write_text("{}", encoding="utf-8")
                (trace_path / "table_definition_llm_output.json").write_text("{}", encoding="utf-8")
                (trace_path / "table_definition_llm_interpretation.json").write_text("{}", encoding="utf-8")
                (trace_path / "table_definition_llm_metrics.json").write_text("{}", encoding="utf-8")
            return SimpleNamespace(
                result=LLMSemanticTableDefinition(
                    table_id=definition.table_id,
                    variables=[],
                    notes=["semantic"],
                    overall_confidence=0.9,
                ),
                error=None,
                monitoring=LLMSemanticCallRecord(
                    table_id=definition.table_id,
                    table_index=context.table_index,
                    should_run_llm_semantics=True,
                    status="success",
                    elapsed_seconds=0.5,
                    trace_dir=str(trace_dir) if trace_dir is not None else None,
                    prompt_char_count=120,
                    output_column_count=0,
                    output_variable_count=0,
                ),
            )

    monkeypatch.setattr(cli, "build_extractor", lambda _: FakeExtractor())
    monkeypatch.setattr(cli, "extract_paper_markdown", lambda _: "# Methods\nExample study population.")
    monkeypatch.setattr(
        cli,
        "parse_markdown_sections",
        lambda _: [PaperSection(section_id="section_0", order=0, heading="Methods", level=1, role_hint="methods_like", content="Example study population.")],
    )
    monkeypatch.setattr(
        cli,
        "build_table_contexts",
        lambda sections, definitions: [
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
    monkeypatch.setattr(cli, "build_llm_client", lambda settings=None: object())
    monkeypatch.setattr(cli, "LLMSemanticTableDefinitionParser", FakeSemanticParser)

    exit_code = cli.main(["parse", str(pdf_path)])

    captured = capsys.readouterr()
    debug_root = tmp_path / "outputs" / "papers" / "paper" / "llm_semantic_debug"
    monitoring_paths = sorted(debug_root.glob("*/llm_semantic_monitoring.json"))

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
