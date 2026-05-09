"""Backend-agnostic layout fallback tests."""

from __future__ import annotations

from table1_parser.extract.layout_fallback import (
    _build_rows_from_line_segment,
    build_text_layout_candidates,
    detect_horizontal_rules,
)


def test_build_text_layout_candidates_detects_unruled_table() -> None:
    """Layout fallback should reconstruct a captioned unruled table from words alone."""
    words = [
        {"text": "Table1", "x0": 50.0, "x1": 90.0, "top": 60.0, "bottom": 68.0},
        {"text": "Baselinecharacteristics", "x0": 50.0, "x1": 220.0, "top": 72.0, "bottom": 80.0},
        {"text": "Q1", "x0": 240.0, "x1": 250.0, "top": 86.0, "bottom": 94.0},
        {"text": "Q2", "x0": 300.0, "x1": 310.0, "top": 86.0, "bottom": 94.0},
        {"text": "Variable", "x0": 50.0, "x1": 110.0, "top": 96.0, "bottom": 104.0},
        {"text": "All", "x0": 180.0, "x1": 195.0, "top": 96.0, "bottom": 104.0},
        {"text": "0.12", "x0": 240.0, "x1": 260.0, "top": 96.0, "bottom": 104.0},
        {"text": "0.13-0.14", "x0": 300.0, "x1": 340.0, "top": 96.0, "bottom": 104.0},
        {"text": "Age", "x0": 50.0, "x1": 70.0, "top": 110.0, "bottom": 118.0},
        {"text": "52.1", "x0": 180.0, "x1": 200.0, "top": 110.0, "bottom": 118.0},
        {"text": "49.8", "x0": 240.0, "x1": 260.0, "top": 110.0, "bottom": 118.0},
        {"text": "53.7", "x0": 300.0, "x1": 320.0, "top": 110.0, "bottom": 118.0},
    ]

    candidates = build_text_layout_candidates(page_num=1, page_text="Table1\nBaselinecharacteristics", words=words)

    assert len(candidates) == 1
    assert candidates[0].caption == "Table1\nBaselinecharacteristics"
    assert candidates[0].metadata["layout_source"] == "text_positions"
    assert candidates[0].raw_rows[0][2:4] == ["Q1", "Q2"]


def test_build_text_layout_candidates_trims_footer_text_after_value_rows() -> None:
    """Text-position fallback should stop before page footer text after the table body."""
    words = [
        {"text": "Table", "x0": 50.0, "x1": 76.0, "top": 60.0, "bottom": 68.0},
        {"text": "1.", "x0": 80.0, "x1": 90.0, "top": 60.0, "bottom": 68.0},
        {"text": "Periodontal", "x0": 94.0, "x1": 150.0, "top": 60.0, "bottom": 68.0},
        {"text": "status.", "x0": 154.0, "x1": 190.0, "top": 60.0, "bottom": 68.0},
        {"text": "Characteristics", "x0": 50.0, "x1": 120.0, "top": 88.0, "bottom": 96.0},
        {"text": "n", "x0": 180.0, "x1": 186.0, "top": 88.0, "bottom": 96.0},
        {"text": "%", "x0": 230.0, "x1": 238.0, "top": 88.0, "bottom": 96.0},
        {"text": "SE", "x0": 280.0, "x1": 292.0, "top": 88.0, "bottom": 96.0},
        {"text": "Total", "x0": 50.0, "x1": 72.0, "top": 102.0, "bottom": 110.0},
        {"text": "3743", "x0": 180.0, "x1": 202.0, "top": 102.0, "bottom": 110.0},
        {"text": "46.1", "x0": 230.0, "x1": 252.0, "top": 102.0, "bottom": 110.0},
        {"text": "1.7", "x0": 280.0, "x1": 296.0, "top": 102.0, "bottom": 110.0},
        {"text": "Age", "x0": 50.0, "x1": 70.0, "top": 116.0, "bottom": 124.0},
        {"text": "435", "x0": 180.0, "x1": 198.0, "top": 116.0, "bottom": 124.0},
        {"text": "24.4", "x0": 230.0, "x1": 252.0, "top": 116.0, "bottom": 124.0},
        {"text": "2.7", "x0": 280.0, "x1": 296.0, "top": 116.0, "bottom": 124.0},
        {"text": "Sex", "x0": 50.0, "x1": 66.0, "top": 130.0, "bottom": 138.0},
        {"text": "1872", "x0": 180.0, "x1": 202.0, "top": 130.0, "bottom": 138.0},
        {"text": "56.4", "x0": 230.0, "x1": 252.0, "top": 130.0, "bottom": 138.0},
        {"text": "2.1", "x0": 280.0, "x1": 296.0, "top": 130.0, "bottom": 138.0},
        {"text": "Downloaded", "x0": 50.0, "x1": 104.0, "top": 214.0, "bottom": 222.0},
        {"text": "from", "x0": 110.0, "x1": 130.0, "top": 214.0, "bottom": 222.0},
        {"text": "https://example.org/10.1902", "x0": 136.0, "x1": 260.0, "top": 214.0, "bottom": 222.0},
        {"text": "Online", "x0": 266.0, "x1": 300.0, "top": 214.0, "bottom": 222.0},
    ]

    candidates = build_text_layout_candidates(page_num=1, page_text="Table 1. Periodontal status.", words=words)

    assert len(candidates) == 1
    assert len(candidates[0].raw_rows) == 4
    assert all("Downloaded" not in " ".join(row) for row in candidates[0].raw_rows)
    assert candidates[0].metadata["trailing_non_table_rows"]["reasons"] == [
        "large_gap_after_last_value_row"
    ]


def test_text_layout_fallback_ignores_repeated_numeric_label_tokens_as_value_anchors() -> None:
    """Numeric-looking label text should not create extra value columns in collapsed grids."""
    lines = [
        {
            "top": 98.0,
            "bottom": 106.0,
            "words": [
                {"text": "Variables", "x0": 56.0, "x1": 90.0, "top": 98.0, "bottom": 106.0},
                {"text": "Overall", "x0": 213.0, "x1": 240.0, "top": 98.0, "bottom": 106.0},
                {"text": "NO", "x0": 312.0, "x1": 324.0, "top": 98.0, "bottom": 106.0},
                {"text": "YES", "x0": 410.0, "x1": 428.0, "top": 98.0, "bottom": 106.0},
                {"text": "P-value", "x0": 509.0, "x1": 540.0, "top": 98.0, "bottom": 106.0},
            ],
        },
        {
            "top": 122.0,
            "bottom": 130.0,
            "words": [
                {"text": "No", "x0": 56.0, "x1": 66.0, "top": 122.0, "bottom": 130.0},
                {"text": "6313", "x0": 213.0, "x1": 236.0, "top": 122.0, "bottom": 130.0},
                {"text": "5646", "x0": 312.0, "x1": 336.0, "top": 122.0, "bottom": 130.0},
                {"text": "667", "x0": 410.0, "x1": 426.0, "top": 122.0, "bottom": 130.0},
            ],
        },
        {
            "top": 134.0,
            "bottom": 142.0,
            "words": [
                {"text": "Antihyperglycemic", "x0": 56.0, "x1": 124.0, "top": 134.0, "bottom": 142.0},
                {"text": "drug", "x0": 126.0, "x1": 142.0, "top": 134.0, "bottom": 142.0},
                {"text": "use", "x0": 146.0, "x1": 160.0, "top": 134.0, "bottom": 142.0},
                {"text": "status,", "x0": 162.0, "x1": 184.0, "top": 134.0, "bottom": 142.0},
                {"text": "n", "x0": 186.0, "x1": 190.0, "top": 134.0, "bottom": 142.0},
                {"text": "(%)", "x0": 192.0, "x1": 206.0, "top": 134.0, "bottom": 142.0},
                {"text": "<0.001", "x0": 509.0, "x1": 538.0, "top": 134.0, "bottom": 142.0},
            ],
        },
        {
            "top": 146.0,
            "bottom": 154.0,
            "words": [
                {"text": "Yes", "x0": 56.0, "x1": 68.0, "top": 146.0, "bottom": 154.0},
                {"text": "147", "x0": 213.0, "x1": 230.0, "top": 146.0, "bottom": 154.0},
                {"text": "126", "x0": 312.0, "x1": 328.0, "top": 146.0, "bottom": 154.0},
                {"text": "21", "x0": 410.0, "x1": 422.0, "top": 146.0, "bottom": 154.0},
            ],
        },
        {
            "top": 158.0,
            "bottom": 166.0,
            "words": [
                {"text": "HEI2020,", "x0": 56.0, "x1": 94.0, "top": 158.0, "bottom": 166.0},
                {"text": "Median", "x0": 98.0, "x1": 126.0, "top": 158.0, "bottom": 166.0},
                {"text": "(Q1-Q3)", "x0": 128.0, "x1": 162.0, "top": 158.0, "bottom": 166.0},
                {"text": "49.71", "x0": 213.0, "x1": 238.0, "top": 158.0, "bottom": 166.0},
                {"text": "49.84", "x0": 312.0, "x1": 338.0, "top": 158.0, "bottom": 166.0},
                {"text": "48.63", "x0": 410.0, "x1": 436.0, "top": 158.0, "bottom": 166.0},
                {"text": "0.162", "x0": 509.0, "x1": 532.0, "top": 158.0, "bottom": 166.0},
            ],
        },
    ]

    rows = _build_rows_from_line_segment(lines)

    assert all(len(row) == 5 for row in rows)
    assert rows[2] == ["Antihyperglycemic drug use status, n (%)", "", "", "", "<0.001"]
    assert rows[4][0].startswith("HEI2020, Median")


def test_text_layout_fallback_restores_spaces_in_collapsed_first_column_tokens() -> None:
    """Fallback extraction should restore readable spacing from char gaps in first-column labels."""
    words = [
        {"text": "Q1", "x0": 220.0, "x1": 235.0, "top": 96.0, "bottom": 104.0},
        {"text": "Q2", "x0": 280.0, "x1": 295.0, "top": 96.0, "bottom": 104.0},
        {"text": "Familypoverty-incomeratio,n(%)", "x0": 50.0, "x1": 150.0, "top": 110.0, "bottom": 118.0},
        {"text": "100", "x0": 220.0, "x1": 235.0, "top": 110.0, "bottom": 118.0},
        {"text": "120", "x0": 280.0, "x1": 295.0, "top": 110.0, "bottom": 118.0},
    ]
    chars = [
        {"text": "F", "x0": 50.0, "x1": 53.0, "top": 110.0, "bottom": 118.0},
        {"text": "a", "x0": 53.0, "x1": 56.0, "top": 110.0, "bottom": 118.0},
        {"text": "m", "x0": 56.0, "x1": 60.0, "top": 110.0, "bottom": 118.0},
        {"text": "i", "x0": 60.0, "x1": 61.5, "top": 110.0, "bottom": 118.0},
        {"text": "l", "x0": 61.5, "x1": 63.0, "top": 110.0, "bottom": 118.0},
        {"text": "y", "x0": 63.0, "x1": 66.0, "top": 110.0, "bottom": 118.0},
        {"text": "p", "x0": 69.0, "x1": 72.0, "top": 110.0, "bottom": 118.0},
        {"text": "o", "x0": 72.0, "x1": 75.0, "top": 110.0, "bottom": 118.0},
        {"text": "v", "x0": 75.0, "x1": 78.0, "top": 110.0, "bottom": 118.0},
        {"text": "e", "x0": 78.0, "x1": 81.0, "top": 110.0, "bottom": 118.0},
        {"text": "r", "x0": 81.0, "x1": 83.0, "top": 110.0, "bottom": 118.0},
        {"text": "t", "x0": 83.0, "x1": 85.0, "top": 110.0, "bottom": 118.0},
        {"text": "y", "x0": 85.0, "x1": 88.0, "top": 110.0, "bottom": 118.0},
        {"text": "-", "x0": 88.0, "x1": 90.0, "top": 110.0, "bottom": 118.0},
        {"text": "i", "x0": 90.0, "x1": 91.5, "top": 110.0, "bottom": 118.0},
        {"text": "n", "x0": 91.5, "x1": 94.5, "top": 110.0, "bottom": 118.0},
        {"text": "c", "x0": 94.5, "x1": 97.5, "top": 110.0, "bottom": 118.0},
        {"text": "o", "x0": 97.5, "x1": 100.5, "top": 110.0, "bottom": 118.0},
        {"text": "m", "x0": 100.5, "x1": 104.5, "top": 110.0, "bottom": 118.0},
        {"text": "e", "x0": 104.5, "x1": 107.5, "top": 110.0, "bottom": 118.0},
        {"text": "r", "x0": 110.5, "x1": 112.5, "top": 110.0, "bottom": 118.0},
        {"text": "a", "x0": 112.5, "x1": 115.5, "top": 110.0, "bottom": 118.0},
        {"text": "t", "x0": 115.5, "x1": 117.5, "top": 110.0, "bottom": 118.0},
        {"text": "i", "x0": 117.5, "x1": 119.0, "top": 110.0, "bottom": 118.0},
        {"text": "o", "x0": 119.0, "x1": 122.0, "top": 110.0, "bottom": 118.0},
        {"text": ",", "x0": 122.0, "x1": 123.5, "top": 110.0, "bottom": 118.0},
        {"text": "n", "x0": 126.5, "x1": 129.5, "top": 110.0, "bottom": 118.0},
        {"text": "(", "x0": 132.5, "x1": 134.0, "top": 110.0, "bottom": 118.0},
        {"text": "%", "x0": 134.0, "x1": 138.0, "top": 110.0, "bottom": 118.0},
        {"text": ")", "x0": 138.0, "x1": 139.5, "top": 110.0, "bottom": 118.0},
    ]

    rows = _build_rows_from_line_segment([{"top": 96.0, "bottom": 104.0, "words": words[:2]}, {"top": 110.0, "bottom": 118.0, "words": words[2:]}], page_chars=chars)

    assert rows[1][0].startswith("Family poverty-income ratio, n (%)")


def test_text_layout_fallback_restores_short_collapsed_category_labels() -> None:
    """Fallback extraction should restore spaces in shorter first-column category labels."""
    other_word = {"text": "Otherrace", "x0": 50.0, "x1": 96.0, "top": 98.0, "bottom": 106.0}
    mexican_word = {"text": "MexicanAmerican", "x0": 50.0, "x1": 122.0, "top": 112.0, "bottom": 120.0}
    chars = [
        {"text": "O", "x0": 50.0, "x1": 54.0, "top": 98.0, "bottom": 106.0},
        {"text": "t", "x0": 54.0, "x1": 56.0, "top": 98.0, "bottom": 106.0},
        {"text": "h", "x0": 56.0, "x1": 60.0, "top": 98.0, "bottom": 106.0},
        {"text": "e", "x0": 60.0, "x1": 64.0, "top": 98.0, "bottom": 106.0},
        {"text": "r", "x0": 64.0, "x1": 67.0, "top": 98.0, "bottom": 106.0},
        {"text": "r", "x0": 70.0, "x1": 73.0, "top": 98.0, "bottom": 106.0},
        {"text": "a", "x0": 73.0, "x1": 77.0, "top": 98.0, "bottom": 106.0},
        {"text": "c", "x0": 77.0, "x1": 81.0, "top": 98.0, "bottom": 106.0},
        {"text": "e", "x0": 81.0, "x1": 85.0, "top": 98.0, "bottom": 106.0},
        {"text": "M", "x0": 50.0, "x1": 56.0, "top": 112.0, "bottom": 120.0},
        {"text": "e", "x0": 56.0, "x1": 60.0, "top": 112.0, "bottom": 120.0},
        {"text": "x", "x0": 60.0, "x1": 64.0, "top": 112.0, "bottom": 120.0},
        {"text": "i", "x0": 64.0, "x1": 66.0, "top": 112.0, "bottom": 120.0},
        {"text": "c", "x0": 66.0, "x1": 70.0, "top": 112.0, "bottom": 120.0},
        {"text": "a", "x0": 70.0, "x1": 74.0, "top": 112.0, "bottom": 120.0},
        {"text": "n", "x0": 74.0, "x1": 78.0, "top": 112.0, "bottom": 120.0},
        {"text": "A", "x0": 81.0, "x1": 87.0, "top": 112.0, "bottom": 120.0},
        {"text": "m", "x0": 87.0, "x1": 93.0, "top": 112.0, "bottom": 120.0},
        {"text": "e", "x0": 93.0, "x1": 97.0, "top": 112.0, "bottom": 120.0},
        {"text": "r", "x0": 97.0, "x1": 100.0, "top": 112.0, "bottom": 120.0},
        {"text": "i", "x0": 100.0, "x1": 102.0, "top": 112.0, "bottom": 120.0},
        {"text": "c", "x0": 102.0, "x1": 106.0, "top": 112.0, "bottom": 120.0},
        {"text": "a", "x0": 106.0, "x1": 110.0, "top": 112.0, "bottom": 120.0},
        {"text": "n", "x0": 110.0, "x1": 114.0, "top": 112.0, "bottom": 120.0},
    ]
    lines = [
        {"top": 84.0, "bottom": 92.0, "words": [{"text": "Race", "x0": 50.0, "x1": 90.0, "top": 84.0, "bottom": 92.0}, {"text": "Overall", "x0": 220.0, "x1": 260.0, "top": 84.0, "bottom": 92.0}]},
        {"top": 98.0, "bottom": 106.0, "words": [other_word, {"text": "10", "x0": 220.0, "x1": 232.0, "top": 98.0, "bottom": 106.0}]},
        {"top": 112.0, "bottom": 120.0, "words": [mexican_word, {"text": "12", "x0": 220.0, "x1": 232.0, "top": 112.0, "bottom": 120.0}]},
    ]

    rows = _build_rows_from_line_segment(lines, page_chars=chars)

    assert rows[1][0].startswith("Other race")
    assert rows[2][0].startswith("Mexican American")


def test_text_layout_fallback_restores_shifted_label_column_tokens() -> None:
    """Collapsed labels should still be restored when extraction shifts the row-label column right by one."""
    chars = [
        {"text": "O", "x0": 132.0, "x1": 136.0, "top": 98.0, "bottom": 106.0},
        {"text": "t", "x0": 136.0, "x1": 138.0, "top": 98.0, "bottom": 106.0},
        {"text": "h", "x0": 138.0, "x1": 142.0, "top": 98.0, "bottom": 106.0},
        {"text": "e", "x0": 142.0, "x1": 146.0, "top": 98.0, "bottom": 106.0},
        {"text": "r", "x0": 146.0, "x1": 149.0, "top": 98.0, "bottom": 106.0},
        {"text": "r", "x0": 152.0, "x1": 155.0, "top": 98.0, "bottom": 106.0},
        {"text": "a", "x0": 155.0, "x1": 159.0, "top": 98.0, "bottom": 106.0},
        {"text": "c", "x0": 159.0, "x1": 163.0, "top": 98.0, "bottom": 106.0},
        {"text": "e", "x0": 163.0, "x1": 167.0, "top": 98.0, "bottom": 106.0},
        {"text": "M", "x0": 132.0, "x1": 138.0, "top": 112.0, "bottom": 120.0},
        {"text": "e", "x0": 138.0, "x1": 142.0, "top": 112.0, "bottom": 120.0},
        {"text": "x", "x0": 142.0, "x1": 146.0, "top": 112.0, "bottom": 120.0},
        {"text": "i", "x0": 146.0, "x1": 148.0, "top": 112.0, "bottom": 120.0},
        {"text": "c", "x0": 148.0, "x1": 152.0, "top": 112.0, "bottom": 120.0},
        {"text": "a", "x0": 152.0, "x1": 156.0, "top": 112.0, "bottom": 120.0},
        {"text": "n", "x0": 156.0, "x1": 160.0, "top": 112.0, "bottom": 120.0},
        {"text": "A", "x0": 163.0, "x1": 169.0, "top": 112.0, "bottom": 120.0},
        {"text": "m", "x0": 169.0, "x1": 175.0, "top": 112.0, "bottom": 120.0},
        {"text": "e", "x0": 175.0, "x1": 179.0, "top": 112.0, "bottom": 120.0},
        {"text": "r", "x0": 179.0, "x1": 182.0, "top": 112.0, "bottom": 120.0},
        {"text": "i", "x0": 182.0, "x1": 184.0, "top": 112.0, "bottom": 120.0},
        {"text": "c", "x0": 184.0, "x1": 188.0, "top": 112.0, "bottom": 120.0},
        {"text": "a", "x0": 188.0, "x1": 192.0, "top": 112.0, "bottom": 120.0},
        {"text": "n", "x0": 192.0, "x1": 196.0, "top": 112.0, "bottom": 120.0},
    ]
    rows = _build_rows_from_line_segment(
        [
            {"top": 84.0, "bottom": 92.0, "words": [{"text": "Overall", "x0": 220.0, "x1": 260.0, "top": 84.0, "bottom": 92.0}, {"text": "Cases", "x0": 300.0, "x1": 340.0, "top": 84.0, "bottom": 92.0}]},
            {"top": 98.0, "bottom": 106.0, "words": [{"text": "Otherrace", "x0": 132.0, "x1": 178.0, "top": 98.0, "bottom": 106.0}, {"text": "10", "x0": 220.0, "x1": 232.0, "top": 98.0, "bottom": 106.0}, {"text": "11", "x0": 300.0, "x1": 312.0, "top": 98.0, "bottom": 106.0}]},
            {"top": 112.0, "bottom": 120.0, "words": [{"text": "MexicanAmerican", "x0": 132.0, "x1": 204.0, "top": 112.0, "bottom": 120.0}, {"text": "12", "x0": 220.0, "x1": 232.0, "top": 112.0, "bottom": 120.0}, {"text": "13", "x0": 300.0, "x1": 312.0, "top": 112.0, "bottom": 120.0}]},
        ],
        page_chars=chars,
    )

    assert rows[1][0].startswith("Other race")
    assert rows[2][0].startswith("Mexican American")


def test_detect_horizontal_rules_merges_fragmented_segments_into_one_boundary() -> None:
    """Collinear rule fragments should count as one wide boundary when coverage is high enough."""
    rules = [
        (40.0, 90.0, 160.0, 90.0),
        (162.0, 91.0, 300.0, 91.0),
        (40.0, 118.0, 180.0, 118.0),
        (182.0, 118.0, 320.0, 118.0),
        (40.0, 156.0, 320.0, 156.0),
    ]

    detected = detect_horizontal_rules(rules, (40.0, 90.0, 320.0, 170.0))

    assert len(detected) == 3
    assert detected[0] == 90.5
    assert detected[1] == 118.0
    assert detected[2] == 156.0
