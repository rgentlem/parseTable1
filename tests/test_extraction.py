"""Extraction layer tests for Phase 2."""

from __future__ import annotations

import json
import sys
from types import ModuleType

import pytest

from table1_parser.extract import build_extractor
from table1_parser.extract import pymupdf4llm_extractor as pymupdf4llm_extractor_module
from table1_parser.extract.layout_fallback import (
    _build_rows_from_line_segment,
    build_row_grid_from_lines,
    build_text_layout_candidates,
    build_word_lines,
)
from table1_parser.extract.pymupdf_page_adapter import extract_page_chars, extract_page_words
from table1_parser.extract.pymupdf4llm_extractor import PyMuPDF4LLMExtractor
from table1_parser.extract.table_detector import (
    DetectedTableCandidate,
    _table_caption_metadata,
    detect_table_candidates,
    score_candidate,
)
from table1_parser.extract.table_selector import select_top_candidates


class FakeRect:
    """Simple page rectangle with PyMuPDF-like width and height attributes."""

    def __init__(self, width: float, height: float) -> None:
        self.width = width
        self.height = height


class FakeCroppedPage:
    """Simple cropped-page test double."""

    def __init__(self, text: str) -> None:
        self._text = text

    def extract_text(self) -> str:
        """Return the cropped text block."""
        return self._text


class FakeTable:
    """Simple legacy table test double."""

    def __init__(
        self,
        rows: list[list[str]],
        bbox: tuple[float, float, float, float] = (10.0, 100.0, 300.0, 220.0),
    ) -> None:
        self._rows = rows
        self.bbox = bbox

    def extract(self) -> list[list[str]]:
        """Return the extracted raw rows."""
        return self._rows


class FakePage:
    """Simple legacy page test double."""

    width = 612.0

    def __init__(
        self,
        text: str,
        tables: list[FakeTable],
        cropped_text: str | None = None,
        words: list[dict[str, object]] | None = None,
        chars: list[dict[str, object]] | None = None,
    ) -> None:
        self._text = text
        self._tables = tables
        self._cropped_text = cropped_text or text
        self._words = words or []
        self.chars = chars or []

    def extract_text(self) -> str:
        """Return page text."""
        return self._text

    def find_tables(self) -> list[FakeTable]:
        """Return preconfigured tables."""
        return self._tables

    def crop(self, _: tuple[float, float, float, float]) -> FakeCroppedPage:
        """Return a cropped page region."""
        return FakeCroppedPage(self._cropped_text)

    def extract_words(self, **_: object) -> list[dict[str, object]]:
        """Return positioned words for text-layout fallback extraction."""
        return self._words


class FakePDF:
    """Simple legacy PDF test double."""

    def __init__(self, pages: list[FakePage]) -> None:
        self.pages = pages

    def __enter__(self) -> FakePDF:
        """Enter the fake context manager."""
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        """Exit the fake context manager."""
        return None


class FakeTableFinder:
    """Simple wrapper mimicking PyMuPDF's TableFinder.tables shape."""

    def __init__(self, tables: list[FakeTable]) -> None:
        self.tables = tables


class FakePyMuPage:
    """Simple PyMuPDF page test double."""

    def __init__(
        self,
        *,
        text: str,
        words: list[dict[str, object]],
        chars: list[dict[str, object]] | None = None,
        rule_segments: list[tuple[float, float, float, float]] | None = None,
        rect: FakeRect | None = None,
        rotation: int = 0,
    ) -> None:
        self.text = text
        self.words = words
        self.chars = chars or []
        self.rule_segments = rule_segments or []
        self.rect = rect
        self.rotation = rotation


class FakePyMuDoc:
    """Simple PyMuPDF document test double."""

    def __init__(self, pages: list[FakePyMuPage]) -> None:
        self._pages = pages
        self.page_count = len(pages)

    def load_page(self, index: int) -> FakePyMuPage:
        return self._pages[index]

    def close(self) -> None:
        return None


@pytest.fixture(autouse=True)
def _install_default_fake_pymupdf_document(monkeypatch) -> None:
    """Keep extraction unit tests from importing the real PyMuPDF bindings by default."""
    _install_fake_pymupdf_document(monkeypatch, [])


def _install_fake_pymupdf4llm(monkeypatch, payload: dict[str, object], *, fail: bool = False) -> None:
    """Install a minimal fake pymupdf4llm module for a test case."""
    module = ModuleType("pymupdf4llm")
    if fail:
        module.to_json = lambda _: (_ for _ in ()).throw(RuntimeError("primary failed"))
    else:
        module.to_json = lambda _: json.dumps(payload)
    monkeypatch.setitem(sys.modules, "pymupdf4llm", module)


def _install_fake_pymupdf4llm_with_stdout(
    monkeypatch,
    payload: dict[str, object],
    message: str,
) -> None:
    """Install a fake pymupdf4llm module that prints to stdout before returning JSON."""
    module = ModuleType("pymupdf4llm")

    def _to_json(_: str) -> str:
        print(message)
        return json.dumps(payload)

    module.to_json = _to_json
    monkeypatch.setitem(sys.modules, "pymupdf4llm", module)


def _install_fake_pymupdf_document(monkeypatch, pages: list[FakePyMuPage]) -> None:
    """Install a fake PyMuPDF document and page adapters for a test case."""
    fake_doc = FakePyMuDoc(pages)
    monkeypatch.setattr(pymupdf4llm_extractor_module, "open_pymupdf_document", lambda _: fake_doc)
    monkeypatch.setattr(pymupdf4llm_extractor_module, "extract_page_text", lambda page: page.text)
    monkeypatch.setattr(pymupdf4llm_extractor_module, "extract_page_words", lambda page: page.words)
    monkeypatch.setattr(pymupdf4llm_extractor_module, "extract_page_chars", lambda page: page.chars)
    monkeypatch.setattr(
        pymupdf4llm_extractor_module,
        "extract_page_rule_segments",
        lambda page, include_filled=True: page.rule_segments,
    )


def test_score_candidate_prefers_table1_like_layout() -> None:
    """Detection should reward Table 1 captions and text-first layouts."""
    candidate = DetectedTableCandidate(
        page_num=1,
        table_index=0,
        raw_rows=[
            ["Variable", "Overall", "P"],
            ["Age", "52.1", "0.03"],
            ["BMI", "27.4", "0.10"],
        ],
        caption="Table 1. Baseline characteristics",
        page_text="Table 1. Baseline characteristics",
        metadata={"is_rectangular": True},
    )

    scored = score_candidate(candidate)

    assert scored.score >= 0.9
    assert scored.metadata["signals"]["caption_match"] is True


def test_score_candidate_uses_embedded_caption_from_collapsed_first_cell() -> None:
    """Single-row collapsed tables should still score when the first cell starts with a caption."""
    candidate = DetectedTableCandidate(
        page_num=9,
        table_index=0,
        raw_rows=[
            [
                "Table 2: Distribution of urinary OPEs metabolites",
                "DPHP\n95.88\n0.74",
                "BDCPP\n93.75\n0.81",
                "BCEP\n82.17\n0.38",
                "DBuP\n51.07\n0.13",
            ]
        ],
        caption=None,
        page_text="",
        metadata={"is_rectangular": False},
    )

    scored = score_candidate(candidate)

    assert scored.caption == "Table 2: Distribution of urinary OPEs metabolites"
    assert scored.metadata["signals"]["caption_match"] is True
    assert scored.score >= 0.8


def test_table_caption_metadata_accepts_pdf_dash_extracted_as_d() -> None:
    """Some rotated captions extract an en dash after the number as a bare d."""
    metadata = _table_caption_metadata("Table 1dCharacteristics of NGT, IGR, or T2D cohort subjects")

    assert metadata is not None
    assert metadata["caption"] == "Table 1. Characteristics of NGT, IGR, or T2D cohort subjects"
    assert metadata["table_number"] == 1
    assert _table_caption_metadata("Table 1 displays baseline values") is None


def test_pymupdf_page_adapter_normalizes_symbol_font_chars_and_words() -> None:
    """Known embedded symbol-font codes should be converted before word/grid reconstruction."""
    raw_chars = [
        {"c": ",", "bbox": (0.0, 0.0, 4.0, 8.0)},
        {"c": "2", "bbox": (5.0, 0.0, 9.0, 8.0)},
        {"c": "3", "bbox": (10.0, 0.0, 14.0, 8.0)},
        {"c": "6", "bbox": (15.0, 0.0, 19.0, 8.0)},
        {"c": "x", "bbox": (20.0, 0.0, 24.0, 8.0)},
    ]

    class FakeSymbolPage:
        def get_text(self, mode: str) -> object:
            if mode == "rawdict":
                return {
                    "blocks": [
                        {
                            "lines": [
                                {
                                    "spans": [
                                        {
                                            "font": "AdvPS586B",
                                            "size": 8.0,
                                            "chars": raw_chars[:4],
                                        },
                                        {
                                            "font": "AdvP4C4E74",
                                            "size": 8.0,
                                            "chars": raw_chars[4:],
                                        },
                                    ]
                                }
                            ]
                        }
                    ]
                }
            if mode == "words":
                return [(0.0, 0.0, 24.0, 8.0, ",236x", 0, 0, 0)]
            return ""

    chars = extract_page_chars(FakeSymbolPage(), page_num=3)
    words = extract_page_words(FakeSymbolPage())

    assert "".join(str(char["text"]) for char in chars) == "<−×±x"
    assert [char.get("raw_text") for char in chars[:4]] == [",", "2", "3", "6"]
    assert all(char.get("text_normalization") == "symbol_font_char_map" for char in chars[:4])
    assert chars[4].get("text_normalization") is None
    assert words[0]["text"] == "<−×±x"


def test_mixed_bbox_rotated_text_block_detector_recovers_vertical_region() -> None:
    """A mixed-orientation backend box should expose its contiguous rotated text block."""
    class FakeMixedOrientationPage:
        def get_text(self, mode: str) -> object:
            if mode != "dict":
                return {}
            return {
                "blocks": [
                    {
                        "type": 0,
                        "bbox": [210.0, 40.0, 430.0, 520.0],
                        "lines": [{"dir": [1.0, 0.0]} for _ in range(8)],
                    },
                    {
                        "type": 0,
                        "bbox": [40.0, 55.0, 175.0, 730.0],
                        "lines": [{"dir": [0.0, 1.0]} for _ in range(6)],
                    },
                ]
            }

    orientation = pymupdf4llm_extractor_module._find_rotated_text_block_in_bbox(
        FakeMixedOrientationPage(),
        (30.0, 30.0, 500.0, 760.0),
    )

    assert orientation is not None
    assert orientation["table_orientation"] == "rotated"
    assert orientation["rotation_direction"] == "vertical_text_down"
    assert orientation["rotation_confidence"] == 1.0
    assert orientation["rotated_text_block_bbox"] == (38.0, 53.0, 177.0, 732.0)


def test_build_extractor_defaults_to_pymupdf4llm() -> None:
    extractor = build_extractor()

    assert isinstance(extractor, PyMuPDF4LLMExtractor)


def test_word_grid_uses_footnoted_p_values_as_column_anchors() -> None:
    """Footnote letters on p-values should not hide a separate rightmost p column."""
    words: list[dict[str, object]] = []
    rows = [
        [(216.0, "Low"), (311.0, "Middle"), (411.0, "High"), (506.0, "p")],
        [(56.0, "Age"), (216.0, "36.0"), (311.0, "44.0"), (411.0, "45.0"), (506.0, "<0.001b")],
        [(56.0, "<65y"), (216.0, "2396"), (311.0, "1772"), (411.0, "1908")],
        [(56.0, "Gender"), (506.0, "<0.001a")],
        [(56.0, "Healthy"), (216.0, "172"), (311.0, "1597"), (411.0, "1540"), (506.0, "<0.001a")],
    ]
    for row_idx, row in enumerate(rows):
        top = 100.0 + row_idx * 14.0
        for x0, text in row:
            words.append({"text": text, "x0": x0, "x1": x0 + max(8.0, len(text) * 4.0), "top": top, "bottom": top + 8.0})

    grid, _ = build_row_grid_from_lines(build_word_lines(words))

    assert grid[0] == ["", "Low", "Middle", "High", "p"]
    assert grid[1] == ["Age", "36.0", "44.0", "45.0", "<0.001b"]
    assert grid[3] == ["Gender", "", "", "", "<0.001a"]


def test_pymupdf4llm_extractor_records_first_column_text_starts(tmp_path, monkeypatch) -> None:
    """Visible first-word x positions should be preserved for indentation inference."""
    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_text("placeholder")
    _install_fake_pymupdf4llm(
        monkeypatch,
        {
            "pages": [
                {
                    "page_number": 1,
                    "boxes": [
                        {
                            "bbox": [34, 80, 260, 96],
                            "boxclass": "text",
                            "textlines": [{"spans": [{"text": "Table 1. Baseline characteristics"}]}],
                        },
                        {
                            "bbox": [34, 120, 280, 160],
                            "boxclass": "table",
                            "table": {
                                "bbox": [34, 120, 280, 160],
                                "extract": [
                                    ["Characteristic", "Overall"],
                                    ["Marital status, n (%)", ""],
                                    ["Married", "10 (50.0)"],
                                ],
                                "cells": [
                                    [[34, 120, 180, 132], [180, 120, 280, 132]],
                                    [[34, 132, 180, 144], [180, 132, 280, 144]],
                                    [[34, 144, 180, 156], [180, 144, 280, 156]],
                                ],
                            },
                        },
                    ],
                }
            ]
        },
    )
    _install_fake_pymupdf_document(
        monkeypatch,
        [
            FakePyMuPage(
                text="Table 1. Baseline characteristics",
                words=[
                    {"text": "Characteristic", "x0": 36.0, "x1": 90.0, "top": 122.0, "bottom": 130.0},
                    {"text": "Overall", "x0": 190.0, "x1": 222.0, "top": 122.0, "bottom": 130.0},
                    {"text": "Marital", "x0": 36.0, "x1": 66.0, "top": 134.0, "bottom": 142.0},
                    {"text": "status", "x0": 68.0, "x1": 92.0, "top": 134.0, "bottom": 142.0},
                    {"text": "Married", "x0": 44.0, "x1": 74.0, "top": 146.0, "bottom": 154.0},
                    {"text": "10", "x0": 190.0, "x1": 202.0, "top": 146.0, "bottom": 154.0},
                ],
            )
        ],
    )

    tables = PyMuPDF4LLMExtractor(max_candidates=3, heuristic_confidence_threshold=0.0).extract(str(pdf_path))

    assert tables[0].metadata["first_column_text_x0_by_row"] == {0: 36.0, 1: 36.0, 2: 44.0}


def test_pymupdf4llm_extractor_returns_empty_on_primary_failure(tmp_path, monkeypatch) -> None:
    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_text("placeholder")
    _install_fake_pymupdf4llm(monkeypatch, {}, fail=True)

    extractor = PyMuPDF4LLMExtractor(max_candidates=3, heuristic_confidence_threshold=0.0)
    tables = extractor.extract(str(pdf_path))

    assert tables == []


def test_pymupdf4llm_extractor_suppresses_library_stdout(tmp_path, monkeypatch, capsys) -> None:
    """Library stdout chatter should not leak into user-visible extractor output."""
    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_text("placeholder")
    _install_fake_pymupdf4llm_with_stdout(
        monkeypatch,
        {"pages": []},
        "OCR disabled because Tesseract language data not found.",
    )

    extractor = PyMuPDF4LLMExtractor(max_candidates=3, heuristic_confidence_threshold=0.0)
    tables = extractor.extract(str(pdf_path))

    captured = capsys.readouterr()
    assert tables == []
    assert captured.out == ""


def test_pymupdf4llm_extractor_refines_rotated_explicit_tables_from_words_and_rules(
    tmp_path,
    monkeypatch,
) -> None:
    """Collapsed rotated explicit tables should be rebuilt in table-local upright coordinates."""
    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_text("placeholder")
    table_bbox = [100.0, 60.0, 280.0, 220.0]

    def to_page_bbox(
        local_x0: float,
        local_top: float,
        local_x1: float,
        local_bottom: float,
    ) -> tuple[float, float, float, float]:
        left, _, _, bottom = table_bbox
        corners = [
            (left + local_top, bottom - local_x0),
            (left + local_top, bottom - local_x1),
            (left + local_bottom, bottom - local_x0),
            (left + local_bottom, bottom - local_x1),
        ]
        return (
            min(point[0] for point in corners),
            min(point[1] for point in corners),
            max(point[0] for point in corners),
            max(point[1] for point in corners),
        )

    upright_words = [
        {"text": "Urinary", "x0": 10.0, "x1": 34.0, "top": 4.0, "bottom": 12.0},
        {"text": "PAH", "x0": 38.0, "x1": 50.0, "top": 4.0, "bottom": 12.0},
        {"text": "Quintile_1", "x0": 70.0, "x1": 92.0, "top": 4.0, "bottom": 12.0},
        {"text": "Quintile_2", "x0": 102.0, "x1": 124.0, "top": 4.0, "bottom": 12.0},
        {"text": "P", "x0": 134.0, "x1": 138.0, "top": 4.0, "bottom": 12.0},
        {"text": "OR", "x0": 70.0, "x1": 78.0, "top": 18.0, "bottom": 26.0},
        {"text": "P", "x0": 88.0, "x1": 92.0, "top": 18.0, "bottom": 26.0},
        {"text": "OR", "x0": 102.0, "x1": 110.0, "top": 18.0, "bottom": 26.0},
        {"text": "P", "x0": 134.0, "x1": 138.0, "top": 18.0, "bottom": 26.0},
        {"text": "Metabolite_A", "x0": 10.0, "x1": 56.0, "top": 36.0, "bottom": 44.0},
        {"text": "Model_1", "x0": 10.0, "x1": 36.0, "top": 48.0, "bottom": 56.0},
        {"text": "Reference", "x0": 70.0, "x1": 96.0, "top": 48.0, "bottom": 56.0},
        {"text": "1.10", "x0": 102.0, "x1": 116.0, "top": 48.0, "bottom": 56.0},
        {"text": "0.200", "x0": 134.0, "x1": 148.0, "top": 48.0, "bottom": 56.0},
        {"text": "Model_2", "x0": 10.0, "x1": 36.0, "top": 60.0, "bottom": 68.0},
        {"text": "Reference", "x0": 70.0, "x1": 96.0, "top": 60.0, "bottom": 68.0},
        {"text": "1.30", "x0": 102.0, "x1": 116.0, "top": 60.0, "bottom": 68.0},
        {"text": "0.040", "x0": 134.0, "x1": 148.0, "top": 60.0, "bottom": 68.0},
    ]
    rotated_words = [
        {
            "text": word["text"],
            "x0": to_page_bbox(word["x0"], word["top"], word["x1"], word["bottom"])[0],
            "x1": to_page_bbox(word["x0"], word["top"], word["x1"], word["bottom"])[2],
            "top": to_page_bbox(word["x0"], word["top"], word["x1"], word["bottom"])[1],
            "bottom": to_page_bbox(word["x0"], word["top"], word["x1"], word["bottom"])[3],
        }
        for word in upright_words
    ]
    rotated_rule_segments = [
        (100.0, 220.0, 100.0, 60.0),
        (130.0, 220.0, 130.0, 60.0),
        (196.0, 220.0, 196.0, 60.0),
    ]
    _install_fake_pymupdf4llm(
        monkeypatch,
        {
            "pages": [
                {
                    "page_number": 1,
                    "boxes": [
                        {
                            "bbox": [100, 36, 340, 52],
                            "boxclass": "text",
                            "textlines": [{"spans": [{"text": "Table 3. Rotated estimates"}]}],
                        },
                        {
                            "bbox": table_bbox,
                            "boxclass": "table",
                            "table": {
                                "bbox": table_bbox,
                                "row_count": 1,
                                "col_count": 3,
                                "extract": [["Header blob", "Body blob", "Note blob"]],
                                "cells": [
                                    [
                                        [100.0, 60.0, 130.0, 220.0],
                                        [130.0, 60.0, 250.0, 220.0],
                                        [250.0, 60.0, 280.0, 220.0],
                                    ]
                                ],
                            },
                        },
                    ],
                }
            ]
        },
    )
    monkeypatch.setattr(
        pymupdf4llm_extractor_module,
        "extract_clipped_line_directions",
        lambda page, clip_bbox: [(0.0, -1.0), (0.0, -1.0), (0.0, -1.0)],
    )
    _install_fake_pymupdf_document(
        monkeypatch,
        [
            FakePyMuPage(
                text="Table 3. Rotated estimates",
                words=rotated_words,
                rule_segments=rotated_rule_segments,
            )
        ],
    )

    tables = PyMuPDF4LLMExtractor(max_candidates=5, heuristic_confidence_threshold=0.0).extract(str(pdf_path))

    assert len(tables) == 1
    assert tables[0].metadata["table_orientation"] == "rotated"
    assert tables[0].metadata["grid_refinement_source"] == "rotated_word_positions_with_rules"
    assert tables[0].metadata["geometry_coordinate_frame"] == "table_local_rotated_normalized"
    assert tables[0].metadata["geometry_transform_source_bbox"] == tuple(table_bbox)
    assert tables[0].metadata["geometry_transform_transposed"] is False
    assert tables[0].metadata["geometry_transform_applied"] is True
    assert tables[0].metadata["explicit_grid_refined_from_words"] is True
    assert tables[0].n_rows >= 5
    assert tables[0].n_cols >= 4
    assert tables[0].metadata["refined_table_cells"] is not None
    assert tables[0].metadata["table_cells"] == tables[0].metadata["refined_table_cells"]
    assert tables[0].cells[0].bbox is not None


def test_pymupdf4llm_extractor_uses_text_layout_fallback_when_json_has_no_tables(
    tmp_path,
    monkeypatch,
) -> None:
    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_text("placeholder")
    _install_fake_pymupdf4llm(
        monkeypatch,
        {
            "pages": [
                {
                    "page_number": 1,
                    "boxes": [
                        {
                            "bbox": [50, 60, 220, 80],
                            "boxclass": "text",
                            "textlines": [{"spans": [{"text": "Table1"}, {"text": "Baselinecharacteristics"}]}],
                        }
                    ],
                }
            ]
        },
    )
    _install_fake_pymupdf_document(
        monkeypatch,
        [
            FakePyMuPage(
                text="Table1\nBaselinecharacteristics\nQ1 Q2",
                words=[
                    {"text": "Table1", "x0": 50.0, "x1": 90.0, "top": 60.0, "bottom": 68.0},
                    {"text": "Baselinecharacteristics", "x0": 50.0, "x1": 220.0, "top": 72.0, "bottom": 80.0},
                    {"text": "Q1", "x0": 220.0, "x1": 235.0, "top": 96.0, "bottom": 104.0},
                    {"text": "Q2", "x0": 280.0, "x1": 295.0, "top": 96.0, "bottom": 104.0},
                    {"text": "Familypoverty-incomeratio,n(%)", "x0": 50.0, "x1": 150.0, "top": 110.0, "bottom": 118.0},
                    {"text": "100", "x0": 220.0, "x1": 235.0, "top": 110.0, "bottom": 118.0},
                    {"text": "120", "x0": 280.0, "x1": 295.0, "top": 110.0, "bottom": 118.0},
                ],
                chars=[
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
                ],
                rule_segments=[(50.0, 94.0, 320.0, 94.0)],
            )
        ],
    )

    tables = PyMuPDF4LLMExtractor(max_candidates=3, heuristic_confidence_threshold=0.0).extract(str(pdf_path))

    assert len(tables) == 1
    assert tables[0].extraction_backend == "pymupdf4llm"
    assert tables[0].metadata["layout_source"] == "pymupdf_text_positions"
    assert tables[0].metadata["fallback_used"] is False
    assert tables[0].metadata["horizontal_rules"] == [94.0]
    cell_map = {(cell.row_idx, cell.col_idx): cell.text for cell in tables[0].cells}
    assert cell_map[(1, 0)].startswith("Family poverty-income ratio, n (%)")


def test_text_layout_candidates_preserve_cell_bboxes_for_indentation() -> None:
    """Text-position fallback should retain first-cell text starts for later indentation inference."""
    words = [
        {"text": "Table", "x0": 50.0, "x1": 76.0, "top": 60.0, "bottom": 68.0},
        {"text": "1.", "x0": 80.0, "x1": 90.0, "top": 60.0, "bottom": 68.0},
        {"text": "Characteristic", "x0": 50.0, "x1": 112.0, "top": 84.0, "bottom": 92.0},
        {"text": "Overall", "x0": 200.0, "x1": 236.0, "top": 84.0, "bottom": 92.0},
        {"text": "Cases", "x0": 260.0, "x1": 288.0, "top": 84.0, "bottom": 92.0},
        {"text": "Controls", "x0": 320.0, "x1": 360.0, "top": 84.0, "bottom": 92.0},
        {"text": "Race", "x0": 50.0, "x1": 74.0, "top": 98.0, "bottom": 106.0},
        {"text": "10", "x0": 200.0, "x1": 212.0, "top": 98.0, "bottom": 106.0},
        {"text": "12", "x0": 260.0, "x1": 272.0, "top": 98.0, "bottom": 106.0},
        {"text": "14", "x0": 320.0, "x1": 332.0, "top": 98.0, "bottom": 106.0},
        {"text": "Male", "x0": 68.0, "x1": 92.0, "top": 112.0, "bottom": 120.0},
        {"text": "4", "x0": 200.0, "x1": 206.0, "top": 112.0, "bottom": 120.0},
        {"text": "6", "x0": 260.0, "x1": 266.0, "top": 112.0, "bottom": 120.0},
        {"text": "8", "x0": 320.0, "x1": 326.0, "top": 112.0, "bottom": 120.0},
        {"text": "Female", "x0": 68.0, "x1": 102.0, "top": 126.0, "bottom": 134.0},
        {"text": "6", "x0": 200.0, "x1": 206.0, "top": 126.0, "bottom": 134.0},
        {"text": "6", "x0": 260.0, "x1": 266.0, "top": 126.0, "bottom": 134.0},
        {"text": "6", "x0": 320.0, "x1": 326.0, "top": 126.0, "bottom": 134.0},
    ]

    candidates = build_text_layout_candidates(
        page_num=1,
        page_text="Table 1. Baseline",
        words=words,
        layout_source="pymupdf_text_positions",
    )

    assert len(candidates) == 1
    assert candidates[0].raw_rows[2][0] == "Male"
    table_cells = candidates[0].metadata["table_cells"]
    assert table_cells[2][0] == (68.0, 112.0, 92.0, 120.0)


def test_text_layout_candidates_keep_lowercase_sentence_fragment_in_caption() -> None:
    """A wrapped lowercase sentence tail belongs to the caption, not row zero."""
    words = [
        {"text": "Table", "x0": 50.0, "x1": 76.0, "top": 60.0, "bottom": 68.0},
        {"text": "1.", "x0": 80.0, "x1": 90.0, "top": 60.0, "bottom": 68.0},
        {"text": "Baseline", "x0": 94.0, "x1": 136.0, "top": 60.0, "bottom": 68.0},
        {"text": "income", "x0": 140.0, "x1": 174.0, "top": 60.0, "bottom": 68.0},
        {"text": "to", "x0": 178.0, "x1": 188.0, "top": 60.0, "bottom": 68.0},
        {"text": "poverty;", "x0": 50.0, "x1": 88.0, "top": 70.0, "bottom": 78.0},
        {"text": "GHGe,", "x0": 92.0, "x1": 124.0, "top": 70.0, "bottom": 78.0},
        {"text": "greenhouse", "x0": 128.0, "x1": 182.0, "top": 70.0, "bottom": 78.0},
        {"text": "gas", "x0": 186.0, "x1": 204.0, "top": 70.0, "bottom": 78.0},
        {"text": "emissions.", "x0": 208.0, "x1": 260.0, "top": 70.0, "bottom": 78.0},
        {"text": "Characteristic", "x0": 50.0, "x1": 112.0, "top": 90.0, "bottom": 98.0},
        {"text": "Q1", "x0": 200.0, "x1": 212.0, "top": 90.0, "bottom": 98.0},
        {"text": "Q2", "x0": 260.0, "x1": 272.0, "top": 90.0, "bottom": 98.0},
        {"text": "Age", "x0": 50.0, "x1": 68.0, "top": 104.0, "bottom": 112.0},
        {"text": "43", "x0": 200.0, "x1": 212.0, "top": 104.0, "bottom": 112.0},
        {"text": "46", "x0": 260.0, "x1": 272.0, "top": 104.0, "bottom": 112.0},
    ]

    candidates = build_text_layout_candidates(
        page_num=1,
        page_text="Table 1. Baseline income to\npoverty; GHGe, greenhouse gas emissions.",
        words=words,
        layout_source="pymupdf_text_positions",
    )

    assert len(candidates) == 1
    assert candidates[0].caption == "Table 1. Baseline income to\npoverty; GHGe, greenhouse gas emissions."
    assert "poverty" not in " ".join(candidates[0].raw_rows[0])
    assert candidates[0].raw_rows[0][0].startswith("Characteristic")


def test_text_layout_grid_prefers_early_stable_value_anchors() -> None:
    """Later noisy rows should not collapse a clear early value-column layout."""
    lines: list[dict[str, object]] = []
    for line_idx in range(4):
        words = [{"text": "Age" if line_idx else "Characteristic", "x0": 10.0, "x1": 50.0, "top": line_idx * 10.0, "bottom": line_idx * 10.0 + 5.0}]
        for col_idx, x0 in enumerate([100.0, 150.0, 200.0, 250.0], start=1):
            words.append({"text": str(10 * line_idx + col_idx), "x0": x0, "x1": x0 + 8.0, "top": line_idx * 10.0, "bottom": line_idx * 10.0 + 5.0})
        lines.append({"text": " ".join(str(word["text"]) for word in words), "words": words})
    for line_idx in range(4, 28):
        words = [{"text": f"Label {line_idx}", "x0": 10.0, "x1": 55.0, "top": line_idx * 10.0, "bottom": line_idx * 10.0 + 5.0}]
        for x0 in [100.0, 166.0, 183.0, 250.0]:
            words.append({"text": str(line_idx), "x0": x0, "x1": x0 + 8.0, "top": line_idx * 10.0, "bottom": line_idx * 10.0 + 5.0})
        lines.append({"text": " ".join(str(word["text"]) for word in words), "words": words})

    rows, _bboxes = build_row_grid_from_lines(lines)

    assert len(rows[0]) == 5
    assert rows[1][1:] == ["11", "12", "13", "14"]


def test_detect_table_candidates_scores_tables_on_a_page() -> None:
    """Table detection should score candidates extracted from a PDF page."""
    pdf = FakePDF(
        pages=[
            FakePage(
                text="Table 1. Baseline characteristics",
                tables=[FakeTable([["Variable", "Overall"], ["Age", "52.1"]])],
            )
        ]
    )

    candidates = detect_table_candidates(pdf)

    assert len(candidates) == 1
    assert candidates[0].page_num == 1
    assert candidates[0].score > 0.7


def test_detect_page_candidates_supports_tablefinder_wrapper() -> None:
    """Table detection should support PyMuPDF find_tables() wrappers with a .tables attribute."""
    page = FakePage(
        text="Table 1. Baseline characteristics",
        tables=[],
    )
    page.find_tables = lambda: FakeTableFinder([FakeTable([["Variable", "Overall"], ["Age", "52.1"]])])  # type: ignore[method-assign]

    candidates = detect_table_candidates(FakePDF(pages=[page]))

    assert len(candidates) == 1
    assert candidates[0].caption == "Table 1. Baseline characteristics"


def test_detect_table_candidates_supports_pymupdf_style_documents() -> None:
    """Table detection should also support page_count/load_page style PDF documents."""
    pdf = FakePyMuDoc(
        pages=[
            FakePyMuPage(
                text="Table 1. Baseline characteristics",
                words=[],
            )
        ]
    )
    pdf.load_page(0).find_tables = lambda: [FakeTable([["Variable", "Overall"], ["Age", "52.1"]])]  # type: ignore[attr-defined]
    pdf.load_page(0).extract_text = lambda: pdf.load_page(0).text  # type: ignore[attr-defined]
    pdf.load_page(0).crop = lambda _: FakeCroppedPage(pdf.load_page(0).text)  # type: ignore[attr-defined]

    candidates = detect_table_candidates(pdf)

    assert len(candidates) == 1
    assert candidates[0].page_num == 1


def test_detect_table_candidates_assigns_page_caption_lines_by_order() -> None:
    """Candidates on the same page should use caption lines in reading order."""
    pdf = FakePDF(
        pages=[
            FakePage(
                text=(
                    "Table 1. Baseline characteristics\n"
                    "Table 2. Secondary outcomes\n"
                ),
                tables=[
                    FakeTable([["Variable", "Overall"], ["Age", "52.1"]]),
                    FakeTable([["Outcome", "Cases"], ["BMI", "27.4"]], bbox=(10.0, 260.0, 300.0, 360.0)),
                ],
                cropped_text=" ",
            )
        ]
    )

    candidates = detect_table_candidates(pdf)

    assert [candidate.caption for candidate in candidates] == [
        "Table 1. Baseline characteristics",
        "Table 2. Secondary outcomes",
    ]
    assert candidates[0].metadata["signals"]["table_1_match"] is True
    assert candidates[1].metadata["signals"]["table_1_match"] is False


def test_detect_table_candidates_rejects_prose_reference_as_caption() -> None:
    """Prose references should not outrank a real table caption on the same page."""
    pdf = FakePDF(
        pages=[
            FakePage(
                text=(
                    "Table 3 displays weighted logistic regression models.\n"
                    "Table 2. Secondary outcomes\n"
                ),
                tables=[FakeTable([["Outcome", "Cases"], ["BMI", "27.4"]])],
                cropped_text=(
                    "Table 3 displays weighted logistic regression models.\n"
                    "Table 2. Secondary outcomes\n"
                ),
            )
        ]
    )

    candidates = detect_table_candidates(pdf)

    assert len(candidates) == 1
    assert candidates[0].caption == "Table 2. Secondary outcomes"
    assert candidates[0].metadata["caption_source"] == "nearby_above_table"
    assert candidates[0].metadata["table_number"] == 2


def test_select_top_candidates_keeps_uncaptioned_continuations() -> None:
    """Continuation pages should survive selection without needing a score exception."""
    candidates = [
        DetectedTableCandidate(
            page_num=24,
            table_index=0,
            raw_rows=[["Characteristic", "Case", "Control", "P"], ["Age", "52.1", "49.8", "0.03"]],
            caption="Table 1. Baseline characteristics",
            score=0.95,
            metadata={
                "signals": {
                    "caption_match": True,
                    "table_1_match": True,
                    "first_column_text_ratio": 1.0,
                    "later_column_numeric_ratio": 1.0,
                    "rectangular": False,
                }
            },
        ),
        DetectedTableCandidate(
            page_num=25,
            table_index=0,
            raw_rows=[["BMI", "29.2", "27.7", "0.39"], ["Waist", "90.2", "86.1", "0.04"]],
            score=0.5,
            metadata={
                "signals": {
                    "caption_match": False,
                    "table_1_match": False,
                    "first_column_text_ratio": 1.0,
                    "later_column_numeric_ratio": 1.0,
                    "rectangular": False,
                }
            },
        ),
        DetectedTableCandidate(
            page_num=26,
            table_index=0,
            raw_rows=[["Obese I", "3.31", "1.76", "0.019"], ["Obese II", "2.88", "1.44", "0.011"]],
            score=0.5,
            metadata={
                "signals": {
                    "caption_match": False,
                    "table_1_match": False,
                    "first_column_text_ratio": 1.0,
                    "later_column_numeric_ratio": 1.0,
                    "rectangular": False,
                }
            },
        ),
    ]

    selected = select_top_candidates(candidates, max_candidates=10, confidence_threshold=0.7)

    assert [(candidate.page_num, candidate.table_index) for candidate in selected] == [
        (24, 0),
        (25, 0),
        (26, 0),
    ]


def test_select_top_candidates_keeps_numbered_gap_fillers_below_main_threshold() -> None:
    """Caption-numbered tables should remain in output even below the old threshold."""
    candidates = [
        DetectedTableCandidate(
            page_num=4,
            table_index=0,
            raw_rows=[["A", "1"], ["B", "2"]],
            caption="Table 1",
            score=0.95,
            metadata={"signals": {"caption_match": True, "caption_table_number": 1}},
        ),
        DetectedTableCandidate(
            page_num=5,
            table_index=0,
            raw_rows=[["A", "1"], ["B", "2"]],
            caption="Table 2",
            score=0.65,
            metadata={"signals": {"caption_match": True, "caption_table_number": 2}},
        ),
        DetectedTableCandidate(
            page_num=6,
            table_index=0,
            raw_rows=[["A", "1"], ["B", "2"]],
            caption="Table 3",
            score=0.9,
            metadata={"signals": {"caption_match": True, "caption_table_number": 3}},
        ),
    ]

    selected = select_top_candidates(candidates, max_candidates=10, confidence_threshold=0.7)

    assert [candidate.page_num for candidate in selected] == [4, 5, 6]


def test_select_top_candidates_recovers_discarded_caption_match_below_gap_threshold() -> None:
    """Low-scoring caption-matched tables should remain without recovery metadata."""
    candidates = [
        DetectedTableCandidate(
            page_num=4,
            table_index=0,
            raw_rows=[["A", "1"], ["B", "2"]],
            caption="Table 1",
            score=0.95,
            metadata={"signals": {"caption_match": True, "caption_table_number": 1, "later_column_numeric_ratio": 1.0}},
        ),
        DetectedTableCandidate(
            page_num=5,
            table_index=0,
            raw_rows=[["A", "1"], ["B", "2"]],
            caption="Table 2",
            score=0.45,
            metadata={"signals": {"caption_match": True, "caption_table_number": 2, "later_column_numeric_ratio": 1.0}},
        ),
        DetectedTableCandidate(
            page_num=6,
            table_index=0,
            raw_rows=[["A", "1"], ["B", "2"]],
            caption="Table 3",
            score=0.9,
            metadata={"signals": {"caption_match": True, "caption_table_number": 3, "later_column_numeric_ratio": 1.0}},
        ),
    ]

    selected = select_top_candidates(candidates, max_candidates=10, confidence_threshold=0.7)

    assert [candidate.page_num for candidate in selected] == [4, 5, 6]
    assert "sequence_gap_recovered" not in selected[1].metadata


def test_select_top_candidates_does_not_cap_explicit_extracted_tables() -> None:
    """Detected tables should not be dropped just because a max-candidate setting is small."""
    candidates = [
        DetectedTableCandidate(
            page_num=5,
            table_index=0,
            raw_rows=[["A", "1"], ["B", "2"]],
            caption="Table 1",
            score=0.95,
            metadata={"layout_source": "pymupdf4llm_json", "primary_representation": "json", "fallback_used": False},
        ),
        DetectedTableCandidate(
            page_num=6,
            table_index=0,
            raw_rows=[["A", "1"], ["B", "2"]],
            caption="Table 1 (continued)",
            score=0.50,
            metadata={"layout_source": "pymupdf4llm_json", "primary_representation": "json", "fallback_used": False},
        ),
        DetectedTableCandidate(
            page_num=7,
            table_index=0,
            raw_rows=[["A", "1"], ["B", "2"]],
            caption="Table 2",
            score=0.45,
            metadata={"layout_source": "pymupdf4llm_json", "primary_representation": "json", "fallback_used": False},
        ),
    ]

    selected = select_top_candidates(candidates, max_candidates=1, confidence_threshold=0.95)

    assert [(candidate.page_num, candidate.table_index) for candidate in selected] == [
        (5, 0),
        (6, 0),
        (7, 0),
    ]


def test_text_layout_fallback_ignores_prose_table_references() -> None:
    """Narrative references like '(Table 2, Figure 1)' should not start a fallback table segment."""
    words = [
        {"text": "134", "x0": 50.0, "x1": 64.0, "top": 60.0, "bottom": 68.0},
        {"text": "(Table", "x0": 70.0, "x1": 98.0, "top": 60.0, "bottom": 68.0},
        {"text": "2,", "x0": 100.0, "x1": 112.0, "top": 60.0, "bottom": 68.0},
        {"text": "Figure", "x0": 114.0, "x1": 142.0, "top": 60.0, "bottom": 68.0},
        {"text": "1).", "x0": 144.0, "x1": 156.0, "top": 60.0, "bottom": 68.0},
        {"text": "Additional", "x0": 160.0, "x1": 208.0, "top": 60.0, "bottom": 68.0},
        {"text": "Cases", "x0": 50.0, "x1": 82.0, "top": 84.0, "bottom": 92.0},
        {"text": "10", "x0": 220.0, "x1": 232.0, "top": 84.0, "bottom": 92.0},
        {"text": "12", "x0": 280.0, "x1": 292.0, "top": 84.0, "bottom": 92.0},
        {"text": "Controls", "x0": 50.0, "x1": 98.0, "top": 98.0, "bottom": 106.0},
        {"text": "11", "x0": 220.0, "x1": 232.0, "top": 98.0, "bottom": 106.0},
        {"text": "13", "x0": 280.0, "x1": 292.0, "top": 98.0, "bottom": 106.0},
    ]

    candidates = build_text_layout_candidates(
        page_num=7,
        page_text="134 (Table 2, Figure 1). Additional",
        words=words,
        layout_source="text_positions",
    )

    assert candidates == []


def test_text_layout_fallback_rejects_prose_table_caption_without_strong_geometry() -> None:
    """Fallback segments that only start with prose table mentions should be rejected."""
    words = [
        {"text": "Table", "x0": 50.0, "x1": 72.0, "top": 60.0, "bottom": 68.0},
        {"text": "2", "x0": 76.0, "x1": 82.0, "top": 60.0, "bottom": 68.0},
        {"text": "presents", "x0": 86.0, "x1": 124.0, "top": 60.0, "bottom": 68.0},
        {"text": "results", "x0": 128.0, "x1": 160.0, "top": 60.0, "bottom": 68.0},
        {"text": "CKD", "x0": 50.0, "x1": 72.0, "top": 84.0, "bottom": 92.0},
        {"text": "and", "x0": 76.0, "x1": 92.0, "top": 84.0, "bottom": 92.0},
        {"text": "sex-specific", "x0": 96.0, "x1": 150.0, "top": 84.0, "bottom": 92.0},
        {"text": "z-scores", "x0": 154.0, "x1": 194.0, "top": 84.0, "bottom": 92.0},
        {"text": "0.91", "x0": 220.0, "x1": 240.0, "top": 98.0, "bottom": 106.0},
        {"text": "95%", "x0": 280.0, "x1": 296.0, "top": 98.0, "bottom": 106.0},
        {"text": "CI", "x0": 320.0, "x1": 330.0, "top": 98.0, "bottom": 106.0},
    ]

    candidates = build_text_layout_candidates(
        page_num=6,
        page_text="Table 2 presents results",
        words=words,
        layout_source="text_positions",
    )

    assert candidates == []


def test_text_layout_fallback_detects_unruled_table(tmp_path, monkeypatch) -> None:
    """The detector should reconstruct a table from positioned words when no grid is found."""
    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_text("placeholder")
    _install_fake_pymupdf4llm(monkeypatch, {"pages": [{"page_number": 1, "boxes": []}]})
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
    _install_fake_pymupdf_document(
        monkeypatch,
        [
            FakePyMuPage(
                text="Table1\nBaselinecharacteristics\nQ1 Q2",
                words=words,
            )
        ],
    )

    extractor = PyMuPDF4LLMExtractor(max_candidates=3, heuristic_confidence_threshold=0.0)
    tables = extractor.extract(str(pdf_path))

    assert len(tables) == 1
    assert tables[0].title == "Table1"
    assert tables[0].caption == "Table1 Baselinecharacteristics"
    assert tables[0].n_rows == 3
    assert tables[0].n_cols == 4
    cell_map = {(cell.row_idx, cell.col_idx): cell.text for cell in tables[0].cells}
    assert cell_map[(0, 2)] == "Q1"
    assert cell_map[(0, 3)] == "Q2"
    assert tables[0].metadata["layout_source"] == "pymupdf_text_positions"


def test_pymupdf4llm_extractor_rebuilds_low_quality_explicit_table_from_positioned_words(
    tmp_path,
    monkeypatch,
) -> None:
    """A low-quality explicit table box should use positioned PyMuPDF rows, not backend cells."""
    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_text("placeholder")
    _install_fake_pymupdf4llm(
        monkeypatch,
        {
            "pages": [
                {
                    "page_number": 1,
                    "boxes": [
                        {
                            "bbox": [40, 50, 260, 72],
                            "boxclass": "text",
                            "textlines": [{"spans": [{"text": "Table 2"}]}],
                        },
                        {
                            "bbox": [40, 72, 320, 86],
                            "boxclass": "text",
                            "textlines": [{"spans": [{"text": "Association with DKD"}]}],
                        },
                        {
                            "bbox": [40, 99, 560, 170],
                            "boxclass": "table",
                            "table": {
                                "bbox": [40, 99, 560, 170],
                                "extract": [
                                    ["", "OR (95% CI), P-value"],
                                    ["", "Participants\nCrude\nModel 1\nModel 2"],
                                    ["", "HEI-2020\n0.991 (0.983-0.999), 0.034\n0.979 (0.970-0.988), <0.001\n0.982 (0.973-0.992), <0.001"],
                                ],
                                "cells": [
                                    [[40, 90, 120, 105], [120, 90, 560, 105]],
                                    [[40, 105, 120, 120], [120, 105, 560, 120]],
                                    [[40, 120, 120, 170], [120, 120, 560, 170]],
                                ],
                            },
                        },
                    ],
                }
            ]
        },
    )
    _install_fake_pymupdf_document(
        monkeypatch,
        [
            FakePyMuPage(
                text="Table 2\nAssociation with DKD",
                words=[
                    {"text": "Table", "x0": 40.0, "x1": 58.0, "top": 50.0, "bottom": 58.0},
                    {"text": "2", "x0": 61.0, "x1": 65.0, "top": 50.0, "bottom": 58.0},
                    {"text": "Association", "x0": 40.0, "x1": 90.0, "top": 62.0, "bottom": 70.0},
                    {"text": "with", "x0": 94.0, "x1": 112.0, "top": 62.0, "bottom": 70.0},
                    {"text": "DKD", "x0": 116.0, "x1": 132.0, "top": 62.0, "bottom": 70.0},
                    {"text": "Participants", "x0": 50.0, "x1": 92.0, "top": 90.0, "bottom": 98.0},
                    {"text": "Crude", "x0": 170.0, "x1": 190.0, "top": 90.0, "bottom": 98.0},
                    {"text": "Model", "x0": 310.0, "x1": 330.0, "top": 90.0, "bottom": 98.0},
                    {"text": "1", "x0": 333.0, "x1": 337.0, "top": 90.0, "bottom": 98.0},
                    {"text": "Model", "x0": 450.0, "x1": 470.0, "top": 90.0, "bottom": 98.0},
                    {"text": "2", "x0": 473.0, "x1": 477.0, "top": 90.0, "bottom": 98.0},
                    {"text": "HEI-2020", "x0": 50.0, "x1": 82.0, "top": 104.0, "bottom": 112.0},
                    {"text": "0.991", "x0": 170.0, "x1": 188.0, "top": 104.0, "bottom": 112.0},
                    {"text": "0.979", "x0": 310.0, "x1": 328.0, "top": 104.0, "bottom": 112.0},
                    {"text": "0.982", "x0": 450.0, "x1": 468.0, "top": 104.0, "bottom": 112.0},
                    {"text": "T1", "x0": 50.0, "x1": 58.0, "top": 118.0, "bottom": 126.0},
                    {"text": "Ref.", "x0": 170.0, "x1": 184.0, "top": 118.0, "bottom": 126.0},
                    {"text": "Ref.", "x0": 310.0, "x1": 324.0, "top": 118.0, "bottom": 126.0},
                    {"text": "Ref.", "x0": 450.0, "x1": 464.0, "top": 118.0, "bottom": 126.0},
                ],
            )
        ],
    )

    tables = PyMuPDF4LLMExtractor(max_candidates=5, heuristic_confidence_threshold=0.7).extract(str(pdf_path))

    assert len(tables) == 1
    assert tables[0].title == "Table 2"
    assert tables[0].n_rows == 3
    assert tables[0].n_cols >= 3
    assert tables[0].metadata["layout_source"] == "pymupdf4llm_json"
    assert tables[0].metadata["grid_refinement_source"] == "pymupdf_positioned_bbox_words"
    assert tables[0].metadata["canonical_extraction_layer"] == "pymupdf_positioned_geometry"
    assert tables[0].metadata["fallback_used"] is False


def test_pymupdf4llm_extractor_refines_collapsed_table1_grid_from_words_in_bbox(
    tmp_path,
    monkeypatch,
) -> None:
    """Collapsed descriptive explicit grids should be rebuilt from words inside the table bbox."""
    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_text("placeholder")
    _install_fake_pymupdf4llm(
        monkeypatch,
        {
            "pages": [
                {
                    "page_number": 1,
                    "boxes": [
                        {
                            "bbox": [40, 50, 260, 66],
                            "boxclass": "text",
                            "textlines": [{"spans": [{"text": "Table 1. Baseline characteristics"}]}],
                        },
                        {
                            "bbox": [40, 90, 560, 170],
                            "boxclass": "table",
                            "table": {
                                "bbox": [40, 90, 560, 170],
                                "extract": [
                                    ["Variables", "Overall\nNO\nYES\nP-value"],
                                    [
                                        "Age\nSex\nMale\nFemale\nBMI",
                                        "61.1\n0.727\n4309 (49.4)\n4417 (50.6)\n29.1",
                                    ],
                                ],
                                "cells": [
                                    [[40, 90, 160, 110], [160, 90, 560, 110]],
                                    [[40, 110, 160, 170], [160, 110, 560, 170]],
                                ],
                            },
                        },
                    ],
                }
            ]
        },
    )
    _install_fake_pymupdf_document(
        monkeypatch,
        [
            FakePyMuPage(
                text="Table 1. Baseline characteristics",
                words=[
                    {"text": "Variables", "x0": 50.0, "x1": 94.0, "top": 92.0, "bottom": 100.0},
                    {"text": "Overall", "x0": 220.0, "x1": 252.0, "top": 92.0, "bottom": 100.0},
                    {"text": "NO", "x0": 330.0, "x1": 344.0, "top": 92.0, "bottom": 100.0},
                    {"text": "YES", "x0": 430.0, "x1": 450.0, "top": 92.0, "bottom": 100.0},
                    {"text": "P-value", "x0": 510.0, "x1": 546.0, "top": 92.0, "bottom": 100.0},
                    {"text": "Age", "x0": 50.0, "x1": 68.0, "top": 106.0, "bottom": 114.0},
                    {"text": "61.1", "x0": 220.0, "x1": 238.0, "top": 106.0, "bottom": 114.0},
                    {"text": "60.3", "x0": 330.0, "x1": 348.0, "top": 106.0, "bottom": 114.0},
                    {"text": "71.0", "x0": 430.0, "x1": 448.0, "top": 106.0, "bottom": 114.0},
                    {"text": "0.03", "x0": 510.0, "x1": 528.0, "top": 106.0, "bottom": 114.0},
                    {"text": "Sex", "x0": 50.0, "x1": 66.0, "top": 120.0, "bottom": 128.0},
                    {"text": "0.727", "x0": 510.0, "x1": 532.0, "top": 120.0, "bottom": 128.0},
                    {"text": "Male", "x0": 50.0, "x1": 72.0, "top": 134.0, "bottom": 142.0},
                    {"text": "4309", "x0": 220.0, "x1": 240.0, "top": 134.0, "bottom": 142.0},
                    {"text": "4008", "x0": 330.0, "x1": 350.0, "top": 134.0, "bottom": 142.0},
                    {"text": "301", "x0": 430.0, "x1": 444.0, "top": 134.0, "bottom": 142.0},
                    {"text": "Female", "x0": 50.0, "x1": 82.0, "top": 148.0, "bottom": 156.0},
                    {"text": "4417", "x0": 220.0, "x1": 240.0, "top": 148.0, "bottom": 156.0},
                    {"text": "4100", "x0": 330.0, "x1": 350.0, "top": 148.0, "bottom": 156.0},
                    {"text": "317", "x0": 430.0, "x1": 444.0, "top": 148.0, "bottom": 156.0},
                    {"text": "BMI", "x0": 50.0, "x1": 70.0, "top": 162.0, "bottom": 170.0},
                    {"text": "29.1", "x0": 220.0, "x1": 238.0, "top": 162.0, "bottom": 170.0},
                    {"text": "27.4", "x0": 330.0, "x1": 348.0, "top": 162.0, "bottom": 170.0},
                    {"text": "34.9", "x0": 430.0, "x1": 448.0, "top": 162.0, "bottom": 170.0},
                    {"text": "0.01", "x0": 510.0, "x1": 528.0, "top": 162.0, "bottom": 170.0},
                ],
            )
        ],
    )

    tables = PyMuPDF4LLMExtractor(max_candidates=5, heuristic_confidence_threshold=0.0).extract(str(pdf_path))

    assert len(tables) == 1
    assert tables[0].n_rows == 6
    assert tables[0].n_cols >= 4
    nonempty_texts = [cell.text for cell in tables[0].cells if cell.text]
    assert any("4309" in text for text in nonempty_texts)
    assert any("Male" in text or "Female" in text for text in nonempty_texts)
    assert any("0.727" in text or "0.03" in text for text in nonempty_texts)
    assert tables[0].metadata["explicit_grid_refined_from_words"] is True
    assert tables[0].metadata["grid_refinement_source"] == "collapsed_explicit_grid_word_positions"


def test_pymupdf4llm_extractor_refines_stacked_first_row_from_words(
    tmp_path,
    monkeypatch,
) -> None:
    """A plausible explicit grid should be rebuilt when row 0 stacks header and body lines."""
    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_text("placeholder")
    columns = [
        (50.0, "Outcome"),
        (150.0, "Numbers"),
        (220.0, "HR"),
        (310.0, "I2%"),
        (370.0, "PBegg"),
        (440.0, "PEgger"),
        (510.0, "Model"),
    ]
    word_rows = [
        ("Outcome", "Numbers", "HR (95% CI)", "I2%", "PBegg value", "PEgger value", "Model"),
        ("colorectal cancer", "3", "0.87 (0.78-0.97)", "0.0", "1.000", "0.901", "Fixed effects model"),
        ("lung cancer", "3", "0.68 (0.59, 0.78)", "0.0", "1.000", "0.685", "Fixed effects model"),
        ("CVDs", "9", "0.83 (0.76-0.90)", "62.7", "0.466", "0.335", "Random effects model"),
        ("CHD", "6", "0.83 (0.78-0.88)", "0.0", "0.452", "0.162", "Fixed effects model"),
        ("diabetes", "7", "0.74 (0.62-0.87)", "93.4", "0.072", "0.119", "Random effects model"),
        ("total stroke", "9", "0.84 (0.76-0.91)", "59.1", "0.466", "0.575", "Random effects model"),
        ("ischemic stroke", "7", "0.94 (0.86-1.03)", "0.0", "0.764", "0.809", "Fixed effects model"),
    ]
    words: list[dict[str, object]] = []
    for row_idx, row in enumerate(word_rows):
        top = 104.0 + row_idx * 12.0
        for col_idx, text in enumerate(row):
            x0 = columns[col_idx][0]
            cursor = x0
            for part in text.split():
                width = max(10.0, len(part) * 4.0)
                words.append(
                    {
                        "text": part,
                        "x0": cursor,
                        "x1": cursor + width,
                        "top": top,
                        "bottom": top + 8.0,
                    }
                )
                cursor += width + 3.0

    _install_fake_pymupdf4llm(
        monkeypatch,
        {
            "pages": [
                {
                    "page_number": 1,
                    "boxes": [
                        {
                            "bbox": [40, 72, 260, 88],
                            "boxclass": "text",
                            "textlines": [{"spans": [{"text": "Table 2. Meta-analysis"}]}],
                        },
                        {
                            "bbox": [40, 100, 580, 210],
                            "boxclass": "table",
                            "table": {
                                "bbox": [40, 100, 580, 210],
                                "extract": [
                                    [
                                        "Outcome\ncolorectal cancer\nlung cancer\nCVDs\nCHD\ndiabetes",
                                        "Numbers\n3\n3\n9\n6\n7",
                                        "HR (95% CI)\n0.87 (0.78-0.97)\n0.68 (0.59, 0.78)\n0.83 (0.76-0.90)\n0.83 (0.78-0.88)\n0.74 (0.62-0.87)",
                                        "I2%\n0.0\n0.0\n62.7\n0.0\n93.4",
                                        "PBegg value\n1.000\n1.000\n0.466\n0.452\n0.072",
                                        "PEgger value\n0.901\n0.685\n0.335\n0.162\n0.119",
                                        "Model\nFixed effects model\nFixed effects model\nRandom effects model\nFixed effects model\nRandom effects model",
                                    ],
                                    ["", "", "", "", "", "", "model"],
                                    ["total stroke", "9", "0.84 (0.76-0.91)", "59.1", "0.466", "0.575", "Random effects"],
                                    ["", "", "", "", "", "", "model"],
                                    ["ischemic stroke", "7", "0.94 (0.86-1.03)", "0.0", "0.764", "0.809", "Fixed effects model"],
                                ],
                                "cells": [
                                    [[40, 100, 120, 172], [120, 100, 190, 172], [190, 100, 300, 172], [300, 100, 360, 172], [360, 100, 430, 172], [430, 100, 500, 172], [500, 100, 580, 172]],
                                    [[40, 172, 120, 182], [120, 172, 190, 182], [190, 172, 300, 182], [300, 172, 360, 182], [360, 172, 430, 182], [430, 172, 500, 182], [500, 172, 580, 182]],
                                    [[40, 182, 120, 192], [120, 182, 190, 192], [190, 182, 300, 192], [300, 182, 360, 192], [360, 182, 430, 192], [430, 182, 500, 192], [500, 182, 580, 192]],
                                    [[40, 192, 120, 202], [120, 192, 190, 202], [190, 192, 300, 202], [300, 192, 360, 202], [360, 192, 430, 202], [430, 192, 500, 202], [500, 192, 580, 202]],
                                    [[40, 202, 120, 212], [120, 202, 190, 212], [190, 202, 300, 212], [300, 202, 360, 212], [360, 202, 430, 212], [430, 202, 500, 212], [500, 202, 580, 212]],
                                ],
                            },
                        },
                    ],
                }
            ]
        },
    )
    _install_fake_pymupdf_document(
        monkeypatch,
        [
            FakePyMuPage(
                text="Table 2. Meta-analysis",
                words=words,
                rule_segments=[(40.0, 114.0, 580.0, 114.0)],
            )
        ],
    )

    tables = PyMuPDF4LLMExtractor(max_candidates=5, heuristic_confidence_threshold=0.0).extract(str(pdf_path))

    assert len(tables) == 1
    assert tables[0].n_rows == 8
    assert tables[0].n_cols == 7
    cell_map = {(cell.row_idx, cell.col_idx): cell.text for cell in tables[0].cells}
    assert cell_map[(0, 0)] == "Outcome"
    assert cell_map[(0, 6)] == "Model"
    assert cell_map[(1, 0)] == "colorectal cancer"
    assert cell_map[(1, 2)] == "0.87 (0.78-0.97)"
    assert cell_map[(5, 0)] == "diabetes"
    assert cell_map[(7, 0)] == "ischemic stroke"
    assert tables[0].metadata["explicit_grid_refined_from_words"] is True
    assert tables[0].metadata["grid_refinement_source"] == "stacked_row_word_positions"
    assert tables[0].metadata["original_backend_rows"] is not None


def test_text_layout_fallback_restores_spaces_in_collapsed_first_column_tokens(
    tmp_path,
    monkeypatch,
) -> None:
    """Fallback extraction should restore readable spacing from char gaps in first-column labels."""
    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_text("placeholder")
    _install_fake_pymupdf4llm(monkeypatch, {"pages": [{"page_number": 1, "boxes": []}]})
    words = [
        {"text": "Table1", "x0": 50.0, "x1": 90.0, "top": 60.0, "bottom": 68.0},
        {"text": "Baselinecharacteristics", "x0": 50.0, "x1": 220.0, "top": 72.0, "bottom": 80.0},
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
    _install_fake_pymupdf_document(
        monkeypatch,
        [
            FakePyMuPage(
                text="Table1\nBaselinecharacteristics\nQ1 Q2",
                words=words,
                chars=chars,
            )
        ],
    )

    extractor = PyMuPDF4LLMExtractor(max_candidates=3, heuristic_confidence_threshold=0.0)
    tables = extractor.extract(str(pdf_path))

    cell_map = {(cell.row_idx, cell.col_idx): cell.text for cell in tables[0].cells}
    assert cell_map[(1, 0)].startswith("Family poverty-income ratio, n (%)")


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
        {
            "top": 84.0,
            "bottom": 92.0,
            "words": [
                {"text": "Race", "x0": 50.0, "x1": 90.0, "top": 84.0, "bottom": 92.0},
                {"text": "Overall", "x0": 220.0, "x1": 260.0, "top": 84.0, "bottom": 92.0},
            ],
        },
        {
            "top": 98.0,
            "bottom": 106.0,
            "words": [
                other_word,
                {"text": "10", "x0": 220.0, "x1": 232.0, "top": 98.0, "bottom": 106.0},
            ],
        },
        {
            "top": 112.0,
            "bottom": 120.0,
            "words": [
                mexican_word,
                {"text": "12", "x0": 220.0, "x1": 232.0, "top": 112.0, "bottom": 120.0},
            ],
        },
    ]

    rows = _build_rows_from_line_segment(lines, page_chars=chars)

    assert rows[1][0].startswith("Other race")
    assert rows[2][0].startswith("Mexican American")


def test_text_layout_fallback_restores_shifted_label_column_tokens() -> None:
    """Collapsed labels should still be restored when extraction shifts the row-label column right by one."""
    lines = [
        {
            "top": 84.0,
            "bottom": 92.0,
            "words": [
                {"text": "Overall", "x0": 220.0, "x1": 260.0, "top": 84.0, "bottom": 92.0},
                {"text": "Cases", "x0": 300.0, "x1": 340.0, "top": 84.0, "bottom": 92.0},
            ],
        },
        {
            "top": 98.0,
            "bottom": 106.0,
            "words": [
                {"text": "Otherrace", "x0": 132.0, "x1": 178.0, "top": 98.0, "bottom": 106.0},
                {"text": "10", "x0": 220.0, "x1": 232.0, "top": 98.0, "bottom": 106.0},
                {"text": "11", "x0": 300.0, "x1": 312.0, "top": 98.0, "bottom": 106.0},
            ],
        },
        {
            "top": 112.0,
            "bottom": 120.0,
            "words": [
                {"text": "MexicanAmerican", "x0": 132.0, "x1": 204.0, "top": 112.0, "bottom": 120.0},
                {"text": "12", "x0": 220.0, "x1": 232.0, "top": 112.0, "bottom": 120.0},
                {"text": "13", "x0": 300.0, "x1": 312.0, "top": 112.0, "bottom": 120.0},
            ],
        },
    ]
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

    rows = _build_rows_from_line_segment(lines, page_chars=chars)

    assert rows[1][0].startswith("Other race")
    assert rows[2][0].startswith("Mexican American")
