"""Paper footnote anchor inventory tests."""

from __future__ import annotations

from table1_parser.paper_footnotes import (
    build_paper_footnote_anchor_inventory,
    build_paper_footnote_definition_candidates,
    glyph_fields,
    link_paper_footnotes,
)
from table1_parser.schemas import (
    CellTextAnnotation,
    CellTextAnnotationTable,
    ColumnHeaderLeaf,
    ColumnHeaderSchema,
    ExtractedTable,
    FootnoteAnchor,
    FootnoteDefinition,
    FootnoteDefinitionCandidateLine,
    PaperFootnotes,
    TableCell,
)


def test_build_anchor_inventory_from_cell_annotations_and_captions() -> None:
    """Anchor inventory should preserve cell and caption markers without links."""
    annotation_table = CellTextAnnotationTable(
        table_id="tbl-1",
        page_num=2,
        n_rows=3,
        n_cols=3,
        annotations=[
            CellTextAnnotation(
                row_idx=0,
                col_idx=1,
                text="a",
                annotation_type="superscript",
                attached_to_text="Group",
                bbox=(10.0, 20.0, 12.0, 22.0),
                confidence=0.9,
            ),
            CellTextAnnotation(
                row_idx=1,
                col_idx=0,
                text="†",
                annotation_type="inline_marker",
                attached_to_text="Race",
                confidence=0.65,
            ),
            CellTextAnnotation(
                row_idx=1,
                col_idx=2,
                text="b",
                annotation_type="superscript",
                attached_to_text="<0.001",
                confidence=0.9,
            ),
        ],
        metadata={"coordinate_frame": "page"},
    )
    extracted_table = ExtractedTable(
        table_id="tbl-1",
        source_pdf="paper.pdf",
        page_num=2,
        title="Table 1†",
        caption="Baseline characteristics‡.",
        n_rows=3,
        n_cols=3,
        extraction_backend="pymupdf4llm",
        metadata={"table_number": 1},
    )
    column_schema = ColumnHeaderSchema(
        schema_id="tbl-1:column_header_schema",
        table_id="tbl-1",
        n_cols=3,
        label_col_idx=0,
        header_rows_considered=[0],
        leaves=[
            ColumnHeaderLeaf(
                leaf_id="leaf-0",
                table_id="tbl-1",
                col_idx=0,
                is_row_label_column=True,
                is_value_column=False,
                leaf_label="Variable",
                leaf_name="Variable",
            )
        ],
    )

    footnotes = build_paper_footnote_anchor_inventory(
        paper_id="paper",
        source_pdf="/tmp/paper.pdf",
        cell_text_annotations=[annotation_table],
        extracted_tables=[extracted_table],
        column_header_schemas=[column_schema],
    )

    assert footnotes.definitions == []
    assert footnotes.links == []
    assert footnotes.metadata["anchor_count"] == 5
    assert [anchor.source_role for anchor in footnotes.anchors[:3]] == ["column_header", "row_label", "body_cell"]
    assert footnotes.anchors[0].glyph_key == "letter:a"
    assert footnotes.anchors[1].glyph_key == "symbol:dagger"
    assert footnotes.anchors[3].source_scope == "table_caption"
    assert footnotes.anchors[3].source_role == "title"
    assert footnotes.anchors[4].source_role == "caption"
    assert footnotes.anchors[0].visual_id == "paper_visual:table:1"


def test_build_anchor_inventory_preserves_unclassified_cell_anchors_without_schema() -> None:
    """Missing column schema should not cause cell anchors to be dropped."""
    annotation_table = CellTextAnnotationTable(
        table_id="tbl-1",
        page_num=2,
        n_rows=1,
        n_cols=1,
        annotations=[
            CellTextAnnotation(
                row_idx=0,
                col_idx=0,
                text="a",
                annotation_type="superscript",
                confidence=0.9,
            )
        ],
    )

    footnotes = build_paper_footnote_anchor_inventory(
        paper_id="paper",
        source_pdf="paper.pdf",
        cell_text_annotations=[annotation_table],
    )

    assert len(footnotes.anchors) == 1
    assert footnotes.anchors[0].source_role is None
    assert footnotes.anchors[0].notes == ["source_role_unclassified:no_column_header_schema"]


def test_build_anchor_inventory_groups_trailing_asterisk_runs() -> None:
    """A final detected asterisk should combine with attached trailing asterisks."""
    annotation_table = CellTextAnnotationTable(
        table_id="tbl-1",
        page_num=1,
        n_rows=1,
        n_cols=1,
        annotations=[
            CellTextAnnotation(
                row_idx=0,
                col_idx=0,
                text="*",
                annotation_type="inline_marker",
                attached_to_text="<0.001**",
                confidence=0.65,
            )
        ],
    )

    footnotes = build_paper_footnote_anchor_inventory(
        paper_id="paper",
        source_pdf="paper.pdf",
        cell_text_annotations=[annotation_table],
    )

    assert footnotes.anchors[0].glyph_raw == "***"
    assert footnotes.anchors[0].glyph_key == "asterisk:3"


def test_build_anchor_inventory_suppresses_math_unit_exponents() -> None:
    """Numeric superscripts in unit notation should not become footnote anchors."""
    annotation_table = CellTextAnnotationTable(
        table_id="tbl-1",
        page_num=1,
        n_rows=2,
        n_cols=2,
        annotations=[
            CellTextAnnotation(
                row_idx=0,
                col_idx=0,
                text="9",
                annotation_type="superscript",
                attached_to_text="RBC, x10",
                confidence=0.9,
            ),
            CellTextAnnotation(
                row_idx=1,
                col_idx=0,
                text="2",
                annotation_type="superscript",
                attached_to_text="eGFR, ml/min/1.73m",
                confidence=0.9,
            ),
            CellTextAnnotation(
                row_idx=1,
                col_idx=1,
                text="1",
                annotation_type="superscript",
                attached_to_text="NHANES",
                confidence=0.9,
            ),
        ],
    )

    footnotes = build_paper_footnote_anchor_inventory(
        paper_id="paper",
        source_pdf="paper.pdf",
        cell_text_annotations=[annotation_table],
    )

    assert footnotes.metadata["math_unit_anchor_suppression_count"] == 2
    assert [anchor.glyph_key for anchor in footnotes.anchors] == ["number:1"]
    assert footnotes.anchors[0].attached_to_text == "NHANES"


def test_build_definition_candidates_from_table_local_and_caption_notes() -> None:
    """Definition extraction should keep table-local and caption-attached note candidates."""
    extracted_table = ExtractedTable(
        table_id="tbl-1",
        source_pdf="paper.pdf",
        page_num=2,
        title="Table 1",
        caption="Baseline characteristics. b Additional caption note.",
        n_rows=2,
        n_cols=2,
        cells=[
            TableCell(row_idx=0, col_idx=0, text="Variable", bbox=(50.0, 100.0, 120.0, 112.0)),
            TableCell(row_idx=0, col_idx=1, text="Overall", bbox=(150.0, 100.0, 220.0, 112.0)),
            TableCell(row_idx=1, col_idx=0, text="Age", bbox=(50.0, 120.0, 120.0, 132.0)),
            TableCell(row_idx=1, col_idx=1, text="52", bbox=(150.0, 120.0, 220.0, 132.0)),
        ],
        extraction_backend="pymupdf4llm",
        metadata={"table_number": 1},
    )
    lines = [
        FootnoteDefinitionCandidateLine(
            line_id="page-2-line-10",
            page_num=2,
            raw_text="a Table-local note text.",
            source_scope="table_note",
            source_id="tbl-1:note:0",
            table_id="tbl-1",
            visual_id="paper_visual:table:1",
            bbox=(52.0, 142.0, 210.0, 152.0),
            page_height=800.0,
            source_artifact="pymupdf4llm_layout",
        )
    ]

    definitions = build_paper_footnote_definition_candidates(lines, [extracted_table])

    assert len(definitions) == 2
    assert definitions[0].source_scope == "table_note"
    assert definitions[0].source_id == "tbl-1:note:0"
    assert definitions[0].definition_text == "Table-local note text."
    assert definitions[0].table_id == "tbl-1"
    assert definitions[0].visual_id == "paper_visual:table:1"
    assert definitions[1].source_scope == "table_caption"
    assert definitions[1].source_id == "tbl-1:caption"
    assert definitions[1].glyph_key == "letter:b"


def test_build_definition_candidates_from_embedded_table_note_markers() -> None:
    """Table notes may define markers after abbreviation prose on the same physical line."""
    extracted_table = ExtractedTable(
        table_id="tbl-1",
        source_pdf="paper.pdf",
        page_num=5,
        title="Table 1",
        caption="Table 1 Baseline characteristics",
        n_rows=2,
        n_cols=2,
        cells=[
            TableCell(row_idx=0, col_idx=0, text="Variable", bbox=(50.0, 100.0, 120.0, 112.0)),
            TableCell(row_idx=0, col_idx=1, text="p", bbox=(500.0, 100.0, 530.0, 112.0)),
            TableCell(row_idx=1, col_idx=0, text="Age", bbox=(50.0, 480.0, 120.0, 492.0)),
            TableCell(row_idx=1, col_idx=1, text="<0.001b", bbox=(500.0, 480.0, 535.0, 492.0)),
        ],
        extraction_backend="pymupdf4llm",
        metadata={"table_number": 1},
    )
    lines = [
        FootnoteDefinitionCandidateLine(
            line_id="page-5-line-12",
            page_num=5,
            raw_text=(
                "significance. a Represents the use of the Chi-square test. "
                "b Represents the use of the Kruskal-Wallis test"
            ),
            source_scope="table_note",
            source_id="tbl-1:note:0",
            table_id="tbl-1",
            visual_id="paper_visual:table:1",
            bbox=(52.0, 540.0, 530.0, 552.0),
            page_height=800.0,
            source_artifact="pymupdf_page_text_lines",
        )
    ]

    definitions = build_paper_footnote_definition_candidates(lines, [extracted_table])

    assert [(definition.glyph_key, definition.definition_text) for definition in definitions] == [
        ("letter:a", "Represents the use of the Chi-square test"),
        ("letter:b", "Represents the use of the Kruskal-Wallis test"),
    ]
    assert {definition.source_scope for definition in definitions} == {"table_note"}
    assert {definition.table_id for definition in definitions} == {"tbl-1"}


def test_build_definition_candidates_from_bracketed_embedded_markers() -> None:
    """Bracketed marker definitions should canonicalize to the visible marker glyph."""
    definitions = build_paper_footnote_definition_candidates(
        [
            FootnoteDefinitionCandidateLine(
                line_id="page-2-line-12",
                page_num=2,
                raw_text="Abbreviations. [a] Chi-square test. [b] Kruskal-Wallis test.",
                source_scope="table_note",
                bbox=(52.0, 540.0, 530.0, 552.0),
            )
        ]
    )

    assert [(definition.glyph_raw, definition.glyph_key) for definition in definitions] == [
        ("a", "letter:a"),
        ("b", "letter:b"),
    ]
    assert definitions[0].definition_text == "Chi-square test"
    assert definitions[1].definition_text == "Kruskal-Wallis test."


def test_build_definition_candidates_from_statistical_star_footer() -> None:
    """Table footer star definitions may be comma-separated after abbreviation prose."""
    extracted_table = ExtractedTable(
        table_id="tbl-1",
        source_pdf="paper.pdf",
        page_num=6,
        title="Table 1",
        caption="Table 1 Baseline characteristics",
        n_rows=2,
        n_cols=2,
        cells=[
            TableCell(row_idx=0, col_idx=0, text="Variable", bbox=(50.0, 100.0, 120.0, 112.0)),
            TableCell(row_idx=0, col_idx=1, text="P value", bbox=(500.0, 100.0, 530.0, 112.0)),
            TableCell(row_idx=1, col_idx=0, text="Age", bbox=(50.0, 460.0, 120.0, 472.0)),
            TableCell(row_idx=1, col_idx=1, text="<0.001***", bbox=(500.0, 460.0, 535.0, 472.0)),
        ],
        extraction_backend="pymupdf4llm",
        metadata={"table_number": 1},
    )
    lines = [
        FootnoteDefinitionCandidateLine(
            line_id="page-6-line-20",
            page_num=6,
            raw_text=(
                "WBC, white blood cell; PLT, platelet. "
                "* P value < 0.05, ** P value < 0.01, *** P value < 0.001"
            ),
            source_scope="table_note",
            source_id="tbl-1:note:0",
            table_id="tbl-1",
            visual_id="paper_visual:table:1",
            bbox=(52.0, 506.0, 530.0, 516.0),
            page_height=800.0,
            source_artifact="pymupdf_page_text_lines",
        )
    ]

    definitions = build_paper_footnote_definition_candidates(lines, [extracted_table])

    assert [(definition.glyph_key, definition.definition_text) for definition in definitions] == [
        ("asterisk:1", "P value < 0.05"),
        ("asterisk:2", "P value < 0.01"),
        ("asterisk:3", "P value < 0.001"),
    ]
    assert {definition.source_scope for definition in definitions} == {"table_note"}
    assert {definition.table_id for definition in definitions} == {"tbl-1"}


def test_build_definition_candidates_from_symbol_footer_without_semantic_body_rule() -> None:
    """Known symbol footer definitions should not depend on the text meaning."""
    definitions = build_paper_footnote_definition_candidates(
        [
            FootnoteDefinitionCandidateLine(
                line_id="page-2-line-10",
                page_num=2,
                raw_text="‡: compared with the reference group.",
                source_scope="table_note",
                bbox=(56.0, 620.0, 260.0, 632.0),
                source_artifact="pymupdf_page_text_lines",
            )
        ]
    )

    assert len(definitions) == 1
    assert definitions[0].glyph_key == "symbol:double_dagger"
    assert definitions[0].definition_text == "compared with the reference group."


def test_definition_candidates_do_not_split_decimal_values_as_numbered_notes() -> None:
    """Decimal-leading table values should not become numbered footnote definitions."""
    definitions = build_paper_footnote_definition_candidates(
        [
            FootnoteDefinitionCandidateLine(
                line_id="page-1-line-1",
                page_num=1,
                raw_text="112.0 [90.0, 138.0]",
                source_scope="table_note",
                bbox=(50.0, 400.0, 180.0, 412.0),
            )
        ]
    )

    assert definitions == []


def test_glyph_fields_canonicalize_common_marker_variants() -> None:
    """Canonical glyph keys should be stable while preserving raw codepoints."""
    assert glyph_fields("A") == ("letter", "letter:a", ["U+0041"])
    assert glyph_fields("ᵃ") == ("letter", "letter:a", ["U+1D43"])
    assert glyph_fields("¹²") == ("number", "number:12", ["U+00B9", "U+00B2"])
    assert glyph_fields("₁") == ("number", "number:1", ["U+2081"])
    assert glyph_fields("＊") == ("asterisk", "asterisk:1", ["U+FF0A"])
    assert glyph_fields("**") == ("asterisk", "asterisk:2", ["U+002A", "U+002A"])
    assert glyph_fields("‡") == ("symbol", "symbol:double_dagger", ["U+2021"])


def test_link_paper_footnotes_prefers_same_table_definition() -> None:
    """Same-table definitions should beat weaker same-page matches."""
    footnotes = PaperFootnotes(
        paper_id="paper",
        source_pdf="paper.pdf",
        anchors=[
            FootnoteAnchor(
                anchor_id="anchor:1",
                glyph_raw="a",
                glyph_key="letter:a",
                glyph_kind="letter",
                glyph_codepoints=["U+0061"],
                source_scope="table_cell",
                source_id="tbl-1:r0:c1",
                page_num=2,
                confidence=0.95,
                table_id="tbl-1",
                visual_id="paper_visual:table:1",
            )
        ],
        definitions=[
            FootnoteDefinition(
                definition_id="definition:page",
                glyph_raw="a",
                glyph_key="letter:a",
                glyph_kind="letter",
                glyph_codepoints=["U+0061"],
                source_scope="page_note",
                source_id="page-note",
                page_num=2,
                raw_text="a Page note.",
                clean_text="a Page note.",
                definition_text="Page note.",
                confidence=0.85,
            ),
            FootnoteDefinition(
                definition_id="definition:table",
                glyph_raw="a",
                glyph_key="letter:a",
                glyph_kind="letter",
                glyph_codepoints=["U+0061"],
                source_scope="table_note",
                source_id="tbl-1:note:0",
                page_num=2,
                raw_text="a Table note.",
                clean_text="a Table note.",
                definition_text="Table note.",
                confidence=0.8,
                table_id="tbl-1",
                visual_id="paper_visual:table:1",
            ),
        ],
    )

    linked = link_paper_footnotes(footnotes)

    assert linked.links[0].link_status == "resolved"
    assert linked.links[0].definition_id == "definition:table"
    assert linked.links[0].scope_distance == "same_table"
    assert linked.links[0].candidate_definition_ids == ["definition:table"]
    assert linked.links[0].link_basis == ["glyph_key_match", "same_table"]
    assert linked.links[0].notes == ["lower_scope_candidate_count:1"]
    assert linked.metadata["resolved_link_count"] == 1


def test_link_paper_footnotes_preserves_ambiguous_same_scope_matches() -> None:
    """Multiple best-scope definitions should remain ambiguous."""
    footnotes = PaperFootnotes(
        paper_id="paper",
        source_pdf="paper.pdf",
        anchors=[
            FootnoteAnchor(
                anchor_id="anchor:1",
                glyph_raw="†",
                glyph_key="symbol:dagger",
                glyph_kind="symbol",
                glyph_codepoints=["U+2020"],
                source_scope="table_cell",
                source_id="tbl-1:r1:c0",
                page_num=3,
                confidence=0.9,
                table_id="tbl-1",
            )
        ],
        definitions=[
            FootnoteDefinition(
                definition_id="definition:1",
                glyph_raw="†",
                glyph_key="symbol:dagger",
                glyph_kind="symbol",
                glyph_codepoints=["U+2020"],
                source_scope="table_note",
                source_id="tbl-1:note:0",
                page_num=3,
                raw_text="† First note.",
                clean_text="† First note.",
                definition_text="First note.",
                confidence=0.85,
                table_id="tbl-1",
            ),
            FootnoteDefinition(
                definition_id="definition:2",
                glyph_raw="†",
                glyph_key="symbol:dagger",
                glyph_kind="symbol",
                glyph_codepoints=["U+2020"],
                source_scope="table_note",
                source_id="tbl-1:note:1",
                page_num=3,
                raw_text="† Second note.",
                clean_text="† Second note.",
                definition_text="Second note.",
                confidence=0.8,
                table_id="tbl-1",
            ),
        ],
    )

    linked = link_paper_footnotes(footnotes)

    assert linked.links[0].link_status == "ambiguous"
    assert linked.links[0].definition_id is None
    assert linked.links[0].scope_distance == "same_table"
    assert linked.links[0].candidate_definition_ids == ["definition:1", "definition:2"]
    assert "multiple_definitions_at_best_scope" in linked.links[0].link_basis
    assert linked.metadata["ambiguous_link_count"] == 1


def test_link_paper_footnotes_preserves_unresolved_anchors() -> None:
    """Anchors with no matching definition should stay visible as unresolved links."""
    footnotes = PaperFootnotes(
        paper_id="paper",
        source_pdf="paper.pdf",
        anchors=[
            FootnoteAnchor(
                anchor_id="anchor:1",
                glyph_raw="b",
                glyph_key="letter:b",
                glyph_kind="letter",
                glyph_codepoints=["U+0062"],
                source_scope="table_cell",
                source_id="tbl-1:r1:c1",
                page_num=1,
                confidence=0.9,
            )
        ],
        definitions=[
            FootnoteDefinition(
                definition_id="definition:1",
                glyph_raw="a",
                glyph_key="letter:a",
                glyph_kind="letter",
                glyph_codepoints=["U+0061"],
                source_scope="page_note",
                source_id="page-note",
                page_num=1,
                raw_text="a Note.",
                clean_text="a Note.",
                definition_text="Note.",
                confidence=0.9,
            )
        ],
    )

    linked = link_paper_footnotes(footnotes)

    assert linked.links[0].link_status == "unresolved"
    assert linked.links[0].definition_id is None
    assert linked.links[0].candidate_definition_ids == []
    assert linked.links[0].link_basis == ["no_matching_glyph_key"]
    assert linked.metadata["unresolved_link_count"] == 1


def test_link_paper_footnotes_does_not_paper_level_link_numeric_row_label_citation() -> None:
    """Numeric row-label citations should not resolve to unrelated table values."""
    footnotes = PaperFootnotes(
        paper_id="paper",
        source_pdf="paper.pdf",
        anchors=[
            FootnoteAnchor(
                anchor_id="anchor:citation",
                glyph_raw="65",
                glyph_key="number:65",
                glyph_kind="number",
                glyph_codepoints=["U+0036", "U+0035"],
                source_scope="table_cell",
                source_id="tbl-1:r10:c0",
                page_num=5,
                confidence=0.9,
                table_id="tbl-1",
                source_role="row_label",
                attached_to_text="NHANES",
            )
        ],
        definitions=[
            FootnoteDefinition(
                definition_id="definition:unrelated-value",
                glyph_raw="65",
                glyph_key="number:65",
                glyph_kind="number",
                glyph_codepoints=["U+0036", "U+0035"],
                source_scope="table_note",
                source_id="tbl-2:note:0",
                page_num=7,
                raw_text="65 (49 - 79)",
                clean_text="65 (49 - 79)",
                definition_text="(49 - 79)",
                confidence=0.75,
                table_id="tbl-2",
            )
        ],
    )

    linked = link_paper_footnotes(footnotes)

    assert linked.links[0].link_status == "unresolved"
    assert linked.links[0].candidate_definition_ids == []
    assert linked.links[0].link_basis == ["numeric_table_cell_anchor_requires_local_definition"]
    assert linked.links[0].notes == ["possible_bibliographic_reference"]
    assert linked.metadata["unresolved_link_count"] == 1
