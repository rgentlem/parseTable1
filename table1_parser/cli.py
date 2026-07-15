"""Command-line interface for the Table 1 parser."""

from __future__ import annotations

import argparse
import inspect
import json
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from table1_parser.body_occupancy import (
    body_occupancy_tables_to_payload,
    build_body_occupancy_tables,
)
from table1_parser.cell_text_annotations import (
    build_cell_text_annotation_tables_from_pdf,
    cell_text_annotation_tables_to_payload,
)
from table1_parser.extract.canonical_extraction import finalize_canonical_extracted_tables
from table1_parser.column_header_schema import (
    build_column_header_schema,
    build_column_header_schemas,
    column_header_schemas_to_payload,
)
from table1_parser.config import Settings
from table1_parser.continued_variable_integration import (
    build_continued_variable_integrations,
    continued_variable_integrations_to_payload,
)
from table1_parser.context import (
    annotate_visual_reference_checks,
    build_paper_positioned_document,
    build_paper_text_stream,
    build_paper_table_mentions,
    build_paper_visual_inventory,
    build_table_contexts,
    build_paper_variable_inventory,
    collect_paper_visual_references,
    paper_variable_inventory_to_payload,
    paper_sections_to_payload,
    paper_table_mentions_to_payload,
    parse_markdown_sections,
)
from table1_parser.diagnostics import ParseQualityReport, build_parse_quality_report
from table1_parser.extract import build_extractor
from table1_parser.extract.provisional_table import ProvisionalExtractedTable
from table1_parser.heuristics.column_role_detector import detect_column_roles
from table1_parser.heuristics.paper_table_inventory import build_paper_table_inventory, paper_table_inventory_to_payload
from table1_parser.heuristics.row_classifier import classify_rows
from table1_parser.heuristics.table_definition_builder import build_table_definitions, table_definitions_to_payload
from table1_parser.heuristics.table_profile import build_table_profiles, table_profiles_to_payload
from table1_parser.heuristics.variable_grouper import group_variable_blocks
from table1_parser.llm import LLMConfigurationError, build_llm_client
from table1_parser.llm.variable_plausibility_parser import LLMVariablePlausibilityTableReviewParser
from table1_parser.leaf_column_candidates import (
    build_leaf_column_candidate_tables,
    leaf_column_candidate_tables_to_payload,
)
from table1_parser.header_structure_candidates import (
    build_header_structure_candidates,
    header_structure_candidates_to_payload,
    inherit_adjacent_continuation_leaf_labels,
)
from table1_parser.normalize import normalize_extracted_tables, normalized_tables_to_payload, write_normalized_tables
from table1_parser.parse import (
    body_element_candidates_to_payload,
    body_row_label_candidates_to_payload,
    build_body_element_candidates,
    build_body_row_label_candidates,
    build_parsed_cell_values,
    build_parsed_tables,
    parsed_cell_values_to_payload,
    parsed_tables_to_payload,
)
from table1_parser.paper_footnotes import (
    build_paper_footnote_anchor_inventory,
    build_paper_footnote_definition_candidates,
    build_paper_footnote_definition_lines_from_extracted_tables,
    build_paper_footnote_footers_from_extracted_tables,
    build_paper_footnote_footers_from_text_stream_lines,
    find_table_footer_definition_lines,
    link_paper_footnotes,
    paper_footnotes_to_payload,
)
from table1_parser.paper_bibliography import (
    build_bibliography_entries_from_sections,
    build_bibliography_entries_from_text_stream,
    build_paper_bibliography,
    paper_bibliography_to_payload,
)
from table1_parser.paper_page_furniture import build_paper_page_furniture, paper_page_furniture_to_payload
from table1_parser.paper_style_profile import build_paper_style_profile, paper_style_profile_to_payload
from table1_parser.processing_status import build_table_processing_statuses
from table1_parser.resolved_tables import build_resolved_table_set
from table1_parser.schemas import (
    BodyOccupancyTable,
    CellTextAnnotation,
    CellTextAnnotationTable,
    ColumnHeaderSchema,
    BodyElementCandidate,
    BodyRowLabelCandidate,
    ExtractedTable,
    BibliographyEntry,
    LLMVariablePlausibilityCallRecord,
    LLMVariablePlausibilityMonitoringReport,
    LeafColumnCandidateTable,
    HeaderStructureCandidate,
    NormalizedTable,
    PaperFootnotes,
    PaperBibliography,
    PaperPageFurniture,
    PaperPositionedDocument,
    PaperSection,
    PaperStyleProfile,
    PaperTableMention,
    PaperTextStream,
    PaperVariableInventory,
    PaperVisual,
    PaperVisualReference,
    ParsedCellValue,
    ParsedTable,
    ResolvedTableSet,
    TableContext,
    TableBoundaryProposal,
    TableDefinition,
    Table1ContinuationGroup,
    TableProfile,
    TableRegion,
)
from table1_parser.table_boundary_proposals import (
    build_table_boundary_proposals,
    table_boundary_proposals_to_payload,
)
from table1_parser.table_regions import build_table_regions, table_regions_to_payload
from table1_parser.table_continuation_columns import (
    build_table_continuation_column_checks,
    table_continuation_column_checks_to_payload,
)
from table1_parser.table1_continuations import (
    build_table1_continuation_artifacts,
    table1_continuation_groups_to_payload,
)
from table1_parser.text_cleaning import clean_text
DEFAULT_OUTPUT_DIR = Path("outputs")


@dataclass(slots=True)
class PaperContextArtifacts:
    """Shared paper-level context artifacts built from one positioned text pass."""

    paper_positioned_document: PaperPositionedDocument
    paper_page_furniture: PaperPageFurniture
    paper_text_stream: PaperTextStream
    paper_sections: list[PaperSection]
    paper_table_mentions: list[PaperTableMention]
    bibliography_entries: list[BibliographyEntry]


@dataclass(slots=True)
class CanonicalExtractionArtifacts:
    """Canonical extracts and their final geometry evidence."""

    extracted_tables: list[ExtractedTable]
    cell_text_annotations: list[CellTextAnnotationTable]
    table_boundary_proposals: list[TableBoundaryProposal]
    table_regions: list[TableRegion]
    body_occupancy: list[BodyOccupancyTable]
    leaf_column_candidates: list[LeafColumnCandidateTable]
    header_structure_candidates: list[HeaderStructureCandidate]


@dataclass(slots=True)
class PaperParseArtifacts:
    """All deterministic parse artifacts for one paper."""

    paper_stem: str
    extracted_tables: list[ExtractedTable]
    table_boundary_proposals: list[TableBoundaryProposal]
    table_regions: list[TableRegion]
    body_occupancy: list[BodyOccupancyTable]
    leaf_column_candidates: list[LeafColumnCandidateTable]
    header_structure_candidates: list[HeaderStructureCandidate]
    normalized_tables: list[NormalizedTable]
    column_header_schemas: list[ColumnHeaderSchema]
    resolved_table_set: ResolvedTableSet
    resolved_tables: list[NormalizedTable]
    resolved_column_header_schemas: list[ColumnHeaderSchema]
    resolved_source_extracted_tables: list[ExtractedTable]
    table1_continuation_groups: list[Table1ContinuationGroup]
    merged_table1_tables: list[NormalizedTable]
    table_profiles: list[TableProfile]
    source_table_definitions: list[TableDefinition]
    table_definitions: list[TableDefinition]
    continued_variable_integrations: list[TableDefinition]
    body_element_candidates: list[BodyElementCandidate]
    body_row_label_candidates: list[BodyRowLabelCandidate]
    parsed_cell_values: list[ParsedCellValue]
    parsed_tables: list[ParsedTable]
    parse_quality_reports: list[ParseQualityReport]
    resolved_parse_quality_reports: list[ParseQualityReport]
    cell_text_annotations: list[CellTextAnnotationTable]
    paper_footnotes: PaperFootnotes
    paper_bibliography: PaperBibliography
    paper_page_furniture: PaperPageFurniture
    paper_positioned_document: PaperPositionedDocument
    paper_style_profile: PaperStyleProfile
    paper_text_stream: PaperTextStream
    paper_markdown: str
    paper_sections: list[PaperSection]
    paper_table_mentions: list[PaperTableMention]
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


def _extract_tables_with_context(
    extractor: object,
    pdf_path: str,
    *,
    paper_page_furniture: PaperPageFurniture | None,
    paper_positioned_document: PaperPositionedDocument | None = None,
    paper_table_mentions: list[PaperTableMention] | None = None,
    paper_text_stream: PaperTextStream | None = None,
    bibliography_entries: Sequence[BibliographyEntry] | None = None,
) -> list[ProvisionalExtractedTable]:
    """Run extraction while passing optional paper-level context when supported."""
    extract = getattr(extractor, "extract")
    try:
        signature = inspect.signature(extract)
    except (TypeError, ValueError):
        return extract(pdf_path, paper_page_furniture=paper_page_furniture)
    supports_table_mentions = "paper_table_mentions" in signature.parameters or any(
        parameter.kind == inspect.Parameter.VAR_KEYWORD
        for parameter in signature.parameters.values()
    )
    supports_text_stream = "paper_text_stream" in signature.parameters or any(
        parameter.kind == inspect.Parameter.VAR_KEYWORD
        for parameter in signature.parameters.values()
    )
    supports_positioned_document = "paper_positioned_document" in signature.parameters or any(
        parameter.kind == inspect.Parameter.VAR_KEYWORD
        for parameter in signature.parameters.values()
    )
    supports_bibliography_entries = "bibliography_entries" in signature.parameters or any(
        parameter.kind == inspect.Parameter.VAR_KEYWORD
        for parameter in signature.parameters.values()
    )
    keyword_arguments: dict[str, object] = {
        "paper_page_furniture": paper_page_furniture,
    }
    if supports_table_mentions:
        keyword_arguments["paper_table_mentions"] = paper_table_mentions
    if supports_text_stream:
        keyword_arguments["paper_text_stream"] = paper_text_stream
    if supports_positioned_document:
        keyword_arguments["paper_positioned_document"] = paper_positioned_document
    if supports_bibliography_entries:
        keyword_arguments["bibliography_entries"] = bibliography_entries
    return extract(pdf_path, **keyword_arguments)


def _extract_payload(tables: list[ExtractedTable]) -> list[dict[str, object]]:
    """Serialize extracted tables as JSON-ready dictionaries."""
    return [table.model_dump(mode="json") for table in tables]


def _build_table_geometry_artifacts(
    pdf_path: str,
    extracted_tables: Sequence[ExtractedTable],
    paper_context: PaperContextArtifacts,
) -> CanonicalExtractionArtifacts:
    """Build the geometry evidence associated with one extraction grid."""
    cell_text_annotations = build_cell_text_annotation_tables_from_pdf(
        pdf_path,
        extracted_tables,
        paper_page_furniture=paper_context.paper_page_furniture,
        paper_positioned_document=paper_context.paper_positioned_document,
    )
    table_boundary_proposals = build_table_boundary_proposals(
        extracted_tables,
        paper_positioned_document=paper_context.paper_positioned_document,
        paper_text_stream=paper_context.paper_text_stream,
    )
    table_regions = build_table_regions(
        extracted_tables,
        paper_text_stream=paper_context.paper_text_stream,
        paper_page_furniture=paper_context.paper_page_furniture,
        cell_text_annotations=cell_text_annotations,
        table_boundary_proposals=table_boundary_proposals,
        paper_positioned_document=paper_context.paper_positioned_document,
    )
    regions_by_table_id = {region.table_id: region for region in table_regions}
    for proposal in table_boundary_proposals:
        region = regions_by_table_id.get(proposal.table_id)
        if region is None:
            continue
        if region.column_header_rows and region.body_rows:
            proposal.selected_header_body_rows = (
                max(region.column_header_rows),
                min(region.body_rows),
            )
        if region.body_rows and region.footer_note_rows:
            proposal.selected_body_footer_rows = (
                max(region.body_rows),
                min(region.footer_note_rows),
            )
        if region.body_rows:
            first_body_row = min(region.body_rows)
            for candidate in proposal.boundary_candidates:
                if (
                    "body_footer" in candidate.possible_roles
                    and candidate.row_before_idx is not None
                    and candidate.row_before_idx < first_body_row
                ):
                    candidate.possible_roles.remove("body_footer")
                    candidate.following_text_line_ids = []
                    candidate.following_text_bbox = None
                    candidate.following_text_styles = []
    body_occupancy = build_body_occupancy_tables(
        extracted_tables,
        paper_positioned_document=paper_context.paper_positioned_document,
        table_regions=table_regions,
        table_boundary_proposals=table_boundary_proposals,
        cell_text_annotations=cell_text_annotations,
    )
    leaf_column_candidates = build_leaf_column_candidate_tables(
        body_occupancy,
        extracted_tables,
    )
    header_structure_candidates = build_header_structure_candidates(
        extracted_tables,
        paper_positioned_document=paper_context.paper_positioned_document,
        table_regions=table_regions,
        table_boundary_proposals=table_boundary_proposals,
        leaf_column_candidates=leaf_column_candidates,
        cell_text_annotations=cell_text_annotations,
    )
    return CanonicalExtractionArtifacts(
        extracted_tables=list(extracted_tables),
        cell_text_annotations=cell_text_annotations,
        table_boundary_proposals=table_boundary_proposals,
        table_regions=table_regions,
        body_occupancy=body_occupancy,
        leaf_column_candidates=leaf_column_candidates,
        header_structure_candidates=header_structure_candidates,
    )


def _build_canonical_extraction_artifacts(
    pdf_path: str,
    paper_context: PaperContextArtifacts,
) -> CanonicalExtractionArtifacts:
    """Detect provisional tables, select their grids, and rebuild final evidence."""
    extractor = _build_default_extractor()
    provisional_tables = _extract_tables_with_context(
        extractor,
        pdf_path,
        paper_page_furniture=paper_context.paper_page_furniture,
        paper_positioned_document=paper_context.paper_positioned_document,
        paper_table_mentions=paper_context.paper_table_mentions,
        paper_text_stream=paper_context.paper_text_stream,
        bibliography_entries=paper_context.bibliography_entries,
    )
    provisional = _build_table_geometry_artifacts(
        pdf_path,
        provisional_tables,
        paper_context,
    )
    canonical_tables = finalize_canonical_extracted_tables(
        provisional_tables,
        paper_positioned_document=paper_context.paper_positioned_document,
        table_boundary_proposals=provisional.table_boundary_proposals,
        leaf_column_candidates=provisional.leaf_column_candidates,
    )
    final = _build_table_geometry_artifacts(
        pdf_path,
        canonical_tables,
        paper_context,
    )
    final.header_structure_candidates = inherit_adjacent_continuation_leaf_labels(
        final.extracted_tables,
        final.header_structure_candidates,
    )
    return final


def _build_paper_context_artifacts(pdf_path: str) -> PaperContextArtifacts:
    """Build shared paper-context artifacts from one positioned PyMuPDF text pass."""
    paper_stem = Path(pdf_path).stem
    paper_positioned_document = build_paper_positioned_document(pdf_path, paper_id=paper_stem)
    if paper_positioned_document.page_count <= 0 or not any(page.lines for page in paper_positioned_document.pages):
        raise RuntimeError("PyMuPDF positioned text extraction failed; cannot parse paper context.")
    paper_page_furniture = build_paper_page_furniture(
        pdf_path,
        paper_id=paper_stem,
        paper_positioned_document=paper_positioned_document,
    )
    paper_text_stream = build_paper_text_stream(
        pdf_path,
        paper_page_furniture=paper_page_furniture,
        paper_positioned_document=paper_positioned_document,
        paper_id=paper_stem,
    )
    if not paper_text_stream.markdown.strip():
        raise RuntimeError("PyMuPDF positioned text stream did not produce paper_markdown.md.")
    paper_sections = parse_markdown_sections(paper_text_stream.markdown)
    paper_table_mentions = build_paper_table_mentions(paper_text_stream)
    bibliography_entries = build_bibliography_entries_from_text_stream(paper_text_stream)
    if not bibliography_entries:
        bibliography_entries = build_bibliography_entries_from_sections(paper_sections)
    return PaperContextArtifacts(
        paper_positioned_document=paper_positioned_document,
        paper_page_furniture=paper_page_furniture,
        paper_text_stream=paper_text_stream,
        paper_sections=paper_sections,
        paper_table_mentions=paper_table_mentions,
        bibliography_entries=bibliography_entries,
    )


def _handle_extract(args: argparse.Namespace) -> int:
    """Run extraction and serialize the extracted output."""
    if _validate_pdf_path(args.pdf_path) is None:
        return 1

    try:
        paper_context = _build_paper_context_artifacts(args.pdf_path)
        canonical = _build_canonical_extraction_artifacts(
            args.pdf_path,
            paper_context,
        )
        tables = canonical.extracted_tables
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
        paper_context = _build_paper_context_artifacts(args.pdf_path)
        canonical = _build_canonical_extraction_artifacts(
            args.pdf_path,
            paper_context,
        )
        normalized_tables = normalize_extracted_tables(
            canonical.extracted_tables,
            table_regions=canonical.table_regions,
        )
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
        artifacts.resolved_source_extracted_tables,
        artifacts.resolved_tables,
        artifacts.table_profiles,
        artifacts.table_definitions,
        artifacts.parsed_tables,
        artifacts.resolved_parse_quality_reports,
        resolved_table_set=artifacts.resolved_table_set,
        source_parse_quality_reports=artifacts.parse_quality_reports,
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
        artifacts.resolved_source_extracted_tables,
        artifacts.resolved_tables,
        artifacts.table_profiles,
        artifacts.table_definitions,
        artifacts.parsed_tables,
        artifacts.resolved_parse_quality_reports,
        resolved_table_set=artifacts.resolved_table_set,
        source_parse_quality_reports=artifacts.parse_quality_reports,
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
    paper_stem = Path(pdf_path).stem
    paper_context = _build_paper_context_artifacts(pdf_path)
    paper_positioned_document = paper_context.paper_positioned_document
    paper_page_furniture = paper_context.paper_page_furniture
    paper_text_stream = paper_context.paper_text_stream
    paper_markdown = paper_text_stream.markdown
    paper_sections = paper_context.paper_sections
    paper_table_mentions = paper_context.paper_table_mentions
    bibliography_entries = paper_context.bibliography_entries
    canonical = _build_canonical_extraction_artifacts(
        pdf_path,
        paper_context,
    )
    extracted_tables = canonical.extracted_tables
    cell_text_annotations = canonical.cell_text_annotations
    table_boundary_proposals = canonical.table_boundary_proposals
    table_regions = canonical.table_regions
    body_occupancy = canonical.body_occupancy
    leaf_column_candidates = canonical.leaf_column_candidates
    header_structure_candidates = canonical.header_structure_candidates
    normalized_tables = normalize_extracted_tables(extracted_tables, table_regions=table_regions)
    column_header_schemas = build_column_header_schemas(
        normalized_tables,
        extracted_tables,
        paper_positioned_document,
        header_structure_candidates,
    )
    resolved_table_set = build_resolved_table_set(normalized_tables, column_header_schemas)
    resolved_tables = [resolved_table.table for resolved_table in resolved_table_set.resolved_tables]
    source_schema_by_table_id = {schema.table_id: schema for schema in column_header_schemas}
    resolved_column_header_schemas: list[ColumnHeaderSchema] = []
    for resolved_table in resolved_table_set.resolved_tables:
        resolved_table_id = resolved_table.table.table_id
        source_schema = (
            source_schema_by_table_id.get(resolved_table.source_table_ids[0])
            if resolved_table.source_table_ids
            else None
        )
        if source_schema is None:
            resolved_column_header_schemas.append(build_column_header_schema(resolved_table.table))
            continue
        resolved_column_header_schemas.append(
            source_schema.model_copy(
                update={
                    "schema_id": f"{resolved_table_id}:column_header_schema",
                    "table_id": resolved_table_id,
                    "header_rows_considered": list(resolved_table.table.header_rows),
                    "body_rows_considered": list(resolved_table.table.body_rows),
                    "leaves": [
                        leaf.model_copy(update={"table_id": resolved_table_id})
                        for leaf in source_schema.leaves
                    ],
                    "groups": [
                        group.model_copy(update={"table_id": resolved_table_id})
                        for group in source_schema.groups
                    ],
                    "relationships": [
                        relationship.model_copy(update={"table_id": resolved_table_id})
                        for relationship in source_schema.relationships
                    ],
                    "evidence": [
                        evidence.model_copy(update={"table_id": resolved_table_id})
                        for evidence in source_schema.evidence
                    ],
                }
            )
        )
    extracted_table_by_id = {table.table_id: table for table in extracted_tables}
    resolved_source_extracted_tables: list[ExtractedTable] = []
    for resolved_index, resolved_table in enumerate(resolved_table_set.resolved_tables):
        source_table_id = resolved_table.source_table_ids[0] if resolved_table.source_table_ids else None
        source_extracted_table = extracted_table_by_id.get(source_table_id) if source_table_id is not None else None
        if source_extracted_table is None and resolved_index < len(extracted_tables):
            source_extracted_table = extracted_tables[resolved_index]
        if source_extracted_table is not None:
            resolved_source_extracted_tables.append(source_extracted_table)
    value_column_indices_by_table_id = {
        schema.table_id: {
            leaf.col_idx
            for leaf in schema.leaves
            if leaf.is_value_column and not leaf.is_row_label_column
        }
        for schema in column_header_schemas
    }
    body_element_candidates = build_body_element_candidates(
        normalized_tables,
        column_header_schemas,
        extracted_tables,
    )
    body_row_label_candidates = build_body_row_label_candidates(
        normalized_tables,
        column_header_schemas,
        extracted_tables,
    )
    logical_body_candidates: list[BodyElementCandidate | BodyRowLabelCandidate] = [
        *body_element_candidates,
        *body_row_label_candidates,
    ]
    candidate_ids_by_source_cell_id: dict[str, set[str]] = {}
    candidate_source_cell_ids: dict[str, list[str]] = {}
    physical_text_by_source_cell_id = {
        f"{table.table_id}:r{cell.row_idx}:c{cell.col_idx}": cell.text
        for table in extracted_tables
        for cell in table.cells
    }
    for candidate in logical_body_candidates:
        for source_cell in candidate.source_cells:
            if (
                source_cell.original_row_idx is not None
                and source_cell.original_col_idx is not None
            ):
                source_cell_id = (
                    f"{source_cell.source_table_id}:"
                    f"r{source_cell.original_row_idx}:c{source_cell.original_col_idx}"
                )
                candidate_ids_by_source_cell_id.setdefault(source_cell_id, set()).add(
                    candidate.candidate_id
                )
                candidate_source_cell_ids.setdefault(candidate.candidate_id, []).append(source_cell_id)
    marker_ids_by_source_cell_id: dict[str, list[str]] = {}
    annotations_by_marker_id: dict[str, CellTextAnnotation] = {}
    for annotation_table in cell_text_annotations:
        for annotation_index, annotation in enumerate(annotation_table.annotations):
            marker_id = annotation.annotation_id or (
                f"{annotation_table.table_id}:marker:{annotation_index}"
            )
            annotations_by_marker_id[marker_id] = annotation
            if annotation.source_cell_id is not None:
                marker_ids_by_source_cell_id.setdefault(annotation.source_cell_id, []).append(marker_id)
    for candidate in logical_body_candidates:
        candidate.marker_ids.extend(
            marker_id
            for source_cell_id in dict.fromkeys(
                candidate_source_cell_ids.get(candidate.candidate_id, [])
            )
            if len(candidate_ids_by_source_cell_id[source_cell_id]) == 1
            for marker_id in marker_ids_by_source_cell_id.get(source_cell_id, [])
        )
        if candidate.marker_ids and candidate.kind != "row_sequence_reconstruction":
            source_cell_ids = list(
                dict.fromkeys(candidate_source_cell_ids.get(candidate.candidate_id, []))
            )
            if all(source_cell_id in physical_text_by_source_cell_id for source_cell_id in source_cell_ids):
                candidate.raw_text = " ".join(
                    physical_text_by_source_cell_id[source_cell_id]
                    for source_cell_id in source_cell_ids
                )
                candidate.base_text = candidate.raw_text

    logical_text_candidates = [
        *((candidate, candidate.notes) for candidate in logical_body_candidates),
        *(
            (node, header_candidate.concerns)
            for header_candidate in header_structure_candidates
            for node in [
                *header_candidate.leaf_candidates,
                *header_candidate.group_candidates,
            ]
        ),
    ]
    for candidate, candidate_diagnostics in logical_text_candidates:
        marker_annotations = [
            (marker_id, annotations_by_marker_id[marker_id])
            for marker_id in candidate.marker_ids
            if marker_id in annotations_by_marker_id
        ]
        if not marker_annotations:
            continue
        compact_indices = [
            index
            for index, character in enumerate(candidate.raw_text)
            if not character.isspace() and character != "\ufeff"
        ]
        compact_text = "".join(candidate.raw_text[index] for index in compact_indices)
        removal_indices: set[int] = set()
        for marker_id, annotation in marker_annotations:
            marker_text = "".join(annotation.text.split()).replace("\ufeff", "")
            attached_text = "".join((annotation.attached_to_text or "").split()).replace(
                "\ufeff", ""
            )
            exact_geometry = (
                annotation.bbox is not None
                and bool(annotation.source_span_references)
                and len(annotation.source_char_indices) == len(marker_text)
            )
            alignment_text = compact_text
            marker_start = len(attached_text)
            if isinstance(candidate, (BodyElementCandidate, BodyRowLabelCandidate)):
                source_text = physical_text_by_source_cell_id.get(
                    annotation.source_cell_id or "", ""
                )
                compact_source_text = "".join(source_text.split()).replace("\ufeff", "")
                source_start = compact_text.find(compact_source_text)
                if (
                    compact_source_text
                    and source_start >= 0
                    and compact_text.find(compact_source_text, source_start + 1) < 0
                ):
                    alignment_text = compact_source_text
                    marker_start += source_start
                else:
                    alignment_text = ""
            if (
                exact_geometry
                and marker_text
                and alignment_text.startswith(attached_text + marker_text)
            ):
                removal_indices.update(
                    compact_indices[marker_start : marker_start + len(marker_text)]
                )
            else:
                candidate_diagnostics.append(
                    "marker_base_text_retained_without_exact_"
                    f"{'geometry' if not exact_geometry else 'alignment'}:{marker_id}"
                )
        candidate.base_text = "".join(
            character
            for index, character in enumerate(candidate.raw_text)
            if index not in removal_indices
        )
        if isinstance(candidate, BodyElementCandidate):
            candidate.candidate_text = clean_text(candidate.base_text)
        elif isinstance(candidate, BodyRowLabelCandidate):
            candidate.candidate_label = clean_text(candidate.base_text)
        else:
            candidate.label = clean_text(candidate.base_text)
        compact_base_text = "".join(candidate.base_text.split()).replace("\ufeff", "")
        for marker_id, annotation in marker_annotations:
            marker_text = "".join(annotation.text.split()).replace("\ufeff", "")
            if (
                marker_text
                and all(not character.isalnum() for character in marker_text)
                and marker_text in compact_base_text
            ):
                candidate_diagnostics.append(
                    f"marker_glyph_retained_without_occurrence:{marker_id}"
                )
        candidate_diagnostics[:] = list(dict.fromkeys(candidate_diagnostics))
    parsed_cell_values = build_parsed_cell_values(
        normalized_tables,
        value_column_indices_by_table_id=value_column_indices_by_table_id,
        body_element_candidates=body_element_candidates,
    )
    resolved_body_element_candidates = build_body_element_candidates(
        resolved_tables,
        resolved_column_header_schemas,
    )
    resolved_body_row_label_candidates = build_body_row_label_candidates(
        resolved_tables,
        resolved_column_header_schemas,
    )
    table1_continuation_groups, merged_table1_tables = build_table1_continuation_artifacts(
        normalized_tables,
        column_header_schemas,
    )
    paper_footnotes = build_paper_footnote_anchor_inventory(
        paper_id=paper_stem,
        source_pdf=pdf_path,
        cell_text_annotations=cell_text_annotations,
        extracted_tables=extracted_tables,
        column_header_schemas=column_header_schemas,
        table1_continuation_groups=table1_continuation_groups,
    )
    paper_footnote_anchors_before_linking = list(paper_footnotes.anchors)
    extracted_table_footers = build_paper_footnote_footers_from_extracted_tables(
        extracted_tables,
        table1_continuation_groups=table1_continuation_groups,
        table_regions=table_regions,
    )
    table_local_footnote_definition_lines = (
        build_paper_footnote_definition_lines_from_extracted_tables(
            extracted_tables,
            table1_continuation_groups=table1_continuation_groups,
            table_regions=table_regions,
            cell_text_annotations=cell_text_annotations,
        )
    )
    table_footer_text_stream_definition_lines = find_table_footer_definition_lines(
        extracted_tables,
        table1_continuation_groups=table1_continuation_groups,
        paper_text_stream=paper_text_stream,
    )
    paper_footnote_definition_lines = [
        *table_local_footnote_definition_lines,
        *table_footer_text_stream_definition_lines,
    ]
    text_stream_table_footers = build_paper_footnote_footers_from_text_stream_lines(
        table_footer_text_stream_definition_lines,
        existing_footers=extracted_table_footers,
    )
    table_footers = [*extracted_table_footers, *text_stream_table_footers]
    paper_footnote_definitions = build_paper_footnote_definition_candidates(
        paper_footnote_definition_lines,
        extracted_tables,
        table1_continuation_groups=table1_continuation_groups,
    )
    paper_footnotes = link_paper_footnotes(
        paper_footnotes.model_copy(
            update={
                "footers": table_footers,
                "definitions": paper_footnote_definitions,
                "metadata": {
                    **paper_footnotes.metadata,
                    "source_artifacts": sorted(
                        {
                            *paper_footnotes.metadata.get("source_artifacts", []),
                            "paper_text_stream.json",
                            "paper_page_furniture.json",
                        }
                    ),
                    "page_furniture_filter_stage": "before_paper_text_stream_footer_detection",
                    "footer_count": len(table_footers),
                    "footer_count_from_extracted_tables": len(extracted_table_footers),
                    "footer_count_from_text_stream": len(text_stream_table_footers),
                    "definition_line_count_from_extracted_tables": len(table_local_footnote_definition_lines),
                    "definition_line_count_from_text_stream": len(table_footer_text_stream_definition_lines),
                    "definition_line_count": len(paper_footnote_definition_lines),
                    "definition_count": len(paper_footnote_definitions),
                    "definitions_status": "built",
                },
            }
        ),
        bibliography_label_keys={entry.label_key for entry in bibliography_entries},
    )
    table_profiles = build_table_profiles(
        resolved_tables,
        body_element_candidates=resolved_body_element_candidates,
        body_row_label_candidates=resolved_body_row_label_candidates,
        column_schemas=resolved_column_header_schemas,
    )
    parse_quality_reports = []
    body_element_candidates_by_table_id: dict[str, list[BodyElementCandidate]] = {}
    for candidate in body_element_candidates:
        body_element_candidates_by_table_id.setdefault(candidate.source_table_id, []).append(candidate)
    body_row_label_candidates_by_table_id: dict[str, list[BodyRowLabelCandidate]] = {}
    for candidate in body_row_label_candidates:
        body_row_label_candidates_by_table_id.setdefault(candidate.source_table_id, []).append(candidate)
    for table_index, table in enumerate(normalized_tables):
        table_candidates = body_element_candidates_by_table_id.get(table.table_id)
        table_label_candidates = body_row_label_candidates_by_table_id.get(table.table_id)
        column_schema = column_header_schemas[table_index] if table_index < len(column_header_schemas) else None
        row_classifications = classify_rows(
            table,
            body_element_candidates=table_candidates,
            body_row_label_candidates=table_label_candidates,
            column_schema=column_schema,
        )
        variable_blocks = group_variable_blocks(
            table,
            classifications=row_classifications,
            body_element_candidates=table_candidates,
            body_row_label_candidates=table_label_candidates,
            column_schema=column_schema,
        )
        column_roles = detect_column_roles(table, column_schema=column_schema)
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
    parse_quality_report_by_table_id = {
        report.table_id: report
        for report in parse_quality_reports
    }
    resolved_parse_quality_reports = [
        parse_quality_report_by_table_id[resolved_table.source_table_ids[0]]
        for resolved_table in resolved_table_set.resolved_tables
        if resolved_table.source_table_ids
        and resolved_table.source_table_ids[0] in parse_quality_report_by_table_id
    ]
    source_table_definitions = build_table_definitions(
        normalized_tables,
        column_header_schemas,
        body_element_candidates=body_element_candidates,
        body_row_label_candidates=body_row_label_candidates,
    )
    table_definitions = build_table_definitions(
        resolved_tables,
        resolved_column_header_schemas,
        body_element_candidates=resolved_body_element_candidates,
        body_row_label_candidates=resolved_body_row_label_candidates,
    )
    continued_variable_integrations = build_continued_variable_integrations(
        normalized_tables,
        source_table_definitions,
        table1_continuation_groups,
    )
    row_provenance_by_table_id = {
        resolved_table.table_id: resolved_table.row_provenance
        for resolved_table in resolved_table_set.resolved_tables
    }
    parsed_tables = build_parsed_tables(
        resolved_tables,
        table_definitions,
        parsed_cell_values=parsed_cell_values,
        row_provenance_by_table_id=row_provenance_by_table_id,
    )
    paper_bibliography = build_paper_bibliography(
        paper_id=paper_stem,
        source_pdf=pdf_path,
        paper_sections=paper_sections,
        footnote_anchors=paper_footnote_anchors_before_linking,
        footnote_definitions=paper_footnote_definitions,
        bibliography_entries=bibliography_entries,
    )
    paper_visual_inventory = build_paper_visual_inventory(extracted_tables, table_definitions, paper_sections)
    paper_references = collect_paper_visual_references(paper_sections, paper_visual_inventory)
    paper_visual_inventory = annotate_visual_reference_checks(paper_visual_inventory, paper_references)
    paper_style_profile = build_paper_style_profile(
        paper_id=paper_stem,
        source_pdf=pdf_path,
        paper_text_stream=paper_text_stream,
        extracted_tables=extracted_tables,
        paper_footnotes=paper_footnotes,
        paper_bibliography=paper_bibliography,
        paper_visual_inventory=paper_visual_inventory,
        paper_references=paper_references,
    )
    paper_variable_inventory = build_paper_variable_inventory(paper_stem, paper_sections, table_definitions)
    table_contexts = build_table_contexts(paper_sections, table_definitions, paper_visual_inventory, paper_references)
    return PaperParseArtifacts(
        paper_stem=paper_stem,
        extracted_tables=extracted_tables,
        table_boundary_proposals=table_boundary_proposals,
        table_regions=table_regions,
        body_occupancy=body_occupancy,
        leaf_column_candidates=leaf_column_candidates,
        header_structure_candidates=header_structure_candidates,
        normalized_tables=normalized_tables,
        column_header_schemas=column_header_schemas,
        resolved_table_set=resolved_table_set,
        resolved_tables=resolved_tables,
        resolved_column_header_schemas=resolved_column_header_schemas,
        resolved_source_extracted_tables=resolved_source_extracted_tables,
        table1_continuation_groups=table1_continuation_groups,
        merged_table1_tables=merged_table1_tables,
        table_profiles=table_profiles,
        source_table_definitions=source_table_definitions,
        table_definitions=table_definitions,
        continued_variable_integrations=continued_variable_integrations,
        body_element_candidates=body_element_candidates,
        body_row_label_candidates=body_row_label_candidates,
        parsed_cell_values=parsed_cell_values,
        parsed_tables=parsed_tables,
        parse_quality_reports=parse_quality_reports,
        resolved_parse_quality_reports=resolved_parse_quality_reports,
        cell_text_annotations=cell_text_annotations,
        paper_footnotes=paper_footnotes,
        paper_bibliography=paper_bibliography,
        paper_page_furniture=paper_page_furniture,
        paper_positioned_document=paper_positioned_document,
        paper_style_profile=paper_style_profile,
        paper_text_stream=paper_text_stream,
        paper_markdown=paper_markdown,
        paper_sections=paper_sections,
        paper_table_mentions=paper_table_mentions,
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
    table_boundary_proposals_output_path = paper_dir / "table_boundary_proposals.json"
    table_regions_output_path = paper_dir / "table_regions.json"
    body_occupancy_output_path = paper_dir / "body_occupancy.json"
    leaf_column_candidates_output_path = paper_dir / "leaf_column_candidates.json"
    header_structure_candidates_output_path = paper_dir / "header_structure_candidates.json"
    normalize_output_path = paper_dir / "normalized_tables.json"
    column_header_schema_output_path = paper_dir / "column_header_schemas.json"
    resolved_table_output_path = paper_dir / "resolved_tables.json"
    table1_continuation_groups_output_path = paper_dir / "table1_continuation_groups.json"
    table_continuation_column_checks_output_path = paper_dir / "table_continuation_column_checks.json"
    merged_table1_output_path = paper_dir / "merged_table1_tables.json"
    table_profile_output_path = paper_dir / "table_profiles.json"
    table_definition_output_path = paper_dir / "table_definitions.json"
    continued_variable_integration_output_path = paper_dir / "continued_variable_integrations.json"
    body_element_candidates_output_path = paper_dir / "body_element_candidates.json"
    body_row_label_candidates_output_path = paper_dir / "body_row_label_candidates.json"
    parsed_cell_values_output_path = paper_dir / "parsed_cell_values.json"
    parsed_output_path = paper_dir / "parsed_tables.json"
    processing_status_output_path = paper_dir / "table_processing_status.json"
    parse_quality_reports_output_path = paper_dir / "parse_quality_reports.json"
    cell_text_annotations_output_path = paper_dir / "cell_text_annotations.json"
    paper_footnotes_output_path = paper_dir / "paper_footnotes.json"
    paper_bibliography_output_path = paper_dir / "paper_bibliography.json"
    paper_page_furniture_output_path = paper_dir / "paper_page_furniture.json"
    paper_positioned_document_output_path = paper_dir / "paper_positioned_document.json"
    paper_style_profile_output_path = paper_dir / "paper_style_profile.json"
    paper_text_stream_output_path = paper_dir / "paper_text_stream.json"
    paper_markdown_output_path = paper_dir / "paper_markdown.md"
    paper_sections_output_path = paper_dir / "paper_sections.json"
    paper_table_mentions_output_path = paper_dir / "paper_table_mentions.json"
    paper_visual_inventory_output_path = paper_dir / "paper_visual_inventory.json"
    paper_references_output_path = paper_dir / "paper_references.json"
    paper_variable_inventory_output_path = paper_dir / "paper_variable_inventory.json"
    paper_table_inventory_output_path = paper_dir / "paper_table_inventory.json"
    table_context_output_dir = paper_dir / "table_contexts"

    paper_dir.mkdir(parents=True, exist_ok=True)
    table_context_output_dir.mkdir(parents=True, exist_ok=True)
    paper_table_inventory = build_paper_table_inventory(
        artifacts.paper_stem,
        artifacts.resolved_source_extracted_tables,
        artifacts.resolved_tables,
        artifacts.table_profiles,
        table_definitions,
        parsed_tables,
        artifacts.resolved_parse_quality_reports,
        table_processing_statuses,
    )
    source_table_profiles = build_table_profiles(
        artifacts.normalized_tables,
        body_element_candidates=artifacts.body_element_candidates,
        body_row_label_candidates=artifacts.body_row_label_candidates,
        column_schemas=artifacts.column_header_schemas,
    )
    table_continuation_column_checks = build_table_continuation_column_checks(
        artifacts.normalized_tables,
        artifacts.extracted_tables,
        source_table_profiles,
        None,
        artifacts.column_header_schemas,
    )

    extract_output_path.write_text(
        json.dumps(_extract_payload(artifacts.extracted_tables), indent=2),
        encoding="utf-8",
    )
    table_boundary_proposals_output_path.write_text(
        json.dumps(
            table_boundary_proposals_to_payload(artifacts.table_boundary_proposals),
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    table_regions_output_path.write_text(
        json.dumps(table_regions_to_payload(artifacts.table_regions), indent=2) + "\n",
        encoding="utf-8",
    )
    body_occupancy_output_path.write_text(
        json.dumps(body_occupancy_tables_to_payload(artifacts.body_occupancy), indent=2) + "\n",
        encoding="utf-8",
    )
    leaf_column_candidates_output_path.write_text(
        json.dumps(
            leaf_column_candidate_tables_to_payload(artifacts.leaf_column_candidates),
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    header_structure_candidates_output_path.write_text(
        json.dumps(
            header_structure_candidates_to_payload(
                artifacts.header_structure_candidates
            ),
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    write_normalized_tables(normalize_output_path, artifacts.normalized_tables)
    column_header_schema_output_path.write_text(
        json.dumps(column_header_schemas_to_payload(artifacts.column_header_schemas), indent=2) + "\n",
        encoding="utf-8",
    )
    resolved_table_output_path.write_text(
        json.dumps(artifacts.resolved_table_set.model_dump(mode="json"), indent=2) + "\n",
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
    body_element_candidates_output_path.write_text(
        json.dumps(body_element_candidates_to_payload(artifacts.body_element_candidates), indent=2) + "\n",
        encoding="utf-8",
    )
    body_row_label_candidates_output_path.write_text(
        json.dumps(body_row_label_candidates_to_payload(artifacts.body_row_label_candidates), indent=2) + "\n",
        encoding="utf-8",
    )
    parsed_cell_values_output_path.write_text(
        json.dumps(parsed_cell_values_to_payload(artifacts.parsed_cell_values), indent=2) + "\n",
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
    paper_bibliography_output_path.write_text(
        json.dumps(paper_bibliography_to_payload(artifacts.paper_bibliography), indent=2) + "\n",
        encoding="utf-8",
    )
    paper_page_furniture_output_path.write_text(
        json.dumps(paper_page_furniture_to_payload(artifacts.paper_page_furniture), indent=2) + "\n",
        encoding="utf-8",
    )
    paper_positioned_document_output_path.write_text(
        json.dumps(artifacts.paper_positioned_document.model_dump(mode="json"), indent=2) + "\n",
        encoding="utf-8",
    )
    paper_style_profile_output_path.write_text(
        json.dumps(paper_style_profile_to_payload(artifacts.paper_style_profile), indent=2) + "\n",
        encoding="utf-8",
    )
    paper_text_stream_output_path.write_text(
        json.dumps(artifacts.paper_text_stream.model_dump(mode="json"), indent=2) + "\n",
        encoding="utf-8",
    )
    paper_markdown_output_path.write_text(artifacts.paper_markdown, encoding="utf-8")
    paper_sections_output_path.write_text(
        json.dumps(paper_sections_to_payload(artifacts.paper_sections), indent=2) + "\n",
        encoding="utf-8",
    )
    paper_table_mentions_output_path.write_text(
        json.dumps(paper_table_mentions_to_payload(artifacts.paper_table_mentions), indent=2) + "\n",
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
