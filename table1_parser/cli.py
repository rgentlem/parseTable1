"""Command-line interface for the Table 1 parser."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from table1_parser.cell_text_annotations import (
    build_cell_text_annotation_tables_from_pdf,
    cell_text_annotation_tables_to_payload,
)
from table1_parser.column_header_schema import build_column_header_schemas, column_header_schemas_to_payload
from table1_parser.config import Settings
from table1_parser.continued_variable_integration import (
    build_continued_variable_integrations,
    continued_variable_integrations_to_payload,
)
from table1_parser.context import (
    annotate_visual_reference_checks,
    build_paper_visual_inventory,
    build_table_contexts,
    build_paper_variable_inventory,
    collect_paper_visual_references,
    extract_paper_markdown,
    paper_variable_inventory_to_payload,
    paper_sections_to_payload,
    parse_markdown_sections,
)
from table1_parser.diagnostics import ParseQualityReport, build_parse_quality_report
from table1_parser.extract import build_extractor
from table1_parser.heuristics.column_role_detector import detect_column_roles
from table1_parser.heuristics.paper_table_inventory import build_paper_table_inventory, paper_table_inventory_to_payload
from table1_parser.heuristics.row_classifier import classify_rows
from table1_parser.heuristics.table_definition_builder import build_table_definitions, table_definitions_to_payload
from table1_parser.heuristics.table_profile import build_table_profiles, table_profiles_to_payload
from table1_parser.heuristics.variable_grouper import group_variable_blocks
from table1_parser.llm import LLMConfigurationError, build_llm_client
from table1_parser.llm.variable_plausibility_parser import LLMVariablePlausibilityTableReviewParser
from table1_parser.normalize import normalize_extracted_tables, normalized_tables_to_payload, write_normalized_tables
from table1_parser.parse import build_parsed_tables, parsed_tables_to_payload
from table1_parser.paper_footnotes import (
    build_paper_footnote_anchor_inventory,
    build_paper_footnote_definition_candidates,
    build_paper_footnote_definition_lines_from_pdf,
    filter_footnote_definition_lines_for_page_furniture,
    link_paper_footnotes,
    paper_footnotes_to_payload,
)
from table1_parser.paper_page_furniture import build_paper_page_furniture, paper_page_furniture_to_payload
from table1_parser.processing_status import build_table_processing_statuses
from table1_parser.schemas import (
    CellTextAnnotationTable,
    ColumnHeaderSchema,
    ExtractedTable,
    LLMVariablePlausibilityCallRecord,
    LLMVariablePlausibilityMonitoringReport,
    NormalizedTable,
    PaperFootnotes,
    PaperPageFurniture,
    PaperSection,
    PaperVariableInventory,
    PaperVisual,
    PaperVisualReference,
    ParsedTable,
    TableContext,
    TableDefinition,
    Table1ContinuationGroup,
    TableProfile,
)
from table1_parser.table_continuation_columns import (
    build_table_continuation_column_checks,
    table_continuation_column_checks_to_payload,
)
from table1_parser.table1_continuations import (
    build_table1_continuation_artifacts,
    table1_continuation_groups_to_payload,
)

DEFAULT_OUTPUT_DIR = Path("outputs")


@dataclass(slots=True)
class PaperParseArtifacts:
    """All deterministic parse artifacts for one paper."""

    paper_stem: str
    extracted_tables: list[ExtractedTable]
    normalized_tables: list[NormalizedTable]
    column_header_schemas: list[ColumnHeaderSchema]
    table1_continuation_groups: list[Table1ContinuationGroup]
    merged_table1_tables: list[NormalizedTable]
    table_profiles: list[TableProfile]
    table_definitions: list[TableDefinition]
    continued_variable_integrations: list[TableDefinition]
    parsed_tables: list[ParsedTable]
    parse_quality_reports: list[ParseQualityReport]
    cell_text_annotations: list[CellTextAnnotationTable]
    paper_footnotes: PaperFootnotes
    paper_page_furniture: PaperPageFurniture
    paper_markdown: str
    paper_sections: list[PaperSection]
    paper_visual_inventory: list[PaperVisual]
    paper_variable_inventory: PaperVariableInventory
    paper_references: list[PaperVisualReference]
    table_contexts: list[TableContext]


def build_parser() -> argparse.ArgumentParser:
    """Create the top-level CLI parser."""
    parser = argparse.ArgumentParser(prog="table1-parser")
    subparsers = parser.add_subparsers(dest="command", required=True)

    extract_parser = subparsers.add_parser("extract", help="Extract tables from a PDF.")
    extract_parser.add_argument("pdf_path", help="Path to the source PDF file.")
    extract_parser.add_argument(
        "--outdir",
        default=str(DEFAULT_OUTPUT_DIR),
        help="Root output directory. Defaults to outputs.",
    )
    extract_parser.add_argument(
        "--stdout",
        action="store_true",
        help="Print extracted JSON to stdout instead of writing files.",
    )
    extract_parser.set_defaults(handler=_handle_extract)

    normalize_parser = subparsers.add_parser("normalize", help="Normalize extracted tables from a PDF.")
    normalize_parser.add_argument("pdf_path", help="Path to the source PDF file.")
    normalize_parser.add_argument(
        "--outdir",
        default=str(DEFAULT_OUTPUT_DIR),
        help="Root output directory. Defaults to outputs.",
    )
    normalize_parser.add_argument(
        "--stdout",
        action="store_true",
        help="Print normalized JSON to stdout instead of writing files.",
    )
    normalize_parser.set_defaults(handler=_handle_normalize)

    parse_parser = subparsers.add_parser("parse", help="Parse a Table 1 PDF deterministically.")
    parse_parser.add_argument("pdf_path", help="Path to the source PDF file.")
    parse_parser.add_argument(
        "--outdir",
        default=str(DEFAULT_OUTPUT_DIR),
        help="Root output directory. Defaults to outputs.",
    )
    parse_parser.set_defaults(handler=_handle_parse)

    plausibility_parser = subparsers.add_parser(
        "review-variable-plausibility",
        help="Run optional LLM review of variable label/type plausibility for descriptive tables.",
    )
    plausibility_parser.add_argument("pdf_path", help="Path to the source PDF file.")
    plausibility_parser.add_argument(
        "--outdir",
        default=str(DEFAULT_OUTPUT_DIR),
        help="Root output directory. Defaults to outputs.",
    )
    plausibility_parser.set_defaults(handler=_handle_review_variable_plausibility)

    return parser


def _error_payload(message: str) -> str:
    """Return a consistent JSON error payload for CLI failures."""
    return json.dumps({"tables": [], "error": message}, indent=2)


def _print_stderr(message: str) -> None:
    """Write one diagnostic line to stderr."""
    print(message, file=sys.stderr)


def _validate_pdf_path(pdf_path: str) -> Path | None:
    """Return the PDF path when it exists, otherwise None."""
    path = Path(pdf_path)
    if path.is_file():
        return path
    _print_stderr(_error_payload(f"PDF not found: {pdf_path}"))
    return None


def _build_default_extractor():
    """Create the configured extraction backend for the current CLI run."""
    settings = Settings()
    return build_extractor(settings.default_extraction_backend)


def _extract_payload(tables: list[ExtractedTable]) -> list[dict[str, object]]:
    """Serialize extracted tables as JSON-ready dictionaries."""
    return [table.model_dump(mode="json") for table in tables]


def _handle_extract(args: argparse.Namespace) -> int:
    """Run extraction and serialize the extracted output."""
    if _validate_pdf_path(args.pdf_path) is None:
        return 1

    extractor = _build_default_extractor()

    try:
        tables = extractor.extract(args.pdf_path)
    except Exception as exc:
        _print_stderr(_error_payload(str(exc)))
        return 1

    payload = _extract_payload(tables)
    if args.stdout:
        print(json.dumps(payload, indent=2))
        return 0

    output_path = _extract_output_path(args.pdf_path, args.outdir)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return 0


def _handle_normalize(args: argparse.Namespace) -> int:
    """Extract and normalize tables from a PDF, then serialize the normalized output."""
    if _validate_pdf_path(args.pdf_path) is None:
        return 1

    try:
        extractor = _build_default_extractor()
        normalized_tables = normalize_extracted_tables(extractor.extract(args.pdf_path))
    except Exception as exc:
        _print_stderr(_error_payload(str(exc)))
        return 1

    payload = normalized_tables_to_payload(normalized_tables)
    if args.stdout:
        print(json.dumps(payload, indent=2))
        return 0

    output_path = _normalize_output_path(args.pdf_path, args.outdir)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    write_normalized_tables(output_path, normalized_tables)
    return 0


def _handle_parse(args: argparse.Namespace) -> int:
    """Run the deterministic parse pipeline once and write all deterministic artifacts."""
    if _validate_pdf_path(args.pdf_path) is None:
        return 1

    try:
        artifacts = _build_paper_parse_artifacts(args.pdf_path)
    except Exception as exc:
        _print_stderr(_error_payload(str(exc)))
        return 1

    table_processing_statuses = build_table_processing_statuses(
        artifacts.extracted_tables,
        artifacts.normalized_tables,
        artifacts.table_profiles,
        artifacts.table_definitions,
        artifacts.parsed_tables,
        artifacts.parse_quality_reports,
    )
    table_definitions, parsed_tables = _annotate_parse_failures(
        artifacts.table_definitions,
        artifacts.parsed_tables,
        table_processing_statuses,
    )
    _write_parse_outputs(
        pdf_path=args.pdf_path,
        outdir=args.outdir,
        artifacts=artifacts,
        table_definitions=table_definitions,
        parsed_tables=parsed_tables,
        table_processing_statuses=table_processing_statuses,
    )
    return 0


def _handle_review_variable_plausibility(args: argparse.Namespace) -> int:
    """Run deterministic parsing plus optional LLM variable-plausibility review."""
    if _validate_pdf_path(args.pdf_path) is None:
        return 1

    try:
        artifacts = _build_paper_parse_artifacts(args.pdf_path)
    except Exception as exc:
        _print_stderr(_error_payload(str(exc)))
        return 1

    table_processing_statuses = build_table_processing_statuses(
        artifacts.extracted_tables,
        artifacts.normalized_tables,
        artifacts.table_profiles,
        artifacts.table_definitions,
        artifacts.parsed_tables,
        artifacts.parse_quality_reports,
    )
    table_definitions, parsed_tables = _annotate_parse_failures(
        artifacts.table_definitions,
        artifacts.parsed_tables,
        table_processing_statuses,
    )
    paper_dir = _write_parse_outputs(
        pdf_path=args.pdf_path,
        outdir=args.outdir,
        artifacts=artifacts,
        table_definitions=table_definitions,
        parsed_tables=parsed_tables,
        table_processing_statuses=table_processing_statuses,
    )

    settings = Settings()
    debug_root = (
        paper_dir / "llm_variable_plausibility_debug" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        if settings.llm_debug
        else None
    )
    reviews = []
    monitoring_items: list[LLMVariablePlausibilityCallRecord] = []
    eligible_items: list[tuple[int, TableProfile, TableDefinition]] = []

    for table_index, (profile, definition) in enumerate(zip(artifacts.table_profiles, table_definitions, strict=True)):
        if profile.table_family == "descriptive_characteristics":
            eligible_items.append((table_index, profile, definition))
        else:
            monitoring_items.append(
                _skipped_variable_plausibility_monitoring_record(
                    table_index=table_index,
                    profile=profile,
                    definition=definition,
                    eligible_for_review=False,
                    status="skipped_not_eligible",
                )
            )

    if eligible_items:
        try:
            client = build_llm_client(settings=settings)
        except LLMConfigurationError as exc:
            monitoring_items.extend(
                _skipped_variable_plausibility_monitoring_record(
                    table_index=table_index,
                    profile=profile,
                    definition=definition,
                    eligible_for_review=True,
                    status="skipped_configuration_error",
                    error_message=str(exc),
                )
                for table_index, profile, definition in eligible_items
            )
            _print_stderr(f"Variable-plausibility LLM review skipped: {exc}")
        else:
            parser = LLMVariablePlausibilityTableReviewParser(client)
            for table_index, profile, definition in eligible_items:
                trace_dir = debug_root / f"table_{table_index}" if debug_root is not None else None
                attempt = parser.review_with_monitoring(
                    definition,
                    table_index=table_index,
                    table_family=profile.table_family,
                    trace_dir=trace_dir,
                )
                monitoring_items.append(attempt.monitoring)
                if attempt.result is not None:
                    reviews.append(attempt.result)
                if attempt.error is not None:
                    _print_stderr(
                        f"Variable-plausibility LLM review skipped for table_index={table_index} "
                        f"(table_id={definition.table_id}): {attempt.error}"
                    )

    review_output_path = paper_dir / "table_variable_plausibility_llm.json"
    review_output_path.write_text(
        json.dumps([review.model_dump(mode="json") for review in reviews], indent=2) + "\n",
        encoding="utf-8",
    )

    if settings.llm_debug and debug_root is not None:
        monitoring_output_path = debug_root / "llm_variable_plausibility_monitoring.json"
        monitoring_output_path.parent.mkdir(parents=True, exist_ok=True)
        monitoring_output_path.write_text(
            json.dumps(
                LLMVariablePlausibilityMonitoringReport(
                    report_timestamp=_utc_timestamp(),
                    provider=settings.llm_provider,
                    model=settings.active_llm_model,
                    items=monitoring_items,
                ).model_dump(mode="json", exclude_none=True),
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    return 0


def _build_paper_parse_artifacts(pdf_path: str) -> PaperParseArtifacts:
    """Run the deterministic parse pipeline and build the paper-level context artifacts."""
    extractor = _build_default_extractor()
    extracted_tables = extractor.extract(pdf_path)
    cell_text_annotations = build_cell_text_annotation_tables_from_pdf(pdf_path, extracted_tables)
    paper_page_furniture = build_paper_page_furniture(pdf_path, paper_id=Path(pdf_path).stem)
    normalized_tables = normalize_extracted_tables(extracted_tables)
    column_header_schemas = build_column_header_schemas(normalized_tables, extracted_tables)
    paper_footnotes = build_paper_footnote_anchor_inventory(
        paper_id=Path(pdf_path).stem,
        source_pdf=pdf_path,
        cell_text_annotations=cell_text_annotations,
        extracted_tables=extracted_tables,
        column_header_schemas=column_header_schemas,
        paper_page_furniture=paper_page_furniture,
    )
    paper_footnote_definition_lines = build_paper_footnote_definition_lines_from_pdf(pdf_path)
    filtered_footnote_definition_lines, footnote_page_furniture_metadata = (
        filter_footnote_definition_lines_for_page_furniture(
            paper_footnote_definition_lines,
            paper_page_furniture,
        )
    )
    paper_footnote_definitions = build_paper_footnote_definition_candidates(
        filtered_footnote_definition_lines,
        extracted_tables,
    )
    paper_footnotes = link_paper_footnotes(
        paper_footnotes.model_copy(
            update={
                "definitions": paper_footnote_definitions,
                "metadata": {
                    **paper_footnotes.metadata,
                    "source_artifacts": sorted(
                        {
                            *paper_footnotes.metadata.get("source_artifacts", []),
                            "pymupdf_page_text_lines",
                            "paper_page_furniture.json",
                        }
                    ),
                    **footnote_page_furniture_metadata,
                    "definition_line_count": len(paper_footnote_definition_lines),
                    "definition_line_count_after_page_furniture": len(filtered_footnote_definition_lines),
                    "definition_count": len(paper_footnote_definitions),
                    "definitions_status": "built",
                },
            }
        )
    )
    table_profiles = build_table_profiles(normalized_tables)
    table1_continuation_groups, merged_table1_tables = build_table1_continuation_artifacts(
        normalized_tables,
        column_header_schemas,
    )
    parse_quality_reports = []
    for table_index, table in enumerate(normalized_tables):
        row_classifications = classify_rows(table)
        variable_blocks = group_variable_blocks(table, classifications=row_classifications)
        column_roles = detect_column_roles(table)
        parse_quality_reports.append(
            build_parse_quality_report(
                table,
                row_classifications,
                variable_blocks,
                column_roles,
                extracted_table=extracted_tables[table_index] if table_index < len(extracted_tables) else None,
                source_identifier=pdf_path,
            )
        )
    table_definitions = build_table_definitions(normalized_tables, column_header_schemas)
    continued_variable_integrations = build_continued_variable_integrations(
        normalized_tables,
        table_definitions,
        table1_continuation_groups,
    )
    parsed_tables = build_parsed_tables(normalized_tables, table_definitions)
    paper_markdown = extract_paper_markdown(pdf_path)
    paper_sections = parse_markdown_sections(paper_markdown)
    paper_stem = Path(pdf_path).stem
    paper_visual_inventory = build_paper_visual_inventory(extracted_tables, table_definitions, paper_sections)
    paper_references = collect_paper_visual_references(paper_sections, paper_visual_inventory)
    paper_visual_inventory = annotate_visual_reference_checks(paper_visual_inventory, paper_references)
    paper_variable_inventory = build_paper_variable_inventory(paper_stem, paper_sections, table_definitions)
    table_contexts = build_table_contexts(paper_sections, table_definitions, paper_visual_inventory, paper_references)
    return PaperParseArtifacts(
        paper_stem=paper_stem,
        extracted_tables=extracted_tables,
        normalized_tables=normalized_tables,
        column_header_schemas=column_header_schemas,
        table1_continuation_groups=table1_continuation_groups,
        merged_table1_tables=merged_table1_tables,
        table_profiles=table_profiles,
        table_definitions=table_definitions,
        continued_variable_integrations=continued_variable_integrations,
        parsed_tables=parsed_tables,
        parse_quality_reports=parse_quality_reports,
        cell_text_annotations=cell_text_annotations,
        paper_footnotes=paper_footnotes,
        paper_page_furniture=paper_page_furniture,
        paper_markdown=paper_markdown,
        paper_sections=paper_sections,
        paper_visual_inventory=paper_visual_inventory,
        paper_references=paper_references,
        paper_variable_inventory=paper_variable_inventory,
        table_contexts=table_contexts,
    )


def _annotate_parse_failures(
    table_definitions: list[TableDefinition],
    parsed_tables: list[ParsedTable],
    table_processing_statuses: list[object],
) -> tuple[list[TableDefinition], list[ParsedTable]]:
    """Attach parse-failure notes to deterministic table definitions and parsed tables."""
    status_by_table_id = {status.table_id: status for status in table_processing_statuses}
    annotated_table_definitions = [
        definition.model_copy(
            update={
                "notes": (
                    [*definition.notes, f"parse_failed:{status_by_table_id[definition.table_id].failure_reason}"]
                    if status_by_table_id[definition.table_id].status == "failed"
                    and f"parse_failed:{status_by_table_id[definition.table_id].failure_reason}" not in definition.notes
                    else definition.notes
                )
            }
        )
        for definition in table_definitions
    ]
    annotated_parsed_tables = [
        parsed_table.model_copy(
            update={
                "notes": (
                    [*parsed_table.notes, f"parse_failed:{status_by_table_id[parsed_table.table_id].failure_reason}"]
                    if status_by_table_id[parsed_table.table_id].status == "failed"
                    and f"parse_failed:{status_by_table_id[parsed_table.table_id].failure_reason}" not in parsed_table.notes
                    else parsed_table.notes
                )
            }
        )
        for parsed_table in parsed_tables
    ]
    return annotated_table_definitions, annotated_parsed_tables


def _write_parse_outputs(
    *,
    pdf_path: str,
    outdir: str,
    artifacts: PaperParseArtifacts,
    table_definitions: list[TableDefinition],
    parsed_tables: list[ParsedTable],
    table_processing_statuses: list[object],
) -> Path:
    """Write the deterministic paper-level parse artifacts and return the paper directory."""
    paper_dir = _paper_output_dir(pdf_path, outdir)
    extract_output_path = paper_dir / "extracted_tables.json"
    normalize_output_path = paper_dir / "normalized_tables.json"
    column_header_schema_output_path = paper_dir / "column_header_schemas.json"
    table1_continuation_groups_output_path = paper_dir / "table1_continuation_groups.json"
    table_continuation_column_checks_output_path = paper_dir / "table_continuation_column_checks.json"
    merged_table1_output_path = paper_dir / "merged_table1_tables.json"
    table_profile_output_path = paper_dir / "table_profiles.json"
    table_definition_output_path = paper_dir / "table_definitions.json"
    continued_variable_integration_output_path = paper_dir / "continued_variable_integrations.json"
    parsed_output_path = paper_dir / "parsed_tables.json"
    processing_status_output_path = paper_dir / "table_processing_status.json"
    parse_quality_reports_output_path = paper_dir / "parse_quality_reports.json"
    cell_text_annotations_output_path = paper_dir / "cell_text_annotations.json"
    paper_footnotes_output_path = paper_dir / "paper_footnotes.json"
    paper_page_furniture_output_path = paper_dir / "paper_page_furniture.json"
    paper_markdown_output_path = paper_dir / "paper_markdown.md"
    paper_sections_output_path = paper_dir / "paper_sections.json"
    paper_visual_inventory_output_path = paper_dir / "paper_visual_inventory.json"
    paper_references_output_path = paper_dir / "paper_references.json"
    paper_variable_inventory_output_path = paper_dir / "paper_variable_inventory.json"
    paper_table_inventory_output_path = paper_dir / "paper_table_inventory.json"
    table_context_output_dir = paper_dir / "table_contexts"

    paper_dir.mkdir(parents=True, exist_ok=True)
    table_context_output_dir.mkdir(parents=True, exist_ok=True)
    paper_table_inventory = build_paper_table_inventory(
        artifacts.paper_stem,
        artifacts.extracted_tables,
        artifacts.normalized_tables,
        artifacts.table_profiles,
        table_definitions,
        parsed_tables,
        artifacts.parse_quality_reports,
        table_processing_statuses,
    )
    table_continuation_column_checks = build_table_continuation_column_checks(
        artifacts.normalized_tables,
        artifacts.extracted_tables,
        artifacts.table_profiles,
        [record.table_category for record in paper_table_inventory.tables],
        artifacts.column_header_schemas,
    )

    extract_output_path.write_text(
        json.dumps(_extract_payload(artifacts.extracted_tables), indent=2),
        encoding="utf-8",
    )
    write_normalized_tables(normalize_output_path, artifacts.normalized_tables)
    column_header_schema_output_path.write_text(
        json.dumps(column_header_schemas_to_payload(artifacts.column_header_schemas), indent=2) + "\n",
        encoding="utf-8",
    )
    table1_continuation_groups_output_path.write_text(
        json.dumps(table1_continuation_groups_to_payload(artifacts.table1_continuation_groups), indent=2) + "\n",
        encoding="utf-8",
    )
    table_continuation_column_checks_output_path.write_text(
        json.dumps(
            table_continuation_column_checks_to_payload(table_continuation_column_checks),
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    write_normalized_tables(merged_table1_output_path, artifacts.merged_table1_tables)
    table_profile_output_path.write_text(
        json.dumps(table_profiles_to_payload(artifacts.table_profiles), indent=2) + "\n",
        encoding="utf-8",
    )
    table_definition_output_path.write_text(
        json.dumps(table_definitions_to_payload(table_definitions), indent=2) + "\n",
        encoding="utf-8",
    )
    continued_variable_integration_output_path.write_text(
        json.dumps(
            continued_variable_integrations_to_payload(artifacts.continued_variable_integrations),
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    parsed_output_path.write_text(
        json.dumps(parsed_tables_to_payload(parsed_tables), indent=2) + "\n",
        encoding="utf-8",
    )
    processing_status_output_path.write_text(
        json.dumps([status.model_dump(mode="json") for status in table_processing_statuses], indent=2) + "\n",
        encoding="utf-8",
    )
    paper_table_inventory_output_path.write_text(
        json.dumps(paper_table_inventory_to_payload(paper_table_inventory), indent=2) + "\n",
        encoding="utf-8",
    )
    parse_quality_reports_output_path.write_text(
        json.dumps([report.model_dump(mode="json") for report in artifacts.parse_quality_reports], indent=2) + "\n",
        encoding="utf-8",
    )
    cell_text_annotations_output_path.write_text(
        json.dumps(cell_text_annotation_tables_to_payload(artifacts.cell_text_annotations), indent=2) + "\n",
        encoding="utf-8",
    )
    paper_footnotes_output_path.write_text(
        json.dumps(paper_footnotes_to_payload(artifacts.paper_footnotes), indent=2) + "\n",
        encoding="utf-8",
    )
    paper_page_furniture_output_path.write_text(
        json.dumps(paper_page_furniture_to_payload(artifacts.paper_page_furniture), indent=2) + "\n",
        encoding="utf-8",
    )
    paper_markdown_output_path.write_text(artifacts.paper_markdown, encoding="utf-8")
    paper_sections_output_path.write_text(
        json.dumps(paper_sections_to_payload(artifacts.paper_sections), indent=2) + "\n",
        encoding="utf-8",
    )
    paper_visual_inventory_output_path.write_text(
        json.dumps([visual.model_dump(mode="json") for visual in artifacts.paper_visual_inventory], indent=2) + "\n",
        encoding="utf-8",
    )
    paper_references_output_path.write_text(
        json.dumps([reference.model_dump(mode="json") for reference in artifacts.paper_references], indent=2) + "\n",
        encoding="utf-8",
    )
    paper_variable_inventory_output_path.write_text(
        json.dumps(paper_variable_inventory_to_payload(artifacts.paper_variable_inventory), indent=2) + "\n",
        encoding="utf-8",
    )
    for table_context in artifacts.table_contexts:
        (table_context_output_dir / f"table_{table_context.table_index}_context.json").write_text(
            json.dumps(table_context.model_dump(mode="json"), indent=2) + "\n",
            encoding="utf-8",
        )
    return paper_dir


def _paper_output_dir(pdf_path: str, outdir: str) -> Path:
    """Return the per-paper output directory."""
    return Path(outdir) / "papers" / Path(pdf_path).stem


def _extract_output_path(pdf_path: str, outdir: str) -> Path:
    """Return the default extracted-table JSON path for one paper."""
    return _paper_output_dir(pdf_path, outdir) / "extracted_tables.json"


def _normalize_output_path(pdf_path: str, outdir: str) -> Path:
    """Return the default normalized-table JSON path for one paper."""
    return _paper_output_dir(pdf_path, outdir) / "normalized_tables.json"


def _skipped_variable_plausibility_monitoring_record(
    *,
    table_index: int,
    profile: TableProfile,
    definition: TableDefinition,
    eligible_for_review: bool,
    status: str,
    error_message: str | None = None,
) -> LLMVariablePlausibilityCallRecord:
    """Build one monitoring record for a table that never reached the provider call."""
    continuous_variable_count = sum(variable.variable_type == "continuous" for variable in definition.variables)
    categorical_variable_count = sum(variable.variable_type == "categorical" for variable in definition.variables)
    binary_variable_count = sum(variable.variable_type == "binary" for variable in definition.variables)
    attached_level_count = sum(len(variable.levels) for variable in definition.variables)
    return LLMVariablePlausibilityCallRecord(
        table_id=definition.table_id,
        table_index=table_index,
        table_family=profile.table_family,
        eligible_for_review=eligible_for_review,
        status=status,
        deterministic_variable_count=len(definition.variables),
        continuous_variable_count=continuous_variable_count,
        categorical_variable_count=categorical_variable_count,
        binary_variable_count=binary_variable_count,
        attached_level_count=attached_level_count,
        error_message=error_message,
    )


def _utc_timestamp() -> str:
    """Return a compact UTC ISO 8601 timestamp with trailing Z."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI entry point."""
    parser = build_parser()
    args = parser.parse_args(argv)
    handler = getattr(args, "handler")
    return handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
