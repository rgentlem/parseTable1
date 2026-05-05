"""Schema validation and serialization tests."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from table1_parser.schemas import (
    ColumnDefinition,
    ColumnHeaderCellEvidence,
    ColumnHeaderGroup,
    ColumnHeaderLeaf,
    ColumnHeaderRelationship,
    ColumnHeaderSchema,
    DefinedColumn,
    DefinedLevel,
    DefinedVariable,
    ExtractedTable,
    LLMVariablePlausibilityCallRecord,
    LLMVariablePlausibilityMonitoringReport,
    NormalizedTable,
    PaperSection,
    PaperVariableInventory,
    PaperVisual,
    PaperVisualReference,
    ParsedColumn,
    ParsedLevel,
    ParsedTable,
    ParsedVariable,
    RetrievedPassage,
    RowView,
    TableCell,
    TableContext,
    TableDefinition,
    TableProcessingAttempt,
    TableProcessingStatus,
    TableProfile,
    VariableCandidate,
    VariableMention,
    ValueRecord,
)


def test_extracted_table_creation_and_serialization() -> None:
    """Extracted tables should instantiate and serialize cleanly."""
    table = ExtractedTable(
        table_id="tbl-1",
        source_pdf="paper.pdf",
        page_num=3,
        title="Table 1",
        caption="Baseline characteristics",
        n_rows=2,
        n_cols=2,
        cells=[
            TableCell(row_idx=0, col_idx=0, text="Age", page_num=3),
            TableCell(row_idx=0, col_idx=1, text="52.1 (8.7)", page_num=3),
        ],
        extraction_backend="pymupdf4llm",
        metadata={"journal": "Example"},
    )

    dumped = table.model_dump()

    assert dumped["table_id"] == "tbl-1"
    assert dumped["cells"][0]["text"] == "Age"
    assert dumped["metadata"]["journal"] == "Example"


def test_row_view_and_normalized_table_creation() -> None:
    """Normalized table schemas should accept row summary inputs."""
    row_view = RowView(
        row_idx=1,
        raw_cells=["Sex", "34 (45%)"],
        first_cell_raw="Sex",
        first_cell_normalized="sex",
        first_cell_alpha_only="sex",
        nonempty_cell_count=2,
        numeric_cell_count=1,
        has_trailing_values=True,
        indent_level=0,
        likely_role="variable",
    )
    table = NormalizedTable(
        table_id="tbl-1",
        title="Table 1",
        caption="Baseline characteristics",
        header_rows=[0],
        body_rows=[1],
        row_views=[row_view],
        n_rows=2,
        n_cols=2,
        metadata={"normalized": True},
    )

    assert table.row_views[0].likely_role == "variable"
    assert table.model_dump()["metadata"]["normalized"] is True


def test_parsed_table_creation_and_serialization() -> None:
    """Parsed table schemas should serialize nested objects correctly."""
    parsed = ParsedTable(
        table_id="tbl-1",
        title="Table 1",
        caption="Baseline characteristics",
        variables=[
            ParsedVariable(
                variable_name="sex",
                variable_label="Sex",
                variable_type="categorical",
                row_start=1,
                row_end=2,
                levels=[ParsedLevel(label="Male", row_idx=2)],
                confidence=0.95,
            )
        ],
        columns=[
            ParsedColumn(
                col_idx=1,
                column_name="overall",
                column_label="Overall",
                inferred_role="overall",
                confidence=0.9,
            )
        ],
        values=[
            ValueRecord(
                row_idx=2,
                col_idx=1,
                variable_name="sex",
                level_label="Male",
                column_name="overall",
                raw_value="34 (45%)",
                value_type="count",
                parsed_numeric=34.0,
                parsed_secondary_numeric=45.0,
                confidence=0.92,
            )
        ],
        notes=["Phase 1 schema smoke test"],
        overall_confidence=0.91,
    )

    dumped = parsed.model_dump(mode="json")

    assert dumped["variables"][0]["levels"][0]["label"] == "Male"
    assert dumped["columns"][0]["inferred_role"] == "overall"
    assert dumped["values"][0]["parsed_secondary_numeric"] == 45.0


def test_table_definition_creation_and_serialization() -> None:
    """TableDefinition schemas should serialize nested row and column definitions correctly."""
    definition = TableDefinition(
        table_id="tbl-1",
        title="Table 1",
        caption="Baseline characteristics by RA status",
        variables=[
            DefinedVariable(
                variable_name="Sex",
                variable_label="Sex",
                variable_type="binary",
                row_start=2,
                row_end=4,
                levels=[
                    DefinedLevel(level_name="Male", level_label="Male", row_idx=3),
                    DefinedLevel(level_name="Female", level_label="Female", row_idx=4),
                ],
                confidence=0.95,
            )
        ],
        column_definition=ColumnDefinition(
            grouping_label="RA status",
            grouping_name="RA status",
            columns=[
                DefinedColumn(
                    col_idx=1,
                    column_name="Overall",
                    column_label="Overall",
                    inferred_role="overall",
                    grouping_variable_hint="RA status",
                    confidence=0.95,
                )
            ],
            confidence=0.95,
        ),
        notes=["deterministic_baseline"],
        overall_confidence=0.95,
    )

    dumped = definition.model_dump(mode="json")

    assert dumped["variables"][0]["levels"][0]["level_label"] == "Male"
    assert dumped["column_definition"]["columns"][0]["inferred_role"] == "overall"


def test_column_header_schema_creation_and_serialization() -> None:
    """ColumnHeaderSchema should serialize flat leaf/group/relationship records."""
    schema = ColumnHeaderSchema(
        schema_id="tbl-1:column_header_schema",
        table_id="tbl-1",
        n_cols=3,
        header_rows_considered=[0, 1],
        body_rows_considered=[2],
        leaf_header_row_idx=1,
        leaves=[
            ColumnHeaderLeaf(
                leaf_id="leaf-1",
                table_id="tbl-1",
                col_idx=1,
                leaf_header_row_idx=1,
                leaf_label="Q1",
                leaf_name="Q1",
                evidence_ids=["evidence-1"],
            )
        ],
        groups=[
            ColumnHeaderGroup(
                group_id="group-1",
                table_id="tbl-1",
                row_idx=0,
                label="Cobalt quartile",
                name="Cobalt quartile",
                col_start=1,
                col_end=1,
                leaf_col_indices=[1],
                evidence_ids=["evidence-0"],
                inference_rule="single_leaf_group",
            )
        ],
        relationships=[
            ColumnHeaderRelationship(
                relationship_id="relationship-1",
                table_id="tbl-1",
                parent_group_id="group-1",
                child_leaf_id="leaf-1",
                leaf_col_idx=1,
                evidence_ids=["evidence-0", "evidence-1"],
            )
        ],
        evidence=[
            ColumnHeaderCellEvidence(
                evidence_id="evidence-0",
                table_id="tbl-1",
                row_idx=0,
                col_idx=1,
                cleaned_text="Cobalt quartile",
                source="normalized_cleaned_row",
            ),
            ColumnHeaderCellEvidence(
                evidence_id="evidence-1",
                table_id="tbl-1",
                row_idx=1,
                col_idx=1,
                cleaned_text="Q1",
                bbox=(10.0, 0.0, 20.0, 8.0),
                source="extracted_cell",
            ),
        ],
    )

    dumped = schema.model_dump(mode="json")

    assert dumped["leaves"][0]["leaf_label"] == "Q1"
    assert dumped["groups"][0]["inference_rule"] == "single_leaf_group"
    assert dumped["evidence"][1]["bbox"] == [10.0, 0.0, 20.0, 8.0]


def test_table_profile_creation_and_serialization() -> None:
    """TableProfile schemas should serialize deterministic route decisions correctly."""
    profile = TableProfile(
        table_id="tbl-route",
        title="Table 1",
        caption="Baseline characteristics",
        table_family="descriptive_characteristics",
        family_confidence=0.9,
        evidence=["title_or_caption_mentions_characteristics"],
        notes=["baseline_route"],
    )

    dumped = profile.model_dump(mode="json")

    assert dumped["table_family"] == "descriptive_characteristics"


def test_table_processing_status_creation_and_serialization() -> None:
    """Table processing status schemas should serialize rescue attempts cleanly."""
    status = TableProcessingStatus(
        table_id="tbl-status",
        status="failed",
        failure_stage="table_definition",
        failure_reason="no_variables_for_descriptive_table",
        attempts=[
            TableProcessingAttempt(
                stage="table_definition",
                name="deterministic_definition",
                considered=True,
                ran=True,
                succeeded=False,
                note="variables=0, usable_columns=1",
            )
        ],
        notes=["parse_failed:no_variables_for_descriptive_table"],
    )

    dumped = status.model_dump(mode="json")

    assert dumped["status"] == "failed"
    assert dumped["attempts"][0]["name"] == "deterministic_definition"


def test_llm_variable_plausibility_monitoring_creation_and_serialization() -> None:
    """Variable-plausibility LLM monitoring schemas should serialize debug timing cleanly."""
    report = LLMVariablePlausibilityMonitoringReport(
        report_timestamp="2026-03-24T10:15:00Z",
        provider="openai",
        model="gpt-4.1-mini",
        items=[
            LLMVariablePlausibilityCallRecord(
                table_id="tbl-1",
                table_index=0,
                table_family="descriptive_characteristics",
                eligible_for_review=True,
                status="success",
                elapsed_seconds=12.4,
                deterministic_variable_count=3,
                attached_level_count=2,
                prompt_char_count=1800,
                response_char_count=900,
            )
        ],
    )

    dumped = report.model_dump(mode="json")

    assert dumped["items"][0]["status"] == "success"
    assert dumped["items"][0]["elapsed_seconds"] == 12.4


def test_document_context_schemas_create_without_llm_logic() -> None:
    """Document-context schemas should serialize cleanly."""
    section = PaperSection(
        section_id="section_0",
        order=0,
        heading="Methods",
        level=1,
        role_hint="methods_like",
        content="Study population and covariates.",
    )
    context = TableContext(
        table_id="tbl-1",
        table_index=0,
        table_label="Table 2",
        title="Table 2",
        caption="Baseline characteristics by DKD status",
        row_terms=["Age"],
        column_terms=["Non-DKD", "DKD"],
        grouping_terms=["DKD status"],
        methods_like_section_ids=["section_0"],
        reference_ids=["paper_ref:section_0:p0:r0"],
        resolved_visual_ids=["paper_visual:table:2"],
        passages=[
            RetrievedPassage(
                passage_id="section_0_p0",
                section_id="section_0",
                heading="Methods",
                text="Age and DKD status were collected.",
                match_type="methods_term_match",
                score=0.8,
            )
        ],
    )

    assert section.model_dump()["role_hint"] == "methods_like"
    assert context.model_dump(mode="json")["passages"][0]["match_type"] == "methods_term_match"
    assert context.model_dump(mode="json")["reference_ids"] == ["paper_ref:section_0:p0:r0"]


def test_paper_visual_reference_schemas_serialize_cleanly() -> None:
    """Paper visual-reference schemas should stay explicit and JSON-serializable."""
    visual = PaperVisual(
        visual_id="paper_visual:figure:2",
        visual_kind="figure",
        label="Figure 2",
        number="2",
        caption="Figure 2. Study flow.",
        caption_source="markdown_caption",
        confidence=0.8,
        text_reference_ids=["paper_ref:section_0:p0:r0"],
        reference_check_status="referenced_in_text",
    )
    reference = PaperVisualReference(
        reference_id="paper_ref:section_0:p0:r0",
        reference_kind="figure",
        reference_label="Figure 2",
        reference_number="2",
        matched_text="Figure 2",
        section_id="section_0",
        heading="Results",
        role_hint="results_like",
        paragraph_index=0,
        start_char=32,
        end_char=40,
        anchor_text="The study selection process is shown in Figure 2.",
        resolved_visual_id="paper_visual:figure:2",
        resolution_status="resolved",
    )

    assert visual.model_dump(mode="json")["visual_kind"] == "figure"
    assert visual.model_dump(mode="json")["reference_check_status"] == "referenced_in_text"
    assert reference.model_dump(mode="json")["resolution_status"] == "resolved"


def test_paper_variable_inventory_schema_serializes_cleanly() -> None:
    """Paper variable inventory schemas should stay explicit and JSON-serializable."""
    inventory = PaperVariableInventory(
        paper_id="paper",
        mentions=[
            VariableMention(
                mention_id="mention_0",
                raw_label="Age, years",
                normalized_label="Age years",
                source_type="text_based",
                mention_role="variable",
                canonical_label="Age",
                section_id="section_0",
                heading="Abstract",
                role_hint="abstract_like",
                paragraph_index=0,
                evidence_text="Age, years was assessed.",
                priority_weight=1.0,
                confidence=0.92,
            )
        ],
        candidates=[
            VariableCandidate(
                candidate_id="candidate_0",
                preferred_label="Age",
                canonical_label="Age",
                normalized_label="age",
                canonical_label_source="deterministic_variable_name",
                promotion_basis="priority_text_support",
                alternate_labels=["Age years"],
                supporting_mention_ids=["mention_0"],
                source_types=["text_based"],
                section_ids=["section_0"],
                section_role_hints=["abstract_like"],
                table_ids=[],
                table_indices=[],
                text_support_count=1,
                table_support_count=0,
                caption_support_count=0,
                filtered_mention_count=0,
                priority_score=1.0,
                confidence=0.92,
                interpretation_status="uninterpreted",
            )
        ],
    )

    dumped = inventory.model_dump(mode="json")

    assert dumped["mentions"][0]["source_type"] == "text_based"
    assert dumped["mentions"][0]["mention_role"] == "variable"
    assert dumped["candidates"][0]["preferred_label"] == "Age"


def test_schema_validation_rejects_invalid_confidence() -> None:
    """Confidence fields should enforce the expected range."""
    with pytest.raises(ValidationError):
        TableCell(row_idx=0, col_idx=0, text="Age", confidence=1.5)
