"""Table-region ownership regression tests."""

from __future__ import annotations

import pytest

from table1_parser.schemas import (
    ExtractedTable,
    PaperTextLine,
    TableBoundaryCandidate,
    TableBoundaryProposal,
    TableCell,
    TablePositionedEvidence,
)
from table1_parser.table_regions import build_table_region


@pytest.mark.parametrize(
    ("image_bbox", "include_following_figure"),
    [
        ((20.0, 60.0, 80.0, 75.0), True),
        ((20.0, -20.0, 80.0, 0.0), False),
    ],
    ids=["below-table-image", "above-table-image"],
)
def test_build_table_region_uses_only_below_table_image_as_footer_barrier(
    image_bbox: tuple[float, float, float, float],
    include_following_figure: bool,
) -> None:
    """A following image stops collection; a preceding image does not suppress it."""
    table_bbox = (0.0, 10.0, 100.0, 40.0)
    orientation_group_id = "page-1-orientation-upright"
    table = ExtractedTable(
        table_id="table-1",
        source_pdf="paper.pdf",
        page_num=1,
        title="Table 1",
        caption="Table 1",
        n_rows=2,
        n_cols=2,
        cells=[
            TableCell(row_idx=0, col_idx=0, text="Variable", page_num=1),
            TableCell(row_idx=0, col_idx=1, text="Group", page_num=1),
            TableCell(row_idx=1, col_idx=0, text="Age", page_num=1),
            TableCell(row_idx=1, col_idx=1, text="52 (10)", page_num=1),
        ],
        extraction_backend="pymupdf",
        metadata={
            "row_bounds": [(12.0, 18.0), (22.0, 36.0)],
            "horizontal_rules": [10.0, 20.0, 40.0],
            "full_width_horizontal_rules": [10.0, 20.0, 40.0],
            "candidate_visual_object_barrier_bbox": image_bbox,
            "table_positioned_evidence": TablePositionedEvidence(
                page_num=1,
                canonical_candidate_bbox=table_bbox,
                orientation_group_id=orientation_group_id,
            ).model_dump(mode="json"),
        },
    )
    proposal = TableBoundaryProposal(
        table_id=table.table_id,
        page_num=1,
        canonical_table_bbox=table_bbox,
        canonical_stub_band=(0.0, 50.0),
        canonical_value_band=(50.0, 100.0),
        canonical_row_bounds=[(12.0, 18.0), (22.0, 36.0)],
        boundary_candidates=[
            TableBoundaryCandidate(
                canonical_y=10.0,
                possible_roles=["table_start"],
                row_after_idx=0,
                table_coverage_fraction=1.0,
            ),
            TableBoundaryCandidate(
                canonical_y=20.0,
                possible_roles=["header_body"],
                row_before_idx=0,
                row_after_idx=1,
                table_coverage_fraction=1.0,
            ),
            TableBoundaryCandidate(
                canonical_y=40.0,
                possible_roles=["table_end"],
                row_before_idx=1,
                table_coverage_fraction=1.0,
            ),
        ],
        credible_rule_geometry=True,
        coherent_positioned_grid=True,
    )
    lines = [
        PaperTextLine(
            line_id="footer-line-1",
            page_num=1,
            block_index=2,
            line_index=0,
            raw_text="Abbreviation definition.",
            text="Abbreviation definition.",
            bbox=(0.0, 43.0, 100.0, 45.0),
            canonical_bbox=(0.0, 43.0, 100.0, 45.0),
            orientation_group_id=orientation_group_id,
            column_index=0,
            column_count=1,
            dominant_font="FooterFont",
            dominant_font_size=8.0,
        ),
        PaperTextLine(
            line_id="footer-line-2",
            page_num=1,
            block_index=2,
            line_index=1,
            raw_text="aValues are presented as n (%).",
            text="aValues are presented as n (%).",
            bbox=(0.0, 49.0, 100.0, 51.0),
            canonical_bbox=(0.0, 49.0, 100.0, 51.0),
            orientation_group_id=orientation_group_id,
            column_index=0,
            column_count=1,
            dominant_font="FooterFont",
            dominant_font_size=8.0,
        ),
    ]
    if include_following_figure:
        lines.extend(
            [
                PaperTextLine(
                    line_id="figure-caption",
                    page_num=1,
                    block_index=3,
                    line_index=0,
                    raw_text="Fig. 2 Same-font caption.",
                    text="Fig. 2 Same-font caption.",
                    bbox=(0.0, 80.0, 45.0, 82.0),
                    canonical_bbox=(0.0, 80.0, 45.0, 82.0),
                    orientation_group_id=orientation_group_id,
                    column_index=0,
                    column_count=1,
                    dominant_font="FooterFont",
                    dominant_font_size=8.0,
                ),
                PaperTextLine(
                    line_id="figure-text-left",
                    page_num=1,
                    block_index=4,
                    line_index=0,
                    raw_text="Left figure text.",
                    text="Left figure text.",
                    bbox=(0.0, 90.0, 30.0, 92.0),
                    canonical_bbox=(0.0, 90.0, 30.0, 92.0),
                    orientation_group_id=orientation_group_id,
                    column_index=0,
                    column_count=2,
                    dominant_font="FooterFont",
                    dominant_font_size=8.0,
                ),
                PaperTextLine(
                    line_id="figure-text-right",
                    page_num=1,
                    block_index=5,
                    line_index=0,
                    raw_text="Right figure text.",
                    text="Right figure text.",
                    bbox=(70.0, 90.0, 100.0, 92.0),
                    canonical_bbox=(70.0, 90.0, 100.0, 92.0),
                    orientation_group_id=orientation_group_id,
                    column_index=1,
                    column_count=2,
                    dominant_font="FooterFont",
                    dominant_font_size=8.0,
                ),
            ]
        )

    region = build_table_region(
        table,
        table_boundary_proposal=proposal,
        positioned_text_lines_by_id={line.line_id: line for line in lines},
        body_text_style=("BodyFont", 10.0),
        paper_space_widths_by_style={("FooterFont", 8.0): [2.0]},
    )

    closing_boundary = proposal.boundary_candidates[-1]
    assert closing_boundary.following_text_line_ids == [
        "footer-line-1",
        "footer-line-2",
    ]
    assert closing_boundary.following_text_bbox == (0.0, 43.0, 100.0, 51.0)
    assert "body_footer" in closing_boundary.possible_roles
    assert region.body_rows == [1]
    assert region.footer_note_rows == []
    assert region.body_footer_rule_y == 40.0
