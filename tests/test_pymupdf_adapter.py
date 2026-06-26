"""PyMuPDF page adapter tests."""

from __future__ import annotations

from table1_parser.extract.pymupdf_page_adapter import (
    extract_page_chars,
    extract_page_rule_segments,
    extract_page_text,
    extract_page_words,
)


class FakePoint:
    def __init__(self, x: float, y: float) -> None:
        self.x = x
        self.y = y


class FakeRect:
    def __init__(self, x0: float, y0: float, x1: float, y1: float) -> None:
        self.x0 = x0
        self.y0 = y0
        self.x1 = x1
        self.y1 = y1


class FakePyMuPage:
    def __init__(
        self,
        *,
        text: str = "",
        words: list[tuple[float, float, float, float, str, int, int, int]] | None = None,
        rawdict: dict[str, object] | None = None,
        drawings: list[dict[str, object]] | None = None,
    ) -> None:
        self._text = text
        self._words = words or []
        self._rawdict = rawdict or {}
        self._drawings = drawings or []

    def get_text(self, mode: str) -> object:
        if mode == "text":
            return self._text
        if mode == "words":
            return self._words
        if mode == "rawdict":
            return self._rawdict
        raise ValueError(mode)

    def get_drawings(self) -> list[dict[str, object]]:
        return self._drawings


def test_extract_page_words_normalizes_word_tuples() -> None:
    page = FakePyMuPage(words=[(50.0, 60.0, 90.0, 68.0, "Table1", 0, 0, 0)])

    words = extract_page_words(page)

    assert words == [{"text": "Table1", "x0": 50.0, "x1": 90.0, "top": 60.0, "bottom": 68.0}]


def test_extract_page_chars_normalizes_rawdict_chars() -> None:
    page = FakePyMuPage(
        rawdict={
            "blocks": [
                {
                    "lines": [
                        {
                            "spans": [
                                {
                                    "size": 8.5,
                                    "font": "TimesNewRomanPSMT",
                                    "flags": 4,
                                    "chars": [
                                        {"c": "A", "bbox": (10.0, 20.0, 14.0, 28.0)},
                                        {"c": "g", "bbox": (14.0, 20.0, 18.0, 28.0)},
                                    ]
                                }
                            ]
                        }
                    ]
                }
            ]
        }
    )

    chars = extract_page_chars(page, page_num=7)

    assert chars[0] == {
        "text": "A",
        "x0": 10.0,
        "x1": 14.0,
        "top": 20.0,
        "bottom": 28.0,
        "char_height": 8.0,
        "page_num": 7,
        "font_size": 8.5,
        "font": "TimesNewRomanPSMT",
        "span_flags": 4,
    }
    assert chars[1]["text"] == "g"


def test_extract_page_rule_segments_reads_rects_and_line_items() -> None:
    page = FakePyMuPage(
        drawings=[
            {"rect": FakeRect(10.0, 24.0, 120.0, 24.8), "items": []},
            {"rect": None, "items": [("l", FakePoint(12.0, 30.0), FakePoint(90.0, 30.0))]},
        ]
    )

    segments = extract_page_rule_segments(page)

    assert (10.0, 24.0, 120.0, 24.8) in segments
    assert (12.0, 30.0, 90.0, 30.0) in segments


def test_adapter_helpers_tolerate_page_errors() -> None:
    class BrokenPage:
        def get_text(self, _: str) -> object:
            raise RuntimeError("broken")

        def get_drawings(self) -> list[dict[str, object]]:
            raise RuntimeError("broken")

    page = BrokenPage()

    assert extract_page_text(page) == ""
    assert extract_page_words(page) == []
    assert extract_page_chars(page) == []
    assert extract_page_rule_segments(page) == []
